#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简离屏渲染库: 二进制 STL 解析 + 正交投影画家算法渲染 (numpy + matplotlib)。"""
import os, sys, json, math
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
try:
    from daimon_runtime import setup_plot
    setup_plot()
except Exception:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    for f in ("/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"):
        if os.path.exists(f):
            font_manager.fontManager.addfont(f)
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["PingFang SC", "Hiragino Sans GB", "sans-serif"]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.collections import PolyCollection

BG = "#F5F1E8"          # 米白底
INK = "#1A1B1D"         # 标注黑
SHADOW = "#CFC7B4"

def load_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        n = np.frombuffer(f.read(4), dtype=np.uint32)[0]
        data = np.frombuffer(f.read(50 * n), dtype=np.uint8)
    rec = data.reshape(n, 50)
    xyz = rec[:, :48].copy().view(np.float32).reshape(n, 12)
    tris = xyz[:, 3:12].reshape(n, 3, 3).astype(np.float64)
    return tris

def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

class Camera:
    """正交相机。az: 绕 Z 从 +Y 向 +X (度); el: 仰角(度)。"""
    def __init__(self, az=35, el=26, target=(0, 0, 85), scale=5.0,
                 cx=1000, cy=750):
        azr, elr = math.radians(az), math.radians(el)
        d = np.array([math.sin(azr) * math.cos(elr),
                      math.cos(azr) * math.cos(elr),
                      math.sin(elr)])          # 物体 -> 相机
        up = np.array([0.0, 0.0, 1.0])
        right = np.cross(d, up)
        n = np.linalg.norm(right)
        if n < 1e-9:                            # 俯视
            right = np.array([1.0, 0.0, 0.0])
        else:
            right /= n
        upv = np.cross(right, d)
        self.d, self.right, self.upv = d, right, upv
        self.target = np.array(target, dtype=float)
        self.scale, self.cx, self.cy = scale, cx, cy

    def project(self, pts):
        """pts (...,3) -> (u, w, depth) 像素坐标(未取整)与深度。"""
        rel = pts - self.target
        u = rel @ self.right
        w = rel @ self.upv
        dep = rel @ self.d
        return self.cx + u * self.scale, self.cy + w * self.scale, dep

def shade_color(rgb, normal, light):
    lam = float(np.dot(normal, light))
    lam = max(0.0, lam)
    amb = 0.55
    k = amb + (1 - amb) * lam
    return tuple(min(1.0, c * k + 0.06 * (1 - k)) for c in rgb)

def smooth_face_normals(tris, crease_deg=28.0):
    """折痕角平滑: 返回每个面的着色法线(顶点平滑法线平均), 保持锐利边。"""
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    fn = np.cross(v1 - v0, v2 - v0)
    ln = np.linalg.norm(fn, axis=1)
    ln[ln == 0] = 1
    fn = fn / ln[:, None]
    # 顶点索引
    pts = tris.reshape(-1, 3)
    keys = np.round(pts, 4)
    vid = {}
    vidx = np.empty(len(pts), dtype=np.int64)
    for i, k in enumerate(map(tuple, keys)):
        j = vid.get(k)
        if j is None:
            j = len(vid)
            vid[k] = j
        vidx[i] = j
    vidx = vidx.reshape(-1, 3)
    # 顶点 -> 面
    from collections import defaultdict
    v2f = defaultdict(list)
    for f in range(len(tris)):
        for vv in vidx[f]:
            v2f[vv].append(f)
    cos_c = math.cos(math.radians(crease_deg))
    out = np.empty_like(fn)
    for f in range(len(tris)):
        acc = np.zeros(3)
        for vv in vidx[f]:
            for g in v2f[vv]:
                if fn[g] @ fn[f] > cos_c:
                    acc += fn[g]
        nrm = np.linalg.norm(acc)
        out[f] = acc / nrm if nrm > 0 else fn[f]
    return out

_SN_CACHE = {}

class Part:
    def __init__(self, name, stl, color, alpha=1.0, dz=0.0, show=True):
        self.name = name
        self.stl = stl
        self.tris = load_stl(stl)
        if dz:
            self.tris = self.tris + np.array([0, 0, dz])
        self.rgb = hex2rgb(color)
        self.alpha = alpha
        self.show = show

    def smooth_normals(self):
        if self.stl not in _SN_CACHE:
            _SN_CACHE[self.stl] = smooth_face_normals(load_stl(self.stl))
        return _SN_CACHE[self.stl]

def render(ax, parts, cam, shadow=False, shadow_vec=(0.32, -0.28, -1.0),
           shadow_alpha=1.0, light=(0.45, 0.55, 0.75)):
    """把零件画到 ax 上(像素坐标系)。"""
    light = np.array(light, dtype=float)
    light /= np.linalg.norm(light)
    if shadow:
        sv = np.array(shadow_vec, dtype=float)
        sv /= -sv[2]
        allt = []
        for p in parts:
            if not p.show:
                continue
            t = p.tris.reshape(-1, 3)
            allt.append(t + np.outer(t[:, 2], sv))
        allt = np.vstack(allt).reshape(-1, 3, 3)
        xs, ys, _ = cam.project(allt)
        polys = np.stack([xs, ys], axis=-1)
        pc = PolyCollection(polys, facecolors=[SHADOW], edgecolors=[SHADOW],
                            linewidths=0.3, alpha=0.55 * shadow_alpha, zorder=1)
        ax.add_collection(pc)

    for pass_alpha in ("opaque", "trans"):
        batch = []
        for p in parts:
            if not p.show:
                continue
            if (pass_alpha == "opaque") != (p.alpha >= 0.99):
                continue
            t = p.tris
            v0, v1, v2 = t[:, 0], t[:, 1], t[:, 2]
            n = np.cross(v1 - v0, v2 - v0)
            ln = np.linalg.norm(n, axis=1)
            ln[ln == 0] = 1
            n = n / ln[:, None]              # 几何法线(用于剔除)
            sn = p.smooth_normals()          # 平滑法线(用于着色)
            if pass_alpha == "opaque":
                facing = n @ cam.d
                keep = facing > 1e-9          # 背面剔除(封闭实体外向法线)
                t, n, sn = t[keep], n[keep], sn[keep]
                if len(t) == 0:
                    continue
            centers = t.mean(axis=1)
            _, _, dep = cam.project(centers)
            cols = np.array([shade_color(p.rgb, nn, light) for nn in sn])
            batch.append((dep, t, cols, p.alpha))
        if not batch:
            continue
        dep = np.concatenate([b[0] for b in batch])
        tris = np.concatenate([b[1] for b in batch])
        cols = np.concatenate([b[2] for b in batch])
        alphas = np.concatenate([np.full(len(b[0]), b[3]) for b in batch])
        order = np.argsort(dep)                # 远的先画
        xs, ys, _ = cam.project(tris[order])
        polys = np.stack([xs, ys], axis=-1)
        if pass_alpha == "trans":
            rgba = np.concatenate([cols[order], alphas[order][:, None]], axis=1)
            pc = PolyCollection(polys, facecolors=rgba, edgecolors="none", zorder=3)
        else:
            pc = PolyCollection(polys, facecolors=cols[order],
                                edgecolors=cols[order], linewidths=0.3, zorder=2)
        ax.add_collection(pc)

def make_fig(w_px, h_px):
    fig = plt.figure(figsize=(w_px / 100, h_px / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w_px)
    ax.set_ylim(0, h_px)
    ax.set_facecolor(BG)
    ax.axis("off")
    return fig, ax

def leader(ax, cam, anchor3d, text, text_xy, ha="left", fs=21, lw=1.4,
           color=INK, dot=True):
    """黑色引线标注: anchor3d 为部件上的点, text_xy 为文字像素位置。"""
    x, y, _ = cam.project(np.array(anchor3d, dtype=float))
    tx, ty = text_xy
    ax.annotate("", xy=(x, y), xytext=(tx, ty),
                arrowprops=dict(arrowstyle="-", color=color, lw=lw,
                                shrinkA=2, shrinkB=0),
                zorder=10)
    if dot:
        ax.plot([x], [y], "o", ms=4.5, color=color, zorder=11)
    ax.text(tx + (6 if ha == "left" else -6), ty, text, fontsize=fs,
            color=color, ha=ha, va="center", zorder=11)

def dim_arrow(ax, p1, p2, text, offset=(0, 0), fs=20, color=INK, lw=1.3,
              text_off=(0, 14), ext=10):
    """二维尺寸标注 (像素坐标): 带延长线的双向箭头。"""
    x1, y1 = p1[0] + offset[0], p1[1] + offset[1]
    x2, y2 = p2[0] + offset[0], p2[1] + offset[1]
    # 延长线
    ax.plot([p1[0], x1 + (x1 - p1[0]) * 0.08 * ext], [p1[1], y1 + (y1 - p1[1]) * 0.08 * ext],
            color=color, lw=0.9, zorder=9)
    ax.plot([p2[0], x2 + (x2 - p2[0]) * 0.08 * ext], [p2[1], y2 + (y2 - p2[1]) * 0.08 * ext],
            color=color, lw=0.9, zorder=9)
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="<->", color=color, lw=lw,
                                shrinkA=0, shrinkB=0), zorder=10)
    ax.text((x1 + x2) / 2 + text_off[0], (y1 + y2) / 2 + text_off[1], text,
            fontsize=fs, color=color, ha="center", va="center", zorder=11)

def title_block(ax, title, subtitle, x=90, y=None, fs_title=40, fs_sub=20):
    if y is None:
        y = ax.get_ylim()[1] - 90
    ax.text(x, y, title, fontsize=fs_title, color=INK, ha="left", va="top",
            fontweight="bold", zorder=12)
    ax.text(x, y - fs_title - 16, subtitle, fontsize=fs_sub, color="#6B6558",
            ha="left", va="top", zorder=12)

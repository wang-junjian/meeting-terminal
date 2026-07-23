#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 SmartMeet T1 全部文档渲染图 (米白底 Reachy 文档风格)。"""
import os, sys, json, math
import numpy as np
from render_lib import (Camera, Part, render, make_fig, leader, dim_arrow,
                        title_block, BG, INK, load_stl)
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(ROOT, "export", "parts")
RENDERS = os.path.join(ROOT, "renders")
os.makedirs(RENDERS, exist_ok=True)
ANCH = json.load(open(os.path.join(ROOT, "export", "anchors.json"), encoding="utf-8"))
PA = ANCH["parts"]

def P(name, color, alpha=1.0, dz=0.0):
    return Part(name, os.path.join(PARTS, name + ".stl"), color, alpha, dz)

def structural(dz_map=None, alpha=1.0):
    dz_map = dz_map or {}
    return [
        P("S01_Shell", "#4A4D52", alpha, dz_map.get("S01_Shell", 0)),
        P("S02_MidFrame", "#3A3D42", alpha, dz_map.get("S02_MidFrame", 0)),
        P("S03_TopCover", "#2E3034", alpha, dz_map.get("S03_TopCover", 0)),
        P("S04_Bezel", "#C0C3C7", alpha, dz_map.get("S04_Bezel", 0)),
        P("S05_Slider", "#33363B", alpha, dz_map.get("S05_Slider", 0)),
    ]

def components(dz_map=None, alpha=1.0):
    dz_map = dz_map or {}
    return [
        P("C_DevKit", "#2E6B3E", alpha, dz_map.get("C_DevKit", 0)),
        P("C_MicPCB", "#1F4E79", alpha, dz_map.get("C_MicPCB", 0)),
        P("C_Speaker", "#4A4A4A", alpha, dz_map.get("C_Speaker", 0)),
        P("C_ScreenModule", "#12161A", alpha, dz_map.get("C_ScreenModule", 0)),
        P("C_LedRing", "#D8D2C2", alpha, dz_map.get("C_LedRing", 0)),
        P("C_AudioBoard", "#5B3A8E", alpha, dz_map.get("C_AudioBoard", 0)),
        P("C_CameraModule", "#101010", alpha, dz_map.get("C_CameraModule", 0)),
    ]

def save(fig, name):
    path = os.path.join(RENDERS, name)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    print("saved", path)

# ================================================================ 1. 等轴测前视
def iso_front():
    W, H = 2000, 1500
    fig, ax = make_fig(W, H)
    cam = Camera(az=38, el=16, target=(0, 0, 74), scale=5.0, cx=W / 2 + 80, cy=H / 2 + 130)
    parts = structural()
    render(ax, parts, cam, shadow=True, shadow_vec=(0.15, -0.12, -1.0))
    title_block(ax, "智会 T1 · SmartMeet T1",
                "AI 智能会议终端 — 等轴测视图  |  190 × 150 × 175 mm", x=90)
    leader(ax, cam, PA["cover_top"], "拾音仓顶盖（12° 前倾）", (1560, 1210), ha="left")
    leader(ax, cam, PA["bezel"], '3.4" 圆形状态屏', (300, 1090), ha="left")
    leader(ax, cam, PA["mic_ring"], "6+1 麦克风阵列", (1490, 1060), ha="left")
    leader(ax, cam, PA["camera"], "4K 摄像头 + 隐私滑盖", (1500, 900), ha="left")
    leader(ax, cam, PA["shell_front"], "主机仓（Jetson Thor）", (1480, 460), ha="left")
    leader(ax, cam, PA["vent"], "进风百叶", (1520, 660), ha="left")
    save(fig, "iso_front.png")

# ================================================================ 2. 三视图尺寸
def silhouette(ax, cam, parts, color="#E4DCC9"):
    """正交剪影: 所有面统一平色覆盖。"""
    from matplotlib.collections import PolyCollection
    for p in parts:
        t = p.tris
        centers = t.mean(axis=1)
        _, _, dep = cam.project(centers)
        order = np.argsort(dep)
        xs, ys, _ = cam.project(t[order])
        polys = np.stack([xs, ys], axis=-1)
        pc = PolyCollection(polys, facecolors=[color], edgecolors="none", zorder=2)
        ax.add_collection(pc)

def dimensions():
    W, H = 2200, 1500
    fig, ax = make_fig(W, H)
    parts = structural()
    s = 3.4
    # ---- 前视图 (从 +Y 看): X 水平, Z 竖直 (左下)
    cam_f = Camera(az=0, el=0, target=(0, 0, 87), scale=s, cx=560, cy=580)
    silhouette(ax, cam_f, parts)
    ax.text(560, 110, "前视图", fontsize=24, color=INK, ha="center")
    xL, yB = cam_f.project(np.array([-95, 0, 0]))[:2]
    xR, _ = cam_f.project(np.array([95, 0, 0]))[:2]
    dim_arrow(ax, (xL, yB), (xR, yB), "190", offset=(0, -70), text_off=(0, -26))
    # ---- 侧视图 (从 +X 看): Y 水平, Z 竖直 (右下)
    cam_s = Camera(az=90, el=0, target=(0, 0, 87), scale=s, cx=1560, cy=560)
    silhouette(ax, cam_s, parts)
    ax.text(1560, 110, "侧视图", fontsize=24, color=INK, ha="center")
    xFr, yB2 = cam_s.project(np.array([0, 75, 0]))[:2]
    xBk2, _ = cam_s.project(np.array([0, -75, 0]))[:2]
    dim_arrow(ax, (xFr, yB2), (xBk2, yB2), "150", offset=(0, -70), text_off=(0, -26))
    xT1, yT1 = cam_s.project(np.array([0, -75, 175]))[:2]
    xB1, yB1 = cam_s.project(np.array([0, -75, 0]))[:2]
    dim_arrow(ax, (xB1, yB1), (xT1, yT1), "175", offset=(90, 0), text_off=(34, 0))
    # 12° 角标注
    pA = cam_s.project(np.array([0, -75, 175]))[:2]
    pB = cam_s.project(np.array([0, 75, 143.1]))[:2]
    ax.plot([pA[0], pB[0]], [pA[1], pB[1]], color=INK, lw=1.0, ls=(0, (4, 3)), zorder=9)
    ax.plot([pA[0], pA[0] + 300], [pA[1], pA[1]], color=INK, lw=1.0, ls=(0, (4, 3)), zorder=9)
    ax.text(pA[0] + 210, pA[1] - 26, "12°", fontsize=22, color=INK, zorder=11)
    # 主机仓/拾音仓分界
    pM = cam_s.project(np.array([0, -75, 112]))[:2]
    pM2 = cam_s.project(np.array([0, 75, 112]))[:2]
    ax.plot([pM[0], pM2[0]], [pM[1], pM2[1]], color="#8A8272", lw=0.9, ls=(0, (2, 3)), zorder=9)
    ax.text(pM[0] - 14, pM[1], "主机仓 110 / 拾音仓 ≈35", fontsize=16, color="#6B6558",
            ha="right", va="center", rotation=90, zorder=11)
    # ---- 顶视图 (从 +Z 看, 右上)
    cam_t = Camera(az=0, el=90, target=(0, 0, 0), scale=s, cx=1620, cy=1240)
    silhouette(ax, cam_t, parts, color="#DCD4BE")
    ax.text(1620, 940, "顶视图", fontsize=24, color=INK, ha="center")
    leader(ax, cam_t, [42, -8, 0], "麦克风环 Φ70", (2010, 1330), ha="left", fs=19)
    leader(ax, cam_t, [-40, 18, 0], "屏幕视窗 Φ72", (2010, 1230), ha="left", fs=19)
    leader(ax, cam_t, [42, 42, 0], "摄像头 Φ8", (2010, 1130), ha="left", fs=19)
    title_block(ax, "智会 T1 · 外形尺寸", "三视图与主要尺寸（mm）  |  跑道形水平截面 R75", x=90, y=1465)
    ax.text(W - 90, 60, "智会 T1 (SmartMeet T1) · 硬件说明书附图", fontsize=15,
            color="#8A8272", ha="right")
    save(fig, "dimensions.png")

# ================================================================ 3. 背部接口
def back_interface():
    W, H = 2000, 1300
    fig, ax = make_fig(W, H)
    cam = Camera(az=180, el=10, target=(0, -60, 50), scale=6.7, cx=W / 2 + 90, cy=H / 2 + 30)
    parts = structural()
    render(ax, parts, cam, shadow=False, light=(0.1, -0.75, 0.65))
    title_block(ax, "背部接口面板", "主机仓背板 I/O 布局（沿弧形背板展开）", x=90)
    # 按投影后的屏幕 x 分配左右标签列
    items = []
    for it in ANCH["ports"]:
        px, py, _ = cam.project(np.array(it["pos"], dtype=float))
        items.append((px, py, it))
    left = sorted([i for i in items if i[0] < W / 2 - 60], key=lambda i: -i[1])
    right = sorted([i for i in items if i[0] >= W / 2 - 60], key=lambda i: -i[1])
    leader(ax, cam, PA["exhaust"], "排风孔阵列", (W - 70, 1180), ha="right", fs=21)
    y = 1050
    for px, py, it in left:
        leader(ax, cam, it["pos"], it["name"], (70, y), ha="left", fs=21)
        y -= 130
    y = 1050
    for px, py, it in right:
        leader(ax, cam, it["pos"], it["name"], (W - 70, y), ha="right", fs=21)
        y -= 130
    save(fig, "back_interface.png")

# ================================================================ 4. 爆炸图
def exploded():
    W, H = 1900, 2100
    fig, ax = make_fig(W, H)
    dz = {"S05_Slider": 195, "S04_Bezel": 170, "S03_TopCover": 110,
          "C_LedRing": 30, "C_ScreenModule": 30, "C_CameraModule": 30,
          "C_MicPCB": 30, "C_Speaker": 30,
          "C_DevKit": -60, "C_AudioBoard": -95, "S02_MidFrame": -130}
    cam = Camera(az=38, el=20, target=(0, 0, 115), scale=4.2, cx=W / 2 - 40, cy=H / 2 + 20)
    parts = structural(dz) + components(dz)
    render(ax, parts, cam, shadow=False)
    title_block(ax, "爆炸图 · 部件布局", "5 个 3D 打印结构件 + 内部采购件", x=80)
    # 中心轴线
    x0, y0, _ = cam.project(np.array([0, 0, -140]))
    x1, y1, _ = cam.project(np.array([0, 0, 370]))
    ax.plot([x0, x1], [y0, y1], color="#A89F8C", lw=1.0, ls=(0, (5, 4)), zorder=1)

    def L(anchor_key, dz_key, text, xy, ha):
        a = list(PA[anchor_key]); a[2] += dz.get(dz_key, 0)
        leader(ax, cam, a, text, xy, ha=ha, fs=20)
    L("slider", "S05_Slider", "隐私滑盖", (110, 1830), "left")
    L("bezel", "S04_Bezel", "屏幕装饰圈（银灰）", (110, 1700), "left")
    L("cover_top", "S03_TopCover", "顶盖 · 拾音仓（近黑）", (110, 1520), "left")
    L("ledring", "C_LedRing", "LED 灯环板", (110, 1270), "left")
    L("screen_mod", "C_ScreenModule", '3.4" 圆形屏模组', (110, 1140), "left")
    L("micpcb", "C_MicPCB", "6+1 麦克风阵列板", (110, 1010), "left")
    L("camera_mod", "C_CameraModule", "4K 摄像头模组", (110, 880), "left")
    L("speaker", "C_Speaker", "5W 全频扬声器", (W - 90, 1560), "right")
    L("shell_front", "S01_Shell", "底壳 · 含背板（深空灰）", (W - 90, 1120), "right")
    L("devkit", "C_DevKit", "Jetson Thor 开发套件", (W - 90, 900), "right")
    L("audioboard", "C_AudioBoard", "USB 音频小板", (W - 90, 720), "right")
    L("midframe", "S02_MidFrame", "内框支架", (W - 90, 500), "right")
    save(fig, "exploded.png")

# ================================================================ 5. 内部布局
def internal_layout():
    W, H = 2000, 1500
    fig, ax = make_fig(W, H)
    cam = Camera(az=42, el=26, target=(0, 0, 82), scale=5.6, cx=W / 2, cy=H / 2 + 30)
    shells = structural(alpha=0.16)
    for p in shells:
        if p.name in ("S02_MidFrame",):
            p.alpha = 0.35
    parts = components() + shells
    render(ax, parts, cam, shadow=True)
    title_block(ax, "内部布局", "外壳半透明显示内部器件排布", x=90)
    leader(ax, cam, PA["devkit"], "Jetson Thor 开发套件\n110×110×65 占位", (1430, 900), ha="left", fs=20)
    leader(ax, cam, PA["micpcb"], "6+1 麦克风阵列板 Φ80", (1280, 1230), ha="left", fs=20)
    leader(ax, cam, PA["screen_mod"], '3.4" 圆形屏模组 Φ87', (240, 1150), ha="left", fs=20)
    leader(ax, cam, PA["speaker"], "5W 全频扬声器", (1250, 640), ha="left", fs=20)
    leader(ax, cam, PA["audioboard"], "USB 音频小板 40×30", (100, 760), ha="left", fs=20)
    leader(ax, cam, PA["ledring"], "LED 灯环板", (250, 960), ha="left", fs=20)
    leader(ax, cam, PA["midframe"], "内框支架", (1250, 400), ha="left", fs=20)
    save(fig, "internal_layout.png")

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    todo = {"iso_front": iso_front, "dimensions": dimensions,
            "back_interface": back_interface, "exploded": exploded,
            "internal_layout": internal_layout}
    for name, fn in todo.items():
        if which in ("all", name):
            fn()

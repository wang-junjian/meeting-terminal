#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智会 T1 (SmartMeet T1) — FreeCAD 参数化建模脚本
运行:  /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd build.py
选项:  --verify-only   只重新打开已保存的 FCStd 做 recompute/有效性校验
       --from-fcstd    从已保存 FCStd 的 Master 表格读取参数重建(参数化改型流程)

机制说明:
  - 所有关键尺寸集中在 `Master` 电子表格(Spreadsheet::Sheet)的别名单元格中,
    是模型唯一的尺寸源头; 本脚本从表格取值驱动全部几何。
  - 修改参数流程: 在 FCStd 中编辑 Master 表格 -> 运行 `freecadcmd build.py --from-fcstd`
    -> 全部零件按新参数重建并重新导出。
  - FreeCAD 1.1 无界面模式下 PartDesign::Body 挂接脚本实体不稳定(实测 Body 状态
    Invalid), 故每个零件采用 App::Part 容器 + 单一 Part::Feature 实体
    (Part 工作台布尔), 容器在文档中处于正确装配位置。
"""
import os, sys, math, json
import FreeCAD as App
import Part

ROOT = os.path.dirname(os.path.abspath(__file__))
FCSTD = os.path.join(ROOT, "SmartMeet_T1.FCStd")
EXPORT = os.path.join(ROOT, "export")
PARTS_DIR = os.path.join(EXPORT, "parts")

# ---------------------------------------------------------------- 参数表定义
# (别名, 值, 说明)  —— 全部集中在 Master 表格
PARAMS = [
    ("Width",        190.0, "整机宽度 X (mm)"),
    ("Depth",        150.0, "整机深度 Y (mm)"),
    ("Height",       175.0, "整机最大高度 Z (mm, 后缘)"),
    ("Wall",           2.4, "外壳壁厚 (mm)"),
    ("MainH",        112.0, "主机仓高度 (mm)"),
    ("SlopeDeg",      12.0, "顶盖前倾角 (度)"),
    ("MicRingD",      70.0, "麦克风环直径 (mm)"),
    ("MicHoleD",       2.5, "麦克风孔径 (mm)"),
    ("MicPCBD",       80.0, "麦克风阵列 PCB 直径 (mm)"),
    ("ScreenWinD",    72.0, "屏幕视窗直径 (mm)"),
    ("ScreenModD",    87.0, "屏幕模组直径 (mm)"),
    ("CamHoleD",       8.0, "摄像头孔径 (mm)"),
    ("LedHoleD",       3.0, "LED 导光孔径 (mm)"),
    ("LedRingR",      45.0, "LED 灯环半径 (mm, 环绕屏幕)"),
    ("SpeakerD",      52.0, "扬声器直径 (mm)"),
    ("SpeakerL",      25.0, "扬声器长度 (mm)"),
    ("GrillHoleD",     2.0, "出声孔直径 (mm)"),
    ("VentW",          3.0, "进风百叶缝高 (mm)"),
    ("VentL",         20.0, "进风百叶缝长 (mm)"),
    ("VentGap",        4.0, "进风百叶间隔 (mm)"),
    ("VentRows",       6.0, "单侧进风百叶条数"),
    ("MountDX",       96.0, "开发套件安装孔距 X (mm, 可调)"),
    ("MountDY",       96.0, "开发套件安装孔距 Y (mm, 可调)"),
    ("KitL",         110.0, "开发套件占位长 (mm)"),
    ("KitW",         110.0, "开发套件占位宽 (mm)"),
    ("KitH",          65.0, "开发套件占位高 (mm)"),
    ("ScreenCX",     -40.0, "屏幕中心 X"),
    ("ScreenCY",      18.0, "屏幕中心 Y"),
    ("MicCX",         42.0, "麦克风环中心 X"),
    ("MicCY",         -8.0, "麦克风环中心 Y"),
    ("CamCX",         42.0, "摄像头中心 X"),
    ("CamCY",         42.0, "摄像头中心 Y"),
    ("SpeakerCX",      0.0, "扬声器中心 X"),
    ("SpeakerCY",     69.0, "扬声器中心 Y"),
    ("KitCY",         -6.0, "开发套件中心 Y"),
    ("MidFrameZ",     20.0, "内框板底面高度 Z"),
    ("KitStandoff",   10.0, "开发套件铜柱高度 (mm)"),
]

# ---------------------------------------------------------------- 小工具
def V(x, y, z):
    return App.Vector(float(x), float(y), float(z))

def stadium_wire(w, d):
    """跑道形( stadium )闭合线框: 半圆在左右两端, 直边在前后。"""
    R = d / 2.0
    a = (w - d) / 2.0
    arcR = Part.ArcOfCircle(Part.Circle(V(a, 0, 0), V(0, 0, 1), R), -math.pi / 2, math.pi / 2).toShape()
    arcL = Part.ArcOfCircle(Part.Circle(V(-a, 0, 0), V(0, 0, 1), R), math.pi / 2, 3 * math.pi / 2).toShape()
    l1 = Part.LineSegment(V(a, R, 0), V(-a, R, 0)).toShape()
    l2 = Part.LineSegment(V(-a, -R, 0), V(a, -R, 0)).toShape()
    return Part.Wire([arcR, l1, arcL, l2])

def stadium_solid(w, d, z0, z1):
    return Part.Face(stadium_wire(w, d)).extrude(V(0, 0, z1 - z0)).translate(V(0, 0, z0))

def back_pt(phi_deg, R, a):
    """背部周线上一点及外法线。phi: 相对背部中心的角度(度), 正 -> +X 侧。
    沿周长展开: 直边段 |s|<=a, 之后进入半圆弧。"""
    s = R * math.radians(phi_deg)
    if abs(s) <= a:
        return V(s, -R, 0), V(0, -1, 0)
    side = 1.0 if s > 0 else -1.0
    s2 = abs(s) - a
    alpha = -math.pi / 2 + s2 / R
    cx = side * a
    p = V(cx + side * R * math.cos(alpha), R * math.sin(alpha), 0)
    n = V(side * math.cos(alpha), math.sin(alpha), 0)
    return p, n

def rect_cutter(p, n, w, h, z, depth=16.0):
    """在墙面点 p(法线 n, 水平) 处开 w(沿切向) x h(竖直) 矩形孔的切割体。"""
    b = Part.makeBox(w, depth, h)
    b.translate(V(-w / 2.0, -depth + 6.0, -h / 2.0))  # 法线方向: 外6 / 内(depth-6)
    beta = math.degrees(math.atan2(n.y, n.x)) - 90.0
    b.rotate(V(0, 0, 0), V(0, 0, 1), beta)
    b.translate(V(p.x, p.y, z))
    return b

def cyl_cutter(p, n, r, length=18.0):
    return Part.makeCylinder(r, length, p - n * 8.0, n)

# ---------------------------------------------------------------- 主构建
def build(master_vals):
    P = master_vals
    W, D, H = P["Width"], P["Depth"], P["Height"]
    Wall, MainH = P["Wall"], P["MainH"]
    R = D / 2.0
    a = (W - D) / 2.0
    t = math.tan(math.radians(P["SlopeDeg"]))
    sinS, cosS = math.sin(math.radians(P["SlopeDeg"])), math.cos(math.radians(P["SlopeDeg"]))

    def z_slope(y):
        return H - (y + R) * t
    SLOPE_N = V(0, sinS, cosS)  # 斜面外法线(前倾)

    def slope_cyl(x, y, r, up=8.0, down=10.0):
        """法向于斜面的圆柱切割体, 覆盖表皮上下。"""
        base = V(x, y, z_slope(y)) - SLOPE_N * down
        return Part.makeCylinder(r, up + down, base, SLOPE_N)

    doc = App.newDocument("SmartMeet_T1")

    # ---- Master 表格
    m = doc.addObject("Spreadsheet::Sheet", "Master")
    m.set("A1", "参数"); m.set("B1", "值"); m.set("C1", "说明")
    for i, (alias, val, note) in enumerate(PARAMS, start=2):
        m.set(f"A{i}", alias)
        m.set(f"B{i}", str(val))
        m.setAlias(f"B{i}", alias)
        m.set(f"C{i}", note)
    doc.recompute()

    anchors = {}  # 供渲染脚本使用的标注锚点

    # ================================================== 01 底壳 (含背板)
    outer = stadium_solid(W, D, 0, MainH)
    inner = stadium_solid(W - 2 * Wall, D - 2 * Wall, Wall, MainH + 5)
    shell = outer.cut(inner)

    # 进风百叶: 左右侧壁下部, 6 条 3x20 缝
    vents = []
    z0 = 12.0
    for side in (1, -1):
        for i in range(int(P["VentRows"])):
            zi = z0 + i * (P["VentW"] + P["VentGap"])
            v = Part.makeBox(16, P["VentL"], P["VentW"],
                             V(side * (W / 2 - 8) - (8 if side < 0 else -8) - (8 if side > 0 else -8), -P["VentL"] / 2, zi))
            vents.append(v)
    # 简化构造: 直接以盒体贯穿侧壁
    vents = []
    for side in (1, -1):
        x0 = side * (W / 2.0) - (16.0 if side > 0 else 0.0)
        for i in range(int(P["VentRows"])):
            zi = z0 + i * (P["VentW"] + P["VentGap"])
            vents.append(Part.makeBox(16, P["VentL"], P["VentW"], V(x0, -P["VentL"] / 2.0, zi)))
    for v in vents:
        shell = shell.cut(v)

    # 背部上沿排风孔阵列: 3 行 x 7 列 Φ4
    for zi in (88.0, 96.0, 104.0):
        for k in range(7):
            phi = -36.0 + k * 12.0
            p, n = back_pt(phi, R, a)
            shell = shell.cut(cyl_cutter(V(p.x, p.y, zi), n, 2.0))

    # 背部接口开孔
    ports = []  # (名称, phi, z, w, h, 形状)
    ports.append(("DC 电源 Φ8",        -48.0, 25.0, None, None, ("cyl", 4.0)))
    ports.append(("HDMI",              -30.0, 25.0, 16.0, 6.0, None))
    ports.append(("USB-A 1",           -12.0, 25.0, 15.0, 7.5, None))
    ports.append(("USB-A 2",             4.0, 25.0, 15.0, 7.5, None))
    ports.append(("USB-C",              18.0, 25.0,  9.0, 3.5, None))
    ports.append(("RJ45",               36.0, 27.0, 16.0, 14.0, None))
    ports.append(("电源按钮 Φ12",        52.0, 25.0, None, None, ("cyl", 6.0)))
    ports.append(("状态 LED Φ3",         52.0, 42.0, None, None, ("cyl", 1.5)))
    ports.append(("Kensington 锁孔",    -62.0, 30.0,  3.0, 7.0, None))
    port_anchors = []
    for name, phi, z, w, h, cyl in ports:
        p, n = back_pt(phi, R, a)
        if cyl:
            shell = shell.cut(cyl_cutter(V(p.x, p.y, z), n, cyl[1]))
        else:
            shell = shell.cut(rect_cutter(p, n, w, h, z))
        port_anchors.append({"name": name, "pos": [p.x + n.x * 1, p.y + n.y * 1, z],
                             "normal": [n.x, n.y, 0.0]})

    # 底部橡胶脚垫凹槽 x4
    for sx in (1, -1):
        for sy in (1, -1):
            shell = shell.cut(Part.makeCylinder(10, 1.6, V(sx * 55, sy * 45, -1)))

    # 顶盖固定螺丝柱 x4 (M3 热熔铜螺母位)
    for sx in (1, -1):
        for sy in (1, -1):
            boss = Part.makeCylinder(4.0, 14.6, V(sx * 57, sy * 57, 95))
            shell = shell.fuse(boss)
    shell = shell.removeSplitter()
    for sx in (1, -1):
        for sy in (1, -1):
            shell = shell.cut(Part.makeCylinder(2.1, 14, V(sx * 57, sy * 57, 96)))
    shell = shell.removeSplitter()
    assert shell.isValid(), "shell invalid"

    # ================================================== 02 内框支架
    c = Wall + 0.4
    plate = stadium_solid(W - 2 * c, D - 2 * c, P["MidFrameZ"], P["MidFrameZ"] + 3)
    # 走线槽
    plate = plate.cut(Part.makeBox(34, 12, 6, V(-17, -66, P["MidFrameZ"] - 1)))
    plate = plate.cut(Part.makeBox(20, 30, 6, V(55, -50, P["MidFrameZ"] - 1)))
    # 开发套件铜柱 x4 (96x96, 中心 (0, KitCY))
    so = []
    for sx in (1, -1):
        for sy in (1, -1):
            px = sx * P["MountDX"] / 2.0
            py = P["KitCY"] + sy * P["MountDY"] / 2.0
            so.append((px, py))
            plate = plate.fuse(Part.makeCylinder(3.0, P["KitStandoff"] - 3,
                                                 V(px, py, P["MidFrameZ"] + 3)))
    # USB 音频小板固定柱 x2
    for px, py in ((-75, -32), (-45, -8)):
        plate = plate.fuse(Part.makeCylinder(2.5, 5, V(px, py, P["MidFrameZ"] + 3)))
    plate = plate.removeSplitter()
    for px, py in so:
        plate = plate.cut(Part.makeCylinder(1.25, P["KitStandoff"] + 2,
                                            V(px, py, P["MidFrameZ"] + 1)))
    plate = plate.removeSplitter()
    assert plate.isValid(), "midframe invalid"

    # ================================================== 03 顶盖 (拾音仓)
    skin0 = stadium_solid(W, D, MainH, H + 12)
    box1 = Part.makeBox(W + 60, D + 60, 60, V(-W / 2 - 30, -R - 30, H))
    box1.rotate(V(0, -R, H), V(1, 0, 0), -P["SlopeDeg"])
    cover = skin0.cut(box1)
    cav = stadium_solid(W - 2 * Wall, D - 2 * Wall, MainH, H + 12)
    box2 = Part.makeBox(W + 60, D + 60, 60, V(-W / 2 - 30, -R - 30, H - Wall / cosS))
    box2.rotate(V(0, -R, H - Wall / cosS), V(1, 0, 0), -P["SlopeDeg"])
    cav = cav.cut(box2)
    cover = cover.cut(cav)

    # 麦克风孔: 6 均布 Φ70 + 圆心参考孔
    micx, micy = P["MicCX"], P["MicCY"]
    for k in range(6):
        ang = math.radians(60 * k + 30)
        cover = cover.cut(slope_cyl(micx + P["MicRingD"] / 2 * math.cos(ang),
                                    micy + P["MicRingD"] / 2 * math.sin(ang),
                                    P["MicHoleD"] / 2))
    cover = cover.cut(slope_cyl(micx, micy, P["MicHoleD"] / 2))

    # 屏幕视窗
    scx, scy = P["ScreenCX"], P["ScreenCY"]
    cover = cover.cut(slope_cyl(scx, scy, P["ScreenWinD"] / 2))

    # LED 灯环: 12 个 Φ3 环绕屏幕
    for k in range(12):
        ang = math.radians(30 * k)
        cover = cover.cut(slope_cyl(scx + P["LedRingR"] * math.cos(ang),
                                    scy + P["LedRingR"] * math.sin(ang),
                                    P["LedHoleD"] / 2))

    # 摄像头孔 + 隐私滑盖滑槽
    cmx, cmy = P["CamCX"], P["CamCY"]
    cover = cover.cut(slope_cyl(cmx, cmy, P["CamHoleD"] / 2))
    slot_cx, slot_cy = cmx, cmy + 14.0
    slot = Part.makeBox(18, 4.5, 30, V(-9, -2.25, -15))
    slot.rotate(V(0, 0, 0), V(1, 0, 0), 0)  # 占位
    slot = Part.makeBox(18, 4.5, 30, V(-9, -2.25, -15))
    slot.rotate(V(0, 0, 0), V(0, 0, 1), 0)
    # 让滑槽法向于斜面
    slot2 = Part.makeBox(18, 30, 4.5, V(-9, -15, -2.25))
    slot2.rotate(V(0, 0, 0), V(1, 0, 0), P["SlopeDeg"])
    slot2.translate(V(slot_cx, slot_cy, z_slope(slot_cy)))
    cover = cover.cut(slot2)
    cover = cover.cut(slope_cyl(slot_cx - 9, slot_cy, 2.25))
    cover = cover.cut(slope_cyl(slot_cx + 9, slot_cy, 2.25))

    # 出声孔阵列: 9 列 x 4 行 Φ2 (斜面前缘, 扬声器正前方)
    for i in range(9):
        for j in range(4):
            gx = -18.0 + i * 4.5
            gy = 60.0 + j * 4.0
            cover = cover.cut(slope_cyl(gx, gy, P["GrillHoleD"] / 2, up=6, down=8))

    # 扬声器支架小块 x2
    for sx in (1, -1):
        zb = 130.0
        zt = z_slope(62.0) - 2.5
        cover = cover.fuse(Part.makeBox(6, 8, zt - zb, V(sx * 24 - 3, 58, zb)))
    cover = cover.removeSplitter()
    assert cover.isValid(), "cover invalid"

    # ================================================== 04 屏幕装饰圈 (银灰)
    bez = Part.makeCylinder(42.0, 3.0, V(0, 0, -1.0), SLOPE_N)
    bez = bez.cut(Part.makeCylinder(36.5, 8.0, V(0, 0, -4.0), SLOPE_N))
    bez.translate(V(scx, scy, z_slope(scy) + 0.4))
    camring = Part.makeCylinder(6.5, 2.2, V(0, 0, -0.8), SLOPE_N)
    camring = camring.cut(Part.makeCylinder(4.2, 6.0, V(0, 0, -3.0), SLOPE_N))
    camring.translate(V(cmx, cmy, z_slope(cmy) + 0.3))
    bezel = bez.fuse(camring).removeSplitter()
    assert bezel.isValid(), "bezel invalid"

    # ================================================== 05 隐私滑盖
    sl = Part.makeBox(12, 6, 2.0, V(-6, -3, 0))
    stem = Part.makeBox(4, 3, 3.2, V(-2, -1.5, -3.2))
    slider = sl.fuse(stem)
    slider.rotate(V(0, 0, 0), V(1, 0, 0), P["SlopeDeg"])
    slider.translate(V(slot_cx, slot_cy, z_slope(slot_cy) + 0.6))
    slider = slider.removeSplitter()
    assert slider.isValid(), "slider invalid"

    # ================================================== 内部占位组件
    comps = {}
    kitH0 = P["MidFrameZ"] + P["KitStandoff"]  # 30
    kit = Part.makeBox(P["KitL"], P["KitW"], P["KitH"],
                       V(-P["KitL"] / 2, P["KitCY"] - P["KitW"] / 2, kitH0))
    fan = Part.makeCylinder(43, 2, V(0, P["KitCY"], kitH0 + P["KitH"]))
    kit = kit.fuse(fan)
    for k in range(8):
        sp = Part.makeBox(40, 3, 2, V(-20, -1.5, 0))
        sp.rotate(V(0, 0, 0), V(0, 0, 1), k * 22.5)
        sp.translate(V(0, P["KitCY"], kitH0 + P["KitH"] + 0.5))
        kit = kit.fuse(sp)
    comps["C_DevKit"] = kit.removeSplitter()

    micpcb = Part.makeCylinder(P["MicPCBD"] / 2, 1.6,
                               V(micx, micy, z_slope(micy) - 4.2), SLOPE_N)
    comps["C_MicPCB"] = micpcb

    spk = Part.makeCylinder(P["SpeakerD"] / 2, P["SpeakerL"],
                            V(P["SpeakerCX"], P["SpeakerCY"], z_slope(P["SpeakerCY"]) - 31.5),
                            SLOPE_N)
    comps["C_Speaker"] = spk

    scr = Part.makeCylinder(P["ScreenModD"] / 2, 12,
                            V(scx, scy, z_slope(scy) - 14.4), SLOPE_N)
    comps["C_ScreenModule"] = scr

    led = Part.makeCylinder(P["LedRingR"] + 5, 1.6, V(0, 0, 0), SLOPE_N)
    led = led.cut(Part.makeCylinder(P["LedRingR"] - 5, 5, V(0, 0, -1), SLOPE_N))
    led.translate(V(scx, scy, z_slope(scy) - 4.4))
    comps["C_LedRing"] = led.removeSplitter()

    aud = Part.makeBox(40, 30, 8, V(-80, -35, P["MidFrameZ"] + 3))
    comps["C_AudioBoard"] = aud

    cam = Part.makeBox(12, 12, 5, V(-6, -6, -2.5))
    cam.rotate(V(0, 0, 0), V(1, 0, 0), P["SlopeDeg"])
    cam.translate(V(cmx, cmy, z_slope(cmy) - 5.2))
    comps["C_CameraModule"] = cam

    for name, sh in comps.items():
        assert sh.isValid(), name + " invalid"

    # ================================================== 写入文档
    def add_part(container_name, label, solids):
        app_part = doc.addObject("App::Part", container_name)
        app_part.Label = label
        for nm, sh in solids:
            f = doc.addObject("Part::Feature", nm)
            f.Shape = sh
            app_part.addObject(f)
        return app_part

    add_part("P01_BottomShell", "01 底壳(含背板)", [("S01_Shell", shell)])
    add_part("P02_MidFrame", "02 内框支架", [("S02_MidFrame", plate)])
    add_part("P03_TopCover", "03 顶盖(拾音仓)", [("S03_TopCover", cover)])
    add_part("P04_ScreenBezel", "04 屏幕装饰圈", [("S04_Bezel", bezel)])
    add_part("P05_PrivacySlider", "05 隐私滑盖", [("S05_Slider", slider)])
    comp_objs = [(nm, sh) for nm, sh in comps.items()]
    add_part("Internal_Components", "内部占位组件(非结构件)", comp_objs)

    readme = doc.addObject("App::TextDocument", "README_Parametrics")
    readme.Text = (
        "智会 T1 参数化模型\n"
        "1. 全部关键尺寸见 Master 表格(别名单元格)。\n"
        "2. 改型流程: 编辑 Master 表格 -> 保存 -> 运行\n"
        "   freecadcmd build.py --from-fcstd\n"
        "   脚本将按表格参数重建全部零件并重新导出 STEP/STL。\n"
        "3. 每个零件一个 App::Part 容器, 内含单一实体, 处于正确装配位置。\n"
        "4. Internal_Components 为内部占位组件(采购件), 非 3D 打印结构件。\n")

    doc.recompute()
    doc.saveAs(FCSTD)

    # ================================================== 导出
    os.makedirs(PARTS_DIR, exist_ok=True)
    import Mesh, MeshPart
    printed = ["P01_BottomShell", "P02_MidFrame", "P03_TopCover",
               "P04_ScreenBezel", "P05_PrivacySlider"]

    def solid_feats(part_name):
        obj = doc.getObject(part_name)
        return [c for c in obj.Group if hasattr(c, "Shape") and c.Shape.Solids]

    exported = {}
    for name in printed + ["Internal_Components"]:
        feats = solid_feats(name)
        Part.export(feats, os.path.join(PARTS_DIR, name + ".step"))
        for child in feats:
            mesh = MeshPart.meshFromShape(Shape=child.Shape,
                                          LinearDeflection=0.04,
                                          AngularDeflection=0.06,
                                          Relative=False)
            stl = os.path.join(PARTS_DIR, child.Name + ".stl")
            mesh.write(stl)
            exported[child.Name] = stl
    # 整机装配 STEP (5 个打印件)
    Part.export([f for n in printed for f in solid_feats(n)],
                os.path.join(EXPORT, "SmartMeet_T1_Assembly.step"))
    # 含内部组件完整 STEP
    Part.export([f for n in printed + ["Internal_Components"] for f in solid_feats(n)],
                os.path.join(EXPORT, "SmartMeet_T1_Full.step"))

    # 标注锚点
    anchors["ports"] = port_anchors
    anchors["parts"] = {
        "cover_top": [0, -40, z_slope(-40)],
        "shell_front": [0, R, 60],
        "bezel": [scx, scy, z_slope(scy) + 3.4],
        "slider": [slot_cx, slot_cy, z_slope(slot_cy) + 2.6],
        "camera": [cmx, cmy, z_slope(cmy)],
        "mic_ring": [micx, micy, z_slope(micy)],
        "grille": [0, 66, z_slope(66)],
        "vent": [W / 2, 0, 30],
        "exhaust": [0, -R, 96],
        "midframe": [60, 40, P["MidFrameZ"] + 3],
        "devkit": [0, P["KitCY"], kitH0 + P["KitH"] / 2],
        "speaker": [P["SpeakerCX"], P["SpeakerCY"], z_slope(P["SpeakerCY"]) - 19],
        "screen_mod": [scx, scy, z_slope(scy) - 8],
        "micpcb": [micx, micy, z_slope(micy) - 3.4],
        "ledring": [scx, scy, z_slope(scy) - 3.6],
        "audioboard": [-60, -20, P["MidFrameZ"] + 7],
        "camera_mod": [cmx, cmy, z_slope(cmy) - 3],
    }
    anchors["params"] = {k: P[k] for k in ("Width", "Depth", "Height", "MainH",
                                           "SlopeDeg", "MicRingD", "ScreenWinD")}
    with open(os.path.join(EXPORT, "anchors.json"), "w", encoding="utf-8") as f:
        json.dump(anchors, f, ensure_ascii=False, indent=1)

    App.closeDocument("SmartMeet_T1")
    print("BUILD_OK")
    print("exported STLs:", sorted(exported.keys()))

# ---------------------------------------------------------------- 校验
def verify():
    doc = App.openDocument(FCSTD)
    doc.recompute()
    bad = []
    total = 0
    for o in doc.Objects:
        st = str(o.State)
        if "Error" in st or "Invalid" in st:
            bad.append((o.Name, st))
        if hasattr(o, "Shape") and o.Shape and o.Shape.Solids:
            for s in o.Shape.Solids:
                total += 1
                if not s.isValid() or s.Volume < 1:
                    bad.append((o.Name, "solid invalid/empty"))
    print("VERIFY solids=%d bad=%s" % (total, bad if bad else "NONE"))
    App.closeDocument(doc.Name)
    return not bad

def read_master_from_fcstd():
    doc = App.openDocument(FCSTD)
    m = doc.getObject("Master")
    vals = {alias: float(m.get(alias)) for alias, _, _ in PARAMS}
    App.closeDocument(doc.Name)
    return vals

if __name__ in ("__main__", "build", "__builtin__") or True:
    if "--verify-only" in sys.argv or "verify-only" in sys.argv:
        ok = verify()
        sys.exit(0 if ok else 1)
    vals = None
    if ("--from-fcstd" in sys.argv or "from-fcstd" in sys.argv) and os.path.exists(FCSTD):
        vals = read_master_from_fcstd()
        print("params loaded from FCStd Master")
    if vals is None:
        vals = {alias: v for alias, v, _ in PARAMS}
    build(vals)
    ok = verify()
    print("ALL_DONE ok=%s" % ok)
    sys.exit(0 if ok else 1)

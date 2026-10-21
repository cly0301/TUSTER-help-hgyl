# -*- coding: utf-8 -*-
"""化工原理课程设计 —— 一键出图

从 design_calc.py 取计算结果，用 ezdxf 生成 CAD 图纸（DXF）：
    assembly  塔设备装配图      A1  594x841   1:30
    tray      塔板布置图        A3  420x297   1:20
    flow      工艺流程图        A2  594x420   示意

用法：
    python design_draw.py --id 23041127                   # 出装配图 + 塔板布置图 + 工艺流程图
    python design_draw.py --id 23041127 --which assembly  # 只出装配图（tray / flow 同理）
    python design_draw.py --id 23041127 --set HT=0.4      # 带自选参数
（要用 PNG 预览，另跑 preview.py，见该脚本说明）
"""

import argparse
import json
import math
import os
import subprocess
import sys

import ezdxf
from ezdxf.enums import TextEntityAlignment

BASE = os.path.dirname(os.path.abspath(__file__))
CALC = os.path.join(BASE, "design_calc.py")

# ── 绘图约定（GB/T 4457.4 线宽系列）────────────────────────────────────────
LAYERS = [
    ("粗实线", 7, "CONTINUOUS", 70),      # 设备轮廓、可见轮廓
    ("细实线", 7, "CONTINUOUS", 25),      # 尺寸线、引出线、剖面线、表格
    ("点画线", 7, "CENTER", 25),          # 中心线、轴线
    ("双点画线", 7, "PHANTOM", 25),       # 假想轮廓：人孔开孔、液位
    ("虚线", 7, "DASHED", 35),            # 不可见轮廓
    ("剖面线", 7, "CONTINUOUS", 18),
    ("文字", 7, "CONTINUOUS", 25),
    ("图框", 7, "CONTINUOUS", 70),
    ("标题栏", 7, "CONTINUOUS", 25),
]


def new_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4          # mm
    doc.header["$LTSCALE"] = 6
    for name, color, lt, lw in LAYERS:
        if lt != "CONTINUOUS" and lt not in doc.linetypes:
            lt = "CONTINUOUS"
        doc.layers.add(name, color=color, linetype=lt, lineweight=lw)
    # 中文字样式：仿宋（GB 制图长仿宋体）。指定 TTF 文件名，AutoCAD 与
    # ezdxf 渲染器都能找到字形；若被大字体样式覆盖会变成方块。
    doc.styles.add("HZ", font="simfang.ttf")
    ds = doc.dimstyles.get("Standard")
    ds.dxf.dimtxt, ds.dxf.dimasz = 3.0, 2.5
    ds.dxf.dimexe, ds.dxf.dimexo = 1.5, 1.0
    ds.dxf.dimgap, ds.dxf.dimdec = 1.0, 0
    ds.dxf.dimtad = 1
    return doc


class Sheet:
    """一张图纸：图框、标题栏，以及画线的便捷函数。长度单位一律 mm。"""

    SIZES = {"A0": (1189, 841), "A1": (841, 594), "A2": (594, 420),
             "A3": (420, 297), "A4": (297, 210)}

    def __init__(self, doc, size="A1", orientation="portrait"):
        self.doc = doc
        self.msp = doc.modelspace()
        w, h = self.SIZES[size]
        if orientation == "portrait":
            w, h = h, w
        self.W, self.H, self.size = w, h, size
        self.margin_left, self.margin = 25, 10
        self.x0, self.y0 = self.margin_left, self.margin
        self.x1, self.y1 = w - self.margin, h - self.margin

    # ---- 基本图元 ----
    def line(self, p1, p2, layer="粗实线"):
        self.msp.add_line(p1, p2, dxfattribs={"layer": layer})

    def rect(self, x0, y0, x1, y1, layer="细实线"):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

    def poly(self, pts, layer="粗实线", close=False):
        self.msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})

    def circle(self, c, r, layer="粗实线"):
        self.msp.add_circle(c, r, dxfattribs={"layer": layer})

    def text(self, s, pos, h=3.0, layer="文字", align="left", rot=0.0):
        a = {"left": TextEntityAlignment.LEFT,
             "center": TextEntityAlignment.MIDDLE_CENTER,
             "mid": TextEntityAlignment.MIDDLE_LEFT,
             "right": TextEntityAlignment.MIDDLE_RIGHT}[align]
        t = self.msp.add_text(str(s), height=h,
                              dxfattribs={"layer": layer, "rotation": rot,
                                          "style": "HZ"})
        t.set_placement(pos, align=a)
        return t

    def centerline(self, p1, p2):
        (x1, y1), (x2, y2) = p1, p2
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        self.line((x1 - 3 * ux, y1 - 3 * uy), (x2 + 3 * ux, y2 + 3 * uy), "点画线")

    def leader(self, p_from, p_to, label, h=3.0, align="mid"):
        """引出标注：斜线 + 横线 + 文字。"""
        self.line(p_from, p_to, "细实线")
        x, y = p_to
        d = 1 if label and align == "mid" else -1
        self.line((x, y), (x + d * 10, y), "细实线")
        self.text(label, (x + d * 10 + (1.5 if d > 0 else -1.5), y), h, "文字", align)

    # ---- 图框 ----
    def draw_border(self):
        self.rect(0, 0, self.W, self.H, "细实线")
        self.rect(self.x0, self.y0, self.x1, self.y1, "图框")
        cx, cy = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        for p1, p2 in [((cx, self.y0), (cx, self.y0 + 5)),
                       ((cx, self.y1), (cx, self.y1 - 5)),
                       ((self.x0, cy), (self.x0 + 5, cy)),
                       ((self.x1, cy), (self.x1 - 5, cy))]:
            self.line(p1, p2, "图框")

    # ---- 标题栏 GB/T 10609.1（180x56）----
    def draw_titlebar(self, meta):
        W, H = 180.0, 56.0
        x1, y0 = self.x1, self.y0
        x0, y1 = x1 - W, y0 + H
        self.rect(x0, y0, x1, y1, "标题栏")
        for dy in (8, 16, 24, 32, 40, 48):
            self.line((x0, y0 + dy), (x1, y0 + dy), "标题栏")
        for dx in (60, 120):
            self.line((x0 + dx, y0), (x0 + dx, y1), "标题栏")
        L = "标题栏"
        for i, k in enumerate(["设计", "制图", "校核", "审核", "审定"]):
            self.text(k, (x0 + 2, y0 + 4 + i * 8), 3.0, L, "mid")
        self.text(meta.get("designer", ""), (x0 + 62, y0 + 36), 3.0, L, "mid")
        self.text(meta.get("designer", ""), (x0 + 62, y0 + 28), 3.0, L, "mid")
        self.text("日期", (x0 + 62, y0 + 12), 3.0, L, "mid")
        self.text(meta.get("date", ""), (x0 + 62, y0 + 4), 3.0, L, "mid")
        self.text(meta.get("project", ""), (x0 + 122, y0 + 44), 3.0, L, "mid")
        self.text(meta.get("title1", ""), (x0 + 122, y0 + 29), 4.5, L, "center")
        self.text(meta.get("title2", ""), (x0 + 122, y0 + 12), 4.5, L, "center")
        self.text("图号", (x0 + 2, y0 + 52), 3.0, L, "mid")
        self.text(meta.get("dwg_no", ""), (x0 + 34, y0 + 52), 3.0, L, "mid")
        self.text("比例", (x0 + 88, y0 + 52), 3.0, L, "mid")
        self.text(meta.get("scale", ""), (x0 + 106, y0 + 52), 3.0, L, "mid")
        self.text(f"共{meta.get('sheets',1)}张  第{meta.get('sheet',1)}张",
                  (x0 + 158, y0 + 52), 2.5, L, "mid")
        self.rect(x0 + 168, y0 + 48, x1, y0 + 56, "标题栏")
        self.text(self.size, (x0 + 174, y0 + 52), 3.5, L, "center")


def scale_label(sc):
    """比例的文字表示。sc 是比例分母：10 -> '1:10'，0.5 -> '2:1'（放大）。"""
    if sc < 1:
        return f"{1.0/sc:g}:1"
    return f"1:{sc:g}"


# ── 计算结果 ────────────────────────────────────────────────────────────────
def get_data(xuehao, overrides=None):
    cmd = [sys.executable, CALC, "--id", str(xuehao), "--json"]
    if overrides:
        cmd += ["--set"] + [f"{k}={v}" for k, v in overrides.items()]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=BASE)
    if r.returncode != 0:
        raise RuntimeError(f"design_calc.py 执行失败：\n{r.stderr or r.stdout}")
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── 装配图 ──────────────────────────────────────────────────────────────────
SCALE = 30.0                       # 1:30
mm = lambda m: m * 1000.0 / SCALE   # 实际米 -> 图上毫米


def build_plates(Ne_rect, Ne_strip, HT, HT2, n_hole, hole_h, y_start):
    """从塔底往上排塔板（图上 mm），返回 [(y, 序号, 是否人孔)]。

    人孔共 n_hole 个，沿塔高均匀分布；人孔处的板间距额外加 hole_h
    —— 课件要求的「人孔处加高 600mm」。每两个人孔之间算一个塔节，
    塔节是标注「板间距×板数=段高」的单位。
    """
    Ne = Ne_rect + Ne_strip
    holes = set()
    if n_hole > 0:
        gap = Ne / float(n_hole + 1)
        holes = {int(round(gap * (i + 1))) for i in range(n_hole)}

    plates, y, n = [], y_start, 0
    for i in range(Ne_strip):                       # 提馏段（最下面）
        n += 1
        y += HT2 if n > 1 else 0.0
        plates.append([y, n, n in holes])
    for i in range(Ne_rect):                        # 精馏段
        n += 1
        is_hole = n in holes
        y += HT + (hole_h if is_hole else 0.0)
        plates.append([y, n, is_hole])
    return plates, holes


# ── 表格绘制 ────────────────────────────────────────────────────────────────
def grid(sh, x, y_top, col_w, row_h, layer="细实线"):
    """在 (x, y_top) 处按列宽/行高画表格外框与格线。返回 (总宽, 总高)。"""
    W, H = sum(col_w), sum(row_h)
    y0 = y_top - H
    sh.rect(x, y0, x + W, y_top, layer)
    yy = y_top
    for h in row_h[:-1]:
        yy -= h
        sh.line((x, yy), (x + W, yy), layer)
    xx = x
    for w in col_w[:-1]:
        xx += w
        sh.line((xx, y0), (xx, y_top), layer)
    return W, H


def cell(sh, x, y_top, col_w, row_h, r, c, s, h=3.0, align="center"):
    """在表格第 r 行第 c 列写文字。"""
    cx = x + sum(col_w[:c]) + col_w[c] / 2.0
    cy = y_top - sum(row_h[:r]) - row_h[r] / 2.0
    sh.text(s, (cx, cy), h, "文字", align)


def part_bubble(sh, num, pos, target, r=3.0):
    """零部件序号：圆圈 + 数字 + 引线（带箭头）指向部件。"""
    sh.circle(pos, r, "细实线")
    sh.text(str(num), pos, 2.6, "文字", "center")
    dx, dy = target[0] - pos[0], target[1] - pos[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    sh.line((pos[0] + ux * r, pos[1] + uy * r), target, "细实线")
    ang = math.atan2(dy, dx)
    for s in (0.42, -0.42):
        a = ang + s
        sh.line(target, (target[0] - 2.2 * math.cos(a), target[1] - 2.2 * math.sin(a)), "细实线")


def draw_spec_tables(sh, data, p, x_right, elevations=None):
    """右侧四张表，自下而上：明细栏 → 管口表 → 技术特性表 → 技术要求。"""
    W = 186.0
    x = x_right - W
    ROW_H = 8.6                      # 统一行高，让整列排得舒展
    HEAD_H = 9.5

    # ---- 明细栏（紧贴标题栏上方）----
    y = sh.y0 + 56.0
    col_w = [12, 40, 58, 34, 22, 20]
    head = ["序号", "名称", "图号或标准号", "材料", "数量", "备注"]
    rows = build_bom(data, p)
    row_h = [HEAD_H] + [ROW_H] * len(rows)
    H = sum(row_h)
    sh.text("明细栏", (x + W / 2, y + H + 5), 4.5, "文字", "center")
    grid(sh, x, y + H, col_w, row_h)
    for c, s in enumerate(head):
        cell(sh, x, y + H, col_w, row_h, 0, c, s, 3.0)
    for r, row in enumerate(rows, start=1):
        cell(sh, x, y + H, col_w, row_h, r, 0, str(r), 2.8)
        for c, s in enumerate(row, start=1):
            cell(sh, x, y + H, col_w, row_h, r, c, s, 2.8,
                 "center" if c in (4, 5) else "mid")
    y += H + 22

    # ---- 管口表（末列是标高，值由主视图里的接管位置算得）----
    col_w = [12, 20, 46, 18, 62, 28]
    head = ["符号", "公称直径", "连接标准", "连接面", "用途或名称", "标高 m"]
    rows = build_nozzle_table(data, p, elevations)
    row_h = [HEAD_H] + [ROW_H] * len(rows)
    H = sum(row_h)
    sh.text("管口表", (x + W / 2, y + H + 5), 4.5, "文字", "center")
    grid(sh, x, y + H, col_w, row_h)
    for c, s in enumerate(head):
        cell(sh, x, y + H, col_w, row_h, 0, c, s, 3.0)
    for r, row in enumerate(rows, start=1):
        for c, s in enumerate(row):
            cell(sh, x, y + H, col_w, row_h, r, c, s, 2.8,
                 "center" if c < 4 or c == 5 else "mid")
    y += H + 22

    # ---- 技术特性表 ----
    col_w = [52, 134]
    rows = build_spec_table(data, p)
    row_h = [HEAD_H] + [ROW_H] * len(rows)
    H = sum(row_h)
    sh.text("技术特性表", (x + W / 2, y + H + 5), 4.5, "文字", "center")
    grid(sh, x, y + H, col_w, row_h)
    cell(sh, x, y + H, col_w, row_h, 0, 0, "项目", 3.0)
    cell(sh, x, y + H, col_w, row_h, 0, 1, "指标", 3.0)
    for r, (k, v) in enumerate(rows, start=1):
        cell(sh, x, y + H, col_w, row_h, r, 0, k, 2.8)
        cell(sh, x, y + H, col_w, row_h, r, 1, v, 2.8, "mid")
    y += H + 22

    # ---- 技术要求（顶部）----
    lines = TECHNICAL_REQUIREMENTS
    LH = 6.2
    Ht = len(lines) * LH + 10
    y_top = sh.y1                        # 顶到内框上边
    sh.text("技术要求", (x + W / 2, y_top - 6), 4.5, "文字", "center")
    sh.rect(x, y_top - Ht, x + W, y_top, "细实线")
    for i, ln in enumerate(lines):
        sh.text(ln, (x + 3, y_top - 15 - i * LH), 3.0, "文字", "left")
    return x


TECHNICAL_REQUIREMENTS = [
    "1. 本设备按 GB 150《压力容器》进行制造、试验和验收。",
    "2. 焊接采用电焊，焊条型号 T422，焊缝形式按 HG/T 20583。",
    "3. 壳体焊缝探伤：纵焊缝≥15%，环焊缝≥10%。",
    "4. 塔体弯曲度应小于 1/1000 塔高，总弯曲度小于 30mm；",
    "   安装垂直偏差不超过塔高的 1/1000，且不大于 15mm。",
    "5. 裙座螺栓中心圆直径偏差±3mm，任意两孔间距偏差±3mm。",
    "6. 塔盘零部件的制造、安装、试验和验收按 JB/T 1205",
    "   《筛板塔盘技术条件》中的相应要求进行。",
    "7. 设备制造完毕后，以 1.2MPa 表压进行液压试验（直立）。",
    "8. 管口方位及标高见本图，未注尺寸以计算结果为准。",
]


def build_spec_table(data, p):
    p = p or {}
    return [
        ("工作压力",        "常压"),
        ("工作温度",        "99.85 ℃"),
        ("生产能力",        "1000 kg/h（日产 24 吨）"),
        ("物料名称",        "乙醇-水"),
        ("塔径",            f"φ{data['d_rect']*1000:.0f} mm"),
        ("塔高",            f"{data['Htot']:.1f} m"),
        ("实际塔板数",      f"{data['Ne']} 块（精馏段 {data['Ne_rect']} + 提馏段 {data['Ne_strip']}）"),
        ("塔板间距",        f"{p.get('HT',0.35)*1000:.0f} / {p.get('HT2',0.65)*1000:.0f} mm"),
        ("筛孔直径 / 孔距",  f"{p.get('d0',5):.0f} / {p.get('t',17):.0f} mm"),
        ("堰长 / 堰高",     f"{data['lw']*1000:.0f} / {data['hw']*1000:.1f} mm"),
        ("降液管宽 / 底隙",  f"{data['Wd']*1000:.0f} mm"),
    ]


def build_nozzle_table(data, p, elevations=None):
    elevations = elevations or {}
    rows = [
        ("a1",  "DN300", "PN10 DN300 GB/T 9119", "PL/RF", "塔顶蒸气出口"),
        ("b1",  "DN80",  "PN10 DN80  GB/T 9119", "PL/RF", "回流口"),
        ("c",   "DN50",  "PN10 DN50  GB/T 9119", "PL/RF", "进料口"),
        ("d",   "DN65",  "PN10 DN65  GB/T 9119", "PL/RF", "釜液出口"),
        ("e1",  "DN300", "PN10 DN300 GB/T 9119", "PL/RF", "加热蒸汽入口"),
        ("f1",  "DN25",  "PN10 DN25  GB/T 9119", "PL/RF", "液面计上口"),
        ("f2",  "DN25",  "PN10 DN25  GB/T 9119", "PL/RF", "液面计下口"),
        ("h1-7", "DN450", "—", "—", "人孔（见主视图）"),
    ]
    out = []
    for sym, dn, std, face, use in rows:
        el = elevations.get(sym)
        out.append((sym, dn, std, face, use, f"+{el:.2f}" if el is not None else "—"))
    return out


def build_bom(data, p):
    """明细栏内容：(名称, 图号或标准号, 材料, 数量, 备注)。"""
    Ne = int(data["Ne"])
    nh = int(data["n_hole"])
    DN = f"DN{data['d_rect']*1000:.0f}"
    return [
        ("筒体",     f"{DN}×6",              "Q235-B", "1",  ""),
        ("封头",     f"{DN}×6",              "Q235-B", "2",  "椭圆封头"),
        ("裙座",     f"{DN}×6",              "Q235-B", "1",  ""),
        ("基础环",   "δ=28",                 "Q235-B", "1",  ""),
        ("压板",     "δ=36",                 "Q235-B", "28", ""),
        ("筋板",     "δ=18",                 "Q235-B", "56", ""),
        ("塔盘",     "筛板 δ=4",             "Q235-B", str(Ne), "含支承板"),
        ("降液管",   "δ=4",                  "Q235-B", str(Ne), ""),
        ("人孔",     "DN450",                "组合件", str(nh), "回转盖"),
        ("补强圈",   "DN450 / DN125",        "Q235-B", "—",  "人孔/小接管"),
        ("除沫器",   DN,                     "组合件", "1",  "丝网"),
        ("吊柱",     "800",                  "Q235-B", "1",  ""),
        ("液封槽",   "δ=5",                  "Q235-B", "1",  ""),
        ("保温圈",   "δ=4",                  "Q235-B", "6",  ""),
        ("接管",     "φ325/89/57/76/32",     "20",     "9",  "各管口"),
        ("法兰",     "PN10 DN300~25",        "Q235-B", "18", "各管口"),
        ("垫片/螺栓/螺母", "δ=2 / M12×60",   "组合件", "—",  "随法兰配套"),
        ("液面计",   "PN16",                 "组合件", "2",  ""),
        ("裙座人孔", "DN600",                "组合件", "1",  ""),
    ]



# ── 详图 ────────────────────────────────────────────────────────────────────
def _arc_pts(cx, cy, r, a0, a1, n=48):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def draw_tray_plan(sh, cx, cy, sc, data, p, tag="塔板布置图", hole_skip=3):
    """塔板布置图（俯视）：外圆、降液管弓形、堰、筛孔阵列。"""
    p = p or {}
    f = lambda m: m * 1000.0 / sc
    D = float(data["d_rect"])
    lw = float(data["lw"])                       # 堰长 = 降液管弦长
    Wd = float(data["Wd"])                       # 降液管宽（弓高）
    Wc = float(p.get("Wc", 50.0)) / 1000.0       # 边缘区
    Ws = float(p.get("Ws", 60.0)) / 1000.0       # 安定区
    d0 = float(p.get("d0", 5.0)) / 1000.0
    t = float(p.get("t", 17.0)) / 1000.0

    R = f(D) / 2.0
    y_half = f(lw) / 2.0                          # 弦半长
    x_bow = math.sqrt(max(R * R - y_half * y_half, 0.0))   # 弦到圆心距离

    sh.circle((cx, cy), R, "粗实线")               # 塔板外圆
    sh.centerline((cx - R - 6, cy), (cx + R + 6, cy))
    sh.centerline((cx, cy - R - 6), (cx, cy + R + 6))

    # 两侧降液管（弓形）：弦在 x = ±x_bow
    for sgn in (-1, 1):
        xc = cx + sgn * x_bow
        a0, a1 = (90, 270) if sgn > 0 else (270, 450)
        pts = _arc_pts(cx, cy, R, a0, a1)
        sh.poly(pts, "粗实线")
        sh.line((xc, cy - y_half), (xc, cy + y_half), "粗实线")   # 堰
        # 降液管填充线（斜线）
        for k in range(1, 6):
            yy = cy - y_half + 2 * y_half * k / 6.0
            xr = math.sqrt(max(R * R - (yy - cy) ** 2, 0.0))
            x_edge = cx + sgn * xr
            x_mid = xc + sgn * (xr - x_bow) * 0.35
            sh.line((x_mid, yy), (x_edge, yy), "剖面线")

    # 筛孔阵列：只布在中央有效区（距圆心<=R-Wc、|x|<=弦位-Ws）
    #   按 hole_skip 倍孔距抽样画 —— 画满会糊成一片，装配图上按示意表达，
    #   真实孔数与排列方式在图注里说明（这是塔板零件图的内容）。
    n_hole = 0
    R_eff = R - f(Wc)
    x_lim = x_bow - f(Ws)
    r_hole = f(d0) / 2.0
    step = f(t) * hole_skip
    xx = -x_lim
    while xx <= x_lim:
        yy = -R_eff
        while yy <= R_eff:
            if xx * xx + yy * yy <= R_eff * R_eff:
                sh.circle((cx + xx, cy + yy), r_hole, "细实线")
                n_hole += 1
            yy += step
        xx += step

    # 标注
    sh.text(tag, (cx, cy - R - 14), 4.5, "文字", "center")
    sh.text(scale_label(sc), (cx, cy - R - 20), 3.5, "文字", "center")
    sh.leader((cx + R * 0.72, cy + R * 0.72), (cx + R + 12, cy + R + 10),
              f"降液管 宽 {Wd*1000:.0f}", 3.0, "mid")
    sh.text(f"筛孔 φ{d0*1000:.0f}，孔距 {t*1000:.0f}，正三角形排列，共 {data['n_holes']} 孔",
            (cx, cy + R + 9), 3.0, "文字", "center")
    sh.text(f"（图中筛孔按示意表示，未按实际孔数绘制）",
            (cx, cy + R + 4.5), 2.5, "文字", "center")
    sh.text(f"堰长 {lw*1000:.0f}", (cx - x_bow, cy + y_half + 4), 3.0, "文字", "center")
    # 区域标注（让图能看懂）
    sh.leader((cx - x_lim * 0.55, cy - y_half * 0.62),
              (cx - R - 16, cy - R * 0.6), "筛孔区", 3.2, "right")
    sh.text("堰", (cx - x_bow + 1.5, cy + y_half * 0.75), 3.2, "文字", "left")
    sh.text("降液管", (cx + x_bow + 2.5, cy + y_half * 0.75), 3.2, "文字", "left")
    return n_hole


def draw_downcomer_detail(sh, cx, cy, sc, data, p, tag="塔板主视图（局部）"):
    """降液管局部详图（放大）：上下两块塔板之间的降液管、堰与液封。

    这是局部视图，不按塔径画 —— 板间距只有塔径的 1/3 左右，画全景会扁成一条线。
    """
    p = p or {}
    f = lambda m: m * 1000.0 / sc
    Wd = float(data["Wd"])
    hw = float(data["hw"])
    HT = float(p.get("HT", 0.35))
    clearance = float(p.get("hH", 28)) / 1000.0    # 降液管底隙（参数 hH，mm）

    x_wall = cx + 26.0                              # 塔壁（局部视图里摆在这）
    x_let = cx - 62.0                               # 塔板被截断处
    gap = f(HT)
    wd = f(Wd)
    y_bot, y_top = cy, cy + gap
    y_seal = y_bot + f(clearance)

    # 上下两块塔板（左端截断）
    sh.line((x_let, y_bot), (x_wall, y_bot), "粗实线")
    sh.line((x_let, y_top), (x_wall, y_top), "粗实线")
    # 塔壁（只比塔板伸出一点）
    sh.line((x_wall, y_bot - 7), (x_wall, y_top + 9), "粗实线")

    # 降液管：从上塔板垂下到液封
    xa = x_wall - wd
    sh.line((xa, y_top), (xa, y_seal), "粗实线")
    sh.line((xa, y_seal), (x_wall, y_seal), "粗实线")
    # 液封存液（下塔板上方的液层）
    for k in range(1, 5):
        xk = xa + wd * k / 5.0
        sh.line((xk, y_seal), (xk, y_bot), "剖面线")

    # 堰：上塔板左端的矮边，向上翘
    sh.line((x_let, y_top), (x_let, y_top + f(hw)), "粗实线")
    sh.line((x_let + 2.0, y_top), (x_let + 2.0, y_top + f(hw)), "粗实线")
    sh.line((x_let, y_top + f(hw)), (x_let + 2.0, y_top + f(hw)), "粗实线")

    # 尺寸
    xd = x_let - 9
    sh.line((x_let, y_bot), (xd, y_bot), "细实线")
    sh.line((x_let, y_top), (xd, y_top), "细实线")
    sh.line((xd, y_bot), (xd, y_top), "细实线")
    sh.text(f"{HT*1000:.0f}", (xd - 1.5, (y_bot + y_top) / 2), 3.0, "文字", "center", 90)

    sh.leader((x_wall, y_seal), (x_wall + 12, y_seal - 12),
              f"底隙 {clearance*1000:.0f}", 3.0, "mid")
    sh.leader((xa, y_top - gap * 0.35), (x_wall + 12, y_top - gap * 0.15),
              f"降液管宽 {Wd*1000:.0f}", 3.0, "mid")
    sh.leader((x_let + 1.0, y_top + f(hw)), (x_let - 12, y_top + f(hw) + 9),
              f"堰高 {hw*1000:.1f}", 3.0, "right")
    # 堰上液层高度（堰顶到液面）
    how = float(data["how"])
    y_liq = y_top + f(hw) + f(how)
    sh.line((x_let + 2.0, y_liq), (x_let + 34.0, y_liq), "细实线")
    sh.line((x_let, y_top + f(hw)), (x_let, y_liq), "细实线")
    sh.leader((x_let + 4.0, y_liq), (x_let + 8.0, y_liq + 7),
              f"堰上液头 {how*1000:.1f}", 3.0, "mid")
    sh.text("堰", (x_let + 1.0, y_top + f(hw) + 4), 3.0, "文字", "center")
    sh.text("塔板", (x_let + 18, y_bot + 3), 3.0, "文字", "mid")

    sh.text(tag, (cx, y_bot - f(0.15) - 9), 4.5, "文字", "center")
    sh.text(scale_label(sc), (cx, y_bot - f(0.15) - 15), 3.5, "文字", "center")


# 课件要求管口方位图 5 个：①进料管 ②蒸汽排出管（正中）③液体回流管（右侧）④蒸汽入口管 ⑤残液排出管
NOZZLE_ANGLES = [("a1", 90, "塔顶蒸气"), ("b1", 0, "液体回流"), ("c", 180, "进料"),
                 ("e1", 270, "蒸汽入口"), ("d", 315, "残液排出")]


def draw_nozzle_plan(sh, cx, cy, sc, data, p, tag="管口方位图"):
    """管口方位图（俯视）：塔体圆 + 各管口方位。"""
    f = lambda m: m * 1000.0 / sc
    R = f(float(data["d_rect"])) / 2.0
    sh.circle((cx, cy), R, "粗实线")
    sh.circle((cx, cy), R - f(0.006), "细实线")          # 壁厚内线
    sh.centerline((cx - R - 8, cy), (cx + R + 8, cy))
    sh.centerline((cx, cy - R - 8), (cx, cy + R + 8))

    for name, ang, use in NOZZLE_ANGLES:
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        r1, r2 = R, R + f(0.28)
        # 管口画成两条平行线 + 端面
        w = f(0.09)
        px, py = -uy * w / 2, ux * w / 2
        sh.line((cx + ux * r1 + px, cy + uy * r1 + py),
                (cx + ux * r2 + px, cy + uy * r2 + py), "粗实线")
        sh.line((cx + ux * r1 - px, cy + uy * r1 - py),
                (cx + ux * r2 - px, cy + uy * r2 - py), "粗实线")
        sh.line((cx + ux * r2 + px, cy + uy * r2 + py),
                (cx + ux * r2 - px, cy + uy * r2 - py), "粗实线")
        # 编号
        tx, ty = cx + ux * (r2 + 4), cy + uy * (r2 + 4)
        sh.text(name, (tx, ty), 3.0, "文字", "center")
    sh.text(tag, (cx, cy - R - 26), 4.5, "文字", "center")
    sh.text(scale_label(sc), (cx, cy - R - 32), 3.5, "文字", "center")


def draw_nozzle_detail(sh, cx, cy, sc, data, p, tag="进料口详图"):
    """接管详图：塔壁 + 接管 + 法兰 + 补强圈（以进料口 φ57×3.5 为例）。"""
    f = lambda m: m * 1000.0 / sc
    od, wall = 0.057, 0.0035                # φ57×3.5
    tw = 0.006                              # 筒体壁厚
    fl_od, fl_t = 0.165, 0.020              # 法兰 DN50
    L = f(0.20)                             # 接管伸出长度

    x_wall = cx + 22.0                      # 塔外壁
    ro = f(od) / 2.0
    ri = ro - f(wall)

    # 塔壁
    sh.line((x_wall, cy - f(0.16)), (x_wall, cy + f(0.16)), "粗实线")
    sh.line((x_wall + f(tw), cy - f(0.16)), (x_wall + f(tw), cy + f(0.16)), "粗实线")
    # 补强圈（塔壁外侧加厚）
    sh.line((x_wall - f(0.01), cy - f(0.075)), (x_wall - f(0.01), cy + f(0.075)), "粗实线")
    sh.line((x_wall - f(0.01), cy - f(0.075)), (x_wall, cy - f(0.075)), "粗实线")
    sh.line((x_wall - f(0.01), cy + f(0.075)), (x_wall, cy + f(0.075)), "粗实线")

    # 接管
    x_out = x_wall - f(0.01) - L
    sh.line((x_out, cy + ri), (x_wall + f(tw), cy + ri), "粗实线")
    sh.line((x_out, cy - ri), (x_wall + f(tw), cy - ri), "粗实线")
    sh.line((x_out, cy + ro), (x_out, cy + ri), "粗实线")
    sh.line((x_out, cy - ro), (x_out, cy - ri), "粗实线")
    sh.line((x_out, cy + ri), (x_wall + f(tw), cy + ri), "剖面线")

    # 法兰
    fx = x_out + f(0.02)
    sh.line((fx, cy - f(fl_od) / 2), (fx, cy + f(fl_od) / 2), "粗实线")
    sh.line((fx + f(fl_t), cy - f(fl_od) / 2), (fx + f(fl_t), cy + f(fl_od) / 2), "粗实线")
    sh.line((fx, cy - f(fl_od) / 2), (fx + f(fl_t), cy - f(fl_od) / 2), "粗实线")
    sh.line((fx, cy + f(fl_od) / 2), (fx + f(fl_t), cy + f(fl_od) / 2), "粗实线")
    # 螺栓孔中心线
    sh.centerline((fx - 2, cy - f(fl_od) * 0.35), (fx + f(fl_t) + 2, cy - f(fl_od) * 0.35))
    sh.centerline((fx - 2, cy + f(fl_od) * 0.35), (fx + f(fl_t) + 2, cy + f(fl_od) * 0.35))

    # 标注
    sh.leader((x_wall - f(0.03), cy + ro), (x_wall - f(0.05), cy + f(0.20)),
              f"接管 φ{od*1000:.0f}×{wall*1000:.1f}", 3.0, "right")
    sh.leader((x_wall - f(0.005), cy - f(0.075)), (x_wall - f(0.10), cy - f(0.20)),
              "补强圈 δ=10", 3.0, "right")
    sh.text(f"法兰 PN10 DN50", (fx, cy - f(fl_od) / 2 - 4), 3.0, "文字", "center")
    sh.text(tag, (cx, cy - f(0.16) - 8), 4.5, "文字", "center")
    sh.text(scale_label(sc), (cx, cy - f(0.16) - 14), 3.5, "文字", "center")


def draw_skirt_detail(sh, cx, cy, sc, data, p, tag="裙座详图"):
    """裙座详图：塔体下段 + 裙座筒身 + 检查孔 + 基础环 + 地脚螺栓。"""
    f = lambda m: m * 1000.0 / sc
    R = f(float(data["d_rect"])) / 2.0
    HS = float(p.get("HS", 1.5))
    tw = max(f(0.006), 0.8)              # 壁厚（太薄时给个可见宽度）
    h_body = f(0.55)                     # 画出的塔体高度

    y_body_bot = cy - h_body
    y_base = y_body_bot - f(HS)
    y_brim = y_base - f(0.05)            # 基础环厚度

    # 塔体（内外壁双线）
    for s in (-1, 1):
        sh.line((cx + s * R, cy), (cx + s * R, y_body_bot), "粗实线")
        sh.line((cx + s * (R - tw), cy), (cx + s * (R - tw), y_body_bot), "粗实线")
    # 裙座筒身
    for s in (-1, 1):
        sh.line((cx + s * R, y_body_bot), (cx + s * R, y_brim), "粗实线")
        sh.line((cx + s * (R - tw), y_body_bot), (cx + s * (R - tw), y_brim), "粗实线")
    # 塔体与裙座的连接焊缝
    sh.line((cx - R - 1.5, y_body_bot), (cx + R + 1.5, y_body_bot), "粗实线")

    # 检查孔（裙座中部）
    hy = (y_body_bot + y_base) / 2.0
    sh.rect(cx - f(0.075), hy - f(0.10), cx + f(0.075), hy + f(0.10), "粗实线")
    sh.centerline((cx - f(0.10), hy), (cx + f(0.10), hy))

    # 基础环（向两侧加宽）
    brim = f(0.10)
    sh.rect(cx - R - brim, y_brim, cx + R + brim, y_base, "粗实线")
    # 地脚螺栓
    for s in (-1, 1):
        xb = cx + s * (R + brim * 0.6)
        sh.line((xb, y_brim), (xb, y_brim - f(0.10)), "粗实线")
        sh.line((xb - 1.2, y_brim - f(0.10)), (xb + 1.2, y_brim - f(0.10)), "粗实线")
    # 基础（下方剖面线示意）
    for k in range(-6, 7):
        xk = cx + k * 4
        sh.line((xk, y_brim - f(0.10)), (xk + 3, y_brim - f(0.15)), "细实线")

    # 尺寸
    sh.line((cx + R + brim + 4, y_base), (cx + R + brim + 10, y_base), "细实线")
    sh.line((cx + R + brim + 4, y_body_bot), (cx + R + brim + 10, y_body_bot), "细实线")
    sh.line((cx + R + brim + 7, y_base), (cx + R + brim + 7, y_body_bot), "细实线")
    sh.text(f"{HS*1000:.0f}", (cx + R + brim + 9, (y_base + y_body_bot) / 2),
            3.0, "文字", "left", 90)
    sh.text(f"φ{float(data['d_rect'])*1000:.0f}", (cx, y_body_bot + 4), 3.0, "文字", "center")
    sh.leader((cx - f(0.075), hy), (cx - R - brim - 8, hy - 8), "检查孔", 2.8, "right")

    sh.text(tag, (cx, y_brim - f(0.18) - 6), 4.5, "文字", "center")
    sh.text(scale_label(sc), (cx, y_brim - f(0.18) - 12), 3.5, "文字", "center")


def draw_hole_detail(sh, cx, cy, sc, p, tag="筛孔排列详图"):
    """筛孔排列详图（放大）：几个孔的三角排列 + 尺寸。"""
    p = p or {}
    f = lambda m: m * 1000.0 / sc
    d0 = float(p.get("d0", 5.0)) / 1000.0
    t = float(p.get("t", 17.0)) / 1000.0
    r = f(d0) / 2.0
    step = f(t)
    # 3 行三角排列
    n = 4
    for i in range(3):
        for j in range(n):
            x = cx + (j - (n - 1) / 2.0) * step + (step / 2 if i % 2 else 0)
            y = cy + (i - 1) * step * 0.866
            sh.circle((x, y), r, "粗实线")
            sh.centerline((x - r - 1.5, y), (x + r + 1.5, y))
    # 尺寸线：孔距
    y0 = cy + step * 0.866 + r + 6
    sh.line((cx - step / 2, cy + step * 0.866 + r),
            (cx - step / 2, y0 + 2), "细实线")
    sh.line((cx + step / 2, cy + step * 0.866 + r),
            (cx + step / 2, y0 + 2), "细实线")
    sh.line((cx - step / 2, y0), (cx + step / 2, y0), "细实线")
    sh.text(f"t={t*1000:.0f}", (cx, y0 + 2), 3.0, "文字", "center")
    sh.text(f"筛孔 φ{d0*1000:.0f}", (cx, cy - step - 8), 3.5, "文字", "center")
    sh.text(tag, (cx, cy - step - 14), 4.0, "文字", "center")
    sh.text(scale_label(sc), (cx, cy - step - 19), 3.0, "文字", "center")


def draw_assembly(data, xuehao, out_path, params=None):
    global SCALE
    # 自适应比例：按总塔高算，保证主视图（含顶部封头）装得进 A1 图框
    Htot = float(data["Htot"])
    avail_h = 841 - 40 - 60
    SCALE = max(30.0, math.ceil(Htot * 1000.0 / avail_h / 5.0) * 5.0)
    p = params or {}
    HD = float(p.get("HD", 1.0))
    HB = float(p.get("HB", 1.0))
    HS = float(p.get("HS", 1.5))
    HT_m = float(p.get("HT", 0.35))
    HT2_m = float(p.get("HT2", 0.65))
    HT, HT2 = mm(HT_m), mm(HT2_m)
    hole_h = mm(float(p.get("hole_h", 0.6)))
    Wd = mm(float(data["Wd"]))
    n_hole = int(data["n_hole"])

    Ne_rect, Ne_strip = int(data["Ne_rect"]), int(data["Ne_strip"])
    d_col = float(data["d_rect"])

    doc = new_doc()
    sh = Sheet(doc, "A1", "portrait")
    sh.draw_border()
    sh.draw_titlebar({"designer": "陈礼杨", "date": "2026年9月",
                      "project": "日产24吨乙醇", "title1": "筛板精馏塔设计",
                      "title2": "装配图", "dwg_no": "EQ-01",
                      "scale": f"1:{SCALE:g}", "sheets": 1, "sheet": 1})

    cx = 100.0                          # 塔中心线
    y_base = 50.0                       # 基础环底面
    R = mm(d_col) / 2.0                 # 塔外半径

    # ---- 竖向尺寸链 ----
    y_tray_bot = y_base + mm(HS) + mm(HB)
    plates, holes = build_plates(Ne_rect, Ne_strip, HT, HT2, n_hole, hole_h, y_tray_bot)
    y_tray_top = plates[-1][0]
    y_head = y_tray_top + mm(HD)         # 上封头切线
    b = R / 2.0                          # 椭圆封头短半轴（2:1）

    # ---- 裙座（基础环 + 地脚螺栓 + 检查孔 + 排气孔，全部画在主体图上）----
    y_skirt_top = y_base + mm(HS)
    sh.rect(cx - R, y_base + 3, cx + R, y_skirt_top, "粗实线")          # 裙座筒身
    sh.rect(cx - R - 7, y_base, cx + R + 7, y_base + 3, "粗实线")       # 基础环
    for s in (-1, 1):                                                   # 地脚螺栓
        xb = cx + s * (R + 4)
        sh.line((xb, y_base), (xb, y_base - 5), "粗实线")
        sh.line((xb - 1.6, y_base - 5), (xb + 1.6, y_base - 5), "粗实线")
        sh.line((xb - 1.0, y_base + 3), (xb + 1.0, y_base + 3), "粗实线")
    sh.rect(cx - 7, y_base + 14, cx + 7, y_base + 26, "粗实线")         # 检查孔
    for s in (-1, 1):                                                   # 排气孔
        sh.line((cx + s * R, y_skirt_top - 7), (cx + s * (R + 1.6), y_skirt_top - 7), "粗实线")
        sh.line((cx + s * (R + 1.6), y_skirt_top - 7), (cx + s * (R + 1.6), y_skirt_top - 9), "粗实线")
    # 下封头（藏在裙座内，虚线椭圆弧，长短轴 2:1）
    b2 = (R - 2) / 2.0
    y_head_bot = y_base + 38
    sh.msp.add_lwpolyline(
        [(cx - (R - 2) * math.cos(math.pi * i / 20),
          y_head_bot - b2 * math.sin(math.pi * i / 20)) for i in range(21)],
        dxfattribs={"layer": "虚线"})

    # ---- 筒身 ----
    sh.line((cx - R, y_skirt_top), (cx - R, y_head), "粗实线")
    sh.line((cx + R, y_skirt_top), (cx + R, y_head), "粗实线")

    # ---- 保温层（筒身外侧薄层 + 支撑环）----
    for s in (-1, 1):
        sh.line((cx + s * (R + 2.5), y_skirt_top), (cx + s * (R + 2.5), y_head), "细实线")
    for i in range(1, 7):
        yb = y_skirt_top + (y_head - y_skirt_top) * i / 7.0
        for s in (-1, 1):
            sh.line((cx + s * R, yb), (cx + s * (R + 2.5), yb), "细实线")

    # ---- 上封头 ----
    sh.poly([(cx - R * math.cos(math.pi * i / 24),
              y_head + b * math.sin(math.pi * i / 24)) for i in range(25)])

    # ---- 吊柱（塔顶吊耳）----
    y_lug = y_head + b + 2.5
    sh.line((cx - 2.0, y_lug), (cx + 2.0, y_lug), "粗实线")
    sh.poly([(cx - 1.2, y_lug), (cx - 1.2, y_lug + 3.0),
             (cx + 1.2, y_lug + 3.0), (cx + 1.2, y_lug)], "粗实线")
    sh.circle((cx, y_lug + 4.2), 1.2, "粗实线")

    # ---- 除沫器（塔顶丝网，画在封头下方的气相空间）----
    y_dm = y_head - mm(0.32)
    sh.line((cx - R + 2, y_dm), (cx + R - 2, y_dm), "粗实线")
    sh.line((cx - R + 2, y_dm + 2), (cx + R - 2, y_dm + 2), "粗实线")
    for k in range(1, 8):
        xk = cx - R + 2 + (2 * R - 4) * k / 8.0
        sh.line((xk, y_dm), (xk, y_dm + 2), "细实线")

    # ---- 保温圈（塔身外侧的支撑环，沿塔高分 6 道）----
    for i in range(1, 7):
        yb = y_skirt_top + (y_head - y_skirt_top) * i / 7.0
        for s in (-1, 1):
            sh.line((cx + s * R, yb), (cx + s * (R + 1.6), yb), "粗实线")
            sh.line((cx + s * (R + 1.6), yb), (cx + s * (R + 1.6), yb - 2.5), "粗实线")

    # ---- 塔板 + 降液管 + 堰 + 人孔 ----
    tray_half = R - 0.8
    y_fallback = y_tray_bot - HT2
    for i, (y, n, is_hole) in enumerate(plates):
        # 塔板
        sh.line((cx - tray_half, y), (cx + tray_half, y), "粗实线")
        # 降液管：从本板一端向下贯通到下一块板（左右交替）
        y_below = plates[i - 1][0] if i > 0 else y_fallback
        if n % 2:
            x_a, x_b = cx - tray_half, cx - tray_half + Wd
            x_w = cx + tray_half                       # 堰在另一侧
        else:
            x_a, x_b = cx + tray_half - Wd, cx + tray_half
            x_w = cx - tray_half
        sh.line((x_a, y), (x_a, y_below), "粗实线")
        sh.line((x_b, y), (x_b, y_below), "粗实线")
        # 堰：对侧板端向上的矮边
        sh.line((x_w, y), (x_w, y + mm(0.05)), "粗实线")
        # 人孔：假想开孔 + 盖 + 手柄
        if is_hole:
            hr = mm(0.45) / 2.0
            sh.circle((cx, y), hr, "双点画线")
            sh.circle((cx, y), hr * 1.3, "粗实线")
            sh.line((cx + hr * 1.3, y), (cx + hr * 1.6, y + hr * 0.6), "粗实线")
            sh.centerline((cx - hr * 1.5, y), (cx + hr * 1.5, y))
            sh.centerline((cx, y - hr * 1.5), (cx, y + hr * 1.5))
            # 编号直接标在塔壁外侧（用引线会占掉右侧好不容易留出的净空）
            sh.line((cx + hr * 1.3, y), (cx + R + 1, y), "细实线")
            sh.text(f"M{n} φ600", (cx + R + 2, y), 2.6, "文字", "mid")
            # 人孔处的塔节法兰（塔径略扩的凸缘）
            sh.line((cx - R - 1.8, y - 3), (cx - R - 1.8, y + 3), "粗实线")
            sh.line((cx + R + 1.8, y - 3), (cx + R + 1.8, y + 3), "粗实线")
            sh.line((cx - R, y - 3), (cx - R - 1.8, y - 3), "粗实线")
            sh.line((cx - R, y + 3), (cx - R - 1.8, y + 3), "粗实线")
            sh.line((cx + R, y - 3), (cx + R + 1.8, y - 3), "粗实线")
            sh.line((cx + R, y + 3), (cx + R + 1.8, y + 3), "粗实线")

    # ---- 进料板标注 + 进料板处塔节法兰 ----
    y_feed = plates[Ne_strip][0] if Ne_strip < len(plates) else plates[-1][0]
    for s in (-1, 1):
        sh.line((cx + s * (R + 1.8), y_feed - 3), (cx + s * (R + 1.8), y_feed + 3), "粗实线")
        sh.line((cx + s * R, y_feed - 3), (cx + s * (R + 1.8), y_feed - 3), "粗实线")
        sh.line((cx + s * R, y_feed + 3), (cx + s * (R + 1.8), y_feed + 3), "粗实线")
    sh.leader((cx - tray_half, y_feed), (cx - R - 16, y_feed + 10), "进料板", 3.0, "right")

    # ---- 塔节分段尺寸（每两个人孔之间为一节）----
    bounds = [0] + sorted(holes) + [len(plates)]
    xseg = cx + R + 12                       # 尺寸线位置
    for k in range(len(bounds) - 1):
        i0, i1 = bounds[k], bounds[k + 1]
        ngap = i1 - i0
        if ngap < 1:
            continue
        y_a, y_b = plates[i0][0], plates[i1 - 1][0]
        sp_mm = HT_m * 1000 if i0 >= Ne_strip else HT2_m * 1000
        h_real = (y_b - y_a) * SCALE
        sh.line((cx + R + 2, y_a), (xseg + 6, y_a), "细实线")
        sh.line((cx + R + 2, y_b), (xseg + 6, y_b), "细实线")
        sh.line((xseg, y_a), (xseg, y_b), "细实线")
        sh.line((xseg - 2, y_a), (xseg + 2, y_a), "细实线")
        sh.line((xseg - 2, y_b), (xseg + 2, y_b), "细实线")
        sh.text(f"{sp_mm:.0f}×{ngap}={h_real:.0f}",
                (xseg + 3, (y_a + y_b) / 2), 3.0, "文字", "left", 90)

    # ---- 接管（法兰外径按 GB/T 9119 PN10 取值）----
    FLANGE_OD = {50: 165.0, 65: 185.0, 80: 200.0, 300: 445.0}
    nozzle_elev = {}                     # 管口中心标高，供管口表使用
    y_feed = plates[Ne_strip][0] if Ne_strip < len(plates) else plates[-1][0]
    nozzles = [
        (y_head - mm(0.25), "L", 325.0, 300, "a1 φ325×8"),
        (y_head - mm(1.30), "R", 89.0, 80, "b1 φ89×4"),
        (y_feed, "L", 57.0, 50, "c φ57×3.5"),
        (y_base + mm(HS) * 0.5, "R", 76.0, 65, "d φ76×4"),
        (y_base - 4.0, "L", 325.0, 300, "e1 φ325×8"),
        (y_skirt_top + mm(0.95), "R", 32.0, 25, "f1 φ32×3.5"),
        (y_skirt_top + mm(0.30), "R", 32.0, 25, "f2 φ32×3.5"),
    ]
    for yy, side, od, dn, label in nozzles:
        L = mm(0.30)
        # 小管径在 1:30 下不足 1mm，给个最小可见宽度（工程图惯例：可夸大画出）
        ro = max(od / 2.0 / SCALE, 0.7)
        rf = max(FLANGE_OD.get(dn, od * 2.2) / 2.0 / SCALE, 1.6)
        xw = cx - R if side == "L" else cx + R
        sgn = -1 if side == "L" else 1
        x_out = xw + sgn * L
        # 接管管身
        sh.line((xw, yy - ro), (x_out, yy - ro), "粗实线")
        sh.line((xw, yy + ro), (x_out, yy + ro), "粗实线")
        # 法兰（两片，按标准外径）
        sh.line((x_out, yy - rf), (x_out, yy + rf), "粗实线")
        sh.line((x_out + sgn * 2.2, yy - rf), (x_out + sgn * 2.2, yy + rf), "粗实线")
        sh.line((x_out, yy - rf), (x_out + sgn * 2.2, yy - rf), "粗实线")
        sh.line((x_out, yy + rf), (x_out + sgn * 2.2, yy + rf), "粗实线")
        # 引出标注：只标编号与管径。标高列进管口表 —— 图上放不下
        # （左侧留白只有约 45mm，带标高的长标签会顶出图框）
        nozzle_elev[label.split()[0]] = (yy - y_base) * SCALE / 1000.0
        txt = label
        xt = x_out + sgn * (2.2 + 5)
        if side == "L":
            sh.leader((x_out, yy), (xt - 8, yy + 7), txt, 2.8, "right")
        else:
            sh.leader((x_out, yy), (xt + 8, yy + 7), txt, 2.8, "mid")

    # ---- 液位计（f1/f2 之间的玻璃板液位计）----
    y_f1 = y_skirt_top + mm(0.95)
    y_f2 = y_skirt_top + mm(0.30)
    x_g = cx + R + mm(0.30) + 3.0
    sh.line((x_g, y_f2), (x_g, y_f1), "细实线")
    sh.rect(x_g - 1.5, y_f2 + 1.5, x_g + 1.5, y_f1 - 1.5, "细实线")

    # ---- 中心线 ----
    sh.centerline((cx, y_base - 12), (cx, y_head + b + 8))

    # ---- 尺寸标注：塔高、塔径 ----
    xdim = cx + R + 56
    sh.line((cx + R + 3, y_base), (xdim + 3, y_base), "细实线")
    sh.line((cx + R + 3, y_head), (xdim + 3, y_head), "细实线")
    sh.line((xdim, y_base), (xdim, y_head), "细实线")
    sh.line((xdim - 2.5, y_base), (xdim + 2.5, y_base), "细实线")
    sh.line((xdim - 2.5, y_head), (xdim + 2.5, y_head), "细实线")
    sh.text(f"H={data['Htot']:.1f}m", (xdim + 3.5, (y_base + y_head) / 2), 3.5,
            "文字", "left", 90)

    sh.line((cx - R, y_base - 11), (cx - R, y_base - 17), "细实线")
    sh.line((cx + R, y_base - 11), (cx + R, y_base - 17), "细实线")
    sh.line((cx - R, y_base - 14), (cx + R, y_base - 14), "细实线")
    sh.line((cx - R, y_base - 14), (cx - R + 2.5, y_base - 12.5), "细实线")
    sh.line((cx - R, y_base - 14), (cx - R + 2.5, y_base - 15.5), "细实线")
    sh.line((cx + R, y_base - 14), (cx + R - 2.5, y_base - 12.5), "细实线")
    sh.line((cx + R, y_base - 14), (cx + R - 2.5, y_base - 15.5), "细实线")
    sh.text(f"φ{int(d_col*1000)}", (cx, y_base - 16.5), 3.5, "文字", "center")

    sh.text(f"主视图  1:{SCALE:g}", (cx, y_base - 28), 5.0, "文字", "center")

    # ---- 中间详图区：两列三行的等距网格 ----
    #   行心 700 / 470 / 240（间距 230），列心 215 / 350 —— 上下分布均匀
    cL, cR = 255.0, 365.0
    draw_tray_plan(sh, cL, 700.0, 10.0, data, p)            # 塔板布置图   1:10
    draw_nozzle_plan(sh, cR, 700.0, 20.0, data, p)          # 管口方位图   1:20
    draw_downcomer_detail(sh, cL, 470.0, 4.0, data, p)      # 塔板主视图   1:4
    draw_nozzle_detail(sh, cR, 470.0, 5.0, data, p)         # 进料口详图   1:5
    draw_hole_detail(sh, cL, 240.0, 0.5, p)                 # 筛孔排列详图 2:1

    # ---- 零部件序号（对应明细栏，全部放在左侧空白区，引线水平指向塔体）----
    hole_ys = [y for (y, n, is_hole) in plates if is_hole]
    tray_ys = [y for (y, n, is_hole) in plates]
    y_mh = hole_ys[len(hole_ys) // 2] if hole_ys else 400.0
    y_tray = tray_ys[len(tray_ys) // 2] if tray_ys else 400.0
    part_bubble(sh, 1,  (58.0, 520.0), (cx - R, 520.0))                 # 筒体
    part_bubble(sh, 2,  (76.0, 758.0), (cx - R + 6, y_head + b * 0.4))  # 上封头
    part_bubble(sh, 3,  (58.0, 104.0), (cx - R, 104.0))                 # 裙座
    part_bubble(sh, 4,  (58.0, 58.0), (cx - R - 2, 58.0))               # 基础环
    part_bubble(sh, 5,  (58.0, 48.0), (cx - R - 6, 51.0))               # 压板
    part_bubble(sh, 6,  (58.0, 38.0), (cx - R - 4, 53.0))               # 筋板
    part_bubble(sh, 7,  (58.0, y_tray), (cx - R, y_tray))               # 塔盘
    part_bubble(sh, 8,  (58.0, y_tray - 14.0), (cx - R + 4, y_tray - 14.0))  # 降液管
    part_bubble(sh, 9,  (58.0, y_mh), (cx - R, y_mh))                   # 人孔
    part_bubble(sh, 10, (58.0, y_feed - 10.0), (cx - R, y_feed - 10.0))          # 补强圈（进料口）
    part_bubble(sh, 11, (76.0, 738.0), (cx - R + 6, y_dm))              # 除沫器
    part_bubble(sh, 12, (100.0, 785.0), (cx, y_lug + 3.5))              # 吊柱
    part_bubble(sh, 13, (58.0, 138.0), (cx - R + 6, 138.0))             # 液封槽
    part_bubble(sh, 14, (58.0, 620.0), (cx - R - 2.5, 620.0))           # 保温圈
    part_bubble(sh, 15, (58.0, 718.0), (cx - R, y_head - mm(0.25)))     # 接管
    part_bubble(sh, 16, (58.0, 696.0), (cx - R - mm(0.30), y_head - mm(0.25)))  # 法兰
    part_bubble(sh, 17, (58.0, y_feed - 26.0), (cx - R - mm(0.30), y_feed - 10.0))  # 垫片/螺栓
    part_bubble(sh, 18, (136.0, 118.0), (cx + R + mm(0.30) + 3.0, 106.0))  # 液面计
    part_bubble(sh, 19, (58.0, 86.0), (cx + 4, 92.0))                   # 裙座人孔

    # ---- 右侧表格 ----
    draw_spec_tables(sh, data, p, sh.x1, nozzle_elev)

    doc.saveas(out_path)
    return out_path


# ── 塔板布置图（独立 A3）────────────────────────────────────────────────────
def draw_tray(data, xuehao, out_path, params=None):
    """塔板平面布置图：上=俯视图（塔板布置），下=主视图（剖面），右=结构参数表。"""
    p = params or {}
    doc = new_doc()
    sh = Sheet(doc, "A3", "landscape")
    sh.draw_border()
    sh.draw_titlebar({"designer": "陈礼杨", "date": "2026年9月",
                      "project": "日产24吨乙醇", "title1": "筛板精馏塔设计",
                      "title2": "塔板平面布置图", "dwg_no": "EQ-02",
                      "scale": "1:8", "sheets": 1, "sheet": 1})

    # 上：俯视图（1:8，塔板直径约 125mm）
    draw_tray_plan(sh, 110.0, 185.0, 8.0, data, p, tag="① 塔板俯视图")

    # 下：主视图（剖面，1:8）
    draw_downcomer_detail(sh, 110.0, 58.0, 8.0, data, p, tag="② 塔板主视图（剖面）")

    # 右：结构参数表
    x_tab = 240.0
    rows = [
        ("塔径 D", f"{float(data['d_rect'])*1000:.0f} mm"),
        ("堰长 lw", f"{float(data['lw'])*1000:.0f} mm"),
        ("堰高 hw", f"{float(data['hw'])*1000:.1f} mm"),
        ("堰上液头 how", f"{float(data['how'])*1000:.1f} mm"),
        ("板上清液层 hL", f"{float(p.get('hL',50)):.0f} mm"),
        ("降液管宽 Wd", f"{float(data['Wd'])*1000:.0f} mm"),
        ("降液管面积 Ad", f"{float(data['Ad']):.4f} m²"),
        ("降液管底隙 hH", f"{float(p.get('hH',28)):.0f} mm"),
        ("开孔区 A0", f"{float(data['A0']):.4f} m²"),
        ("筛孔孔径 d0", f"{float(p.get('d0',5)):.0f} mm"),
        ("孔距 t", f"{float(p.get('t',17)):.0f} mm"),
        ("开孔率 φ", f"{float(data.get('phi_hole', data.get('phi',0))):.4f}"),
        ("孔数 n", f"{int(data['n_holes'])} 个"),
        ("板厚 tp", f"{float(p.get('tp',4)):.1f} mm"),
        ("边缘区 Wc", f"{float(p.get('Wc',50)):.0f} mm"),
        ("安定区 Ws", f"{float(p.get('Ws',60)):.0f} mm"),
    ]
    col_w = [62.0, 78.0]
    row_h = [7.5] * len(rows)
    grid(sh, x_tab, 292.0, col_w, row_h)
    for r, (k, v) in enumerate(rows):
        cell(sh, x_tab, 292.0, col_w, row_h, r, 0, k, 2.8, "mid")
        cell(sh, x_tab, 292.0, col_w, row_h, r, 1, v, 2.8, "center")
    sh.text("塔板结构参数", (x_tab + 70.0, 296.0), 3.8, "文字", "center")

    doc.saveas(out_path)
    return out_path


# ── 工艺流程图（独立 A2）───────────────────────────────────────────────────
def draw_flow(data, xuehao, out_path, params=None):
    """工艺流程图（带控制点）：设备 + 物料线 + 阀件 + 仪表 + 控制回路 + 公用工程 + 设备参数。"""
    p = params or {}
    doc = new_doc()
    sh = Sheet(doc, "A2", "landscape")
    sh.draw_border()
    sh.draw_titlebar({"designer": "陈礼杨", "date": "2026年9月",
                      "project": "日产24吨乙醇", "title1": "筛板精馏塔设计",
                      "title2": "工艺流程图", "dwg_no": "EQ-03",
                      "scale": "示意", "sheets": 1, "sheet": 1})

    def arrow(p1, p2, layer="细实线"):
        sh.line(p1, p2, layer)
        ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        L = 3.5
        for s in (0.4, -0.4):
            a = ang + s
            sh.line(p2, (p2[0] - L * math.cos(a), p2[1] - L * math.sin(a)), layer)

    def valve(cx, cy, tag="", h=3.6):
        """调节阀：对顶三角形 + 阀杆 + 执行机构。"""
        sh.poly([(cx - h, cy - h * 0.7), (cx - h, cy + h * 0.7), (cx, cy)], "粗实线")
        sh.poly([(cx + h, cy - h * 0.7), (cx + h, cy + h * 0.7), (cx, cy)], "粗实线")
        sh.line((cx, cy), (cx, cy + h * 1.4), "细实线")
        sh.circle((cx, cy + h * 1.9), 1.5, "细实线")
        if tag:
            sh.text(tag, (cx, cy - h * 1.6), 2.0, "文字", "center")

    def instrument(cx, cy, tag, r=4.2):
        sh.circle((cx, cy), r, "细实线")
        sh.text(tag, (cx, cy), 1.8, "文字", "center")

    def ctrl(p1, p2):
        sh.line(p1, p2, "虚线")

    def exch(x1, y1, x2, y2, tag, param=""):
        """列管式换热器：壳体 + 管板 + 管束。"""
        sh.rect(x1, y1, x2, y2, "粗实线")
        sh.line((x1, y1 + 5), (x2, y1 + 5), "细实线")
        sh.line((x1, y2 - 5), (x2, y2 - 5), "细实线")
        for k in range(1, 7):
            xk = x1 + (x2 - x1) * k / 7.0
            sh.line((xk, y1 + 5), (xk, y2 - 5), "细实线")
        sh.text(tag, ((x1 + x2) / 2, y2 + 6), 2.8, "文字", "center")
        if param:
            sh.text(param, ((x1 + x2) / 2, y1 - 7), 2.2, "文字", "center")

    # ---- 设备 ----
    tx1, ty1, tx2, ty2 = 180.0, 100.0, 220.0, 350.0
    sh.rect(tx1, ty1, tx2, ty2, "粗实线")
    for i in range(1, 13):
        yy = ty1 + i * (ty2 - ty1) / 13.0
        sh.line((tx1, yy), (tx2, yy), "细实线")
    sh.text("T-101 精馏塔", ((tx1 + tx2) / 2, ty2 + 8), 3.2, "文字", "center")
    sh.text(f"Φ{data['d_rect']*1000:.0f}  H={data['Htot']:.1f}m  {data['Ne']}板",
            ((tx1 + tx2) / 2, ty2 + 2), 2.0, "文字", "center")

    exch(110.0, 285.0, 170.0, 315.0, "E-102 原料预热器", "A≈7 m2")
    exch(290.0, 325.0, 390.0, 355.0, "E-101 全凝器", f"A={data['A_cond']:.1f} m2")
    exch(470.0, 235.0, 530.0, 265.0, "E-103 产品冷却器", "A≈3 m2")

    # 安全阀 PSV-101（塔顶放空）
    sh.line((180.0, 340.0), (170.0, 340.0), "细实线")
    sh.line((170.0, 340.0), (170.0, 365.0), "细实线")
    valve(170.0, 370.0, "PSV-101")
    arrow((170.0, 378.0), (170.0, 392.0))

    vx1, vy1, vx2, vy2 = 300.0, 245.0, 390.0, 270.0
    sh.rect(vx1, vy1, vx2, vy2, "粗实线")
    sh.text("V-101 回流罐", ((vx1 + vx2) / 2, vy2 + 6), 2.8, "文字", "center")
    sh.text("V≈2.5 m3", ((vx1 + vx2) / 2, vy1 - 6), 2.2, "文字", "center")

    def pump(cx, cy, tag, param=""):
        sh.circle((cx, cy), 9.0, "粗实线")
        sh.line((cx - 4, cy - 5), (cx - 4, cy + 5), "粗实线")
        sh.poly([(cx - 4, cy - 5), (cx + 5, cy), (cx - 4, cy + 5)], "粗实线")
        sh.text(tag, (cx, cy - 15), 2.6, "文字", "center")
        if param:
            sh.text(param, (cx, cy - 20), 2.0, "文字", "center")
    pump(60.0, 300.0, "P-102 进料泵", "Q≈2.8 m3/h")
    pump(430.0, 257.0, "P-101 回流泵", "Q≈3.4 m3/h")

    # ---- 物料线 ----
    arrow((18, 300), (51, 300))
    sh.text("原料液 F", (16, 307), 2.8, "文字", "mid")
    valve(85, 300, "FV-101")
    arrow((69, 300), (110, 300))
    arrow((170, 300), (176, 300))
    arrow((176, 300), (176, 250))
    arrow((176, 250), (180, 250))

    arrow((220, 340), (290, 340))
    sh.text("塔顶蒸汽", (245, 347), 2.3, "文字", "center")

    arrow((340, 325), (340, 270))
    sh.text("冷凝液", (345, 298), 2.3, "文字", "mid")

    arrow((390, 257), (421, 257))                       # 回流罐→泵
    arrow((439, 257), (456, 257))                       # 泵→产品阀→冷却器
    valve(447, 257, "FV-103")
    arrow((457, 257), (470, 257))                       # 进冷却器
    arrow((530, 250), (548, 250))                       # 产品出
    sh.text("塔顶产品 D", (548, 257), 2.6, "文字", "mid")
    arrow((430, 266), (430, 375))                       # 泵→回流
    arrow((430, 375), (200, 375))
    arrow((200, 375), (200, 350))
    sh.text("回流 L", (310, 381), 2.4, "文字", "center")
    valve(330, 375, "FV-102")

    arrow((18, 110), (180, 110))
    sh.text("直接蒸汽 S", (16, 117), 2.8, "文字", "mid")
    valve(85, 110, "TV-101")

    arrow((220, 110), (250, 110))
    arrow((250, 110), (250, 60))
    sh.text("釜液 W", (228, 103), 2.4, "文字", "mid")
    valve(250, 85, "FV-104")

    # ---- 管线号 ----
    sh.text("PL-101", (32, 295), 1.6, "文字", "mid")
    sh.text("PL-102", (250, 336), 1.6, "文字", "mid")
    sh.text("PL-103", (346, 300), 1.6, "文字", "mid")
    sh.text("PL-104", (305, 380), 1.6, "文字", "mid")
    sh.text("PL-105", (548, 256), 1.6, "文字", "mid")
    sh.text("PL-106", (32, 106), 1.6, "文字", "mid")
    sh.text("PL-107", (232, 106), 1.6, "文字", "mid")

    # 冷却水（公用工程）
    arrow((290, 370), (290, 355))
    sh.text("CW", (280, 368), 2.2, "文字", "right")
    arrow((390, 340), (420, 340))
    sh.text("CW", (426, 338), 2.2, "文字", "mid")
    arrow((470, 280), (470, 265))
    sh.text("CW", (460, 278), 2.2, "文字", "right")
    arrow((530, 280), (560, 280))
    sh.text("CW", (564, 278), 2.2, "文字", "mid")

    # ---- 仪表 + 控制回路（虚线指向被测点/被控阀）----
    # FIC-101：进料流量 → FV-101 阀
    instrument(62, 340, "FIC-101")
    ctrl((62, 336), (85, 306))

    # TIC-102：预热器 → E-102 本体
    instrument(140, 340, "TIC-102")
    ctrl((140, 336), (140, 315))

    # PIC-101：塔顶压力 → 塔顶
    instrument(155, 385, "PIC-101")
    ctrl((155, 381), (155, 350))
    ctrl((155, 350), (180, 350))

    # TIC-101：冷凝温度 → E-101 右侧
    instrument(400, 340, "TIC-101")
    ctrl((400, 336), (390, 336))

    # LIC-101：回流罐液位 → FV-103 产品阀
    instrument(432, 300, "LIC-101")
    ctrl((432, 296), (447, 264))

    # LIC-102：塔釜液位 → 釜液管线
    instrument(140, 140, "LIC-102")
    ctrl((140, 136), (140, 110))
    ctrl((140, 110), (240, 110))

    # TIC-103：塔釜温度 → 塔釜
    instrument(140, 80, "TIC-103")
    ctrl((140, 84), (140, 104))
    ctrl((140, 104), (180, 104))

    # FIC-102：冷却水流量 → E-103 冷却水管
    instrument(555, 400, "FIC-102")
    ctrl((555, 396), (555, 280))
    ctrl((555, 280), (530, 280))

    # FIC-103：塔顶产品流量 → E-103 产品出口
    instrument(540, 292, "FIC-103")
    ctrl((540, 288), (540, 252))

    # ---- 图例（右侧空白区）----
    lx, ly = 472.0, 352.0
    sh.text("图例", (lx, ly + 48), 3.5, "文字", "center")
    valve(lx, ly + 30, "")
    sh.text("调节阀", (lx + 12, ly + 29), 2.6, "文字", "mid")
    instrument(lx, ly + 12, "FIC")
    sh.text("仪表", (lx + 12, ly + 11), 2.6, "文字", "mid")
    sh.line((lx - 8, ly), (lx + 8, ly), "虚线")
    sh.text("控制线", (lx + 12, ly - 1), 2.6, "文字", "mid")
    arrow((lx - 8, ly - 16), (lx + 8, ly - 16))
    sh.text("物料线", (lx + 12, ly - 17), 2.6, "文字", "mid")

    doc.saveas(out_path)
    return out_path


# ── 入口 ────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--which", default="all", help="assembly / tray / flow / all")
    ap.add_argument("--out", default=None)
    ap.add_argument("--set", nargs="*", default=None, metavar="KEY=VAL")
    args = ap.parse_args(argv)

    overrides = {}
    for kv in (args.set or []):
        k, v = kv.split("=", 1)
        overrides[k] = v

    data = get_data(args.id, overrides)
    outdir = args.out or os.getcwd()
    os.makedirs(outdir, exist_ok=True)

    impl = {"assembly": draw_assembly, "tray": draw_tray, "flow": draw_flow}
    which = ["assembly", "tray", "flow"] if args.which == "all" else [args.which]
    made = 0
    for name in which:
        fn = impl.get(name)
        if fn is None:
            print(f"[跳过] {name}：尚未实现")
            continue
        path = os.path.join(outdir, f"{name}_{args.id}.dxf")
        fn(data, args.id, path, data.get("params"))
        print(f"已生成 {path}")
        made += 1
    print(f"\n共 {made} 张。塔径 {data['d_rect']} m、实际板 {data['Ne']} 块、"
          f"全塔高 {data['Htot']} m")


if __name__ == "__main__":
    main()

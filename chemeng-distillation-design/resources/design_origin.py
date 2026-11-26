# -*- coding: utf-8 -*-
"""用 Origin 画「气体液体负荷性能图」（按参考样式）。

参考样式（气体液相负荷性能图.pdf）：
  - 横轴 V_L (m3/s)，纵轴 V_G (m3/s)
  - 五条线各取 2 个端点、带不同标记（漏液■ / 液泛● / 夹带▲ / 下限▼ / 上限◆）
  - 操作点用 ◀ 标记并标坐标
  - 图上标注 V_Gmax、V_Gmin、操作弹性、稳定系数

教育版 Origin 同时只能开 10 个表 → 每段 1 张表（共 2 张）、2 个独立图。

用法：
    python design_origin.py --id 23044401
    python design_origin.py --id 23044401 --out D:\\某目录
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import originpro as op

import design_plot as dp

# Origin 颜色索引：1 黑 2 红 3 绿 4 蓝 6 品红 21 橙黄
C_LEAK = 1
C_FLOOD = 2
C_ENT = 4
C_LOW = 3
C_HIGH = 6
C_OP = 21

# 符号：1 方块 2 圆 3 上三角 4 下三角 5 菱形 6 左三角
S_LEAK = 1
S_FLOOD = 2
S_ENT = 3
S_LOW = 4
S_HIGH = 5
S_OP = 6


def get_section(d, name):
    """返回某一段的 5 条线端点 + 操作点（单位 m3/s）。"""
    VL, lk, en, fl, VL_lo, VL_hi, VLop, VVop = dp._load_perf_curves(d, name)

    def at(x, arr):
        return float(np.interp(x, VL, arr))

    x_lo, x_hi = float(VL_lo), float(VL_hi)
    leak = [at(x_lo, lk) / 3600.0, at(x_hi, lk) / 3600.0]
    ent = [at(x_lo, en) / 3600.0, at(x_hi, en) / 3600.0]
    flood = [at(x_lo, fl) / 3600.0, at(x_hi, fl) / 3600.0]

    Vop = float(VVop) / 3600.0
    Vmin = at(VLop, lk) / 3600.0
    Vmax = min(at(VLop, en), at(VLop, fl)) / 3600.0
    ymax = max(max(ent), max(flood)) * 1.15

    return dict(
        name=name,
        x=[x_lo / 3600.0, x_hi / 3600.0],
        leak=leak, entrain=ent, flood=flood,
        x_lo=x_lo / 3600.0, x_hi=x_hi / 3600.0,
        Vop=Vop, Vmin=Vmin, Vmax=Vmax,
        VLop=float(VLop) / 3600.0, ymax=ymax,
    )


def make_sheet(sec):
    """每段一张表，列名干净（图例才好看）。"""
    wks = op.new_sheet("w", sec["name"])
    wks.from_list(0, sec["x"], "V_L")
    wks.from_list(1, sec["leak"], "漏液线")
    wks.from_list(2, sec["entrain"], "雾沫夹带上限线")
    wks.from_list(3, sec["flood"], "液泛线")
    wks.from_list(4, [sec["x_lo"], sec["x_lo"]], "x_下限")
    wks.from_list(5, [0.0, sec["ymax"]], "液相流率下限")
    wks.from_list(6, [sec["x_hi"], sec["x_hi"]], "x_上限")
    wks.from_list(7, [0.0, sec["ymax"]], "液相流率上限")
    wks.from_list(8, [0.0, sec["VLop"] * 1.6], "x_操作线")
    wks.from_list(9, [0.0, sec["Vop"] * 1.6], "操作线")
    wks.from_list(10, [sec["VLop"]], "x_操作点")
    wks.from_list(11, [sec["Vop"]], "操作点")
    return wks


def style(p, color=None, symbol=None, size=None, line_width=None, line_style=None):
    """设置颜色/标记/线宽（line 模板下逐条生效）。"""
    if color is not None:
        try:
            p.colorinc = 0
        except Exception:
            pass
        try:
            p.color = color
        except Exception:
            pass
    if symbol is not None:
        try:
            p.symbol_kind = symbol
        except Exception:
            pass
    if size is not None:
        try:
            p.symbol_size = size
        except Exception:
            pass
    if line_width is not None:
        try:
            p.set_float("width", line_width)
        except Exception:
            pass
    if line_style is not None:
        try:
            p.set_float("style", line_style)
        except Exception:
            pass


def build_graph(sec, wks, outdir, xuehao):
    """画单个图并导出 PNG。"""
    gp = op.new_graph(f"{sec['name']}_负荷性能图", "line")
    gl = gp[0]

    style(gl.add_plot(wks, 1, 0, type="linesymbol"),
          color=C_LEAK, symbol=S_LEAK, size=10, line_width=1.2)
    style(gl.add_plot(wks, 3, 0, type="linesymbol"),
          color=C_FLOOD, symbol=S_FLOOD, size=10, line_width=1.2)
    style(gl.add_plot(wks, 2, 0, type="linesymbol"),
          color=C_ENT, symbol=S_ENT, size=10, line_width=1.2)
    style(gl.add_plot(wks, 5, 4, type="linesymbol"),
          color=C_LOW, symbol=S_LOW, size=10, line_width=1.2)
    style(gl.add_plot(wks, 7, 6, type="linesymbol"),
          color=C_HIGH, symbol=S_HIGH, size=10, line_width=1.2)
    style(gl.add_plot(wks, 9, 8, type="l"),
          color=C_LEAK, line_width=1.0)
    style(gl.add_plot(wks, 11, 10, type="s"),
          color=C_OP, symbol=S_OP, size=12)

    gl.set_xlim(0, sec["x_hi"] * 1.5)
    gl.set_ylim(0, sec["ymax"])
    gl.axis("x").title = "V_L (m3/s)"
    gl.axis("y").title = "V_G (m3/s)"

    # 操作点坐标
    try:
        gl.add_label("( %.6f , %.3f )" % (sec["VLop"], sec["Vop"]),
                     sec["VLop"] * 1.25, sec["Vop"] * 1.12)
    except Exception:
        pass
    # 上下限与弹性/稳定系数（避开曲线）
    try:
        gl.add_label("V_Gmax=%.3f m3/s" % sec["Vmax"],
                     sec["x_hi"] * 0.30, sec["Vmax"] * 1.10)
        gl.add_label("V_Gmin=%.3f m3/s" % sec["Vmin"],
                     sec["x_hi"] * 0.12, sec["Vmin"] * 0.70)
        gl.add_label("操作弹性: V_Gmax/V_Gmin = %.2f" % (sec["Vmax"] / sec["Vmin"]),
                     sec["x_hi"] * 0.50, sec["ymax"] * 0.38)
        gl.add_label("稳定系数: V_G/V_Gmin = %.2f" % (sec["Vop"] / sec["Vmin"]),
                     sec["x_hi"] * 0.50, sec["ymax"] * 0.28)
    except Exception:
        pass

    png = os.path.join(outdir, f"负荷性能图_{sec['name']}_{xuehao}.png")
    gp.save_fig(png, width=1400)
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="学号")
    ap.add_argument("--out", default=None, help="输出目录（默认当前目录）")
    args = ap.parse_args()

    d = dp.get_json(args.id)
    outdir = args.out or os.getcwd()
    os.makedirs(outdir, exist_ok=True)

    try:
        op.new()
    except Exception:
        pass

    pngs = []
    for name in ("精馏段", "提馏段"):
        sec = get_section(d, name)
        wks = make_sheet(sec)
        pngs.append(build_graph(sec, wks, outdir, args.id))

    opju = os.path.join(outdir, f"负荷性能图_Origin_{args.id}.opju")
    try:
        op.save(opju)
    except Exception:
        pass

    for p in pngs:
        print("已导出", p)
    print("已保存工程", opju)


if __name__ == "__main__":
    main()

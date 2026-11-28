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

try:
    import originpro as op
    HAS_ORIGIN = True
except Exception:                                    # 没装 originpro / Origin 起不来
    op = None
    HAS_ORIGIN = False

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


def plot_mpl_fallback(sec, outdir, xuehao):
    """Origin 不可用时的 matplotlib 兜底：样式与 Origin 版一致。

    只在 originpro 缺失 / Origin 启动失败时使用，保证「没有 Origin 也能出图」。
    """
    dp._setup_matplotlib()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 5.6), facecolor="white")
    xs = [sec["x_lo"], sec["x_hi"]]
    ax.plot(xs, sec["leak"], "-s", color="black", ms=7, lw=1.2, label="漏液线")
    ax.plot(xs, sec["flood"], "-o", color="red", ms=7, lw=1.2, label="液泛线")
    ax.plot(xs, sec["entrain"], "-^", color="blue", ms=7, lw=1.2, label="雾沫夹带上限线")
    ax.plot([sec["x_lo"]] * 2, [0, sec["ymax"]], "-v", color="green", ms=7, lw=1.2,
            label="液相流率下限")
    ax.plot([sec["x_hi"]] * 2, [0, sec["ymax"]], "-D", color="magenta", ms=7, lw=1.2,
            label="液相流率上限")
    ax.plot([0, sec["VLop"] * 1.6], [0, sec["Vop"] * 1.6], "k-", lw=1.0, label="操作线")
    ax.plot([sec["VLop"]], [sec["Vop"]], "P", color="orange", ms=10, label="操作点")

    ax.set_xlim(0, sec["x_hi"] * 1.5)
    ax.set_ylim(0, sec["ymax"])
    ax.set_xlabel("V_L (m3/s)")
    ax.set_ylabel("V_G (m3/s)")
    ax.set_title(f"{sec['name']} 气体液体负荷性能图", fontsize=12)
    ax.grid(True, ls=":", lw=0.5, alpha=0.5)

    ax.annotate(f"V_Gmax={sec['Vmax']:.3f} m3/s", (sec["x_hi"] * 0.30, sec["Vmax"] * 1.10))
    ax.annotate(f"V_Gmin={sec['Vmin']:.3f} m3/s", (sec["x_hi"] * 0.12, sec["Vmin"] * 0.70))
    ax.annotate(f"( {sec['VLop']:.6f} , {sec['Vop']:.3f} )",
                (sec["VLop"] * 1.25, sec["Vop"] * 1.12))
    ax.annotate(f"操作弹性: V_Gmax/V_Gmin = {sec['Vmax'] / sec['Vmin']:.2f}",
                (sec["x_hi"] * 0.50, sec["ymax"] * 0.38))
    ax.annotate(f"稳定系数: V_G/V_Gmin = {sec['Vop'] / sec['Vmin']:.2f}",
                (sec["x_hi"] * 0.50, sec["ymax"] * 0.28))
    ax.legend(fontsize=8, loc="upper right", framealpha=0.95)

    out = os.path.join(outdir, f"负荷性能图_{sec['name']}_{xuehao}.png")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="学号")
    ap.add_argument("--out", default=None, help="输出目录（默认当前目录）")
    ap.add_argument("--force-mpl", action="store_true",
                    help="强制用 matplotlib 兜底（不用 Origin）")
    args = ap.parse_args()

    d = dp.get_json(args.id)
    # 必须用绝对路径：Origin 的 save_fig 不认相对路径，会存到它自己的工作目录
    outdir = os.path.abspath(args.out or os.getcwd())
    os.makedirs(outdir, exist_ok=True)

    secs = [get_section(d, name) for name in ("精馏段", "提馏段")]

    use_origin = HAS_ORIGIN and not args.force_mpl
    if use_origin:
        try:
            op.new()
        except Exception as e:
            print("Origin 启动失败，改用 matplotlib 兜底：", e)
            use_origin = False

    if use_origin:
        pngs = []
        for sec in secs:
            wks = make_sheet(sec)
            pngs.append(build_graph(sec, wks, outdir, args.id))
        opju = os.path.join(outdir, f"负荷性能图_Origin_{args.id}.opju")
        try:
            op.save(opju)
        except Exception:
            pass
    else:
        if not HAS_ORIGIN:
            print("未检测到 originpro / Origin，改用 matplotlib 版（样式相同）")
        pngs = [plot_mpl_fallback(sec, outdir, args.id) for sec in secs]
        opju = None

    # 并排合成一张标准图（装订进说明书用这个）
    combined = None
    try:
        from PIL import Image

        a = Image.open(pngs[0])
        b = Image.open(pngs[1])
        h = max(a.height, b.height)
        w = a.width + b.width
        canvas = Image.new("RGB", (w, h), "white")
        canvas.paste(a, (0, 0))
        canvas.paste(b, (a.width, 0))
        combined = os.path.join(outdir, f"负荷性能图_{args.id}.png")
        canvas.save(combined)
    except Exception as e:
        print("合成失败（单图仍可用）：", e)

    for p in pngs:
        print("已导出", p)
    if combined:
        print("已合成", combined)
    if opju:
        print("已保存工程", opju)


if __name__ == "__main__":
    main()

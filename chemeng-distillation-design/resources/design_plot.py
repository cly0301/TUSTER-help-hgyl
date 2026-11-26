# -*- coding: utf-8 -*-
"""生成课设附图：负荷性能图 + 图解理论板图（matplotlib）。

用法：
    python design_plot.py --id 23044401
    python design_plot.py --id 23044401 --out D:\\我的图

输出：
    理论板图_<学号>.png      平衡线/操作线/q线/对角线 + 阶梯 + 板号 + 塔顶塔釜局部放大 + 3 条线方程
    负荷性能图_<学号>.png    五条线 + 操作点 + 操作线（精馏段/提馏段两幅）
"""

import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
CALC = os.path.join(BASE, "design_calc.py")
VLE = os.path.join(BASE, "ethanol-water-vle.csv")


def _setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    for fp in ("C:/Windows/Fonts/simfang.ttf", "C:/Windows/Fonts/simhei.ttf",
               "C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/msyh.ttc"):
        if os.path.exists(fp):
            try:
                font_manager.fontManager.addfont(fp)
            except Exception:
                pass
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "SimFang", "SimHei", "SimSun", "Microsoft YaHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return matplotlib


def get_json(xuehao, overrides=None):
    cmd = [sys.executable, CALC, "--id", str(xuehao), "--json"]
    if overrides:
        cmd += ["--set"] + [f"{k}={v}" for k, v in overrides.items()]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=BASE)
    if r.returncode != 0:
        raise RuntimeError(f"design_calc.py 失败：\n{r.stderr or r.stdout}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def load_vle():
    """返回 (x_mole, y_mole)，按 x 升序。"""
    xs, ys = [], []
    with open(VLE, encoding="utf-8-sig") as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 2:
                continue
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
    xy = sorted(zip(xs, ys))
    return np.array([p[0] for p in xy]), np.array([p[1] for p in xy])


def _op_lines(d):
    """返回 (精馏段操作线 mi, bi, 提馏段操作线 ms, bs, q线 xF, xW*, xD)。"""
    R = d["R"]
    xD, xF, xW = d["xD"], d["xF"], d["xW"]
    mi = R / (R + 1.0)
    bi = xD / (R + 1.0)
    yF = mi * xF + bi
    ms = yF / (xF - xW)
    bs = -ms * xW
    return mi, bi, ms, bs, xF, xW, xD


def plot_mccabe(d, out_path):
    _setup_matplotlib()
    import matplotlib.pyplot as plt

    vx, vy = load_vle()
    mi, bi, ms, bs, xF, xW, xD = _op_lines(d)

    def x_eq_of_y(y):
        return float(np.interp(y, vy, vx))

    # ---- 阶梯（与 design_calc.py 同一逻辑，额外记录坐标）----
    pts_x, pts_y = [xD], [xD]
    x, y = xD, xD
    n_rect = n_strip = 0
    steps = []          # [(x0,y0,x1,y1), ...] 水平段+垂直段
    while x > xW:
        x_eq = x_eq_of_y(y)
        if x_eq >= x:
            break
        if x >= xF:
            y_new = mi * x_eq + bi
            n_rect += 1
        else:
            y_new = ms * x_eq + bs
            n_strip += 1
        steps.append((x, y, x_eq, y))
        steps.append((x_eq, y, x_eq, y_new))
        x, y = x_eq, y_new
        pts_x.append(x)
        pts_y.append(y)
        if y <= 0 or len(pts_x) > 300:
            break

    fig = plt.figure(figsize=(11, 8.5), facecolor="white")
    ax = fig.add_axes([0.09, 0.09, 0.62, 0.86])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("液相摩尔分率 x（乙醇）")
    ax.set_ylabel("气相摩尔分率 y（乙醇）")
    ax.set_title("乙醇-水筛板精馏塔 图解理论板图", fontsize=13)
    ax.grid(True, ls=":", lw=0.5, alpha=0.6)

    ax.plot([0, 1], [0, 1], "k--", lw=1.0, label="对角线 y=x")
    ax.plot(vx, vy, "b-", lw=1.8, label="平衡线")
    xx = np.linspace(0, 1, 400)
    ax.plot(xx, mi * xx + bi, "r-", lw=1.5, label="精馏段操作线")
    ax.plot(xx, ms * xx + bs, "g-", lw=1.5, label="提馏段操作线")
    ax.axvline(xF, color="m", ls="-.", lw=1.2, label=f"q 线 x={xF:.4f}")

    for (x0, y0, x1, y1) in steps:
        ax.plot([x0, x1], [y0, y1], color="0.35", lw=1.0)

    # 板号（每隔几块标一个，避免糊）
    step_no = 0
    for (x0, y0, x1, y1) in steps:
        if abs(y0 - y1) < 1e-9:      # 水平段 -> 新板
            step_no += 1
            if step_no % 5 == 0 or step_no == 1:
                ax.text((x0 + x1) / 2, y0 + 0.012, str(step_no),
                        fontsize=7, color="0.25", ha="center")

    ax.plot([xD], [xD], "ko", ms=5)
    ax.plot([xW], [xW], "ko", ms=5)
    ax.plot([xF], [mi * xF + bi], "ms", ms=5)

    def sign(v):
        """把 +-0.0022 写成 - 0.0022（带符号，符号与数值分开）。"""
        return f"+ {v:.4f}" if v >= 0 else f"- {abs(v):.4f}"

    eq = (f"精馏段操作线: y={mi:.4f}x {sign(bi)}\n"
          f"提馏段操作线: y={ms:.4f}x {sign(bs)}\n"
          f"q 线: x={xF:.4f}（泡点进料 q=1）\n"
          f"理论级数 {d['n_rect']+d['n_strip']}（精{d['n_rect']}+提{d['n_strip']}，含塔釜）\n"
          f"理论板 N={d['N_trays']}  实际板 Ne={d['Ne']}（精{d['Ne_rect']}+提{d['Ne_strip']}）")
    ax.text(0.56, 0.30, eq, fontsize=8.5, va="top", family="sans-serif",
            bbox=dict(boxstyle="round", fc="white", ec="0.6", alpha=0.9))
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # ---- 塔顶 / 塔釜局部放大 ----
    for rect, xlim, ylim, tag in [
        ([0.74, 0.62, 0.24, 0.34], (0.55, 0.90), (0.55, 0.90), "塔顶局部放大"),
        ([0.74, 0.10, 0.24, 0.34], (0.0, 0.12), (0.0, 0.12), "塔釜局部放大"),
    ]:
        axi = fig.add_axes(rect)
        axi.set_xlim(*xlim)
        axi.set_ylim(*ylim)
        axi.set_title(tag, fontsize=8)
        axi.grid(True, ls=":", lw=0.4, alpha=0.6)
        axi.plot([xlim[0], xlim[1]], [xlim[0], xlim[1]], "k--", lw=0.8)
        axi.plot(vx, vy, "b-", lw=1.2)
        axi.plot(xx, mi * xx + bi, "r-", lw=1.0)
        axi.plot(xx, ms * xx + bs, "g-", lw=1.0)
        for (x0, y0, x1, y1) in steps:
            axi.plot([x0, x1], [y0, y1], color="0.35", lw=0.8)

    fig.savefig(out_path, dpi=160, facecolor="white")
    plt.close(fig)
    return out_path


def _load_perf_curves(d, name):
    """返回 (VL 数组 m3/h, 漏液, 雾沫夹带, 液泛, VL_lo, VL_hi, 操作点)。"""
    p = d["params"]
    D = float(d["d_rect"])
    A = math.pi / 4.0 * D * D
    Ad, lw, A0 = float(d["Ad"]), float(d["lw"]), float(d["A0"])
    rhoL = float(d[f"rhoL_{'rect' if name == '精馏段' else 'strip'}"])
    rhoG = float(d[f"rhoG_{'rect' if name == '精馏段' else 'strip'}"])
    sig = float(d[f"sig_{'rect' if name == '精馏段' else 'strip'}"])
    HT = float(d[f"HT_{'rect' if name == '精馏段' else 'strip'}"])
    hw = float(d["hw"])
    Hd = float(d[f"Hd_{'rect' if name == '精馏段' else 'strip'}"])
    g = 9.81
    hsig = 4e-3 * sig / (rhoL * g * p["d0"] / 1000.0)
    hH = p["hH"] / 1000.0

    def how_of(VL):
        return 0.0028 * p["Fw"] * (VL * 3600.0 / lw) ** (2.0 / 3.0)

    def leak(VL):
        h0min = 0.0056 + 0.13 * (hw + how_of(VL)) - hsig
        u0min = p["C0"] * math.sqrt(2 * g * h0min * rhoL / rhoG) if h0min > 0 else 0.0
        return u0min * A0 * 3600.0

    def entrain(VL):
        hL = hw + how_of(VL)
        u = (HT - 2.5 * hL) * (0.1 * sig / 0.0057) ** (1.0 / 3.2)
        return u * (A - Ad) * 3600.0

    def flood(VL):
        hL = hw + how_of(VL)
        hd = 0.153 * (VL / (lw * hH)) ** 2
        target = p["phi_foam"] * (HT + hw)
        lo, hi = 1e-6, 10.0
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            dHt = 0.5 / g * (mid / A0 / p["C0"]) ** 2 * (rhoG / rhoL) + p["beta"] * hL
            if hL + hd + dHt > target:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi) * 3600.0

    VL_lo = lw * (0.006 / (0.0028 * p["Fw"])) ** 1.5 / 3600.0 * 3600.0
    VL_hi = Ad * Hd / 3.0 * 3600.0
    VLop = float(d[f"Vl_{'rect' if name == '精馏段' else 'strip'}"]) * 3600.0
    VVop = float(d[f"Vg_{'rect' if name == '精馏段' else 'strip'}"]) * 3600.0
    VL = np.linspace(max(VL_lo * 0.5, 0.5), VL_hi * 1.3, 60)
    return (VL, np.array([leak(v / 3600.0) for v in VL]),
            np.array([entrain(v / 3600.0) for v in VL]),
            np.array([flood(v / 3600.0) for v in VL]),
            VL_lo, VL_hi, VLop, VVop)


def plot_loading(d, out_path):
    _setup_matplotlib()
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2), facecolor="white")
    for ax, name in zip(axes, ("精馏段", "提馏段")):
        VL, lk, en, fl, VL_lo, VL_hi, VLop, VVop = _load_perf_curves(d, name)
        ax.plot(VL, lk, "b-", lw=1.5, label="漏液线")
        ax.plot(VL, en, "r-", lw=1.5, label="雾沫夹带线")
        ax.plot(VL, fl, "g-", lw=1.5, label="液泛线")
        ax.axvline(VL_lo, color="m", ls="--", lw=1.2, label="液相下限")
        ax.axvline(VL_hi, color="m", ls="--", lw=1.2, label="液相上限")
        ax.plot([0, VLop * 1.6], [0, VVop * 1.6], "k-.", lw=1.0, label="操作线")
        ax.plot([VLop], [VVop], "ko", ms=7, label="操作点")

        up = min(float(np.interp(VLop, VL, en)), float(np.interp(VLop, VL, fl)))
        down = float(np.interp(VLop, VL, lk))
        ax.set_xlim(0, VL_hi * 1.35)
        ax.set_ylim(0, max(np.nanmax(en), np.nanmax(fl)) * 1.1)
        ax.set_xlabel("液相流量 L（m3/h）")
        ax.set_ylabel("气相流量 V（m3/h）")
        ax.set_title(f"{name} 塔板负荷性能图", fontsize=12)
        ax.grid(True, ls=":", lw=0.5, alpha=0.6)
        info = (f"操作点: L={VLop:.2f}, V={VVop:.1f}\n"
                f"气相下限 {down:.1f}\n气相上限 {up:.1f}\n"
                f"弹性 {up / down:.2f}" if down > 0 else "操作点附近无下限")
        ax.text(0.02, 0.97, info, transform=ax.transAxes, fontsize=8,
                va="top", bbox=dict(boxstyle="round", fc="white", ec="0.6"))
        ax.legend(fontsize=7.5, loc="lower right", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=160, facecolor="white")
    plt.close(fig)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="学号")
    ap.add_argument("--set", nargs="*", default=None, metavar="KEY=VAL")
    ap.add_argument("--out", default=None, help="输出目录（默认当前目录）")
    args = ap.parse_args(argv)

    overrides = {}
    for kv in (args.set or []):
        k, v = kv.split("=", 1)
        overrides[k] = v

    d = get_json(args.id, overrides)
    outdir = args.out or os.getcwd()
    os.makedirs(outdir, exist_ok=True)

    p1 = os.path.join(outdir, f"理论板图_{args.id}.png")
    p2 = os.path.join(outdir, f"负荷性能图_{args.id}.png")
    plot_mccabe(d, p1)
    plot_loading(d, p2)
    print("已生成", p1)
    print("已生成", p2)
    print(f"理论级数 {d['n_rect']+d['n_strip']}（精{d['n_rect']}+提{d['n_strip']}，含塔釜）、"
          f"理论板 N={d['N_trays']}、实际板 Ne={d['Ne']}（精{d['Ne_rect']}+提{d['Ne_strip']}）")


if __name__ == "__main__":
    main()

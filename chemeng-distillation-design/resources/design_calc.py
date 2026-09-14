#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
乙醇-水筛板精馏塔 课程设计 一键计算脚本
========================================
用法（需同目录下有 resources/ethanol-water-vle.csv）：

    python resources/design_calc.py --xuehao 01 --banhao 445

或直接改 CONFIG 里的两个值。输出完整设计计算报告。

说明：
- 本脚本为「参考实现」，用于复算、验证与教学。气液平衡曲线用自然三次样条插值；
  图表类取值（Smith 负荷系数图）用查表近似，与手算查图有 1到5% 量级差异。
- 平均相对挥发度 alpha 按「每块理论板的相对挥发度取几何平均」计算（与教材一致）。
"""
import csv, math, os, argparse, sys, io, json, contextlib

CONFIG = {"xuehao": "01", "banhao": "445"}   # 学号后两位 / 班号后三位

# main() 结束时写入的关键指标，供 --advise 增量核算读取
METRICS = {}

MA, MB = 46.0, 18.0          # 乙醇 / 水 摩尔质量 kg/kmol
P0 = 101.3                    # 操作压力 kPa
PROD_TONS_DAY = 24.0          # 日产 24 吨

# 自选参数（与 SKILL.md 第 2 节的建议值对应）
PARAMS = {
    # ---- 塔板结构（长度 mm / 塔径板间距 m）----
    "HT": 0.35,        # 精馏段板间距 m
    "HT2": 0.65,       # 提馏段板间距 m
    "lw_ratio": 0.7,   # 堰长比 lw/D
    "hL": 50.0,        # 板上清液层 hL mm
    "hH": 28.0,        # 降液管底隙 hH mm
    "Wc": 50.0,        # 边缘区宽度 mm
    "Ws": 60.0,        # 安定区宽度 mm
    "d0": 5.0,         # 筛孔孔径 mm
    "t": 17.0,         # 孔距 mm（正三角形排列；t/d0=3.4，开孔率约 7.8%）
    "tp": 4.0,         # 板厚 mm
    "C0": 0.82,        # 干筛孔流量系数
    "beta": 0.6,       # 液层阻力修正系数
    "phi_foam": 0.6,   # 泡沫密度系数（降液管液面校核用）
    "Fw": 1.02,        # 堰上液头校正系数
    "u_uF": 0.8,       # 空塔气速系数 u/uF（0.5~0.8）
    # ---- 接管流速 m/s ----
    "u_liq": 0.5,      # 进料管 / 釜液排出管
    "u_liq_ret": 0.3,  # 回流管
    "u_gas": 15.0,     # 塔顶蒸汽 / 塔底进气
    # ---- 附属设备 ----
    "K_cond": 915.0,   # 全凝器总传热系数 W/(m2·K)
    "t_cool_in": 30.0,   # 冷却水进口 ℃
    "t_cool_out": 45.0,  # 冷却水出口 ℃（≤50）
    # ---- 塔高 ----
    "HD": 1.0,         # 塔顶空间 m
    "HB": 1.0,         # 塔底空间 m
    "HS": 1.5,         # 裙座高 m
    "hole_every": 6,   # 每几块板设一个人孔
    "hole_h": 0.6,     # 人孔处板间距加高 m（人孔 Φ600）
}

DEFAULT_PARAMS = dict(PARAMS)   # 出厂默认值快照，供增量核算做对比基准

# 标准无缝钢管规格 (外径 mm, 壁厚 mm)，GB/T 8163
PIPES = [(18, 3), (25, 3), (32, 3), (38, 3), (45, 3), (57, 3.5), (76, 4),
         (89, 4), (108, 4), (133, 4), (159, 4.5), (219, 6), (273, 8),
         (325, 8), (377, 9), (426, 9), (480, 9), (530, 9), (630, 9)]


def pick_pipe(d_req_mm):
    """按下限内径选标准管，返回 (外径, 壁厚, 内径) mm。"""
    for od, wall in PIPES:
        if od - 2 * wall >= d_req_mm:
            return od, wall, od - 2 * wall
    od, wall = PIPES[-1]
    return od, wall, od - 2 * wall


def pipe_size(V_m3s, u):
    """按 d = sqrt(4V/(pi*u)) 算内径 (mm) 并选标准管。"""
    d = math.sqrt(4.0 * V_m3s / (math.pi * u)) * 1000.0
    od, wall, id_ = pick_pipe(d)
    return d, od, wall, id_

# ---------------- 物性关联式（T 单位 ℃，结果 SI） ----------------
def rho_water(T):
    return 1000.0 - 0.0178 * (T - 4.0) ** 1.7

def rho_ethanol(T):
    return 765.7 - 1.17 * (T - 60.0)

def mu_water(T_C):
    T = T_C + 273.15
    return 2.414e-5 * 10 ** (247.8 / (T - 140.0)) * 1000.0

def mu_ethanol(T_C):
    T = T_C + 273.15
    return 0.00327 * math.exp(1730.0 / T)

def sigma_water(T):
    return 75.7 - 0.165 * T

def sigma_ethanol(T):
    return 24.1 - 0.089 * T

def r_latent_ethanol(T):
    return 855.0 - 2.5 * (T - 78.0)

def r_latent_water(T):
    return 2500.0 - 2.4 * T

def mu_mix(x, T):
    mue, muw = mu_ethanol(T), mu_water(T)
    return math.exp(x * math.log(mue) + (1.0 - x) * math.log(muw))

def rho_mix(x, T):
    """混合液体密度 kg/m3，按摩尔体积加和（等价于质量分数体积加和）。"""
    rA, rB = rho_ethanol(T), rho_water(T)
    Vm = x * MA / rA + (1.0 - x) * MB / rB   # m3/kmol
    M = x * MA + (1.0 - x) * MB              # kg/kmol
    return M / Vm

def sigma_mix(x, T):
    P_A, P_B = 126.4, 42.6
    Pm = x * P_A + (1.0 - x) * P_B
    M = x * MA + (1.0 - x) * MB
    rho = rho_mix(x, T)
    Vm = M / (rho / 1000.0)
    return (Pm / Vm) ** 4

# ---------------- 数据与样条 ----------------
def load_vle(path):
    xs, ys, ts = [], [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            xs.append(float(row["x_mole"]))
            ys.append(float(row["y_mole"]))
            ts.append(float(row["t_C"]))
    return xs, ys, ts

def natural_spline(xs, ys):
    """自然三次样条，返回 (xs, ys, b, c, d)。"""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    alpha = [0.0] * (n - 1)
    for i in range(1, n - 1):
        alpha[i] = 3.0 / h[i] * (ys[i + 1] - ys[i]) - 3.0 / h[i - 1] * (ys[i] - ys[i - 1])
    l = [1.0] + [0.0] * (n - 1)
    mu = [0.0] * n
    z = [0.0] * n
    for i in range(1, n - 1):
        l[i] = 2.0 * (xs[i + 1] - xs[i - 1]) - h[i - 1] * mu[i - 1]
        mu[i] = h[i] / l[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]
    l[n - 1] = 1.0
    c = [0.0] * n
    b = [0.0] * n
    d = [0.0] * n
    for j in range(n - 2, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (ys[j + 1] - ys[j]) / h[j] - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0
        d[j] = (c[j + 1] - c[j]) / (3.0 * h[j])
    return xs, ys, b, c, d

def spline_eval(spl, x):
    xs, ys, b, c, d = spl
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            dx = x - xs[i]
            return ys[i] + b[i] * dx + c[i] * dx * dx + d[i] * dx * dx * dx
    return ys[-1]

# ---------------- Smith 负荷系数图（查表近似） ----------------
SMITH = {
    0.30: [(0.01, 0.072), (0.02, 0.066), (0.05, 0.058), (0.1, 0.050), (0.2, 0.042), (0.5, 0.031), (1.0, 0.023)],
    0.45: [(0.01, 0.085), (0.02, 0.078), (0.05, 0.069), (0.1, 0.060), (0.2, 0.051), (0.5, 0.038), (1.0, 0.028)],
    0.60: [(0.01, 0.095), (0.02, 0.088), (0.05, 0.078), (0.1, 0.068), (0.2, 0.058), (0.5, 0.043), (1.0, 0.032)],
}
def c20_smith(FLV, spacing):
    keys = sorted(SMITH.keys())
    def at(s):
        pts = SMITH[s]
        if FLV <= pts[0][0]:
            return pts[0][1]
        if FLV >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            f0, c0 = pts[i]; f1, c1 = pts[i + 1]
            if f0 <= FLV <= f1:
                lg = math.log10(FLV); l0 = math.log10(f0); l1 = math.log10(f1)
                t = (lg - l0) / (l1 - l0)
                return c0 + t * (c1 - c0)
        return pts[-1][1]
    if spacing <= keys[0]:
        return at(keys[0])
    if spacing >= keys[-1]:
        return at(keys[-1])
    for i in range(len(keys) - 1):
        s0, s1 = keys[i], keys[i + 1]
        if s0 <= spacing <= s1:
            t = (spacing - s0) / (s1 - s0)
            return at(s0) + t * (at(s1) - at(s0))
    return at(keys[-1])

# ---------------- 参数换算 ----------------
def convert_params(xuehao, banhao):
    a = int(xuehao); b = int(banhao)
    aF = (30 + b * 0.02 + a * 0.05) / 100.0
    aD = (93.5 + a * 0.02) / 100.0
    aW = 0.003
    return aF, aD, aW, (1.4 + a * 0.01)

def mass_to_mole(a):
    return (a / MA) / (a / MA + (1.0 - a) / MB)

def round_up_diameter(x_m):
    """塔径圆整（课件 5.6）：<=1000mm 按 100mm 递增；>1000mm 按 200mm 递增。"""
    mm = x_m * 1000.0
    step = 100.0 if mm <= 1000.0 else 200.0
    return math.ceil(mm / step) * step / 1000.0

# ---------------- McCabe-Thiele ----------------
def mccabe_thiele(xD, xW_star, xF, spl_yx, spl_xy, R):
    """图解法步进理论板。返回 (总板数, 精馏段板数, 提馏段板数, 板液相组成列表)。"""
    mR = R / (R + 1.0)
    bR = xD / (R + 1.0)
    def y_op_rect(x):
        return mR * x + bR
    yF_int = y_op_rect(xF)
    mS = yF_int / (xF - xW_star)
    bS = -mS * xW_star
    def y_op_strip(x):
        return mS * x + bS
    def x_eq_of_y(y):
        return spline_eval(spl_xy, y)

    x, y = xD, xD
    x_list = [xD]
    n_rect = 0
    n_strip = 0
    while x > xW_star:
        x_eq = x_eq_of_y(y)
        if x_eq >= x:
            break
        if x >= xF:
            y = y_op_rect(x_eq)
            n_rect += 1
        else:
            y = y_op_strip(x_eq)
            n_strip += 1
        x = x_eq
        x_list.append(x)
        if y <= 0 or len(x_list) > 300:
            break
    return n_rect + n_strip, n_rect, n_strip, x_list

# ---------------- 3.6 塔板结构设计 ----------------
def tray_geometry(D, p):
    """塔板几何尺寸（两段共用同一塔径 D，单位 m）。"""
    A = math.pi / 4.0 * D * D
    lw = p["lw_ratio"] * D
    R = D / 2.0
    a = lw / 2.0
    Wd = R - math.sqrt(R * R - a * a)                  # 弓形降液管宽
    th = 2.0 * math.asin(a / R)
    Ad = R * R / 2.0 * (th - math.sin(th))             # 弓形降液管面积
    r = R - p["Wc"] / 1000.0                           # 鼓泡区半径
    x = R - (Wd + p["Ws"] / 1000.0)                    # 鼓泡区半弦
    if 0.0 < x < r:
        Aa = 2.0 * (x * math.sqrt(r * r - x * x)
                    + math.pi / 180.0 * r * r * math.degrees(math.asin(x / r)))
    else:
        Aa = 0.0
    phi = 0.907 * (p["d0"] / p["t"]) ** 2              # 开孔率
    A0 = phi * Aa                                      # 开孔区面积
    n = int(1.155 * Aa / (p["t"] / 1000.0) ** 2)       # 孔数
    return dict(D=D, A=A, lw=lw, Wd=Wd, Ad=Ad, AdA=Ad / A, Aa=Aa,
                phi=phi, A0=A0, n=n, d0=p["d0"], t=p["t"], tp=p["tp"],
                hH=p["hH"], Wc=p["Wc"], Ws=p["Ws"])


def weir_head(VL, lw, p):
    """堰上液头 how (m) 与堰高 hw (m)；VL 为液相体积流量 m3/s。"""
    how = 0.0028 * p["Fw"] * (VL * 3600.0 / lw) ** (2.0 / 3.0)
    hw = p["hL"] / 1000.0 - how
    return how, hw


# ---------------- 3.7 流体力学验算 ----------------
def hydraulic_check(tray, VL, VV, rhoL, rhoV, sig, HT, hw, how, p):
    """单段流体力学验算。VL/VV 为 m3/s，sig 为 mN/m，长度均为 m。"""
    g = 9.81
    A, Ad, lw, A0 = tray["A"], tray["Ad"], tray["lw"], tray["A0"]
    d0 = tray["d0"] / 1000.0
    hL = hw + how
    u0 = VV / A0                                        # 筛孔气速
    h0 = 0.5 / g * (u0 / p["C0"]) ** 2 * (rhoV / rhoL)  # 干板压降（m 液柱）
    he = p["beta"] * hL                                 # 液层压降
    dHt = h0 + he                                       # 单板压降
    hd = 0.153 * (VL / (lw * p["hH"] / 1000.0)) ** 2    # 降液管阻力
    Hd = hL + hd + dHt                                  # 降液管内液面高
    tau = Ad * Hd / VL                                  # 停留时间
    u = VV / (A - Ad)                                   # 有效截面气速
    eV = 0.0057 / sig * (u / (HT - 2.5 * hL)) ** 3.2    # Hunt 液沫夹带
    hsig = 4e-3 * sig / (rhoL * g * d0)
    h0min = 0.0056 + 0.13 * hL - hsig
    u0min = p["C0"] * math.sqrt(2 * g * h0min * rhoL / rhoV) if h0min > 0 else 0.0
    return dict(hL=hL, u0=u0, h0=h0, he=he, dHt=dHt, hd=hd, Hd=Hd,
                Hd_lim=p["phi_foam"] * (HT + hw), tau=tau, u=u, eV=eV,
                hsig=hsig, h0min=h0min, u0min=u0min,
                K=(u0 / u0min if u0min > 0 else float("inf")))


# ---------------- 3.8 塔板负荷性能图 ----------------
def load_perf(tray, rhoL, rhoV, sig, HT, hw, Hd_design, p, VLpts):
    """五条线。返回 (L, 漏液线, 雾沫夹带线, 液泛线) 采样点 + 液相上下限。"""
    g = 9.81
    A, Ad, lw, A0 = tray["A"], tray["Ad"], tray["lw"], tray["A0"]
    hsig = 4e-3 * sig / (rhoL * g * tray["d0"] / 1000.0)
    hH = p["hH"] / 1000.0

    def how_of(VL):
        return 0.0028 * p["Fw"] * (VL * 3600.0 / lw) ** (2.0 / 3.0)

    def leak(VL):                                       # 漏液线（气相下限）
        h0min = 0.0056 + 0.13 * (hw + how_of(VL)) - hsig
        u0min = p["C0"] * math.sqrt(2 * g * h0min * rhoL / rhoV) if h0min > 0 else 0.0
        return u0min * A0 * 3600.0

    def entrain(VL):                                    # 雾沫夹带线（eV = 0.1）
        hL = hw + how_of(VL)
        u = (HT - 2.5 * hL) * (0.1 * sig / 0.0057) ** (1.0 / 3.2)
        return u * (A - Ad) * 3600.0

    def flood(VL):                                      # 液泛线（Hd = φ(HT+hw)）
        hL = hw + how_of(VL)
        hd = 0.153 * (VL / (lw * hH)) ** 2
        target = p["phi_foam"] * (HT + hw)
        lo, hi = 1e-6, 10.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            dHt = 0.5 / g * (mid / A0 / p["C0"]) ** 2 * (rhoV / rhoL) + p["beta"] * hL
            if hL + hd + dHt > target:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi) * 3600.0

    VL_lo = lw * (0.006 / (0.0028 * p["Fw"])) ** 1.5 / 3600.0   # how = 6 mm
    VL_hi = Ad * Hd_design / 3.0                                # tau = 3 s
    pts = [(VL, leak(VL), entrain(VL), flood(VL)) for VL in VLpts]
    return dict(pts=pts, VL_lo=VL_lo, VL_hi=VL_hi)

def ok(flag):
    """校核结论标记。"""
    return "OK" if flag else "**不合格**"


def suggest_fix(tray, results, hyd, p, names, Ne_rect, Ne_strip):
    """扫描候选参数并逐一带入完整试算，返回确实能让全部校核合格的建议值。"""
    D = tray['D']

    def assess(pp):
        """给定参数，返回 (不合格列表, 塔板几何, 各段验算, 全塔压降 kPa)。"""
        tt = tray_geometry(D, pp)
        hs, bad = {}, []
        for i, n in enumerate(names):
            r = results[n]
            HT_seg = pp['HT'] if i == 0 else pp['HT2']   # 扫描时必须用候选值，不能用原值
            how, hw = weir_head(r['Vl'], tt['lw'], pp)
            h = hydraulic_check(tt, r['Vl'], r['Vg'], r['rhoL'], r['rhoG'],
                                r['sig'], HT_seg, hw, how, pp)
            h.update(how=how, hw=hw)
            hs[n] = h
            if h['how'] <= 0.006:
                bad.append(f"{n}堰上液头不足")
            if h['Hd'] > h['Hd_lim']:
                bad.append(f"{n}降液管液面过高")
            if h['tau'] <= 3.0:
                bad.append(f"{n}停留时间不足")
            if h['eV'] >= 0.1:
                bad.append(f"{n}液沫夹带过大")
            if h['K'] <= 1.5:
                bad.append(f"{n}稳定系数不足")
        dP = (Ne_rect * hs[names[0]]['dHt'] * results[names[0]]['rhoL']
              + Ne_strip * hs[names[1]]['dHt'] * results[names[1]]['rhoL']) * 9.81 / 1000.0
        if dP > 30.0:
            bad.append("全塔压降超限")
        return bad, tt, hs, dP

    def sync_hH(pp):
        """hL 变小后堰高随之降低，把降液管底隙压到 hw-8mm 以内（须形成液封且流得出）。"""
        tt = tray_geometry(D, pp)
        for n in names:
            _, hw = weir_head(results[n]['Vl'], tt['lw'], pp)
            hH_max = (hw - 0.008) * 1000.0
            if pp['hH'] > hH_max:
                pp['hH'] = max(15.0, math.floor(hH_max))

    def scan(key, values, describe, adjust=None):
        """扫描某参数，返回首个可行值（取离当前值最近者）。"""
        cur = p[key]
        good = []
        for v in values:
            pp = dict(p)
            pp[key] = v
            if adjust:
                adjust(pp)
            if not assess(pp)[0]:
                good.append(v)
        if not good:
            return None
        rec = min(good, key=lambda v: abs(v - cur))
        if abs(rec - cur) < 1e-9:
            return None
        pp = dict(p)
        pp[key] = rec
        if adjust:
            adjust(pp)
        _, tt, hs, dP = assess(pp)
        return describe(cur, rec, pp, tt, hs, dP)

    tips = []
    h0, h1 = names[0], names[1]
    bad0 = assess(p)[0]
    bad_segs = [n for n in names if any(b.startswith(n) for b in bad0)]

    def seg_cand(n):
        key = 'HT' if n == h0 else 'HT2'
        lo = 0.30 if key == 'HT' else 0.40
        return (key, [round(lo + 0.05 * i, 2) for i in range(13)],
                lambda c, r, pp, tt, hs, dP, n=n:
                f"{n}板间距：{c*1000:.0f} → **{r*1000:.0f} mm**\n"
                f"        试算：液沫夹带 {hs[n]['eV']:.4f}、降液管液面 {hs[n]['Hd']*1000:.1f} mm"
                f"（限 {hs[n]['Hd_lim']*1000:.1f}）—— 全部合格")

    # 全局参数（同时影响两段）
    global_cands = [
        ('t', [float(v) for v in range(10, 31)],
         lambda c, r, pp, tt, hs, dP:
         f"孔距 t：{c:.0f} → **{r:.0f} mm**（开孔率 {tray['phi']:.4f}→{tt['phi']:.4f}）\n"
         f"        试算：稳定系数 {hs[h0]['K']:.2f}/{hs[h1]['K']:.2f}、"
         f"全塔压降 {dP:.1f} kPa、单板压降 {hs[h0]['dHt']*1000:.1f}/{hs[h1]['dHt']*1000:.1f} mm 液柱 —— 全部合格"),
        ('lw_ratio', [round(0.40 + 0.05 * i, 2) for i in range(12)],
         lambda c, r, pp, tt, hs, dP:
         f"堰长比 lw/D：{c} → **{r}**（堰长 {tt['lw']*1000:.0f} mm、"
         f"降液管面积 {tt['Ad']:.4f} m²、Ad/A {tt['AdA']:.4f}）\n"
         f"        试算：停留时间 {hs[h0]['tau']:.2f}/{hs[h1]['tau']:.2f} s、"
         f"堰上液头 {hs[h0]['how']*1000:.1f}/{hs[h1]['how']*1000:.1f} mm —— 全部合格"),
    ]
    hL_cand = ('hL', [float(v) for v in range(40, 81, 5)],
               lambda c, r, pp, tt, hs, dP:
               f"板上清液层 hL：{c:.0f} → **{r:.0f} mm**（堰高 hw 随之变化，"
               f"降液管底隙已联动调至 {pp['hH']:.0f} mm）\n"
               f"        试算：液沫夹带 {hs[h0]['eV']:.4f}/{hs[h1]['eV']:.4f}、"
               f"稳定系数 {hs[h0]['K']:.2f}/{hs[h1]['K']:.2f} —— 全部合格")

    # 只坏一段时优先调该段板间距（副作用最小）；两段都坏则先调全局参数
    seg = [seg_cand(n) for n in bad_segs]
    candidates = (seg + global_cands if len(bad_segs) == 1 else global_cands + seg) + [hL_cand]
    for key, values, describe in candidates:
        msg = scan(key, values, describe, adjust=(sync_hH if key == 'hL' else None))
        if msg:
            tips.append(msg)
            break
    if not tips:
        tips.append("单靠调整孔距/堰长/板间距/清液层已无法全部达标：\n"
                    "        · 压降与稳定系数互相矛盾时，应改变塔径"
                    "（加大塔径可同时降低气速、压降与夹带）；\n"
                    "        · 也可重新选定板间距组合（精馏段 300~600、提馏段可取得更大）。")
    return tips

# ---------------- 主计算 ----------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--xuehao", default=None, help="学号后两位")
    ap.add_argument("--banhao", default=None, help="班号后三位（给学号时可省略，自动按学号第4到6位拆）")
    ap.add_argument("--id", default=None, help="完整8位学号(如 23044401)")
    ap.add_argument("--set", nargs="*", default=None, metavar="KEY=VAL",
                    help="覆盖自选参数，如 --set HT=0.45 HT2=0.6 t=15 u_uF=0.7")
    ap.add_argument("--show-params", action="store_true",
                    help="只列出全部可调参数及当前值，然后退出")
    ap.add_argument("--advise", action="store_true",
                    help="增量核算：输出当前选择的影响，以及后续各参数的可行范围")
    ap.add_argument("--json", action="store_true", help="只输出指标 JSON（内部使用）")
    args = ap.parse_args(argv)

    # 自选参数覆盖（使用者逐组选定后由此传入）
    overrides = {}
    if args.set:
        for kv in args.set:
            if "=" not in kv:
                print(f"[错误] 参数格式应为 KEY=VAL，收到：{kv}")
                sys.exit(1)
            k, v = kv.split("=", 1)
            if k not in PARAMS:
                print(f"[错误] 未知参数 {k}。可用参数：\n  {', '.join(sorted(PARAMS))}")
                sys.exit(1)
            try:
                PARAMS[k] = type(PARAMS[k])(v)
                overrides[k] = PARAMS[k]
            except ValueError:
                print(f"[错误] 参数 {k} 无法解析为 {type(PARAMS[k]).__name__}：{v}")
                sys.exit(1)
    if args.show_params:
        print("可调自选参数（当前值）：")
        for k in sorted(PARAMS):
            print(f"  {k:12s} = {PARAMS[k]}")
        sys.exit(0)
    if args.id:
        s = str(args.id).zfill(8)
        args.xuehao = s[6:8]                 # 学号后两位 = 末两位
        if args.banhao is None:
            args.banhao = s[3:6]             # 只给学号时：班号后三位 = 第4到6位
    # 既给学号又给班号时用用户给的班号；都没给用默认值
    xh = args.xuehao if args.xuehao is not None else CONFIG["xuehao"]
    bh = args.banhao if args.banhao is not None else CONFIG["banhao"]

    # 增量核算模式：不进主流程，由 do_advise 自己反复试算
    if args.advise:
        do_advise(xh, bh, overrides)
        return

    base = os.path.dirname(os.path.abspath(__file__))
    vle_path = os.path.join(base, "ethanol-water-vle.csv")
    if not os.path.exists(vle_path):
        print(f"找不到 VLE 数据文件：{vle_path}")
        sys.exit(1)

    vle_x, vle_y, vle_t = load_vle(vle_path)
    spl_yx = natural_spline(vle_x, vle_y)   # y = f(x)
    spl_xy = natural_spline(vle_y, vle_x)   # x = f(y)
    spl_tx = natural_spline(vle_x, vle_t)   # t = f(x)
    y_eq = lambda x: spline_eval(spl_yx, x)
    t_eq = lambda x: spline_eval(spl_tx, x)

    aF, aD, aW, R_factor = convert_params(xh, bh)
    xF, xD, xW = mass_to_mole(aF), mass_to_mole(aD), mass_to_mole(aW)

    print("=" * 66)
    print("乙醇-水筛板精馏塔 课程设计 计算报告")
    print("=" * 66)
    print(f"学号后两位 = {xh}   班号后三位 = {bh}")
    print(f"进料 aF = {aF*100:.2f}%  xF = {xF:.4f}")
    print(f"塔顶 aD = {aD*100:.2f}%  xD = {xD:.4f}")
    print(f"塔釜 aW = {aW*100:.2f}%  xW = {xW:.5f}")
    print(f"自选参数：HT={PARAMS['HT']*1000:.0f}/{PARAMS['HT2']*1000:.0f} mm  "
          f"lw/D={PARAMS['lw_ratio']}  hL={PARAMS['hL']:.0f} mm  hH={PARAMS['hH']:.0f} mm  "
          f"d0/t={PARAMS['d0']:.0f}/{PARAMS['t']:.0f} mm  u/uF={PARAMS['u_uF']}")
    print("  （改动自选参数用 --set KEY=VAL，完整清单见 --show-params）")

    # ---- 2.1 塔顶产品量 ----
    MD = MA * xD + MB * (1 - xD)
    D = (PROD_TONS_DAY * 1000 / 24) / MD
    print("\n[2.1 塔顶产品量]")
    print(f"  MD = {MD:.3f} kg/kmol")
    print(f"  塔顶 D = {D:.2f} kmol/h  (日产 24t => {D*MD:.0f} kg/h)")

    # ---- 2.2 最小回流比（切线法，样条）----
    N_scan = 8000
    m_max, x_tan = 0.0, xF
    for i in range(1, N_scan):
        xx = xF + (xD - xF) * i / N_scan
        yy = y_eq(xx)
        m = (xD - yy) / (xD - xx)
        if m > m_max:
            m_max, x_tan = m, xx
    y_tan = y_eq(x_tan)
    Rmin = m_max / (1.0 - m_max)
    ym = xD / (Rmin + 1.0)          # 切线在 y 轴上的截距 = xD/(Rmin+1)
    print("\n[2.2 最小回流比（切线法）]")
    print(f"  切点 (x,y) = ({x_tan:.4f}, {y_tan:.4f})")
    print(f"  切线 y 轴截距 ym = {ym:.4f}")
    print(f"  Rmin = xD/ym - 1 = {xD:.4f}/{ym:.4f} - 1 = {Rmin:.3f}")

    # ---- 2.3 操作回流比与直接蒸汽 ----
    R = R_factor * Rmin
    S = D * (R + 1.0)               # 直接蒸汽：S = V = V' = (R+1)D
    print("\n[2.3 操作回流比与直接蒸汽]")
    print(f"  回流比 R = {R_factor:.2f} x Rmin = {R:.3f}")
    print(f"  直接蒸汽 S = (R+1)D = {S:.2f} kmol/h")

    # ---- 2.4 全塔物料衡算（直接蒸汽加热）----
    # 总衡算 F + S = D + W ；乙醇衡算 F·xF = D·xD + W·xW
    F = (D * (xD - xW) + S * xW) / (xF - xW)
    W = F + S - D
    xWstar = (F * xF - D * xD) / W   # 恒等于 xW
    Lprime = R * D + F
    print("\n[2.4 全塔物料衡算（直接蒸汽加热）]")
    print(f"  进料 F = [D(xD-xW)+S·xW]/(xF-xW) = {F:.2f} kmol/h")
    print(f"  釜液 W = F - D + S = {W:.2f} kmol/h")
    print(f"  釜液浓度 x*W = {xWstar:.5f}  (应等于 xW = {xW:.5f}；提馏段操作线过 (x*W, 0))")
    print(f"  提馏段液相 L' = RD + F = {Lprime:.2f} kmol/h")

    # ---- 2.5 理论塔板数 ----
    N, n_rect, n_strip, x_plates = mccabe_thiele(xD, xWstar, xF, spl_yx, spl_xy, R)
    N_trays = N - 1   # 最后一级为塔釜/直接蒸汽入口
    print("\n[2.5 理论塔板数（图解法）]")
    print(f"  理论级数(含塔釜) = {N}  (精馏段 {n_rect}, 提馏段 {n_strip})")
    print(f"  理论板数 N(不含塔釜) = {N_trays}")

    # ---- 2.6 实际塔板数（alpha 按每块板取几何平均）----
    def alpha_at(x):
        y = y_eq(x)
        return (y / x) / ((1.0 - y) / (1.0 - x))
    x_valid = [x for x in x_plates if 0.0 < x < 1.0]
    alpha = math.exp(sum(math.log(alpha_at(x)) for x in x_valid) / len(x_valid))
    T_top = t_eq(xD)
    T_bot = t_eq(xW)
    T_avg = (T_top + T_bot) / 2.0
    # 课件 4.2：以进料 xF 为基准，在全塔平均温度下线性加和
    mu_avg = mu_ethanol(T_avg) * xF + mu_water(T_avg) * (1.0 - xF)
    E = 0.49 * (alpha * mu_avg) ** (-0.245)
    E_sieve = E * 1.1
    # 课件 4.3：实际板数为两段分别取整后的和
    Ne_rect = math.ceil(n_rect / E_sieve)
    Ne_strip = math.ceil(n_strip / E_sieve)
    Ne = Ne_rect + Ne_strip
    print("\n[2.6 实际塔板数（O'Connell 效率）]")
    print(f"  塔顶温度 T顶 = {T_top:.2f} ℃   塔底温度 T底 = {T_bot:.2f} ℃")
    print(f"  平均相对挥发度 alpha = {alpha:.3f}   平均粘度 mu = {mu_avg:.3f} mPa·s")
    print(f"  全塔效率 E = {E:.4f}   筛板校正后 E' = {E_sieve:.4f}")
    print(f"  精馏段 {n_rect}/{E_sieve:.4f} = {n_rect/E_sieve:.2f} -> {Ne_rect} 块")
    print(f"  提馏段 {n_strip}/{E_sieve:.4f} = {n_strip/E_sieve:.2f} -> {Ne_strip} 块")
    print(f"  实际板 Ne = {Ne_rect} + {Ne_strip} = {Ne} 块")

    # ---- 2.7 塔径（精馏段用塔顶组成，提馏段按进料组成）----
    print("\n[2.7 塔径计算]")
    yF_eq = y_eq(xF)
    T_feed = t_eq(xF)
    results = {}
    # 提馏段压力取塔釜表压约 18 kPa（教材：酒精精馏塔塔釜表压 18到20 kPa）
    for name, x_liq, y_vap, T, P, HT, V_kmol, L_kmol in [
        ("精馏段", xD, xD, T_top, 101.3, PARAMS["HT"], D * (R + 1.0), R * D),
        ("提馏段", xF, yF_eq, T_feed, 101.3 + 18.0, PARAMS["HT2"], S, Lprime),
    ]:
        M_liq = MA * x_liq + MB * (1 - x_liq)
        M_gas = MA * y_vap + MB * (1 - y_vap)
        rhoG = P * M_gas / (8.314 * (T + 273.15))
        rhoL = rho_mix(x_liq, T)
        sig = sigma_mix(x_liq, T)
        Vg = V_kmol * M_gas / 3600.0 / rhoG
        Vl = L_kmol * M_liq / 3600.0 / rhoL
        FLV = (L_kmol * M_liq) / (V_kmol * M_gas) * math.sqrt(rhoG / rhoL)
        c20 = c20_smith(FLV, HT)
        C = c20 * (sig / 20.0) ** 0.2
        uF = C * math.sqrt((rhoL - rhoG) / rhoG)
        u = PARAMS["u_uF"] * uF
        An = Vg / u                       # 有效截面积
        AdA = 0.1                         # 弓形降液管 Ad/A 初估
        A = An / (1.0 - AdA)              # 塔总截面积
        Dcol = math.sqrt(4.0 * A / math.pi)
        results[name] = dict(T=T, P=P, HT=HT, rhoG=rhoG, rhoL=rhoL, sig=sig,
                             Vg=Vg, Vl=Vl, FLV=FLV, c20=c20, C=C, uF=uF, u=u,
                             Dcol=Dcol, M_liq=M_liq, M_gas=M_gas,
                             V_kmol=V_kmol, L_kmol=L_kmol)
        print(f"  [{name}] T={T:.1f}℃  rhoG={rhoG:.3f} rhoL={rhoL:.1f} sigma={sig:.2f}")
        print(f"     VG={Vg:.5f} m3/s  VL={Vl:.6f} m3/s  FLV={FLV:.4f}")
        print(f"     C20={c20:.4f}  C={C:.4f}  uF={uF:.3f}  u={u:.3f} m/s")
        print(f"     D = {Dcol:.3f} m  -> 圆整 {round_up_diameter(Dcol):.1f} m")

    # ---- 2.8 塔板结构设计（两段统一用精馏段塔径）----
    d_rect = round_up_diameter(results['精馏段']['Dcol'])
    d_strip = round_up_diameter(results['提馏段']['Dcol'])
    tray = tray_geometry(d_rect, PARAMS)
    print("\n[2.8 塔板结构设计]")
    print(f"  塔径 D = {d_rect:.1f} m（精馏段计算 {results['精馏段']['Dcol']:.3f}、提馏段 {results['提馏段']['Dcol']:.3f}，统一取精馏段）")
    print(f"  塔截面积 A = {tray['A']:.4f} m2")
    print(f"  堰长 lw = {PARAMS['lw_ratio']}D = {tray['lw']*1000:.0f} mm")
    print(f"  降液管：宽 Wd = {tray['Wd']*1000:.0f} mm  面积 Ad = {tray['Ad']:.4f} m2 (Ad/A={tray['AdA']:.4f})  底隙 hH = {PARAMS['hH']:.0f} mm")
    print(f"  鼓泡区 Aa = {tray['Aa']:.4f} m2  开孔率 phi = {tray['phi']:.4f}  开孔区 A0 = {tray['A0']:.4f} m2  孔数 n = {tray['n']}")
    print(f"  筛孔 d0 = {PARAMS['d0']:.0f} mm  孔距 t = {PARAMS['t']:.0f} mm（正三角）  板厚 tp = {PARAMS['tp']:.0f} mm")

    # ---- 2.9 流体力学验算（精馏段 / 提馏段各一套）----
    print("\n[2.9 流体力学验算]")
    hyd = {}
    for name in ("精馏段", "提馏段"):
        r = results[name]
        how, hw = weir_head(r['Vl'], tray['lw'], PARAMS)
        h = hydraulic_check(tray, r['Vl'], r['Vg'], r['rhoL'], r['rhoG'],
                            r['sig'], r['HT'], hw, how, PARAMS)
        h.update(how=how, hw=hw)
        hyd[name] = h
        print(f"  [{name}] HT={r['HT']*1000:.0f} mm")
        print(f"     how={how*1000:.1f} mm (>6 {ok(how>0.006)})   hw={hw*1000:.1f} mm   hL={(hw+how)*1000:.1f} mm")
        print(f"     孔速 u0={h['u0']:.2f} m/s   单板压降 dHt = h0({h['h0']*1000:.2f}) + he({h['he']*1000:.2f}) = {h['dHt']*1000:.2f} mm 液柱")
        print(f"     降液管 Hd={h['Hd']*1000:.2f} mm <= {h['Hd_lim']*1000:.2f} mm  {ok(h['Hd']<=h['Hd_lim'])}")
        print(f"     停留时间 tau={h['tau']:.2f} s (>3 {ok(h['tau']>3)})")
        print(f"     液沫夹带 eV={h['eV']:.4f} (<0.1 {ok(h['eV']<0.1)})")
        print(f"     漏液 u0min={h['u0min']:.2f} m/s  稳定系数 K={h['K']:.2f} (>1.5 {ok(h['K']>1.5)})")
    dP = (Ne_rect * hyd['精馏段']['dHt'] * results['精馏段']['rhoL']
          + Ne_strip * hyd['提馏段']['dHt'] * results['提馏段']['rhoL']) * 9.81 / 1000.0
    print(f"  全塔压降 = {Ne_rect}x{hyd['精馏段']['dHt']:.4f}m + {Ne_strip}x{hyd['提馏段']['dHt']:.4f}m 液柱 = {dP:.2f} kPa")

    # ---- 2.10 塔板负荷性能图（五条线，两段各一张）----
    print("\n[2.10 塔板负荷性能图]")
    lpf = {}
    for name in ("精馏段", "提馏段"):
        r, h = results[name], hyd[name]
        VL0 = r['Vl']
        lp = load_perf(tray, r['rhoL'], r['rhoG'], r['sig'], r['HT'],
                       h['hw'], h['Hd'], PARAMS,
                       [0.5 * VL0, VL0, 2.0 * VL0])
        lpf[name] = lp
        print(f"  [{name}] 液相下限 VL_min = {lp['VL_lo']*3600:.3f} m3/h (how=6mm)   液相上限 VL_max = {lp['VL_hi']*3600:.3f} m3/h (tau=3s)")
        print(f"     VL(m3/h)    漏液线       雾沫夹带线    液泛线     (气相 m3/h)")
        for VL, lk, en, fl in lp['pts']:
            print(f"     {VL*3600:8.3f}  {lk:10.1f}  {en:10.1f}  {fl:10.1f}")
        Vop = r['Vg'] * 3600.0
        leak_op = lp['pts'][1][1]
        ent_op, flood_op = lp['pts'][1][2], lp['pts'][1][3]
        up_op = min(ent_op, flood_op)          # 气相上限取夹带线与液泛线的较小者
        ctrl = "雾沫夹带" if ent_op <= flood_op else "液泛"
        print(f"     操作点 (VL={VL0*3600:.3f}, VV={Vop:.1f}) m3/h")
        print(f"     气相下限(漏液)={leak_op:.1f}  气相上限({ctrl})={up_op:.1f} m3/h")
        print(f"     操作弹性 = VV,上/VV,下 = {up_op/leak_op:.2f}   稳定系数 K = {h['K']:.2f} (>1.5 {ok(h['K']>1.5)})")

    # ---- 校核结论汇总 ----
    bad = []
    for name in ("精馏段", "提馏段"):
        h = hyd[name]
        if h['how'] <= 0.006:
            bad.append(f"{name}堰上液头<=6mm")
        if h['Hd'] > h['Hd_lim']:
            bad.append(f"{name}降液管液面超限")
        if h['tau'] <= 3.0:
            bad.append(f"{name}停留时间<3s")
        if h['eV'] >= 0.1:
            bad.append(f"{name}液沫夹带>=0.1")
        if h['K'] <= 1.5:
            bad.append(f"{name}稳定系数<=1.5")
    if dP > 30.0:
        bad.append(f"全塔压降{dP:.1f}kPa>30")
    print("\n  校核结论：" + ("全部合格" if not bad else "**不合格** -> " + "；".join(bad)))
    if bad:
        print("\n  建议调整（下列数值已按建议值试算验证）：")
        for tip in suggest_fix(tray, results, hyd, PARAMS,
                               ("精馏段", "提馏段"), Ne_rect, Ne_strip):
            print(f"    · {tip}")
        print("  （改好参数后重跑本脚本，确认结论变为「全部合格」再填进说明书）")

    # ---- 2.11 塔高 ----
    HT, HT2 = PARAMS["HT"], PARAMS["HT2"]
    n_hole = math.ceil(Ne / PARAMS["hole_every"])
    H_tray = (Ne_rect - 1) * HT + (Ne_strip - 1) * HT2
    H_hole = n_hole * PARAMS["hole_h"]
    HE = H_tray + H_hole
    Htot = HE + PARAMS["HD"] + PARAMS["HB"] + PARAMS["HS"]
    print("\n[2.11 塔高]")
    print(f"  精馏段 {Ne_rect} 块 @HT={HT*1000:.0f}mm, 提馏段 {Ne_strip} 块 @HT'={HT2*1000:.0f}mm")
    print(f"  塔板段高度 = {H_tray:.2f} m")
    print(f"  人孔 {n_hole} 个 x {PARAMS['hole_h']*1000:.0f}mm = {H_hole:.2f} m")
    print(f"  有效高度 HE = {H_tray:.2f} + {H_hole:.2f} = {HE:.2f} m")
    print(f"  塔顶 {PARAMS['HD']}m / 塔底 {PARAMS['HB']}m / 裙座 {PARAMS['HS']}m")
    print(f"  全塔高 H = {Htot:.2f} m")

    # ---- 2.12 附属设备（全凝器）----
    r_mix = aD * r_latent_ethanol(T_top) + (1 - aD) * r_latent_water(T_top)
    QT = D * (R + 1) * MD * r_mix
    t_in, t_out, Kc = PARAMS["t_cool_in"], PARAMS["t_cool_out"], PARAMS["K_cond"]
    mS_cool = QT / (4.18 * (t_out - t_in)) / 3600.0
    dtm = ((T_top - t_in) - (T_top - t_out)) / math.log((T_top - t_in) / (T_top - t_out))
    A_cond = QT * 1000.0 / 3600.0 / (Kc * dtm)
    print("\n[2.12 附属设备（全凝器）]")
    print(f"  塔顶蒸汽潜热 r = {r_mix:.1f} kJ/kg")
    print(f"  热负荷 QT = {QT:.0f} kJ/h = {QT/3600:.1f} kW")
    print(f"  冷却水量 mS = {mS_cool:.2f} kg/s ({t_in:.0f}->{t_out:.0f}℃)")
    print(f"  平均温差 dtm = {dtm:.1f} ℃   换热面积 A = {A_cond:.1f} m2 (K={Kc:.0f})")

    # ---- 2.13 接管管径（五种）----
    print("\n[2.13 接管管径]  d = sqrt(4V/(pi*u)) 圆整到 GB/T 8163 标准管")
    M_F = MA * xF + MB * (1 - xF)
    M_W = MA * xW + MB * (1 - xW)
    rhoF, rhoD, rhoW = rho_mix(xF, T_feed), rho_mix(xD, T_top), rho_mix(xW, T_bot)
    T_steam = 105.0                       # 塔釜绝压 119.3 kPa 下饱和蒸汽约 105 ℃
    rho_steam = (101.3 + 18.0) * 18.0 / (8.314 * (T_steam + 273.15))
    pipes = [
        ("进料管",       F * M_F / rhoF / 3600.0,                    PARAMS["u_liq"]),
        ("回流管",       R * D * MD / rhoD / 3600.0,                 PARAMS["u_liq_ret"]),
        ("塔顶蒸汽出口", D * (R + 1.0) * MD / results['精馏段']['rhoG'] / 3600.0, PARAMS["u_gas"]),
        ("塔底进气",     S * 18.0 / rho_steam / 3600.0,              PARAMS["u_gas"]),
        ("釜液排出",     W * M_W / rhoW / 3600.0,                    PARAMS["u_liq"]),
    ]
    nozzle_out = []
    for nm, Vv, u in pipes:
        d_req, od, wall, id_ = pipe_size(Vv, u)
        nozzle_out.append((nm, d_req, od, wall, id_))
        print(f"  {nm:12s} V={Vv*3600:9.3f} m3/h  u={u:.1f} m/s  计算内径 {d_req:6.1f} mm  ->  phi {od}x{wall} (内径 {id_:.0f} mm)")

    print("\n" + "=" * 66)
    print("关键结果汇总")
    print("=" * 66)
    print(f"  F={F:.2f}  D={D:.2f}  W={W:.2f}  S={S:.2f} kmol/h")
    print(f"  Rmin={Rmin:.2f} (ym={ym:.4f})  R={R:.2f}")
    print(f"  理论板 N={N_trays}(不含塔釜)={n_rect}+{n_strip}  实际板 Ne={Ne}(精馏段{Ne_rect}+提馏段{Ne_strip})")
    print(f"  塔径 D={d_rect:.1f} m (精馏段 {d_rect:.1f} / 提馏段 {d_strip:.1f}，统一取精馏段)")
    print(f"  全塔高 H={Htot:.2f} m (含人孔加高 {H_hole:.2f} m)")
    print(f"  塔板: lw={tray['lw']*1000:.0f}  Wd={tray['Wd']*1000:.0f} mm  Ad={tray['Ad']:.4f}  A0={tray['A0']:.4f} m2  n={tray['n']} 孔")
    print(f"  堰: how={hyd['精馏段']['how']*1000:.1f}  hw={hyd['精馏段']['hw']*1000:.1f}  hH={PARAMS['hH']:.0f} mm")
    print(f"  全塔压降 {dP:.2f} kPa   稳定系数: 精馏段 {hyd['精馏段']['K']:.2f} / 提馏段 {hyd['提馏段']['K']:.2f}")
    print("  接管: " + "  ".join(f"{nm} phi{od}x{wall}" for nm, _, od, wall, _ in nozzle_out))
    print("\n(注：3.3.8 平均密度、3.3.9 平均表面张力已含在 2.7 物性中；全凝器见 2.12；)")
    print(" 原料预热器、进料泵、回流泵需按负荷与扬程另行选型。)")

    # ---- 供 --advise 增量核算读取的指标快照 ----
    METRICS.clear()
    METRICS.update(
        xF=xF, xD=xD, xW=xW, F=F, D=D, W=W, S=S, R=R, Rmin=Rmin,
        N_trays=N_trays, n_rect=n_rect, n_strip=n_strip,
        Ne=Ne, Ne_rect=Ne_rect, Ne_strip=Ne_strip,
        d_rect=d_rect, d_strip=d_strip, Dcol_rect=results['精馏段']['Dcol'],
        Htot=Htot, H_tray=H_tray, H_hole=H_hole, n_hole=n_hole,
        dP=dP, QT=QT, A_cond=A_cond, mS_cool=mS_cool,
        K_rect=hyd['精馏段']['K'], K_strip=hyd['提馏段']['K'],
        eV_rect=hyd['精馏段']['eV'], eV_strip=hyd['提馏段']['eV'],
        tau_rect=hyd['精馏段']['tau'], tau_strip=hyd['提馏段']['tau'],
        dHt_rect=hyd['精馏段']['dHt'], dHt_strip=hyd['提馏段']['dHt'],
        how=hyd['精馏段']['how'], hw=hyd['精馏段']['hw'],
        lw=tray['lw'], Wd=tray['Wd'], Ad=tray['Ad'], A0=tray['A0'],
        n_holes=tray['n'], phi=tray['phi'], Aa=tray['Aa'],
        u0_rect=hyd['精馏段']['u0'], u0_strip=hyd['提馏段']['u0'],
        bad=list(bad), params=dict(PARAMS),
    )


# ---------------- 增量核算（--advise）----------------

# 可扫描的参数及其取值序列（用于反算“使整体合格”的范围）
SCAN_SPEC = [
    ("HT",        "精馏段板间距", "m",  [round(0.25 + 0.05 * i, 2) for i in range(13)]),
    ("HT2",       "提馏段板间距", "m",  [round(0.30 + 0.05 * i, 2) for i in range(13)]),
    ("lw_ratio",  "堰长比 lw/D",  "",   [round(0.50 + 0.05 * i, 2) for i in range(8)]),
    ("hL",        "板上清液层",   "mm", [float(v) for v in range(40, 85, 5)]),
    ("hH",        "降液管底隙",   "mm", [float(v) for v in range(20, 44, 2)]),
    ("d0",        "筛孔孔径",     "mm", [4.0, 5.0, 6.0, 8.0]),
    ("t",         "孔距",         "mm", [float(v) for v in range(12, 31)]),
    ("u_uF",      "空塔气速系数", "",   [round(0.55 + 0.05 * i, 2) for i in range(6)]),
    ("Wc",        "边缘区",       "mm", [25.0, 40.0, 50.0, 60.0, 75.0]),
    ("Ws",        "安定区",       "mm", [50.0, 60.0, 75.0, 100.0]),
    ("tp",        "板厚",         "mm", [3.0, 4.0]),
]


def query_metrics(xh, bh, overrides, reset=False):
    """进程内静默跑一次完整计算，返回指标字典（不打印报告）。

    reset=True 时先恢复出厂默认参数，再叠加 overrides —— 对比基准必须用这个模式，
    否则会拿到“已叠加使用者选择”的结果，对比全部显示为「不变」。
    """
    saved = dict(PARAMS)
    if reset:
        PARAMS.clear()
        PARAMS.update(DEFAULT_PARAMS)
    PARAMS.update(overrides)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            main(["--xuehao", str(xh), "--banhao", str(bh)])
        return dict(METRICS)
    finally:
        PARAMS.clear()
        PARAMS.update(saved)


def do_advise(xh, bh, overrides):
    """打印：当前选择的后果 + 后续参数的合理取值范围。"""
    base = query_metrics(xh, bh, {}, reset=True)
    cur = query_metrics(xh, bh, overrides, reset=True)
    if not cur:
        print("核算失败，请检查参数。")
        return

    print("=" * 66)
    print("增量核算：当前选择的影响 + 后续参数建议")
    print("=" * 66)
    if overrides:
        print("已改参数：" + "  ".join(f"{k}={v}" for k, v in overrides.items()))
    else:
        print("已改参数：（无，全部用推荐值）")
    print()

    def line(name, a, b, unit="", fmt="{:.2f}", note_hi_good=False):
        if a is None or b is None:
            return
        d = b - a
        if abs(d) < 1e-9:
            print(f"  {name:12s} {fmt.format(a)}{unit}   （不变）")
        else:
            pct = d / a * 100 if abs(a) > 1e-9 else 0.0
            arrow = "↑" if d > 0 else "↓"
            print(f"  {name:12s} {fmt.format(a)}{unit} → {fmt.format(b)}{unit}"
                  f"   （{arrow}{fmt.format(abs(d))}{unit}, {pct:+.1f}%）")

    print("【对整体设计的影响】")
    line("全塔高", base["Htot"], cur["Htot"], " m")
    line("塔板段高", base["H_tray"], cur["H_tray"], " m")
    line("精馏段塔径", base["Dcol_rect"], cur["Dcol_rect"], " m", "{:.3f}")
    line("圆整塔径", base["d_rect"], cur["d_rect"], " m", "{:.1f}")
    line("实际板数", base["Ne"], cur["Ne"], " 块", "{:.0f}")
    line("全塔压降", base["dP"], cur["dP"], " kPa")
    line("单板压降(精)", base["dHt_rect"] * 1000, cur["dHt_rect"] * 1000, " mm液柱", "{:.1f}")
    line("稳定系数(精)", base["K_rect"], cur["K_rect"], "", "{:.2f}")
    line("稳定系数(提)", base["K_strip"], cur["K_strip"], "", "{:.2f}")
    line("液沫夹带(精)", base["eV_rect"], cur["eV_rect"], "", "{:.4f}")
    line("停留时间(精)", base["tau_rect"], cur["tau_rect"], " s")
    line("堰上液头", base["how"] * 1000, cur["how"] * 1000, " mm", "{:.1f}")
    line("孔数", base["n_holes"], cur["n_holes"], " 个", "{:.0f}")
    line("开孔率", base["phi"], cur["phi"], "", "{:.4f}")
    line("全凝器面积", base["A_cond"], cur["A_cond"], " m²", "{:.1f}")
    if cur["bad"]:
        print(f"  ⚠ 校核结论：**不合格** -> {'；'.join(cur['bad'])}")
    else:
        print("  ✓ 校核结论：全部合格")
    print()

    print("【后续参数建议（基于当前已选参数推算）】")
    print("  下表“可行范围”指：其余参数保持现值时，该参数取范围内任一点都能通过全部校核。")
    print()
    for key, label, unit, values in SCAN_SPEC:
        cur_v = cur["params"][key]
        ok_vals = []
        for v in values:
            ov = dict(overrides)
            ov[key] = v
            m = query_metrics(xh, bh, ov, reset=True)
            if m and not m["bad"]:
                ok_vals.append(v)
        if ok_vals:
            lo, hi = min(ok_vals), max(ok_vals)
            mark = "✓" if (lo - 1e-9) <= cur_v <= (hi + 1e-9) else "⚠ 现值超出可行范围"
            rng = f"{lo:g} ~ {hi:g}" if abs(hi - lo) > 1e-9 else f"仅 {lo:g}"
            print(f"  {key:10s} {label:12s} 现值 {cur_v:g} {unit:4s}  可行 {rng} {unit}   {mark}")
        else:
            print(f"  {key:10s} {label:12s} 现值 {cur_v:g} {unit:4s}  可行范围：需同时调整其他参数")
    print()
    if cur["bad"]:
        print("⚠ 当前组合**不合格**：请使用者先调整上表中标「⚠ 现值超出可行范围」的参数"
              "（优先调本次刚定的那个），把它们带回可行范围内，再继续问下一组。")
        print("  上表里没标 ⚠ 的参数保持现值即可，不用动。")
    else:
        print("提示：把上面「可行范围」作为下一组参数的推荐区间告诉使用者；")
        if overrides:
            print("      并结合【对整体设计的影响】说明本次选择牵动了哪些指标、为什么。")


if __name__ == "__main__":
    if "--json" in sys.argv:                 # 静默跑一次，只吐指标
        with contextlib.redirect_stdout(io.StringIO()):
            main()
        sys.stdout.write(json.dumps(METRICS, ensure_ascii=False))
    else:
        main()

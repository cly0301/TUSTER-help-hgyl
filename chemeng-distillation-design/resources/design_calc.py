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
import csv, math, os, argparse, sys

CONFIG = {"xuehao": "01", "banhao": "445"}   # 学号后两位 / 班号后三位

MA, MB = 46.0, 18.0          # 乙醇 / 水 摩尔质量 kg/kmol
P0 = 101.3                    # 操作压力 kPa
PROD_TONS_DAY = 24.0          # 日产 24 吨

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

def round_up_01(x):
    return math.ceil(x * 10) / 10.0

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

# ---------------- 主计算 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xuehao", default=None, help="学号后两位")
    ap.add_argument("--banhao", default=None, help="班号后三位（给学号时可省略，自动按学号第4到6位拆）")
    ap.add_argument("--id", default=None, help="完整8位学号(如 23044401)")
    args = ap.parse_args()
    if args.id:
        s = str(args.id).zfill(8)
        args.xuehao = s[6:8]                 # 学号后两位 = 末两位
        if args.banhao is None:
            args.banhao = s[3:6]             # 只给学号时：班号后三位 = 第4到6位
    # 既给学号又给班号时用用户给的班号；都没给用默认值
    xh = args.xuehao if args.xuehao is not None else CONFIG["xuehao"]
    bh = args.banhao if args.banhao is not None else CONFIG["banhao"]

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

    # ---- 2.1 物料衡算 ----
    MD = MA * xD + MB * (1 - xD)
    D = (PROD_TONS_DAY * 1000 / 24) / MD
    F = D * (xD - xW) / (xF - xW)
    W = F - D
    print("\n[2.1 物料衡算]")
    print(f"  MD = {MD:.3f} kg/kmol")
    print(f"  塔顶 D = {D:.2f} kmol/h  (日产 24t => {D*MD:.0f} kg/h)")
    print(f"  进料 F = {F:.2f} kmol/h")
    print(f"  塔釜 W = {W:.2f} kmol/h")

    # ---- 2.3 最小回流比（切线法，样条）----
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
    ym = xD / (Rmin + 1.0)
    print("\n[2.3 最小回流比（切线法）]")
    print(f"  切点 (x,y) = ({x_tan:.4f}, {y_tan:.4f})")
    print(f"  切线截距 ym = {ym:.4f}   Rmin = {Rmin:.3f}")

    # ---- 2.4 操作回流比 ----
    R = R_factor * Rmin
    S = D * (R + 1.0)
    Wstar = W + S
    xWstar = W * xW / Wstar
    Lprime = R * D + F
    print("\n[2.4 操作回流比与直接蒸汽]")
    print(f"  回流比 R = {R_factor:.2f} x Rmin = {R:.3f}")
    print(f"  蒸汽量 S = {S:.2f} kmol/h   釜液总量 W* = {Wstar:.2f} kmol/h")
    print(f"  釜液浓度 x*W = {xWstar:.5f}  (提馏段操作线过 (x*W, 0))")
    print(f"  提馏段液相 L' = {Lprime:.2f} kmol/h")

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
    log_alpha_sum = sum(math.log(alpha_at(x)) for x in x_plates if x > 0 and x < 1)
    alpha = math.exp(log_alpha_sum / len(x_plates))
    T_top = t_eq(xD)
    T_bot = t_eq(xW)
    T_avg = (T_top + T_bot) / 2.0
    # 课件：以进料 xF 为基准，在全塔平均温度下按摩尔加和
    mu_avg = mu_ethanol(T_avg) * xF + mu_water(T_avg) * (1.0 - xF)
    E = 0.49 * (alpha * mu_avg) ** (-0.245)
    E_sieve = E * 1.1
    Ne = math.ceil(N_trays / E_sieve)
    print("\n[2.6 实际塔板数（O'Connell 效率）]")
    print(f"  塔顶温度 T顶 = {T_top:.2f} ℃   塔底温度 T底 = {T_bot:.2f} ℃")
    print(f"  平均相对挥发度 alpha = {alpha:.3f}   平均粘度 mu = {mu_avg:.3f} mPa·s")
    print(f"  全塔效率 E = {E:.4f}   筛板校正后 E' = {E_sieve:.4f}")
    print(f"  实际板 Ne = {N_trays}/{E_sieve:.4f} = {N_trays/E_sieve:.2f} -> {Ne} 块")

    # ---- 2.7 塔径（精馏段用塔顶组成，提馏段按进料组成）----
    print("\n[2.7 塔径计算]")
    yF_eq = y_eq(xF)
    T_feed = t_eq(xF)
    results = {}
    # 提馏段压力取塔釜表压约 18 kPa（教材：酒精精馏塔塔釜表压 18到20 kPa）
    for name, x_liq, y_vap, T, P, HT, V_kmol, L_kmol in [
        ("精馏段", xD, xD, T_top, 101.3, 0.35, D * (R + 1.0), R * D),
        ("提馏段", xF, yF_eq, T_feed, 101.3 + 18.0, 0.65, S, Lprime),
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
        u = 0.8 * uF
        An = Vg / u                       # 有效截面积
        AdA = 0.1                         # 弓形降液管 Ad/A 初估
        A = An / (1.0 - AdA)              # 塔总截面积
        Dcol = math.sqrt(4.0 * A / math.pi)
        results[name] = dict(T=T, rhoG=rhoG, rhoL=rhoL, sig=sig, Vg=Vg, Vl=Vl,
                             FLV=FLV, c20=c20, C=C, uF=uF, u=u, Dcol=Dcol)
        print(f"  [{name}] T={T:.1f}℃  rhoG={rhoG:.3f} rhoL={rhoL:.1f} sigma={sig:.2f}")
        print(f"     VG={Vg:.5f} m3/s  VL={Vl:.6f} m3/s  FLV={FLV:.4f}")
        print(f"     C20={c20:.4f}  C={C:.4f}  uF={uF:.3f}  u={u:.3f} m/s  (u/uF={u/uF:.2f}<=0.9)")
        print(f"     D = {Dcol:.3f} m  -> 圆整 {round_up_01(Dcol):.1f} m")

    # ---- 2.11 塔高 ----
    Ne_rect = max(1, round(Ne * n_rect / N))
    Ne_strip = Ne - Ne_rect
    HE = (Ne_rect - 1) * 0.35 + (Ne_strip - 1) * 0.65
    Htot = HE + 1.0 + 1.0 + 1.5
    print("\n[2.11 塔高]")
    print(f"  精馏段 {Ne_rect} 块 @HT=0.35m, 提馏段 {Ne_strip} 块 @HT=0.65m")
    print(f"  有效高度 HE = {HE:.2f} m   塔顶 1m / 塔底 1m / 裙座 1.5m")
    print(f"  全塔高 H = {Htot:.2f} m")

    # ---- 2.12 附属设备（全凝器）----
    r_mix = aD * r_latent_ethanol(T_top) + (1 - aD) * r_latent_water(T_top)
    QT = D * (R + 1) * MD * r_mix
    mS_cool = QT / (4.18 * (45 - 30)) / 3600.0
    dtm = ((T_top - 30) - (T_top - 45)) / math.log((T_top - 30) / (T_top - 45))
    A_cond = QT * 1000.0 / 3600.0 / (915.0 * dtm)
    print("\n[2.12 附属设备（全凝器）]")
    print(f"  塔顶蒸汽潜热 r = {r_mix:.1f} kJ/kg")
    print(f"  热负荷 QT = {QT:.0f} kJ/h = {QT/3600:.1f} kW")
    print(f"  冷却水量 mS = {mS_cool:.2f} kg/s (30->45℃)")
    print(f"  平均温差 dtm = {dtm:.1f} ℃   换热面积 A = {A_cond:.1f} m2 (K=915)")

    print("\n" + "=" * 66)
    print("关键结果汇总")
    print("=" * 66)
    print(f"  F={F:.2f}  D={D:.2f}  W={W:.2f}  S={S:.2f} kmol/h")
    print(f"  Rmin={Rmin:.2f}  R={R:.2f}  理论板 N={N_trays}(不含塔釜)  实际板 Ne={Ne}")
    d_rect = round_up_01(results['精馏段']['Dcol'])
    d_strip = round_up_01(results['提馏段']['Dcol'])
    print(f"  塔径: 精馏段 {d_rect:.1f} m / 提馏段 {d_strip:.1f} m (最终统一用精馏段塔径 {d_rect:.1f} m)")
    print(f"  全塔高 H={Htot:.2f} m")
    print("\n(注：塔板结构尺寸、流体力学验算、负荷性能图、管路管径详见 SKILL.md 第 2.8到2.10 节；)")
    print(" 脚本已覆盖核心链路，其余量可按 SKILL.md 公式扩展。)")

if __name__ == "__main__":
    main()

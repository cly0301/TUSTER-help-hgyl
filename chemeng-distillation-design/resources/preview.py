# -*- coding: utf-8 -*-
"""把 design_draw.py 生成的 DXF 渲染成 PNG，不用打开 AutoCAD 就能看图。

用法：
    python preview.py 装配图_23041127.dxf                  # 整图
    python preview.py 图.dxf --box 55 200 380 841          # 只看某个区域
    python preview.py 图.dxf --box 0 300 0 400 --px 1800   # 区域 + 指定像素宽
    python preview.py 图.dxf --tiles                       # 自动切成 2x2 四块

依赖 matplotlib；中文字体从系统字体目录自动加载（仿宋/黑体/宋体）。
"""

import argparse
import os
import sys


def _cjk_fonts():
    """动态找系统里的中文字体（Windows / Linux / macOS），不写死 C 盘路径。"""
    import glob
    from matplotlib import font_manager

    keywords = ("simhei", "simfang", "simsun", "msyh", "simkai",
                "notosanscjk", "sourcehansans", "wqy", "arphic", "uming", "ukai")
    dirs = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        os.path.expanduser("~/.fonts"),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/System/Library/Fonts",
        "/Library/Fonts",
    ]
    found = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for pat in ("**/*.ttf", "**/*.ttc", "**/*.otf"):
            for fp in glob.glob(os.path.join(d, pat), recursive=True):
                low = os.path.basename(fp).lower()
                if any(k in low for k in keywords):
                    found.append(fp)
    for fp in found[:6]:
        try:
            font_manager.fontManager.addfont(fp)
        except Exception:
            pass
    return found


def _setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    _cjk_fonts()
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "SimHei", "SimFang", "SimSun", "Microsoft YaHei", "Noto Sans CJK SC",
        "WenQuanYi Zen Hei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return matplotlib


def render(dxf_path, out_path, box=None, px=1600.0):
    """把 dxf_path 渲染成 out_path。box=(x0,x1,y0,y1) 指定区域，None 为整图。"""
    matplotlib = _setup_matplotlib()
    import matplotlib.pyplot as plt
    import ezdxf
    from ezdxf import bbox
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration, ColorPolicy

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    if box is None:
        ext = bbox.extents(msp)
        x0, x1 = ext.extmin.x, ext.extmax.x
        y0, y1 = ext.extmin.y, ext.extmax.y
    else:
        x0, x1, y0, y1 = box

    w, h = x1 - x0, y1 - y0
    fig = plt.figure(figsize=(px / 100.0, px * (h / w) / 100.0))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_aspect("equal")
    Frontend(RenderContext(doc), MatplotlibBackend(ax),
             config=Configuration(color_policy=ColorPolicy.BLACK)
             ).draw_layout(msp, finalize=True)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    # ezdxf 的 MatplotlibBackend 在 finalize 时会改写 figure 尺寸，
    # 这里重新按 px 设定，保证 --px 真正生效。
    fig.set_size_inches(px / 100.0, px * (h / w) / 100.0)
    fig.savefig(out_path, dpi=100, facecolor="white")
    plt.close(fig)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", help="要渲染的 DXF 文件")
    ap.add_argument("--out", default=None, help="输出 PNG（默认与 DXF 同名）")
    ap.add_argument("--box", nargs=4, type=float, default=None,
                    metavar=("X0", "X1", "Y0", "Y1"), help="只渲染这个区域")
    ap.add_argument("--px", type=float, default=1600.0, help="输出像素宽（默认 1600）")
    ap.add_argument("--tiles", action="store_true", help="自动切成 2x2 四块输出")
    args = ap.parse_args(argv)

    if not os.path.exists(args.dxf):
        print(f"找不到文件：{args.dxf}")
        sys.exit(1)
    stem = os.path.splitext(args.dxf)[0]

    if args.tiles:
        import ezdxf
        from ezdxf import bbox
        ext = bbox.extents(ezdxf.readfile(args.dxf).modelspace())
        x0, x1, y0, y1 = ext.extmin.x, ext.extmax.x, ext.extmin.y, ext.extmax.y
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        quads = [("左上", (x0, cx, cy, y1)), ("右上", (cx, x1, cy, y1)),
                 ("左下", (x0, cx, y0, cy)), ("右下", (cx, x1, y0, cy))]
        for name, b in quads:
            p = f"{stem}_{name}.png"
            render(args.dxf, p, box=b, px=args.px)
            print("已生成", p)
        return

    out = args.out or f"{stem}.png"
    render(args.dxf, out, box=tuple(args.box) if args.box else None, px=args.px)
    print("已生成", out)


if __name__ == "__main__":
    main()

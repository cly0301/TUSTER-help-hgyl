# 化工原理课程设计助手 · 使用说明（零基础版）

> 写给**完全没接触过编程**的同学。照着一步一步做就行，不用理解原理。

---

## 0. 这到底是干什么的？（30 秒看懂）

你有一份**化工原理课程设计**作业：设计一座「乙醇-水筛板精馏塔」。

这个 skill 干的事：**你告诉它学号，它帮你算出全部设计数据，并生成：**

- 一份完整的《设计说明书》（7 章，公式 + 数字都有）
- 3 张 CAD 图（装配图 / 塔板布置图 / 工艺流程图）
- 2 张附图（图解理论板图 / 塔板负荷性能图）

**你只需要：** 提供学号 → 回答几个参数选择 → 抄写说明书、打开图纸。

---

## 1. 先认几个词（看不懂的术语都在这）

| 词 | 是什么 | 你要不要管 |
|---|---|---|
| **Python** | 一个免费软件，用来运行计算脚本 | 要装（第 2.2 节） |
| **pip** | Python 自带的「装包工具」 | 用一下（第 2.4 节） |
| **DSH / DeepSeek Harness** | 你现在用的这个 AI 助手 | 已经装了 |
| **skill（技能包）** | 让 AI 学会干某件事的「说明书 + 工具」 | 要装（第 3 节） |
| **DXF** | AutoCAD 图纸文件格式 | 用 AutoCAD 打开 |
| **PNG** | 普通图片格式 | 双击就能看 |
| **命令行 / cmd / PowerShell** | 一个黑底白字的窗口，输入命令用 | 会用（第 5 节） |
| **依赖包** | Python 干活要用的「零件」 | 装 3 个（第 2.4 节） |

---

## 2. 你需要准备什么

**一句话：装 4 样东西，按顺序来。**

| # | 装什么 | 在哪一节 | 大概耗时 | 必须吗 |
|---|---|---|---|---|
| 1 | Windows 电脑 | 2.1 | — | 必须 |
| 2 | Python | 2.2 | 5 分钟 | 必须（算数要用） |
| 3 | DSH | 2.3 | 10 分钟 | 必须（聊天界面要用） |
| 4 | 依赖包（ezdxf 等） | 2.4 | 3 分钟 | 出图才要，只算数可跳过 |

> 已经装过的跳过对应小节即可。**顺序不要乱**：先装 Node.js 才能装 DSH，先装 Python 才能装依赖包。

### 2.1 一台 Windows 电脑

Windows 10 或 Windows 11 都行。

### 2.2 装 Python（如果还没装）

**检查是否已装：**

1. 按键盘 `Win + R`，弹出「运行」小窗。
2. 输入 `cmd`，回车，会弹出一个黑窗口。
3. 在黑窗口里输入：

   ```
   python --version
   ```

4. 按回车：
   - 显示 `Python 3.x.x` → **已装好，跳到 2.4 节**
   - 显示「不是内部或外部命令」→ **需要装，继续往下看**

**安装 Python：**

1. 打开浏览器，访问 **https://www.python.org/downloads/**
2. 点页面上的黄色按钮 **Download Python 3.x.x**
3. 下载完双击安装包
4. ⚠️ **最关键的一步**：安装界面最下方有一个勾选框
   **「Add Python 3.x to PATH」——必须打勾！**
   （漏了这一步，后面所有命令都会报「不是内部或外部命令」）
5. 点 **Install Now**，等待完成
6. 关掉所有黑窗口，重新按 `Win + R` → `cmd` → 输入 `python --version` 验证

### 2.3 装 DSH（DeepSeek Harness）

**先判断装没装：** 如果你现在正在用 DSH 的网页界面聊天，说明已经装好了，**跳过本节**。

**如果没装，按下面 4 步走：**

#### 第 1 步：装 Node.js

DSH 是跑在 Node.js 上的，所以得先装它。

1. 打开浏览器，访问 **https://nodejs.org/**
2. 点绿色的 **LTS** 按钮（长期支持版，最稳）
3. 下载后双击安装，一路点「Next / 下一步」，**全部默认选项**即可
   （Node.js 安装程序会自动把它加到 PATH，不用像 Python 那样手动勾）
4. **验证**：按 `Win + R` → 输入 `cmd` → 回车，在黑窗口里输入：

   ```
   node --version
   npm --version
   ```

   两个都显示版本号（例如 `v22.11.0`、`10.9.0`）就成功了。

#### 第 2 步：装 DSH

在同一个 cmd 窗口里输入：

```
npm install -g @deepseek-ai/dsh
```

> `-g` 表示「装到全局」，之后在任何文件夹都能直接用 `dsh` 命令。

安装过程会下载一会儿（几十 MB），看到 `added ... packages` 就是装完了。

**验证：**

```
dsh --version
```

显示版本号（例如 `0.1.0-rc.6`）就成功。

#### 第 3 步：启动 DSH

在 cmd 里输入：

```
dsh web
```

启动后，终端里会显示类似：

```
DeepSeek Harness Web UI: http://127.0.0.1:3080
```

把 **http://127.0.0.1:3080** 复制到浏览器地址栏打开，就进入 DSH 的聊天界面了。

> ⚠️ **这个黑窗口不能关！** 关了窗口服务就停了，网页会打不开。
> - 想换端口（3080 被占用时）：`dsh web --port 8080`
> - 想停止服务：在这个窗口按 `Ctrl + C`
> - 想再启动：重新 `dsh web` 一次即可

#### 第 4 步：首次配置（填模型密钥）

第一次打开 DSH 网页，会让你配置模型的 **API Key**。

1. 打开 **https://platform.deepseek.com/** 注册 / 登录
2. 左侧菜单点 **「API Keys」** → **「创建 API Key」**
3. 复制生成的密钥（`sk-` 开头的一长串）
4. 粘贴到 DSH 的配置页面里，保存

> 如果老师/学校给了统一的 key，直接用老师发的那串。
> 后续想改：在 DSH 网页右上角的设置里找「模型 / Model」相关配置。

---

**DSH 装好之后**，再回到第 3 节，把 skill 放进 DSH 的预设目录。

### 2.4 装依赖包（出图才需要）

> 只想要「计算数据」的话，这一节可以跳过。
> 想要「CAD 图 + 附图」就必须装。

**在 cmd 黑窗口里**，输入下面这一行，回车：

```
pip install -r requirements.txt
```

**如果提示找不到 requirements.txt**，说明你不在 skill 目录里。先按第 5.2 节进入目录再执行。

**如果上面这行报错**，就一个一个装（每次一行，回车等它跑完）：

```
pip install ezdxf
pip install matplotlib
pip install numpy
```

**看到什么算成功？** 最后出现 `Successfully installed ...` 就是成功。

| 脚本 | 需要哪些包 | 不装会怎样 |
|---|---|---|
| 算数（design_calc.py） | **啥也不用** | 任何 Python 都能跑 |
| 出 CAD 图（design_draw.py） | ezdxf | 报 `No module named 'ezdxf'` |
| 出附图（design_plot.py） | matplotlib、numpy | 报 `No module named 'matplotlib'` |
| DXF 转 PNG（preview.py） | ezdxf、matplotlib | 只能看 DXF 源文件 |
| **Origin 版负荷性能图**（design_origin.py） | **Origin 软件 + originpro 包** | 不装也能用，只是出不了 Origin 版 |

> ⚠️ `design_origin.py` 是**可选功能**，老师没要求用 Origin 就不用管它

---

## 3. 把 skill 装进 DSH

### 3.1 下载 skill

1. 打开浏览器，访问：
   **https://github.com/cly0301/TUSTER-help-hgyl**
2. 点绿色的 **Code** 按钮 → 选 **Download ZIP**
3. 下载完成后，右键压缩包 → **全部解压**
4. 解压后你会看到一个文件夹，名字类似 `TUSTER-help-hgyl-main`

### 3.2 找到「预设目录」

1. 按 `Win + R`，输入下面这行，回车：

   ```
   %USERPROFILE%\.dsh\.agent-presets
   ```

2. 这会打开一个文件夹。
   - **如果提示「找不到文件」**：说明 `.agent-presets` 文件夹还不存在，需要手动建：
     在文件资源管理器地址栏输入 `%USERPROFILE%\.dsh`，回车，右键 → 新建 → 文件夹，命名为 `.agent-presets`（注意前面有个点）。

### 3.3 放进 skills 文件夹

1. 在 `.agent-presets` 里，找到你的预设文件夹（比如 `chemeng`）。
   - 没有的话，就复制一个现成的预设文件夹改个名，或者直接新建一个。
2. 进入这个预设文件夹，找到 `skills` 文件夹（没有就新建）。
3. 把解压出来的 **`chemeng-distillation-design` 整个文件夹**，复制到 `skills` 里面。

### 3.4 检查目录结构

放好之后，路径应该长这样：

```
C:\Users\<你的用户名>\.dsh\.agent-presets\<你的预设名>\skills\chemeng-distillation-design\
    ├── SKILL.md
    ├── README.md
    ├── requirements.txt
    ├── 14429 设计说明书107.pdf
    ├── 设计说明书_23044401.md
    ├── assembly_23044401.dxf        ← 示例图（可删）
    ├── assembly_23044401.png
    ├── tray_23044401.dxf
    ├── tray_23044401.png
    ├── flow_23044401.dxf
    ├── flow_23044401.png
    ├── 理论板图_23044401.png
    ├── 负荷性能图_23044401.png
    ├── 负荷性能图_Origin_23044401.png     ← Origin 版示例（可删）
    ├── 负荷性能图_Origin_23044401.opju
    └── resources\
        ├── 模板原文_14429.txt              ← 默认底稿（7 章结构）
        ├── 模板原文_天津科技大学2023.txt    ← 官方版（老师要求时用）
        ├── 课件要点_设计方法与校验标准.md
        ├── design_calc.py
        ├── design_draw.py
        ├── design_plot.py
        ├── design_origin.py               ← Origin 版负荷性能图（可选）
        ├── preview.py
        └── ethanol-water-vle.csv
```

> ⚠️ **必须复制整个文件夹！**
> 只复制 `SKILL.md` 一个文件是不行的——计算脚本、模板、平衡数据都在 `resources\` 里，
> 少一个就跑不起来。

### 3.5 重启 DSH

关掉 DSH，重新打开。

---

## 4. 怎么用（在 DSH 里，最省事）

1. 打开 DSH，**新开一个会话**。
2. 在「预设」选择里，选 **「化工原理课设助手」**。
3. 在对话框里说：

   > 帮我做乙醇-水筛板精馏塔课程设计，学号 23044401

   （把学号换成你自己的）

4. 它会：
   - 自动拆出你的班号和学号
   - 一项一项问你「要自己选的参数」，每项都给**推荐值**和**可行范围**
   - 你**不确定就选推荐**，最稳妥
   - 每选一个，它会告诉你这个选择对塔径/塔高/压降的影响
5. 全部选完后，它给出：
   - 完整《设计说明书》
   - 装配图绘制指导
   - 生成图纸的命令

> **重要提醒**：如果它问的某个值你选了「不推荐」的，它会提醒你「这样会导致 XX 不合格」——
> 这是正常的，听它的改回推荐值就好。

---

## 5. 怎么用（不开 DSH，直接跑脚本）

### 5.1 打开黑窗口

按 `Win + R` → 输入 `cmd` → 回车。

### 5.2 进入 skill 目录

在黑窗口里输入（把路径换成你自己的）：

```
cd /d "C:\Users\你的用户名\.dsh\.agent-presets\你的预设名\skills\chemeng-distillation-design"
```

> 小技巧：输完 `cd /d ` 后，可以直接把文件夹从资源管理器**拖进黑窗口**，路径会自动填上。

### 5.3 计算（生成全部数据）

```
python resources\design_calc.py --id 23044401
```

把 `23044401` 换成你的学号。屏幕上会打印全部计算结果，**最后一行看「校核结论」**：
- `全部合格` → 可以往下走
- `不合格 -> ...` → 它会告诉你改哪个参数，照做再跑一次

### 5.4 出 CAD 图

```
python resources\design_draw.py --id 23044401
```

会在当前目录生成 3 个 DXF 文件（装配图/塔板布置图/工艺流程图）。

### 5.5 出附图

```
python resources\design_plot.py --id 23044401
```

会生成 2 个 PNG 文件（理论板图/负荷性能图）。

### 5.6 把 DXF 转成图片看（不想开 AutoCAD 时）

```
python resources\preview.py assembly_23044401.dxf
```

会生成同名的 PNG，双击就能看。

想要更清晰的图，加 `--px 2400`：

```
python resources\preview.py assembly_23044401.dxf --px 2400
```

### 5.7 Origin 版负荷性能图（可选）

老师要求用 Origin 出图时才需要，**平时不用管**：

```
python resources\design_origin.py --id 23044401
```

会生成 `负荷性能图_精馏段_<学号>.png`、`负荷性能图_提馏段_<学号>.png` 和一个 `.opju` Origin 工程文件。

> 前提：电脑装了 Origin，且 Python 装了 `originpro` 包
> 教育版 Origin 同时只能开 10 张表，脚本已按「每段 1 张表」设计

---

## 6. 三种学号输入方式（任选一种）

| 情况 | 命令 |
|---|---|
| 只知学号 | `python resources\design_calc.py --id 23044401` |
| 学号 + 班号 | `python resources\design_calc.py --id 23044401 --banhao 445` |
| 直接给后两位/后三位 | `python resources\design_calc.py --xuehao 01 --banhao 445` |

**学号怎么拆？** 一般 8 位：`23044401` = 前3位 `230` + 班号 `444` + 学号 `01`。
如果你们学校班号规则不一样，用 `--banhao` 单独填。

---

## 7. 你会得到什么

| 产物 | 文件 | 用途 |
|---|---|---|
| 设计说明书 | `设计说明书_<学号>.md` | 照着抄到作业本（手写） |
| 塔设备装配图 | `assembly_<学号>.dxf` | A1 图纸，AutoCAD 打印（43 项明细 / 11 个管口 / 6 个详图） |
| 塔板平面布置图 | `tray_<学号>.dxf` | A3 图纸 |
| 工艺流程图 | `flow_<学号>.dxf` | A2 图纸（7 台设备 + 设备一览表） |
| 图解理论板图 | `理论板图_<学号>.png` | 贴进说明书 |
| 塔板负荷性能图 | `负荷性能图_<学号>.png` | 贴进说明书 |
| **Origin 版负荷性能图**（可选） | `负荷性能图_Origin_<学号>.png` + `.opju` | 老师要求 Origin 时用 |

---

## 8. 安装后自检（强烈建议做一次）

在 skill 目录里依次跑这三条，**都成功就说明环境没问题**：

```
python resources\design_calc.py --id 23044401
python resources\design_draw.py --id 23044401
python resources\design_plot.py --id 23044401
```

**预期看到：**

| 命令 | 成功的标志 |
|---|---|
| 第 1 条 | 末尾出现 **「校核结论：全部合格」** |
| 第 2 条 | 出现 **「共 3 张。塔径 1.0 m、实际板 43 块、全塔高 24.9 m」** |
| 第 3 条 | 出现 **「理论级数 26（精23+提3，含塔釜）」** |

如果第 2、3 条报 `No module named ...`，说明依赖没装，回第 2.4 节。

---

## 9. 常见报错对照表

| 报错信息 | 原因 | 怎么解决 |
|---|---|---|
| `'python' 不是内部或外部命令` | Python 没装，或装的时候没勾 PATH | 重装 Python，**务必勾选 Add to PATH** |
| `No module named 'ezdxf'` | 没装 ezdxf | `pip install ezdxf` |
| `No module named 'matplotlib'` | 没装 matplotlib | `pip install matplotlib` |
| `No module named 'numpy'` | 没装 numpy | `pip install numpy` |
| `FileNotFoundError: ethanol-water-vle.csv` | 不在 skill 目录里 | 先 `cd /d` 到 skill 目录 |
| `PermissionError: ... .dxf` | 这个 DXF 正被 AutoCAD 打开 | **关掉 AutoCAD 里打开的文件**，再重跑 |
| `校核结论：不合格` | 参数组合不达标 | 看它下面给的「建议调整」，改参数重跑 |
| 终端里中文是乱码 | 编码问题 | 在命令前加 `chcp 65001` 或忽略（不影响文件内容） |

---

## 10. 常见问题

**Q1：我只复制 `SKILL.md` 到 skills 目录行不行？**
不行。`SKILL.md` 只是「说明书」，真正算数的是 `resources\design_calc.py`，还有模板、平衡数据在 `resources\` 里。必须整个文件夹一起复制。

**Q2：它问的参数我不会选怎么办？**
一律选「推荐」。推荐值都是教材标准值，最稳妥。

**Q3：理论板数和同学不一样？**
图解法数理论板本身有 ±1~2 块的读图误差，正常。以你自己画的图为准。

**Q4：装好之后还要联网吗？**
不用。所有文件都在本地，算数和出图都不联网。

**Q5：说明书能直接抄吗？**
**不能照抄。** 说明书必须**手写**；文字部分参照模板的表达方式，计算过程和数字按你的学号重新算出（不能抄别人的数）。

**Q6：我能改图纸里的东西吗？**
可以。DXF 用 AutoCAD 打开后随便改。生成的图只是「初稿」，你可以调字体、挪位置、加标注。

**Q7：换学号要重新装吗？**
不用。只改命令里的 `--id 学号` 就行，所有数值自动重算。

**Q8：生成的文件在哪？**
在你运行命令的**当前目录**（就是你 `cd` 进去的那个目录）。想指定输出目录，加 `--out D:\某文件夹`。

---

## 11. 目录里都有什么

| 文件 | 作用 | 能不能删 |
|---|---|---|
| `SKILL.md` | 给 AI 看的「操作手册」 | ❌ 不能删 |
| `README.md` | 就是本说明 | 可以（但建议留着） |
| `requirements.txt` | 依赖包清单 | ❌ 不能删（装依赖要用） |
| `14429 设计说明书107.pdf` | 说明书模板原件 | ❌ 不能删 |
| `设计说明书_23044401.md` | 示例说明书 | 建议留着 |
| `resources\模板原文_14429.txt` | 模板纯文字版（**默认底稿**，7 章结构） | ❌ 不能删 |
| `resources\模板原文_天津科技大学2023.txt` | 官方 2023 版模板全文（老师要求时用） | 建议留着 |
| `resources\课件要点_设计方法与校验标准.md` | 老师课件的方法与标准 | ❌ 不能删 |
| `resources\design_calc.py` | 计算脚本（核心） | ❌ 不能删 |
| `resources\design_draw.py` | 出 CAD 图脚本 | ❌ 不能删 |
| `resources\design_plot.py` | 出附图脚本 | ❌ 不能删 |
| `resources\design_origin.py` | Origin 版负荷性能图 | 可以删（不用 Origin 就删） |
| `resources\preview.py` | DXF 转 PNG | 可以删（不影响出图） |
| `resources\ethanol-water-vle.csv` | 乙醇-水气液平衡数据 | ❌ 不能删 |
| `assembly_*.dxf/png` 等 | 示例成品图 | 可以删 |

---

## 12. 安全提醒

- 这个 skill 是**帮你算、帮你理清步骤**的工具，**不是替你考试**。
- 说明书必须**手写**；论述文字参照模板的表达方式，计算过程和数值必须按你自己的学号重新算。
- 直接抄别人的数值，属于学术不端。

---

## 13. 还搞不定？

把**完整报错信息**（红字那几行）+ 你执行的命令 一起发给我，我帮你定位。

# 给 AI 的安装说明（用户只需把仓库地址发给你）

> 这份文件写给「收到安装请求」的 DSH agent。
> 用户说「帮我把 https://github.com/cly0301/TUSTER-help-hgyl 装上」时，你照着下面做完即可。
> 全程 3~5 分钟，不需要用户懂任何命令。

## 0. 先判断 DSH 版本

```powershell
(Get-Item "$env:LOCALAPPDATA\Programs\DeepSeek Harness\DeepSeek Harness.exe" -ErrorAction SilentlyContinue).VersionInfo.FileVersion
```

| 版本 | 做法 |
|---|---|
| **0.2.x 及以上** | 做第 1 步 + 第 2 步（两者都要） |
| **0.1.x** | 只做第 1 步（旧版会自动扫描 `~/.dsh/.agent-presets`，跳过第 2 步） |

## 1. 装 skill 到全局 skill 根

```powershell
$repo = "$env:TEMP\chemeng-repo"
if (Test-Path $repo) { Remove-Item -Recurse -Force $repo }

git clone --depth 1 https://github.com/cly0301/TUSTER-help-hgyl.git $repo

New-Item -ItemType Directory -Force "$env:USERPROFILE\.dsh\skills" | Out-Null
$dst = "$env:USERPROFILE\.dsh\skills\chemeng-distillation-design"
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse -Force "$repo\chemeng-distillation-design" $dst
Remove-Item -Recurse -Force "$dst\tmp_out","$dst\resources\__pycache__" -ErrorAction SilentlyContinue
```

**没有 git 时**改用下载 ZIP：

```powershell
$zip = "$env:TEMP\chemeng.zip"
Invoke-WebRequest "https://github.com/cly0301/TUSTER-help-hgyl/archive/refs/heads/main.zip" -OutFile $zip
Expand-Archive $zip "$env:TEMP\chemeng-unzip" -Force
$src = "$env:TEMP\chemeng-unzip\TUSTER-help-hgyl-main\chemeng-distillation-design"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.dsh\skills" | Out-Null
Copy-Item -Recurse -Force $src "$env:USERPROFILE\.dsh\skills\"
```

装完 skill 后，**新会话的 skill 列表里就会出现 `chemeng-distillation-design`**。

## 2. 装预设「化工原理课设助手」（仅 0.2.x 需要）

先把预设包放到固定位置：

```powershell
$dst = "$env:USERPROFILE\.dsh\chemeng-preset"
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse -Force "$env:TEMP\chemeng-repo\chemeng-preset" $dst
```

然后**必须用 `plugin_manager` 工具**（不要用 shell 改 profile 的 package.json —— 那是它的职责）：

```
plugin_manager(action="install_bundle", target="C:\\Users\\<用户名>\\.dsh\\chemeng-preset")
```

（`<用户名>` 换成实际值；返回 `"application": "applied"` 即成功。）

装完让用户**刷新页面（F5）**，预设选择器里就会出现「化工原理课设助手」。

## 3. 验证

```powershell
cd "$env:USERPROFILE\.dsh\skills\chemeng-distillation-design"
python resources\design_calc.py --id 23044401
```

看到 `校核结论：全部合格` 就说明装好了。

## 4. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 预设卡片显示「加载失败」 | 预设 patch 里有 0.2.x 不认的字段 | 让用户把报错发来，按提示改 `chemeng-preset/cordis.patch.yml` |
| 预设不出现 | 没刷新 / 没装预设包 | 刷新页面；确认第 2 步 `install_bundle` 返回 applied |
| 计算脚本报 `No module named 'ezdxf'` | 缺 Python 依赖 | `pip install ezdxf matplotlib numpy` |
| 负荷性能图出不来 | 缺 Origin | 让用户按 README 2.5 节免费申请学习版 |

## 5. 装完之后

告诉用户：

> 装好了。新开一个会话，预设选「化工原理课设助手」，直接说「帮我做乙醇-水筛板精馏塔课设，学号 XXXXXXXXX」就行。
> 就算不用预设，在任意会话里说同样的话也能触发（skill 已全局可用）。

---

## 附：预设包结构（供排查）

```
chemeng-preset/
├── package.json          # { dsh.bundle.patch: "./cordis.patch.yml" }
└── cordis.patch.yml      # insert 一条 @deepseek-ai/dsh-agent-preset 行
```

`cordis.patch.yml` 的关键结构：

```yaml
- insert:
    - id: preset-chemeng
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: chemeng
        name: 化工原理课设助手
        description: ...
        order: 10
        plugins:
          - id: persona
            name: '@deepseek-ai/dsh-persona'
            config:
              prefix: |-        # ← 0.2.x 用 prefix（旧版是 text）
                ...{{model}}...  # ← 只支持 {{provider}} {{model}}，不要用 {{cwd}}
          ...
```

**0.2.x 踩过的坑（改预设时注意）：**

1. `persona` 配置字段是 **`prefix`**，不是旧版的 `text`
2. persona 变量只注册了 **`provider`、`model`**，`{{cwd}}` 会报 unknown prompt variable
3. `@deepseek-ai/dsh-tool-subagent-control/list-agents` 子路径在 0.2.x 已没有，别引用
4. `workflow-worker-thread` / `tool-workflow` / `tool-ralph` 在 0.2.x 主体包里不存在，别引用

# BranchCheck 分支剧情逻辑检查器

BranchCheck 1.2 检查互动剧情中“真的能走到哪里”。它把节点位置与全部布尔变量组成状态，使用 BFS 搜索，生成可重放的最短路径证据，并把诊断关联到源 JSON Pointer、具体状态下的条件解释和变量写入线索。

运行时仅使用 Python 标准库，无需 API Key、网络服务或图形界面。支持严格的自定义 JSON，以及一个只读、单文件的 Ren'Py 有限语法导入器。可以发现不可达节点/结局、死路、矛盾条件、始终不可用的选择、断言失败及没有结束路线的状态。

Ren'Py 导入只覆盖顶层布尔 `default`、全局 label、布尔赋值、结构化条件与菜单、静态 jump、无参 return、pass 和普通单行叙述。它不执行输入脚本，不加载 Ren'Py SDK，不模拟其他文件、Python、存档、回滚或显示系统。BranchCheck 仍不支持 Ink/Twine、数值状态、概率、时间、剧情编辑、自动修改剧情或文笔评价。剧情 `schema_version` 仍为 1，报告 `report_version` 仍为 2。

## 安装与最短运行

需要 **Python 3.11 或更高版本**。从 [GitHub 仓库](https://github.com/Inquifur/branchcheck) 下载 ZIP 并解压后，打开 PowerShell，进入包含 `pyproject.toml` 的项目目录。也可使用 Git 克隆仓库后进入该目录。首次安装需要访问包源。

```powershell
# 使用已安装的 Python 3.11+；以下以 3.12 为例
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m branchcheck check examples/minimal_ok.json
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples/renpy/minimal_ok.rpy
```

无需激活环境。Linux/macOS 使用 `python3 -m venv .venv`，将后续命令中的 `.\.venv\Scripts\python.exe` 替换为 `.venv/bin/python`，并先确认 Python 版本为 3.11+。本次实际验证环境为 Windows / Python 3.12.14；其他平台和版本由 CI 矩阵检验。

安装后，分析和报告生成均可离线运行。上面两个检查都返回 0；Ren'Py 最小样例有 2 条 warning，返回 0 不代表没有 warning。

## 一个定位与修复例子

`examples/case_study/fault_wrong_exit_condition.json` 将档案室出口条件误写成“没有通行证”：玩家持证进入后出不来。生成 HTML 报告：

```powershell
.\.venv\Scripts\python.exe -m branchcheck check examples/case_study/fault_wrong_exit_condition.json --format html --output reports/demo/broken.html
# 预设故障返回 1，报告仍然生成；这不是安装失败
Start-Process reports/demo/broken.html
.\.venv\Scripts\python.exe -m branchcheck check examples/case_study/investigation_ok.json
```

报告中的 `DEAD_END` 定位到 `archive_room`，路径证据显示 `has_archive_pass=true`，而唯一出口要求 false。对照基准，将 `/nodes/3/choices/0/condition/eq` 恢复为 true 后，基准检查返回 0：229 个状态、357 条转移、0 error、0 warning。完整步骤见 [两分钟演示](docs/demo.md)。

HTML 是可直接双击打开的离线单文件，输出目录会自动创建。报告中的建议需要作者核对，不会自动修改剧情。

## 从 Ren'Py 片段开始

直接导入并检查，不需要先生成 JSON：

```powershell
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\minimal_ok.rpy
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\menu_fallback.rpy --format html --output reports\v1.2\menu_fallback.html
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\nested_flow.rpy --format json --output reports\v1.2\nested_flow.json
```

需要查看或复用编译模型时使用：

```powershell
.\.venv\Scripts\python.exe -m branchcheck import-renpy examples\renpy\minimal_ok.rpy --output reports\v1.2\minimal.json
.\.venv\Scripts\python.exe -m branchcheck check reports\v1.2\minimal.json
```

成功导出会同时生成 `reports/v1.2/minimal.sources.json`。模型文件仍是严格的 `schema_version=1`，可以交给旧 `check` 命令；sidecar 单独保存源 SHA-256、相对文件名、行范围、label、语句类型、编译 ID/Pointer 和原始/自动标记。普通 `check` 不会自动读取 sidecar，避免误用过期映射；需要源行号时使用 `check-renpy`。

导入器会验证整份 `.rpy`，包括不可达 label。不支持的 Python 块、call、动态 jump、数值状态、带说话者 say、screen/资源语句或非法缩进会按源行拒绝，不会跳过后给出通过。完整合同见 [Ren'Py 有限语法](docs/renpy-subset.md)，编译与来源映射见 [导入器设计](docs/renpy-import-design.md)。

`examples/renpy/` 是 adapted 合同样例。本仓库在 V1.2 开发前没有真实 `.rpy` 原文，因此这些结果不代表真实 Ren'Py 工程已经接入或通过。

## JSON 输入与报告

以下两节点剧情是合法输入；完整的带显式断言案例在 `examples/minimal_ok.json`：

```json
{
  "schema_version": 1,
  "title": "找到钥匙",
  "start": "door",
  "variables": {"has_key": false},
  "nodes": [
    {"id": "door", "title": "门前", "choices": [
      {"id": "pick_key", "text": "拿起钥匙并开门", "target": "end",
       "effects": {"has_key": true}}
    ]},
    {"id": "end", "title": "离开", "ending": true}
  ]
}
```

```powershell
.\.venv\Scripts\python.exe -m branchcheck check examples\mystery_broken.json
.\.venv\Scripts\python.exe -m branchcheck check examples\mystery_broken.json --format json --output reports\mystery.json
.\.venv\Scripts\python.exe -m branchcheck check examples\mystery_broken.json --format html --output reports\mystery.html
.\.venv\Scripts\python.exe -m branchcheck check examples\mystery_fixed.json
.\.venv\Scripts\python.exe -m branchcheck check examples\state_cycle_ok.json --max-states 1000 --max-transitions 5000
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\investigation_ok.json --format html --output reports\v1.1\investigation_ok.html
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\fault_wrong_exit_condition.json --format html --output reports\v1.1\fault_wrong_exit_condition.html
```

双击 `reports/mystery.html` 或用浏览器打开它即可，单文件离线可读，不启动服务器。展开 `ASSERTION_FAILED` 可查看到达“出示照片”时的变量快照，展开 `DEAD_END` 可查看读取 SD 卡后证据被消耗的路径。JSON 输出可供程序读取；未指定 `--output` 时报告写到标准输出，指定后自动创建父目录并将简短状态写到标准错误。

预设错误示例是 `confront.photo_required`：玩家从门厅选择 `rush` 到达“出示照片”，当时 `has_photo=false`，违反保留在剧情中的照片断言。工具给出真实经过的选择，而不是根据节点连线猜测路径。

报告会继续回答四个问题：发生了什么、证据是什么、源在哪里、下一步应人工核对什么。JSON 输入显示 Pointer；`check-renpy` 在保留编译 Pointer 的同时显示 `.rpy` 相对文件名、label、行范围和原语句。条件树显示每个 `all` / `any` / `not` 子项在该代表路径终点的实际结果。变量赋值位置是静态排查线索，只有标记为“实际搜索已触发”的选择才属于执行证据。

`examples/case_study/` 提供一段 19 节点、8 变量的 **adapted（改编试用）** 调查剧情和三份独立故障。它没有接入真实 Ren’Py 工程；来源映射、简化假设和修复对照见 [调查剧情案例](docs/case-study.md)。

## 结果与退出码

| 退出码 | 含义 |
|---|---|
| 0 | 导入成功；或完整分析且无 error（只有 warning 也返回 0） |
| 1 | 完整分析且发现剧情 error |
| 2 | JSON/Ren'Py 输入、参数、读取文件或写输出失败；导入失败不运行分析 |
| 3 | 达到分析上限而未完成，即使已经发现 error |

整体状态依次优先采用 `invalid`、`incomplete`、`failed`、`warning`、`passed`。默认最多发现 50000 个不同状态、记录 200000 条有效转移；`check` 与 `check-renpy` 都可用 `--max-states` / `--max-transitions` 调整。未完成时不会把未发现内容判成不可达，也不会显示通过。

“完整通过”仅表示在这个布尔模型和已声明规则下未发现所检查的问题，不保证故事质量，也不保证玩家的每一种选择最终结束。超过 12 个不同变量的条件局部矛盾检查会标记 `skipped`，不猜测结果。

## 项目导航

- `src/branchcheck/`：独立输入校验、条件求值、状态分析、报告渲染和 CLI。
- `examples/`：最小正常案例、12 节点悬疑错误/修正对照、合法钥匙循环。
- `examples/renpy/`：V1.2 有限语法、控制流和拒绝行为的 adapted `.rpy` 样例及手写参考模型。
- `examples/case_study/`：V1.1 adapted 调查案例、基准和三份单点故障。
- `tests/`：核心语义、搜索边界、路径重放、输入校验和报告/退出码测试。
- [剧情格式与报告字段](docs/story-format.md)：完整输入规范和诊断代码。
- [如何阅读诊断](docs/diagnostics.md)：源 Pointer、条件解释、路径证据和变量线索的边界。
- [调查剧情案例](docs/case-study.md)：来源说明、两种调查顺序和三份独立故障。
- [算法与边界](docs/algorithm.md)：状态编码、搜索、反向可达和复杂度。
- [Ren'Py 有限语法](docs/renpy-subset.md)：支持/拒绝列表、控制流合同和单文件边界。
- [Ren'Py 导入器设计](docs/renpy-import-design.md)：AST、CFG、来源 sidecar 和作者视图投影。
- [两分钟演示](docs/demo.md)：命令、实际结果与修复对照。
- [交付验收记录](docs/verification.md)：测试覆盖、实际结果和未验证项。
- [V1.1 验收记录](docs/verification-v1.1.md)：兼容性基线、案例结果、HTML 产物和已知限制。
- [V1.2 验收记录](docs/verification-v1.2.md)：导入语义、独立等价性、CLI 产物和真实接入状态。
- `.github/workflows/tests.yml`：Linux/Windows、Python 3.11/3.13 测试矩阵配置。只有当前机器实际运行的环境会在演示记录中列为已验证；CI 配置本身不代表云端已通过。

## 开发与后续方向

运行全部测试：`.\.venv\Scripts\python.exe -m pytest`。本次本地验证为 279 项通过，见 [上传前验证](docs/github-upload.md)。CI 配置包含 Windows/Linux × Python 3.11/3.13；实际云端结果请在仓库 Actions 中查看。

已实现：布尔状态搜索、显式断言、路径证据、三种报告和单文件 Ren'Py 子集。未来可评估多文件真实工程接入与更丰富的变量类型；这些尚未实现。工具不会从对白自行理解规则，也不证明完整游戏正确。

运行时没有第三方依赖。构建使用 setuptools，测试使用 pytest；它们各自保留原有许可。本项目采用 [MIT 许可证](LICENSE)，版权署名为 Inquifur。

# BranchCheck V1.1 验收记录

验收日期：2026-11-03。当前项目不是 Git 工作树，因此本轮通过测试、固定样例基线、文件清单和实际报告结果控制改动范围，不能提供 Git diff 或提交记录。

## 环境与实际命令

- Windows 11，项目根目录。
- 项目 `.venv`：Python 3.12.14。
- 包版本：1.1.0。
- 剧情 `schema_version`：仍为 1。
- 输出 `report_version`：2。

完整测试实际执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .codex-pytest-temp\root-full-final-1
```

结果：`196 passed in 0.51s`，进程退出码 0。使用仓库内 `--basetemp` 是为了避开系统临时目录在 pytest 清理阶段出现的 Windows 权限错误；测试本身没有失败或警告。

## V1 兼容性基线

四个原样例均通过 CLI 重新分析。新增字段没有改变搜索计数、原诊断 code/相关 ID/受影响状态数或退出码。

| 样例 | 完整 | 状态 | 发现状态 | 转移 | error/warning | 退出码 |
|---|---:|---|---:|---:|---:|---:|
| `examples/minimal_ok.json` | 是 | `passed` | 4 | 3 | 0/0 | 0 |
| `examples/mystery_broken.json` | 是 | `failed` | 36 | 52 | 2/7 | 1 |
| `examples/mystery_fixed.json` | 是 | `passed` | 68 | 115 | 0/0 | 0 |
| `examples/state_cycle_ok.json` | 是 | `passed` | 5 | 5 | 0/0 | 0 |

`mystery_broken.json` 的聚合诊断仍为：

- `ASSERTION_FAILED`：`confront.photo_required`，4 个状态。
- `DEAD_END`：`spent_card`，2 个状态。
- `UNREACHABLE_NODE`：`photo_room`。
- `UNREACHABLE_ENDING`：`hidden_end`。
- `CONTRADICTORY_CONDITION`：`foyer.impossible`。
- 四条 `NEVER_ENABLED_CHOICE`：`permit_desk.issue`、`lab_entry.enter`、`confront.secret`、`spent_card.submit`，受影响状态数分别为 4、4、4、2。

回归由 `tests/test_v1_compatibility.py` 锁定，不以报告文字逐字快照代替语义检查。

## V1.1 新增行为验证

测试覆盖：

- RFC 6901 Pointer 构造及 `~`、`/` token 转义；节点、选择、断言使用原数组索引。
- `all`、`any`、`not`、常量和嵌套条件解释与原求值器一致。
- 聚合诊断的每条代表路径使用自己的终点快照。
- 不可达诊断没有路径或到达快照，只保留结构入边线索。
- 变量初始 true、无显式写入、写回 false、可达源节点上的未触发选择，以及不完整分析中的 unknown。
- 矛盾条件的全赋值局部证明和超过上限的 `skipped`。
- HTML 稳定锚点、目录链接、Pointer、条件树、变量线索、转义、无脚本和无外部资源。
- JSON stdout 仍为纯 JSON，文本/JSON/HTML 渲染不修改报告，CLI 退出码 0/1/2/3 保持不变。

## Adapted 调查案例

仓库内没有可访问的真实 Ren’Py 剧情原文，因此本轮使用 `examples/case_study/` 中的 **adapted（改编试用）**“笔记失窃与实验室调查”。它包含 19 个节点、8 个布尔变量、两种调查顺序、返回大厅后解锁的新选项、条件证人对话和 3 个结局。详细来源与假设见 `docs/case-study.md`。

| 文件 | 状态 | 状态/转移 | error/warning | 主要结果 | 退出码 |
|---|---|---:|---:|---|---:|
| `investigation_ok.json` | `passed` | 229/357 | 0/0 | 基准无意外诊断 | 0 |
| `fault_missing_photo_effect.json` | `failed` | 229/357 | 1/0 | `photo_briefing.photo_must_exist` 断言失败，1 个状态 | 1 |
| `fault_wrong_exit_condition.json` | `failed` | 109/165 | 1/10 | `archive_room` 死路，5 个状态；后续内容产生伴随 warning | 1 |
| `fault_wrong_target.json` | `failed` | 229/356 | 1/1 | 错跳现存 `truth_end` 后断言失败，1 个状态 | 1 |

`tests/test_case_study.py` 证明每份故障只相对基准改变一个 Pointer，独立重放代表路径，并在恢复唯一旧值后得到与基准完全相同的 JSON 和完整报告。

## 实际 HTML 产物

已生成以下离线单文件报告：

- `reports/v1.1/investigation_ok.html`：正常案例，0 error / 0 warning。
- `reports/v1.1/fault_wrong_exit_condition.html`：死路、代表路径、条件解释、Pointer 和变量写入线索。
- `reports/v1.1/investigation_incomplete.html`：`--max-states 25` 的不完整分析。

不完整案例实际返回退出码 3：发现 25 个状态、展开 20 个状态、记录 34 条转移，诊断仅有 `ANALYSIS_LIMIT_REACHED`，9 个未访问节点保持 `unknown`。HTML 有持续可见的“不完整”提示，不显示为通过。

生成命令：

```powershell
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\investigation_ok.json --format html --output reports\v1.1\investigation_ok.html
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\fault_wrong_exit_condition.json --format html --output reports\v1.1\fault_wrong_exit_condition.html
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\investigation_ok.json --format html --max-states 25 --output reports\v1.1\investigation_incomplete.html
```

## 视觉检查状态

结构测试已经验证长文本换行、容器横向滚动、目录目标、条件树、路径折叠、可见焦点样式、转义、CSP、无脚本和无外部资源。

本轮尝试用本机 Chrome 做视觉检查，但 Windows Computer Use 在读取页面前因无法高置信度确认当前浏览器 URL 而安全终止；没有发生点击或输入，也没有绕过限制。因此真实浏览器视觉检查标记为 **未完成**，不能把文件生成或 HTML 结构测试声称为视觉验收成功。

人工检查清单：

1. 打开三份 HTML，确认正常、故障、不完整三种顶部状态明显不同。
2. 在故障报告中从目录跳到诊断，展开 3 条代表路径和嵌套条件树。
3. 检查长中文标题、Pointer、ID 和变量名不覆盖相邻内容。
4. 使用 Tab 键确认目录链接、Pointer、`summary` 均有可见焦点。
5. 缩窄窗口，确认指标网格换行、诊断内容不横向溢出，宽表只在自身容器滚动。

## CI 与剩余限制

- `.github/workflows/tests.yml` 仍配置 Linux/Windows 与 Python 3.11/3.13；本轮没有实际运行 GitHub Actions，不能写“CI 已通过”。
- 未接入真实 Ren’Py、Ink、Twine 或 Python 条件；案例仍是自定义布尔 JSON 的 adapted 模型。
- Pointer 定位 JSON 结构，不提供准确源文件行号或编辑器跳转。
- 静态写入位置只用于排查，不进行自动根因推断、修复建议或最小修复集计算。
- 条件局部检查仍最多枚举 12 个不同变量；超过时为 `skipped`。

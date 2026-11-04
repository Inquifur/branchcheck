# V1.1 调查剧情案例

## 案例性质与来源

本案例是 **adapted（改编试用案例）**，不是从真实 Ren’Py 工程导出的剧情，也不声称复现某个正式游戏。实施前只检查了当前 BranchCheck 仓库中明确提供的 README、文档和 `examples/`；仓库内没有可追溯到真实工程的剧情原文或导出文件。

案例沿用 `examples/mystery_fixed.json` 中“笔记失窃与实验室事故调查”的工具测试背景，将其扩展为 19 个节点、8 个布尔变量和 3 个结局，用来验证接近实际创作流程的往返调查、条件对话、证据复盘和故障定位。将来接入真实素材时，需要作者提供明确可读的剧情文本、导出文件或仓库内路径，并说明哪些断言属于正式剧情约束。

| 原剧情步骤/材料位置 | JSON 节点 | 变量与条件 | 简化或假设 |
|---|---|---|---|
| `examples/mystery_fixed.json` 的 `foyer` 调查枢纽 | `lobby` | 证据齐全后启用 `review_evidence` | 改编为可反复返回的学院大厅；证据可以按不同顺序取得 |
| `record_room` 与 `permit_desk` | `reception`、`archive_door`、`archive_room` | `has_archive_pass`、`has_memo` | 将“先取得记录”扩展为办理通行证后查阅借阅备忘 |
| 原案例没有对应的完整证人段落 | `witness_hall`、`witness_dialogue`、`witness_resists`、`witness_cooperative` | 有备忘时可确认时间；无备忘时先被拒绝 | 为验证条件对话而增加的改编内容，不代表正式剧情 |
| `lab_entry` 与 `photo_room` | `lab_door`、`lab_bench`、`photo_station` | `has_lab_access`、`has_photo`、`photo_logged` | 将现场访问拆成许可、拍照和影像登记；登记与持有照片分别建模以便注入单点故障 |
| `sd_desk` 与 `analysis_room` 的证据处理思路 | `sample_station` | `has_sample_result` | 改为检验档案封套残留物，避免宣称存在正式 SD 卡剧情 |
| `confront` 的照片断言与多证据隐藏选项 | `evidence_review`、`photo_briefing`、`timeline_check` | 照片、备忘、证词、样本齐全后复盘 | 将一次对峙拆成两种复盘入口；两种入口都必须建立 `case_ready` |
| `truth`、`quiet_end`、`hidden_end` | `truth_end`、`protected_end`、`unresolved_end` | 正式结论要求 `case_ready` | 三个结局均为本次改编的作者约束，不是从真实剧情原文提取的断言 |

## 模型与调查顺序

基准文件为 `examples/case_study/investigation_ok.json`。八个变量分别记录档案通行证、借阅备忘、证词、实验室许可、实际照片、影像登记、样本结果和复盘完成状态。

案例允许至少两种主要调查顺序：

1. 先办档案手续、取得备忘并完成证人访谈，再进入实验室取得照片和样本结果。
2. 先完成实验室拍照与样本检验，再去询问证人；没有备忘时会进入拒绝对话，取得备忘后可再次返回并完成访谈。

两条顺序都会多次回到 `lobby`。只有 `has_memo`、`witness_interviewed`、`photo_logged` 和 `has_sample_result` 全部为 `true` 时，同一节点上的 `review_evidence` 才出现。复盘后可以到达“提交完整证据链”或“保护目击者”两个正式结局；调查中也可以随时选择暂缓结局。

## 基准实测

2026-11-03 在项目自带 `.venv`、Python 3.12 环境中运行当前分析器：

| 文件 | 状态 | 完整性 | 状态数 | 转移数 | error | warning |
|---|---:|---:|---:|---:|---:|---:|
| `investigation_ok.json` | `passed` | 完整 | 229 | 357 | 0 | 0 |

基准的 19 个节点和 3 个结局全部可达，没有意外 warning。测试还分别重放“档案优先”和“实验室优先”的选择序列，确认两条顺序都能在证据齐全后从 `lobby` 进入 `evidence_review`。

## 独立故障与修复对照

三份故障文件都只相对基准改变一个 JSON 位置。伴随诊断是搜索语义的正常结果，测试只把表中的主诊断当作该故障的直接观察，不要求整个报告只有一条诊断。

| 故障文件 | JSON Pointer | 旧值 | 新值 | 预期观察 | 2026-11-03 实际诊断 |
|---|---|---|---|---|---|
| `fault_missing_photo_effect.json` | `/nodes/10/choices/0/effects/has_photo` | `true` | 字段删除 | 影像已登记但没有实际照片，照片复盘断言失败 | `ASSERTION_FAILED`，节点 `photo_briefing`，断言 `photo_must_exist`，1 个受影响状态，0 warning |
| `fault_wrong_exit_condition.json` | `/nodes/3/choices/0/condition/eq` | `true` | `false` | 已持有通行证进入档案室后，唯一出口不可执行，形成可达死路 | `DEAD_END`，节点 `archive_room`，5 个受影响状态；另有 10 个由后续内容不可达或选择无法启用产生的 warning |
| `fault_wrong_target.json` | `/nodes/12/choices/1/target` | `timeline_check` | `truth_end` | 时间线复盘错误跳到仍存在的正式结局，尚未建立 `case_ready` | `ASSERTION_FAILED`，节点 `truth_end`，断言 `truth_requires_review`，1 个受影响状态；`timeline_check` 同时报告不可达 |

`tests/test_case_study.py` 对每份故障执行以下检查：

- 递归比较基准与故障 JSON，证明只有表中一个 Pointer 不同。
- 检查主诊断的 code、节点和断言，并独立重放报告中的代表路径。
- 逐步验证选择条件成立、effect 产生的变量变化、目标节点和最终快照一致。
- 将唯一差异恢复为旧值，证明 JSON 与基准完全相同，并验证恢复后的完整报告等于基准报告。

定向回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_case_study.py -q
```

当前结果：`8 passed`。这些测试不依赖诊断文案的逐字匹配，也没有为案例增加专用分析规则。

## 仍未接入的内容

- 尚未接入真实 Ren’Py、Python 条件或人物知识状态；当前仍只使用 BranchCheck V1 的布尔变量 JSON。
- 案例中的证人段落、样本证据和两个正式结局是为试用流程建立的改编约束。
- 若提供真实剧情素材，应重新核对节点映射、变量含义和断言依据，而不是把本案例中的假设直接当作正式剧情事实。

# BranchCheck 1.2 演示

## V1.2：从 `.rpy` 到源行报告

本节使用 `examples/renpy/` 的 adapted 片段。它们专门用于验证有限语法导入，不是从真实 Ren'Py 工程抽取的原文；因此演示证明的是导入合同和报告链路，不是完整游戏兼容性。

### 0:00–0:30 直接检查片段

```powershell
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\minimal_ok.rpy
```

`check-renpy` 在内存中完成整文件导入和状态分析。它不会执行 `.rpy`，也不会修改源文件。报告应明确标注“单文件有限子集、新游戏默认状态、未模拟外部引擎逻辑”；路径中的 menu option 是玩家选择，label 进入、条件分派、赋值、jump 与 return 是自动执行步骤。

### 0:30–1:00 导出模型和来源映射

```powershell
.\.venv\Scripts\python.exe -m branchcheck import-renpy examples\renpy\minimal_ok.rpy --output reports\v1.2\minimal.json
.\.venv\Scripts\python.exe -m branchcheck check reports\v1.2\minimal.json
```

第一条命令生成一份严格 `schema_version=1` 模型和 `reports/v1.2/minimal.sources.json`。模型可由原 `check` 命令读取；sidecar 记录源 SHA-256、行范围和编译映射。普通 `check` 不读取 sidecar，所以第二条命令验证的是模型本身；要在报告中显示 `.rpy` 行号，仍应使用 `check-renpy`。

### 1:00–1:30 查看 menu 回退与嵌套流

```powershell
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\menu_fallback.rpy --format html --output reports\v1.2\menu_fallback.html
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\nested_flow.rpy --format json --output reports\v1.2\nested_flow.json
```

在 menu 回退样例中，所有选项条件都为假时才允许自动进入 menu 后继；只要一个选项可用，报告路径中就不应出现跳过 menu 的路线。嵌套样例用于核对分支赋值、汇合和提前 jump/return，完整编译路径会保留赋值步骤，即使它比玩家可见操作更多。

### 1:30–1:50 对比搜索不完整

```powershell
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\nested_flow.rpy --format json --max-states 1
```

达到搜索上限时返回退出码 3，状态为 `incomplete`。自动生成的节点同样计入限制；未访问节点和未观察到的选择保持 `unknown`，不能据此认定不可达或通过。

### 1:50–2:00 确认拒绝而不是静默跳过

```powershell
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\unsupported.rpy --format json
```

该文件包含 V1.2 未建模的语句。命令应返回退出码 2、`INVALID_INPUT`、`import_complete=false` 和准确源行，并明确未运行状态分析。若 `import-renpy` 目标已有旧文件，本次失败不会覆盖模型或 sidecar。

实际回归数字、等价性验证和生成产物见 `docs/verification-v1.2.md`；不要用本页的预期检查点替代实际命令结果。

## V1.1：JSON 调查案例

这部分继续使用 `examples/case_study/` 中的 **adapted（改编试用）**调查剧情。它没有接入真实 Ren'Py 工程；目标是演示作者如何从故障报告定位 JSON、理解具体状态证据、恢复一处修改并重新分析。

## 0:00–0:20 生成故障报告

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\fault_wrong_exit_condition.json --format html --output reports\v1.1\fault_wrong_exit_condition.html
```

实际结果为 `failed`、退出码 1：109 个发现/展开状态、165 条有效转移、1 个 error 和 10 个 warning。主问题是 `archive_room` 的 `DEAD_END`，影响 5 个不同状态；伴随 warning 来自档案证据链中断后不可达的后续内容。

## 0:20–1:15 从报告读出证据

手动打开 `reports/v1.1/fault_wrong_exit_condition.html`，按以下顺序查看：

1. 顶部确认分析完整，状态不是 `incomplete`。
2. 从诊断目录跳到 `DEAD_END`。
3. 查看主要源位置 `/nodes/3`，以及唯一选择条件 `/nodes/3/choices/0/condition`。
4. 展开一条代表路径，确认玩家已经取得 `has_archive_pass=true` 并实际到达 `archive_room`。
5. 展开“具体状态下的条件解释”：选择 `copy_memo` 要求 `has_archive_pass=false`，实际为 true，因此不满足。
6. 查看变量赋值位置线索，区分静态写入 Pointer、源节点可达性和实际触发记录。

报告最多展示 3 条代表路径；它们不是全部 5 个问题状态。路径中的变量变化来自真实搜索，静态写入位置只用于人工排查。

## 1:15–1:40 恢复唯一故障

故障文件相对基准只有一个值不同：

| Pointer | 故障值 | 基准值 |
|---|---:|---:|
| `/nodes/3/choices/0/condition/eq` | `false` | `true` |

可以直接对照 `examples/case_study/investigation_ok.json`，不要删除断言、添加结局或改写其他条件。恢复后，分析基准文件：

```powershell
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\investigation_ok.json
```

实际结果为 `passed`、退出码 0：229 个状态、357 条转移、0 error、0 warning。档案室死路和全部伴随诊断消失，19 个节点与 3 个结局均可达。

## 1:40–2:00 对比不完整分析

```powershell
.\.venv\Scripts\python.exe -m branchcheck check examples\case_study\investigation_ok.json --format html --max-states 25 --output reports\v1.1\investigation_incomplete.html
```

实际返回退出码 3、状态 `incomplete`：发现 25 个状态、展开 20 个状态、34 条转移，仅报告 `ANALYSIS_LIMIT_REACHED`。9 个未访问节点显示 `unknown`，不会被误报为不可达；HTML 顶部持续显示分析未完成提示。

## 其他两个独立故障

| 文件 | 唯一变更 | 主诊断 |
|---|---|---|
| `fault_missing_photo_effect.json` | 删除 `/nodes/10/choices/0/effects/has_photo` | `photo_briefing.photo_must_exist` 的 `ASSERTION_FAILED`，1 个状态 |
| `fault_wrong_target.json` | `/nodes/12/choices/1/target` 从 `timeline_check` 改到现存 `truth_end` | `truth_end.truth_requires_review` 的 `ASSERTION_FAILED`，1 个状态 |

三份故障的唯一差异、代表路径重放和恢复验证由 `tests/test_case_study.py` 覆盖。完整来源映射与改编假设见 `docs/case-study.md`，字段解释见 `docs/diagnostics.md`。

## V1.2：从脚本到源行证据

运行 `python -m branchcheck check-renpy examples/renpy/nested_flow.rpy --format html --output reports/v1.2/nested_flow.html`，打开报告，查看 `.rpy` 行号、label、原语句和自动执行标记。自动赋值仍完整保留在路径里；最短编译路径不承诺最少玩家点击。

再运行 `python -m branchcheck check-renpy examples/renpy/closed_loop.rpy`，可以看到静态 jump 封闭循环及无法到达 return 的证据。运行 `python -m branchcheck check-renpy examples/renpy/unsupported.rpy` 会在第 2 行拒绝 call，而不会宣称通过。

修改/恢复演示应使用测试副本；自动测试已在临时副本中验证 return→jump start→return 的诊断出现与消失。源样例均为 adapted，不代表真实工程接入。命令、等价性证据、产物和未验证项见 [V1.2 验收](verification-v1.2.md)。

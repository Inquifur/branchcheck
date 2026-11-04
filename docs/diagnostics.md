# 如何阅读 V1.1 诊断

BranchCheck V1.1 的报告按“结论、源位置、执行证据、排查线索”分层。最重要的原则是：路径和状态来自真实搜索；Pointer、入边和变量写入位置来自静态 JSON 结构；两者不能互相替代。

## 先看完整性和证据类型

报告顶部先说明 `analysis_complete`。完整搜索可以给出不可达、始终不可用等否定结论；达到上限时状态为 `incomplete`、退出码为 3，未访问节点和未观察选择保持 `unknown`，不能被解释成通过或不可达。

诊断的 `evidence_kind` 用来区分依据：

| 值 | 含义 |
|---|---|
| `specific_state` | 某个实际到达状态直接证明，例如断言失败或死路 |
| `global_conclusion_with_state_samples` | 完整搜索得出全局结论，并展示最多 3 个真实源状态样本 |
| `global_conclusion` | 完整图上的结论，例如不可达；没有虚构到达快照 |
| `local_proof` | 对单个条件的全部局部布尔赋值检查，不是一次运行快照 |
| `analysis_status` | 搜索上限等分析状态 |
| `input_error` | 输入解析或校验失败，未执行状态搜索 |

## 用 Source Pointer 定位 JSON

`source_refs` 中的 `pointer` 是标准 JSON Pointer，数组编号严格使用输入文件原顺序。例如：

```text
/nodes/3
/nodes/3/choices/0/condition
/nodes/10/assertions/0/condition
```

每个引用还会包含可用的 `node_id`、`choice_id`、`assertion_id`、标题或文字，以及“失败断言”“不可执行选择条件”等角色。HTML 中 Pointer 可选择复制，节点 ID 可跳到页内稳定锚点。Pointer 不等于源文件行号；工具不会通过文本搜索猜测行号。

全局问题可以没有 Pointer。JSON 语法错误继续使用解析器给出的行列。不可达诊断通常定位目标节点，并把声明入边的 `target` 字段列为排查线索。

## 重放代表路径

聚合诊断的 `affected_state_count` 是所有不同问题状态的数量；报告最多保留 3 条最短代表路径。它们不是全部路径。

每条路径都包含：

1. 初始节点和完整变量快照。
2. 实际执行的选择、源/目标节点和选择 Pointer。
3. 该步真正发生的变量变化；没有变化时显示空对象。
4. 最终节点和完整变量快照。

零步路径表示问题就在初始状态。路径中的变量变化直接来自搜索状态，不由静态写入索引推测。

## 阅读条件解释

`ASSERTION_FAILED`、`DEAD_END` 和 `NEVER_ENABLED_CHOICE` 的代表路径可带 `condition_explanations`。每条解释都以该路径自己的最终状态求值：

- `var`：变量名、要求值、实际值、是否满足。
- `const`：常量值和直接结果。
- `all`：整体与每个子项的结果；一个失败子项会使整体失败。
- `any`：整体与每个子项的结果；失败叶子不代表整体失败。
- `not`：先显示子项结果，再显示取反后的整体结果。

条件解释与实际分析共用同一求值器。报告不会把所有 false 叶子都写成“缺少条件”，也不会猜测最小修复集。

`CONTRADICTORY_CONDITION` 不使用一份 false 快照当证明。它的 `local_proof` 表示在条件引用变量的全部赋值下都无法成立；超过 12 个不同变量时检查为 `skipped`，不生成矛盾结论。

## 变量写入位置是线索

`variable_sources` 记录变量初始值及所有显式 `effects` 写入位置。每条写入同时显示：

- 写入的 true/false 值、源节点、选择、目标和 Pointer。
- `source_reachability`：源节点可达、不可达或未知。
- `observation_status`：`triggered`、`not_triggered` 或 `unknown`。

源节点可达不代表选择触发。`triggered` 必须来自实际搜索记录；完整搜索中未触发才会标为 `not_triggered`；分析不完整时未观察到只能是 `unknown`。没有显式写入不表示变量永远为 false，初始值仍可能为 true。

## 不可达问题没有虚构路径

`UNREACHABLE_NODE` 和 `UNREACHABLE_ENDING` 的 `paths` 必须为空。报告只列目标节点、声明入边、入边条件和源节点可达性。没有入边时会明确显示“无声明入边”。这些结构线索不能被描述成已经执行的路径。

## 人工排查顺序

1. 确认分析是否完整，以及诊断属于哪种证据类型。
2. 从首个 `source_refs` Pointer 定位条件、断言或节点。
3. 重放代表路径，核对每一步条件、effects 和最终变量快照。
4. 展开条件树，找出实际不满足的叶子，但不要直接假定修改方案。
5. 查看相关变量的初始值和写入位置，并区分静态位置与实际触发。
6. 修改一处后重新分析，确认目标诊断消失且其他业务结果没有回退。

BranchCheck 给出证据和排查范围，不会自动要求删除条件、删除断言、改变初始值或把死路改成结局。

# 剧情 JSON 与报告格式

## 输入文件

使用 UTF-8 JSON，版本固定为 1。ID 只能匹配 `[A-Za-z_][A-Za-z0-9_]*`，标题、选择文字和断言消息可使用中文。JSON 对象禁止重复键，所有层级禁止未知字段。字段名拼错会直接报错，不会被默默忽略。

### 顶层

| 字段 | 必填 | 类型与约束 |
|---|---|---|
| `schema_version` | 是 | 整数 1；`true`、1.0、字符串均不合法 |
| `title` | 是 | 非空字符串 |
| `start` | 是 | 节点 ID，必须存在 |
| `variables` | 是 | 对象，键为变量 ID，值严格为 JSON `true` / `false`；允许没有变量 |
| `nodes` | 是 | 至少一个节点的数组 |

变量初始值会影响实际可达性。数字 0、1 不会当作布尔值。

### 节点

| 字段 | 必填 | 类型与约束 |
|---|---|---|
| `id` | 是 | 全部节点中唯一的 ID |
| `title` | 是 | 非空字符串 |
| `ending` | 否 | 严格布尔值，默认 `false` |
| `assertions` | 否 | 断言数组，默认 `[]` |
| `choices` | 否 | 选择数组，默认 `[]` |

`ending=true` 是显式终止状态，不再展开。这样的节点禁止非空 `choices`，可以省略选择或声明 `[]`。非结局节点可以声明空选择，但如果实际到达，将形成死路；从未到达的空节点只报告不可达。

### 选择

| 字段 | 必填 | 类型与约束 |
|---|---|---|
| `id` | 是 | 在所属节点内唯一的 ID |
| `text` | 是 | 非空字符串 |
| `target` | 是 | 已存在的节点 ID |
| `condition` | 否 | 下文定义的条件，默认 `true` |
| `effects` | 否 | 变量赋值对象，默认 `{}`；键须已声明，值须严格为布尔值 |

所有满足条件的选择都属于玩家可能采取的路线。数组中的顺序用于稳定搜索，不代表“只执行第一个条件成立的选项”。

### 断言

断言恰好包含 `id`、`condition`、`message` 三个必填字段。`id` 在所属节点内唯一，`message` 为非空字符串。断言和选择的 ID 分别在自己的数组中检查唯一性。

```json
{
  "id": "photo_required",
  "condition": {"var": "has_photo", "eq": true},
  "message": "进入出示照片的剧情前，应已取得照片。"
}
```

断言是作者要求每个到达状态满足的规则，**不是进入条件**。初始节点也检查断言。失败后记录 `ASSERTION_FAILED`，继续搜索，便于同时发现后续问题。工具只检查明确写出的规则，不从剧情文字推测人物动机或隐含规则。

## 条件表达式

只接受以下形状，不解析字符串表达式，不执行 `eval`：

```json
true
false
{"var": "has_photo", "eq": true}
{"all": [{"var": "has_photo", "eq": true}, {"var": "has_permission", "eq": false}]}
{"any": [{"var": "has_photo", "eq": true}, {"var": "has_record", "eq": true}]}
{"not": {"var": "has_photo", "eq": true}}
```

上方各行是独立表达式，并非一个 JSON 文件。

- 叶子对象恰好含 `var` 和 `eq`；变量须已声明，`eq` 严格为布尔值。
- 组合对象恰好含 `all`、`any`、`not` 中的一个键。
- `all` / `any` 接受非空表达式数组，分别表示全部成立/至少一项成立。
- `not` 接受单个表达式，表示取反；可以嵌套或互相抵消。
- 根表达式深度算 1，每层嵌套加 1，最大 32；常量和叶子也占一层。
- 混合形状如 `{"all": [true], "not": false}`、空数组、未知键、字符串条件都无效。

## 状态与赋值顺序

状态由节点 ID 和全部变量的布尔值组成。同一个节点在有钥匙和无钥匙时是两个状态。

1. 在源状态上计算条件，决定能执行哪些选择。
2. 采取某个选择后，一次性应用其 `effects`，未出现的变量保持原值。
3. 到达目标节点，检查目标断言，再展开后续选择。

例如条件要求 `has_sd=true`，效果将它设为 `false`，该选择可以执行，但到达目标后已不持有 SD 卡。每条分支使用独立的不可变状态，赋值不会污染兄弟分支。节点本身没有进入效果。

## 输入错误

非法 JSON 尽可能显示行列，结构错误显示字段路径，例如 `nodes[2].choices[0].target`。错误会区分未知变量、类型错误和目标不存在。重复对象键、重复节点/局部 ID、悬空引用、缺失/未知字段、非法类型、过深条件都会导致 `INVALID_INPUT`，不进入状态分析。文件读取和报告写入失败使用退出码 2，并给出可理解的说明。

## 诊断代码

| Code | 级别 | 含义 |
|---|---|---|
| `INVALID_INPUT` | error | 输入无法解析或违反格式约束；不搜索 |
| `UNREACHABLE_NODE` | warning | 完整搜索后，非结局节点从未到达 |
| `UNREACHABLE_ENDING` | warning | 完整搜索后，声明的结局节点从未到达 |
| `DEAD_END` | error | 已完整展开的非结局状态没有可执行选择 |
| `CONTRADICTORY_CONDITION` | warning | 选择条件在所有布尔赋值下都为假 |
| `NEVER_ENABLED_CHOICE` | warning | 源节点可达，但完整搜索后该选择始终不可执行 |
| `ASSERTION_FAILED` | error | 实际到达状态违反节点断言 |
| `NO_REACHABLE_ENDING` | error | 完整搜索后没有到达任何结局；未声明结局也属于此情形 |
| `NO_ENDING_PATH` | warning | 完整图中，可达非结局状态已无法通往任何结局；同状态已有 `DEAD_END` 时不重复报告 |
| `ANALYSIS_LIMIT_REACHED` | warning | 为继续搜索需要超过状态/转移上限，分析未完成 |

逻辑矛盾与实际故事中无法触发不同。只在引用变量不超过 12 个时穷举局部条件；超过则 `skipped`，既不判矛盾也不宣称局部检查通过。相同条件缓存检查结果。矛盾选择不重复报 `NEVER_ENABLED_CHOICE`；不可达源节点的选项也不逐个报该项。

## JSON 报告

V1.1 使用 `report_version=2`。剧情输入的 `schema_version` 仍固定为 1；报告版本升级只表示增加解释与源位置字段，不放宽输入校验，也不改变原诊断 code、严重度或退出码。报告不含当前日期或随机 ID，便于稳定比较。

| 顶层字段 | 含义 |
|---|---|
| `story_title` | 剧情标题；输入无效时可能使用占位标题 |
| `analysis_complete` | 是否完整搜索所有实际可达状态 |
| `stop_reason` | 未完成时的具体停止原因，正常完成为 `null` |
| `overall_status` | `invalid`、`incomplete`、`failed`、`warning`、`passed`，按此前后优先级选择 |
| `limits` | 实际采用的 `max_states`、`max_transitions` |
| `summary` | 计数摘要，详见下表 |
| `diagnostics` | 聚合后的诊断数组 |
| `node_results` | 每个声明节点的可达性、状态数和选择触发结果 |
| `local_condition_checks` | 每个选择的局部条件检查及 completed/skipped 状态 |
| `variable_sources` | 每个变量的初始值、初始 Pointer 和所有静态 `effects` 写入位置 |

`summary` 包含以下字段：

| 字段 | 含义 |
|---|---|
| `node_count` / `variable_count` | 声明的节点数 / 布尔变量数 |
| `declared_ending_count` / `reached_ending_count` | 声明的 / 已到达的不同结局节点数 |
| `discovered_states` / `expanded_states` | 已发现的唯一状态数 / 已完整展开的状态数 |
| `transition_count` | 已记录的有效状态转移数，包含进入已发现状态的边 |
| `error_count` / `warning_count` | 聚合后的 error / warning 诊断条目数，不是受影响状态数 |

每条诊断保留 V1 的 `code`、`severity`、中文 `message`、`node_id`、`choice_id`、`assertion_id`、相关 `condition`、`affected_state_count`、`representative_path_count` 和最多三条 `paths`，并增量增加：

- `source_refs`：按原输入数组顺序生成的标准 JSON Pointer，以及节点/选择/断言 ID、展示文字和该位置在问题中的角色。全局问题可以为空。
- `evidence_kind`：区分 `specific_state`、`global_conclusion`、`global_conclusion_with_state_samples`、`local_proof`、`analysis_status` 或 `input_error`。
- `variable_sources`：只包含与当前条件有关的变量初始值和静态写入位置，并附源节点可达性及 `triggered` / `not_triggered` / `unknown` 观察状态。
- `local_proof`：矛盾条件的全赋值局部证明信息；它不是某一份 false 状态快照。

`representative_path_count` 是实际截取的代表路径数；无关 ID 与条件可以为 `null`。按 `(code, node_id, choice_id, assertion_id)` 聚合，以不同状态计数，并优先保留最短路径。局部矛盾和不可达等没有具体问题状态的诊断，此状态数为 0。

路径包括 `initial_state`、`steps`、`final_state` 和可选的 `condition_explanations`。两个状态快照均包含 `node_id`、`node_title`、完整 `variables` 和节点 `source_refs`。每一步包含源/目标节点 ID 和标题、选择 ID 和文字、实际选择的 `source_refs`，以及只记录真实变化的 `changes`，形如 `{"has_sd": {"before": true, "after": false}}`；无变化时为 `{}`。起点问题的步骤数组可以为空，但仍保留初始快照。

`condition_explanations` 总是使用该代表路径自己的终点状态：变量叶子包含 `name`、`expected`、`actual`、`satisfied`；常量包含值与结果；`all`、`any`、`not` 包含自身结果与全部子解释。解释节点的 `result` 使用同一套条件求值器计算，因此成功的 `any` 可以同时显示失败叶子，失败的 `not` 会显示其子项实际为真。

不可达问题不含执行路径，使用可选的 `incoming_edges` 列出来源节点、选择 ID、条件、源节点可达性和目标字段 Pointer 作为线索；没有入边也可能是有效结果。这些线索不代表能实际执行该入边。死路诊断还可带 `related_conditions`，列出该节点的选择 ID、文字、未满足条件和源位置，方便结合每条代表路径自己的终点快照逐项核对。

`node_results` 按输入节点顺序提供 `node_id`、`title`、`ending`、`declared_choice_count`、`triggered_choices`、`reachable_state_count`、`reachability`、`choices` 和节点 `source_refs`。`reachability` 为 `reachable`、`unreachable` 或 `unknown`。每个选择含 `choice_id`、`text`、`target`、`condition`、`triggered`、`status` 和 `source_refs`；状态为 `enabled`、`never_enabled`、`source_unreachable` 或 `unknown`。节点声明了多少个选择，与实际触发过多少个选择，是两个独立信息。

`local_condition_checks` 含 `node_id`、`choice_id`、原始 `condition`、`source_refs`、`proof_kind`、`assignment_count`、`status`、`variable_count`、`satisfiable`、`reason`。`completed` 表示局部检查已执行，不表示条件一定可满足；条件矛盾时 `satisfiable=false`，`proof_kind=all_assignments`。`skipped` 时 `satisfiable=null`、`assignment_count=null` 并解释原因。它不影响 BFS 对实际状态求值。

顶层 `variable_sources` 按变量声明顺序列出 `variable`、`initial_value`、`initial_pointer` 和 `writes`。每个写入位置包含 Pointer、写入值、源节点/选择、目标节点、`source_reachability` 与 `observation_status`。静态写入只表示 JSON 中存在该 `effects`，不证明选择可执行；只有 `observation_status=triggered` 才表示搜索记录过实际转移。不完整分析时，未观察到的写入保持 `unknown`。

不完整搜索保留已证明的断言失败和死路，以及局部矛盾结果；不会输出依赖完整搜索的不可达、`NO_REACHABLE_ENDING`、`NO_ENDING_PATH` 或 `NEVER_ENABLED_CHOICE` 诊断。未发现节点和未触发选择标记 `unknown`，已实际到达/触发的事实仍保留。`incomplete` 优先于 `failed`，因此其中可以同时存在已确认的 error。

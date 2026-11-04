# Ren'Py 导入器设计

## 分层与信任边界

V1.2 使用一条单向流水线：

```text
UTF-8 单文件
  -> 行、引号、注释与缩进扫描
  -> 有源范围的有限语法 AST
  -> 布尔表达式白名单转换
  -> 稳定控制流模型与来源 sidecar
  -> 现有 schema_version=1 校验
  -> 现有状态分析器
  -> Ren'Py 来源投影与既有 text/json/html 渲染
```

输入 `.rpy` 从不作为 Python 或 Ren'Py 脚本执行。解析器只识别合同中的语句；表达式虽然使用 `ast.parse(..., mode="eval")` 取得语法树，但每个节点仍须通过白名单，随后转换为 BranchCheck 的不可变 `Condition`。

现有搜索核心不知道 Ren'Py。导入器输出普通 `Story`，因此状态去重、BFS、反向结束可达性、搜索上限、诊断 code 与退出码继续由同一套实现负责。普通 `branchcheck check story.json` 也不会查找或信任旁边的来源 sidecar。

## 中间 AST

解析层保留 `Default`、`Label`、`Assign`、`If`、`Menu`、`Jump`、`Return`、`Pass` 与 `Narration`。每个节点记录 1-based、末行包含的源范围、短片段、所属 label 和稳定的解析顺序。条件分支和菜单选项也保留自己的标题行位置，而不是用字符串搜索回猜行号。

语义引用在整文件解析完成后统一检查：变量可以在文本后部由顶层 `default` 声明，jump 可以指向后部 label；但重复 default/label、缺少 start、未知变量、未知目标和末尾合同都会阻止编译。这样既支持初始化位置无关，也保证不可达区域同样被验证。

## CFG 编译

每个 label、运行语句和控制结构使用确定性 ID；相同输入内容重复导入会得到相同模型顺序和来源映射。ID 不包含当前时间、随机数、绝对路径或 Python hash。

- label 入口通过自动边进入首条语句。块正常结束时，continuation 指向同层后继；label 顶层 continuation 是文件中的下一 label。
- 赋值节点的自动出边携带 `effects`，确保赋值在后继条件前生效。
- `if` 分支 i 的有效守卫为“此前所有条件均假，并且当前条件为真”；`else` 为此前条件全部为假。无 else 时相同的全假守卫进入后继。
- menu 选项使用作者条件；额外回退边使用“所有选项条件均假”。回退边是自动边，不是玩家选择。
- 分支和选项块以自己的 continuation 汇合。内部 jump/return 忽略传入 continuation，因此不会泄漏到兄弟分支或原位置后继。
- return 编译为明确 ending；普通 label 不会自动设为 ending。

编译后的自动节点和边与作者节点一样计入分析状态及转移上限。V1.2 不改变 BFS 权重，所以报告保留完整编译路径，并同时标注玩家选择和自动执行；它不承诺计算最少玩家点击次数。

## 来源映射 sidecar

`import-renpy input.rpy --output model.json` 只在 `model.json` 写入严格的 `schema_version=1` 数据，并同时写入 `model.sources.json`。sidecar 拥有独立 `mapping_version`，包含源内容 SHA-256、相对显示文件名、行数，以及 default、编译节点和编译选择的映射。

每条映射至少包含：

- 相对文件名、起止行、所属 label、语句类型和短片段；
- 编译 node/choice ID 与模型 JSON Pointer；
- `source` 或 `synthetic` 来源分类；
- 条件选择需要时保存作者原条件与有效守卫的关系。

sidecar 不包含机器绝对路径。模型先通过既有严格 loader 自检；模型和 sidecar 均在临时文件成功写完后才替换目标。导入失败不输出部分模型，也不覆盖旧产物。

`check-renpy` 在同一进程内导入、分析并投影，不需要先落盘模型。来源投影在保留编译 Pointer 的同时增加 `.rpy` 行号；相同文本出现多次时仍由 AST 源范围区分。

## 作者视图与 raw 诊断

编译结构可能产生没有作者意义的 warning，例如 menu 全禁回退或纯自动连接的内部条件。Ren'Py 报告保留分析器的 `raw_diagnostics`，再生成作者视图：

- error、完整性、状态快照、封闭循环和全局问题从不抑制；
- 不可达源 label 和从未可用的源 menu 选项从不抑制；
- 只有明确标记为 compiler-only 的内部汇合、自动边或 menu 回退 warning 可以隐藏；
- 投影记录抑制数量及原因，不把组合有效守卫的矛盾冒充作者原表达式矛盾。

报告 `report_version` 仍为 2。普通 JSON 输入的报告形状和渲染保持原行为；Ren'Py 报告增量提供导入边界、来源位置、raw 区域与投影摘要。

当前实现为每条原语句建立节点，没有单独制造汇合节点，因此保留全部语句节点（包括 return）的不可达 warning。抑制对象仅为没有作者选择意义的自动连接/回退条件；原菜单选项的诊断保留。if/elif 有效守卫诊断也保留，但标注 `condition_scope=effective_guard` 并解释前序条件约束，不将其说成原表达式独立矛盾。节点/选择来源记录分别为原语句和 synthetic 自动转移。

两份文件先全部写入同目录临时文件，再依次替换；普通第二次替换失败会恢复原文件对，测试有故障注入覆盖。操作系统不提供两文件原子提交，因此进程崩溃或断电仍可能留下不匹配的一对；普通 check 始终不读取 sidecar，check-renpy 始终从当前源码重新生成映射。

## 失败与完整性

导入错误生成 `INVALID_INPUT`，标记 `import_complete=false` 和“未执行状态分析”，退出码 2。导入成功后，完整分析有 error 返回 1，无 error 返回 0；搜索达到 `--max-states` 或 `--max-transitions` 返回 3。

“导入成功”仅表示受支持语法已完整转换，不表示剧情没有逻辑问题。“分析完整”也只表示编译布尔状态图已完整搜索，不扩大到 Ren'Py 引擎行为。

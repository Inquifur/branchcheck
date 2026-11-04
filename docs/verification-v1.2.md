# V1.2 实际进度与验收

本轮先检查既有文件：版本号和 README 已更新为 1.2.0，六个 adapted `.rpy` 样例、三份手写 JSON 参考和两份设计文档已存在；导入器、CLI 新命令、来源投影和对应测试尚缺失。本次补齐这些实现，保留 V1.1 搜索核心，剧情 schema_version=1、report_version=2。

## 环境与基线

Windows、项目 `.venv` Python 3.12.14。没有安装或运行 Ren'Py SDK。原基线测试阶段跑完后，pytest 清理系统 Temp 中旧 `pytest-current` 时遇到 WinError 5；没有改系统目录权限或删除旧临时文件。改用新的项目内临时目录确认：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-v12-baseline -o tmp_path_retention_count=0
```

实际 **196 passed in 0.39s**，进程退出 0。原四份 V1 模型及 V1.1 案例回归包含在测试中，未调整预期计数或删除测试。

最终完整验收命令：`.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-v12-acceptance -o tmp_path_retention_count=0`。实际 **279 passed in 0.52s**，无测试警告，进程退出 0（原 196 项加 83 项新增）。临时目录参数用于避开本机旧系统 Temp 的清理权限问题，不跳过任何测试。

## 新增实现和证据

- `src/branchcheck/renpy.py`：有位置 AST、表达式白名单、基于 continuation 的 CFG、sidecar、作者报告投影。整份文件验证后才交给原 loader 和 analyzer，不执行源码。
- `cli.py`：import-renpy/check-renpy；导出模型和 sidecar、输入保护、失败保留旧文件、I/O 错误处理。普通 check 不读取 sidecar。
- `reports.py`：在原 Pointer 旁显示源文件、label、行范围、原语句及折叠的 synthetic 自动边；变量写入索引关联实际赋值行；报告顶部显示子集边界。
- `tests/test_renpy.py`：独立手写模型与人工终态、指定菜单序列、初始化/赋值/贯穿、提前 jump/return、拒绝与源行号、资源限制、投影、CLI、HTML 转义、导出回滚和测试副本故障恢复。

三份参考模型开发前已存在于 `examples/renpy/reference/`，未由本次导入器生成或改写。比较终态集合而非内部节点数量：

| 脚本 | 人工预期及参考核对 |
|---|---|
| elif_priority | first/second 均 true，但仅 result_first 被写为 true，result_second 保持 false |
| menu_fallback | has_access=false，菜单全部不可用，仍执行公共赋值，return 时 continued=true |
| nested_flow | 三种终态：有线索且已记录、无线索且已记录、直接撤离且未记录 |

嵌套案例另按“搜索→带走线索”“搜索→只做记录”“直接撤离”三条玩家选择序列运行编译图，分别到 truth、leave、empty 的实际源 return；alarmed=true 变体证明提前 return 不再写入 reviewed。参考模型与编译器的控制流整理相互独立；测试共享原条件求值器，但没有共享 CFG 构建代码。

## CLI 实际产物

在项目目录执行（模块形式适用于本机）：

```powershell
.\.venv\Scripts\python.exe -m branchcheck import-renpy examples\renpy\minimal_ok.rpy --output reports\v1.2\minimal.json
.\.venv\Scripts\python.exe -m branchcheck check reports\v1.2\minimal.json
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\nested_flow.rpy --format html --output reports\v1.2\nested_flow.html
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\closed_loop.rpy --format html --output reports\v1.2\closed_loop.html
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\unsupported.rpy --format json --output reports\v1.2\unsupported.json
.\.venv\Scripts\python.exe -m branchcheck check-renpy examples\renpy\nested_flow.rpy --max-states 2 --format json --output reports\v1.2\incomplete.json
```

对应 JSON 同样已实际生成。下表为作者视图聚合计数；保留原语句不可达与有效分支无法执行的 warning，并不要求正常脚本中所有源分支都可达。

| 输入 | 结果 | error/warning | 退出码 |
|---|---|---:|---:|
| minimal_ok | warning | 0/2 | 0 |
| menu_fallback | warning | 0/2 | 0 |
| elif_priority | warning | 0/4 | 0 |
| label_fallthrough | passed | 0/0 | 0 |
| nested_flow | warning | 0/2 | 0 |
| closed_loop | failed | 1/7 | 1 |
| unsupported | invalid、import_complete=false，未搜索；第 2 行 call 被拒绝 | 1/0 | 2 |
| nested_flow，max-states=2 | incomplete | 0/1 | 3 |

nested_flow 实测 23 个编译节点、26 个发现/展开状态、25 条有效转移、4 个声明 return 中到达 3 个。import-renpy 的严格模型可被普通 check 读入；普通 check 的 warning 数可能更多，因为它不应用来源投影。JSON 保存 raw_diagnostics 和抑制明细，code/严重度不改写。报告不记录日期、随机 ID 或源机器绝对路径；sidecar 哈希对应本次读取的 UTF-8 源内容。

失败导入保留旧模型及 sidecar 的字节内容；模拟第二文件替换失败验证恢复原文件对。源码中包含恶意调用时仅解析拒绝，无文件副作用。测试副本由 return 改为 jump start，实际检查为 failed/退出 1，恢复后 passed/退出 0。未改用户真实源码。

## 真实接入、视觉与 CI

只检查了当前项目已有材料，没有全盘扫描。本轮可用 `.rpy` 都是 `examples/renpy/` 中的 adapted 合同样例，没有用户真实工程原文，也没有 derived 抽取片段。因此**未完成真实工程接入**。unsupported.rpy 的拒绝说明的是合同边界，不是对真实工程的扫描结果。

HTML 已生成且通过源片段/引号/标签安全转义与离线结构测试。本轮未执行浏览器视觉验收；此前该项目浏览器工具拒绝 file: 协议，不绕过该限制，也不把结构测试算作视觉验收。用户可手动打开报告。GitHub Actions 未在云端执行；本轮仅声称本机 Python 3.12.14 的实际测试结果。

支持合同、具体资源上限、与 Ren'Py 运行环境的差别见 renpy-subset.md。多文件、Python、call、显示系统等仍拒绝；没有作者断言时，能结束但不符合作者意图的跳转不一定可证明为问题。

核对的官方文档：[Label 和控制流](https://www.renpy.org/doc/html/label.html)、[菜单和全禁回退](https://www.renpy.org/doc/html/menus.html)、[顺序条件分支](https://www.renpy.org/doc/html/conditional.html)、[Python/default](https://www.renpy.org/doc/html/python.html)。这些是本阶段合同的语义依据，不表示支持文档列出的全部功能。

# V1 交付验收记录

本机环境为 Windows 11（构建 26200）、Python 3.12.14，使用从零创建的项目 `.venv`。系统默认 Python 3.10 保持原样。没有发布、部署或推送仓库。

## 已执行的验收

| 项目 | 实际证据 |
|---|---|
| 新环境安装与入口 | 创建 `.venv`，执行 `python -m pip install -e ".[dev]"` 成功；`python -m branchcheck --help` 退出 0。模块入口不依赖 Windows 自动生成的未签名控制台 `.exe` |
| 正常案例 | minimal_ok：4 状态/3 转移；mystery_fixed：68 状态/115 转移；state_cycle_ok：5 状态/5 转移；均完整通过、0 error/0 warning、退出 0 |
| 故障案例 | mystery_broken：36 状态/52 转移、2 error/7 warning、退出 1；照片断言、SD 卡死路、矛盾条件、隐藏结局与调查室不可达均实际检出 |
| 路径证据 | 自动测试逐条重放故障案例所有代表路径，校验每个选择条件、效果、实际变量变化和最终完整快照 |
| 报告 | text/json/html 均实测；JSON 可直接解析、结果稳定；指定文件自动创建父目录，状态信息输出到 stderr |
| 状态上限 | `python -m branchcheck check examples/state_cycle_ok.json --max-states 2 --format json --output reports/state_limit.json`：incomplete，退出 3 |
| 转移上限 | `python -m branchcheck check examples/state_cycle_ok.json --max-transitions 1 --format json --output reports/transition_limit.json`：incomplete，退出 3 |
| 全套自动测试 | `.venv\Scripts\python.exe -m pytest -q`：157 passed in 0.35s，无警告 |
| 小型性能实测 | 2 节点/10 布尔变量模型：2048 状态、11264 转移、0.010198 秒；仅计 analyze 调用，单次测量，详见 demo.md |
| 运行时依赖 | 仅 Python 标准库；无需 API Key、在线服务或图形界面；pytest 是开发依赖 |

## 测试覆盖位置

- `tests/test_loader.py`：严格类型、必填与未知字段、重复键/ID、变量与目标引用、表达式形状与深度 32/33、UTF-8、结局约束等输入边界。
- `tests/test_conditions.py`：all/any/not/常量真值、嵌套取反、12/13 变量局部检查边界、缓存隔离。
- `tests/test_analyzer.py`：初始赋值与状态去重、effects 重置与兄弟分支隔离、可达死路、初始/到达断言、路径重放、合法及封闭循环、同节点不同结束能力、汇合边保留、最短路径及并列稳定性、两种限额及刚好完成、未知结论抑制、诊断聚合与三路径上限、四个真实样例回归。
- `tests/test_cli_reports.py`：三种格式、stdout/输出文件、退出码 0/1/2/3、参数/读写失败、UTF-8 重定向含 emoji、HTML 结构与文本转义、无外部资源、零步证据和阻塞条件说明。

## 明确未验证或不支持的内容

1. 真实浏览器视觉验收未完成：浏览器工具的 URL 安全策略禁止 `file:` 协议。没有通过其他协议、命令或替代浏览器绕过限制。HTML 已通过自动化结构与安全测试；用户可手动双击生成的报告检查视觉效果。
2. CI 已配置 Ubuntu/Windows、Python 3.11/3.13，但未实际在 GitHub 运行；本次仅声称 Windows Python 3.12.14 的实测结果。
3. V1 只分析自定义 JSON 和布尔状态；不解析 Ren’Py/Ink/Twine，不推测自然语言规则或循环依赖根因。超过 12 个不同变量的局部矛盾检查明确 skipped；状态或转移超限会明确 incomplete。
4. “完整通过”限于当前模型与已声明断言，不保证文笔、完整游戏逻辑或任意玩家策略必然结束。性能数字只对应演示模型和当前机器。

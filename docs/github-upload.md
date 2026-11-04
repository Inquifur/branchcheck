# V1.2 GitHub 上传前验证

验证日期：2026-11-04。项目版本 1.2.0，Windows / Python 3.12.14。

## 实际结果

- 原目录：`python -m pytest -q --basetemp=.test-tmp-upload`，279 passed。
- 将 Git 暂存清单复制到全新中文路径目录，新建虚拟环境后执行 `python -m pip install ".[dev]"`，成功构建并安装 wheel；没有复用原环境中的项目安装。
- 干净目录执行 `python -m pytest -q --basetemp=.test-tmp-clean-tests`，279 passed。
- JSON minimal_ok、调查基准、Ren'Py minimal_ok 和 menu_fallback HTML 均返回 0。
- 调查出口故障生成 HTML 返回 1；Ren'Py unsupported 返回 2；nested_flow 限制 2 状态返回 3，均符合文档。
- README 全部 16 条分析/导入命令均已在干净环境运行，返回码符合样例性质；本地 Markdown 文件链接无缺失。
- 输出父目录自动创建，中文工程路径下运行成功。HTML 结构由现有测试覆盖，本轮没有浏览器视觉验收，也没有实际调用桌面文件打开命令。
- 本机未安装 Python 3.11/3.13，未本地验证 Linux/macOS。CI 配置为 Windows/Linux × Python 3.11/3.13；云端结果以上传后的 Actions 为准。

## 待上传范围与检查

源码、测试、配置、文档、虚构 JSON/Ren'Py 合同案例及 benchmark 工具。案例来源和改编假设见 case-study.md；未发现真实游戏原文、外部图片、音频或其他第三方素材，没有据此编造素材授权。

排除虚拟环境、缓存、egg-info、构建产物、本地报告和测试临时目录；保留原有本地文件。补充忽略凭据常见文件名。报告由用户按 README 重新生成。

工程此前没有 .git，因此没有既有 Git 历史可扫描或需要重写。对初始 54 个待提交文件（334409 字节，最大 38292 字节）扫描常见 token、私钥、秘密赋值、邮箱和个人路径模式，无命中；已人工核对样例来源说明。扫描不构成对所有潜在敏感信息的保证。验收文档中的作者电脑绝对路径已改为项目根目录。

运行时仅标准库；当前环境 setuptools 与 pytest 的包元数据标注 MIT，项目未复制这些包的源码。所有者已明确选择公开仓库与 MIT 许可证。已添加 LICENSE 与包元数据，版权署名使用 GitHub 账号 Inquifur；未创建 release 或 tag。

README 补充无须激活的安装步骤、故障到修复示例、真实退出码、HTML 打开方式及已实现/计划功能边界。没有修改分析器。首次云端执行后，修正了一项测试对 Python 旧版 JSON 错误位置的固定假设，仍严格核对当前解码器给出的行列，未跳过或删除测试。

## 远程核验

已创建公开仓库 [Inquifur/branchcheck](https://github.com/Inquifur/branchcheck)，默认分支 main，MIT 许可证。首次上传 56 个文件，远程所有 blob SHA 与本地提交逐一相同。

首轮 [Actions](https://github.com/Inquifur/branchcheck/actions/runs/41806298704) 中 Windows/Linux 的 Python 3.11 均通过；Python 3.13 均为 278 passed、1 failed。失败原因是标准库将尾随逗号定位在第 2 行第 21 列，而旧测试固定期待第 3 行第 1 列。测试现改为核对实际解码器的行列，并保留输入错误类型和中文错误前缀检查；分析器行为不变。修正提交会触发新的四项矩阵，最终云端结果见 [Actions](https://github.com/Inquifur/branchcheck/actions)。

Git 直连 github.com:443 失败后，通过本机已有的代理完成推送；仅为本次命令指定代理，没有修改全局配置。仓库未包含代理配置、私人邮箱或本地生成报告。原样保留三份故障 JSON 末尾空行，git diff --check 会提示这三处空行，不影响输入语义和测试。

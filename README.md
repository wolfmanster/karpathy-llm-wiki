# LLM Wiki

基于两个上游仓库整合的个人 LLM 知识库工作区:

- **[MinerU-GUI](MinerU-GUI/)** — 文档解析桌面工具(CustomTkinter),把 PDF / 图片 / Office 文件解析成 Markdown。作为 git submodule 挂载在 `MinerU-GUI/`,保留独立历史,可从上游拉取更新。
- **karpathy-llm-wiki** — Karpathy 式 LLM wiki 的 [Agent Skills](https://agentskills.io) 技能(wolfmanster 对 [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) 的 fork)。技能文件 `SKILL.md`、`references/`、`scripts/`、`examples/`、`tests/`、`assets/` 直接平铺在项目根目录,使根目录本身就是一个可用的 wiki 工作区。

## 这是什么

**LLM wiki** 是一种知识系统:LLM 在摄入时把新来源编译成持久的 Markdown 知识页,而不是在每次提问时重新检索原始文档。知识随时间复利累积,回答时引用已经整理好的页面。

来源存入 `raw/`(不可变素材),由 LLM 编译进 `wiki/`(整理后的知识页),并用 `wiki/index.md`(全局索引)和 `wiki/log.md`(操作日志)维护。完整规范见 [SKILL.md](SKILL.md)。

## 目录结构

```
.
├── SKILL.md                  # wiki 技能的完整规范(操作规则、模板引用)
├── raw/                      # ← 不可变素材(来源文档的 Markdown 版),按主题分子目录
├── wiki/                     # ← LLM 编译的知识页,一层主题子目录 + index.md + log.md
├── MinerU-GUI/               # ← submodule:PDF/图片/Office → Markdown 解析工具
├── references/               # 文章 / 索引 / 日志 / 归档模板
├── scripts/check_evidence.py # 源保真度检查脚本(证据校验)
├── examples/                 # 示例 wiki 页面、源文件、操作日志
├── tests/                    # check_evidence.py 的测试
└── assets/                   # 上游素材(Karpathy 推文截图等)
```

## 快速开始

三个核心操作(完整流程见 [SKILL.md](SKILL.md)):

| 操作 | 触发方式 | 作用 |
|------|----------|------|
| **Ingest** | 给 Claude 一个 URL、文件或粘贴的文本 | 存进 `raw/` → 分类 → 创建/更新 `wiki/` 文章 |
| **Query** | "我 wiki 里有什么关于 X 的?" | 搜索 wiki 并带引用回答(不写文件) |
| **Lint** | "lint 我的 wiki" | 检查索引一致性、坏链、过期引用,自动修复 + 报告 |

第一次摄入会自动初始化 `wiki/index.md` 和 `wiki/log.md`(首次 Ingest 前只存在空的 `raw/` 和 `wiki/`)。

## 用 MinerU-GUI 把文档变成素材

1. 启动解析工具:双击 [MinerU-GUI/start.bat](MinerU-GUI/start.bat)(首次需先运行 `setup.bat` 并按 `pip install mineru[core]` 安装解析引擎)。
2. 拖入 PDF / 图片 / Office 文件,选好参数,点"开始转换"。
3. 产物在 `MinerU-GUI/output/` 下(每个文件一个目录,含 `.md` 和 `images/`)。
4. 把产物 Markdown 作为素材进行 Ingest(可先移动到 `raw/<topic>/` 或直接让 Claude 读取),让知识编译进 wiki。

也可以在 Python 中直接调用,不启动 GUI:

```python
import sys
sys.path.insert(0, r"MinerU-GUI")
from mineru_api import convert_document, batch_convert

result = convert_document("report.pdf", device="cpu")
print(result.output_md)
```

## 更新上游

```bash
# 更新 MinerU-GUI 到最新版
git submodule update --remote MinerU-GUI
cd MinerU-GUI && git log --oneline @{1}..HEAD   # 查看本次更新内容

# 更新本仓库的技能文件(平铺部分)
#   尚无上游远程:git remote add upstream https://github.com/wolfmanster/karpathy-llm-wiki.git
git pull upstream main
```

## 许可证

- 本仓库整合的 karpathy-llm-wiki 部分:[MIT](LICENSE)
- MinerU-GUI 部分:其目录内的 [LICENSE](MinerU-GUI/) 为准(同为 MIT)

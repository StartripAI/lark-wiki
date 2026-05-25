# lark-wiki

> 🧠 本地 Markdown 是知识源头，飞书是协作和检索的入口，`lark-cli` 把两边拼起来。

笔记、论文、决策、运营记录都先在本地写，再推到飞书 Docs / Wiki / Base，团队协作、跨文档搜索、运营台账都从飞书侧用。出错可以回滚到本地原文。

和 Obsidian 这种主打本地笔记的工具不同：协作、权限、多维表、项目都交给飞书，本地只留原文和整理后的版本。

![本地 Markdown 和附件经过 lark-wiki 编译、再用 lark-cli 推到飞书 Docs / Wiki / Base / Project，按个人、工作、公司三条赛道组织。](assets/lark-wiki-readme-hero.png)

## ✨ 思路

```text
本地 Markdown + 附件
        → lark-wiki 编译
        → 关系图 / lint / 摘要
        → lark-cli
        → 飞书 Docs / Wiki / Base
```

四条原则：

- **原文留在本地**。`knowledge/wiki_src/**` 放原始资料和整理后的页面；飞书是镜像，不是单一真相源。
- **走飞书原生**。Docs、Wiki、Base 都通过 `lark-cli` 接，不绕外部封装。
- **LLM 只看你给的资料**。摘要、找冲突、补遗漏，全部基于明确传入的来源。
- **重要改动先过一眼**。Paper Evidence Workbench、Knowledge Relation Map、远端拉回的差异都会先进草稿或队列，人看过再写到正式页面。

## 🚀 两块最值得单独拿出来说

光把 Markdown 丢给 LLM 并不稀奇。我们更关心两件事：读论文时别把“作者说了什么”和“证据能支持什么”混在一起；做知识库时别让页面变成一堆孤岛。

| 组件 | 解决什么 |
| --- | --- |
| Paper Evidence Workbench | 把论文、结论、证据、没想明白的问题放在同一张工作台里，不替你下判断，帮你少忘关键信息 |
| Knowledge Relation Map | 先把有哪些页面、它们为什么有关、哪里坏了或太薄、下一步该读什么说清楚，让知识可以沿着上下文继续走 |

这两块做好后，`lark-wiki` 就不只是“给笔记加个总结”的小工具。它可以落到项目交付、公司 Wiki、Base 运营台账和多人协作里。

## 🧩 谁会用得上

- **个人知识库**：笔记、阅读、论文、决策、灵感、生活/工作运营文档
- **项目 Wiki**：runbook、handoff、会议纪要、状态同步、风险记录
- **公司协作**：共享制度、流程库、项目组合视图、Base 支撑的运营台账
- **论文研究**：用 Paper Evidence Workbench 记清论文结论、证据和还没解决的问题
- **知识网络**：用 Knowledge Relation Map 看清页面清单、关联理由、问题和下一步阅读顺序，文件不再散

默认四个命名空间：

| 命名空间 | 用途 |
| --- | --- |
| `account` | portfolio 主页、总索引、管理页、运行日志 |
| `project::<slug>` | 个人 / 项目 / 团队 / 客户 / 部门空间 |
| `shared` | 已审核的规则、术语、模板 |
| `inbox` | 还没分类的素材 |

## ⚡ 上手

### 1. 本地跑通

不需要远端授权，只写本地 `state/` 和 `knowledge/build/`。

```bash
python3 scripts/lark_wiki.py --help
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::agent_workspace
python3 scripts/lark_wiki.py inventory --namespace project::agent_workspace
python3 scripts/lark_wiki.py build_graph --namespace project::agent_workspace
python3 scripts/lark_wiki.py lint --namespace project::agent_workspace
python3 scripts/lark_wiki.py query --namespace project::agent_workspace --query handoff
```

### 2. 配置本地 workspace

```bash
mkdir -p state
cp examples/llm_wiki_v1.local.example.toml state/llm_wiki_v1.local.toml
```

凭据、seed nodes、Base ID、本机路径只放在 `state/`，默认不进 git。

### 3. 接飞书

```bash
npm install -g @larksuite/cli@1.0.19
lark-cli config init --new
lark-cli auth login
lark-cli doctor
```

可选：

```bash
npx skills add https://github.com/larksuite/cli -y -g
```

### 4. 同步远端

先同步 account/root，再同步 project，否则 project push 会缺父级 Wiki root。

```bash
python3 scripts/lark_wiki.py upgrade_preflight
python3 scripts/lark_wiki.py discover_feishu_docs
python3 scripts/lark_wiki.py discover_feishu_bases
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py inventory --namespace account
python3 scripts/lark_wiki.py build_graph --namespace account
python3 scripts/lark_wiki.py sync_push --namespace account --limit 1
python3 scripts/lark_wiki.py ingest --namespace project::agent_workspace
python3 scripts/lark_wiki.py inventory --namespace project::agent_workspace
python3 scripts/lark_wiki.py build_graph --namespace project::agent_workspace
python3 scripts/lark_wiki.py sync_push --namespace project::agent_workspace --limit 1
```

命令风险等级：

| 等级 | 命令 |
| --- | --- |
| 只写本地，不调远端 | `bootstrap_portfolio`、`bootstrap_namespace`、`discover_local_repo_assets`、`classify_assets`、`ingest`、`inventory`、`build_graph`、`agent_context`、`query --query <text>` |
| 主要本地，可能拉绑定的镜像 | `lint` |
| 远端只读 + 本地落盘 | `upgrade_preflight`、`discover_feishu_docs`、`discover_feishu_bases`、`discover_feishu_project`、`sync_pull` |
| 远端写 | `sync_push`、`bootstrap_ops_base`、`sync_ops_base` |

## 🛠️ 场景教程

- [Personal Life OS](examples/tutorials/personal-life-os/README.md)：个人笔记、阅读、决策，把整理过的内容分享给团队
- [Work Delivery Room](examples/tutorials/work-delivery-room/README.md)：项目交付、handoff、runbook、风险与状态同步
- [Company Collaboration OS](examples/tutorials/company-collaboration-os/README.md)：公司协作 Wiki、共享标准、Base 运营台账
- [Paper Evidence Workbench](examples/tutorials/research-paper-workbench/README.md)：论文阅读、结论与证据整理、Knowledge Relation Map

更轻量的 starter：

- [Personal KB](examples/personal/README.md)：最小个人知识库
- [Work Project](examples/work-project/README.md)：最小项目知识库
- [Company OS](examples/company-os/README.md)：account/shared 起步配置
- [lark-cli recipes](examples/lark-cli-recipes.md)：底层平台命令速查
- [Optional analysis](examples/optional-analysis.md)：LLM、Paper Evidence Workbench、Knowledge Relation Map 能力说明

## 🧱 技术架构

![架构图：本地 Markdown 和附件 → lark-wiki 编译器 + 可选分析层 → lark-cli → 飞书 Docs / Wiki / Base / Project。](assets/lark-wiki-architecture.svg)

公开 CLI 当前覆盖的范围：

| 平台面 | 支持情况 |
| --- | --- |
| Docs / Wiki | 通过 `lark-cli` 搜索、读取、创建、更新；Wiki 节点发现和同步 |
| Base | 发现 table / field / record；Ops Base 可镜像 sources / pages / runs / issues / merge queue |
| Project | 配置快照 + 本地 sync-state 发现，不承诺 live API 同步 |
| Drive | 仅在 `upgrade_preflight` 里检查能力，不作为同步入口 |

## 📁 目录结构

```text
assets/                          README 里用的图
demo/agent_workspace_assets/     合成的演示数据
examples/                        starter、教程、配方
knowledge/wiki_src/              wiki 源页面
scripts/lark_wiki.py             公开 CLI 入口
scripts/lark_wiki/               编译、同步、lint、发现
tests/                           公开 starter 测试
```

运行时输出全在本地，git 忽略：

```text
state/
knowledge/raw/
knowledge/assets/
knowledge/build/
```

## ⚙️ 配置

配置从通用到本地分层叠加：

```text
scripts/lark_wiki/defaults.toml
state/llm_wiki.portfolio.toml
state/llm_wiki.projects.toml
state/llm_wiki_v1.local.toml
state/llm_wiki.projects/*.toml
```

`state/llm_wiki_v1.local.toml` 放本机的 LLM 和 workspace 设置；`state/llm_wiki.projects/*.toml` 放每个项目的 starter profile，从 `examples/` 复制过来。

最小 LLM 配置：

```toml
[llm]
provider = "disabled"
model = "gpt-5.4-mini"
command = ""
timeout_seconds = 180
max_assets_per_prompt = 6
max_chars_per_asset = 3500
semantic_lint_enabled = true
```

provider 模式：

| 模式 | 用法 |
| --- | --- |
| `disabled` | 只跑确定性的编译和同步 |
| `mock` | 本地测试和 CI |
| `command` | 调用自己的 JSON 命令 provider |
| `codex_exec` | 用 `codex exec` 总结传入的来源 |
| `auto` | 优先 `codex`，回退 command，再回退 disabled |

## 🔌 可选的分析能力

主流程只要 Python 和 `lark-cli` 就跑得起来。下面这些按 workspace 单独开关，不会替代你审核过的页面：

| 能力 | 作用 |
| --- | --- |
| `@larksuite/cli@1.0.19` | 必装的平台连接器 |
| Knowledge Relation Map | 基于 `inventory` 看页面有哪些、关系为什么成立、哪些地方断了或太薄，并给出可执行的阅读和补充建议 |
| External relation map import | 读取外部关系图产物，镜像到本地 build 目录，再让 `query` 用这些关系扩展阅读顺序 |
| Paper Evidence Workbench | 论文笔记、结论笔记、证据表 |
| LLM provider | 总结你给的来源，标记可能的冲突 |

完整关系图刷新由外部分析工作流完成；lark-wiki 负责导入、盘点和查询消费：

```bash
python3 scripts/lark_wiki.py agent_context --namespace project::agent_workspace
python3 scripts/lark_wiki.py query --namespace project::agent_workspace --query handoff
```

## 🧪 验证

```bash
python3 scripts/lark_wiki.py --help
python3 -m unittest discover -s tests -v
python3 scripts/lark_wiki.py lint --namespace project::agent_workspace
```

带授权的运行时检查：

```bash
python3 scripts/lark_wiki.py upgrade_preflight
```

公开发布前的 cleanroom 扫描：

```bash
rg -n "replace-with-your-private-pattern" README.md examples assets scripts tests knowledge
```

## 📚 常用命令

完整命令以 `python3 scripts/lark_wiki.py --help` 为准。日常最常用的是这些：

```text
bootstrap_portfolio
discover_local_repo_assets
classify_assets
ingest
inventory
build_graph
agent_context
lint
query --query <text> [--namespace project::<slug>]
upgrade_preflight
discover_feishu_bases
discover_feishu_docs
sync_pull
sync_push
```

## 🧭 接下来

- 装好就能用的 `lark-wiki` 控制台命令
- 带截图的首次同步指引
- 更多个人 / 工作 / 团队场景的实用模板
- 把 Paper Evidence Workbench 和 Knowledge Relation Map 的接入步骤写得更清楚

# lark-wiki

> 🚀 `lark-cli` 优先的本地知识库：适合个人笔记、工作项目和团队运营 Wiki。

`lark-wiki` 把本地 Markdown、文件资产和 Lark/Feishu 工作面连成一套可运行的知识库。你在本地维护权威内容，用 `lark-cli` 同步到 Docs / Wiki / Base / Project，再用 lint、graph 和可选 LLM 层保持内容可追踪、可审计、可协作。

本地 Markdown 是权威来源，Lark/Feishu 是协作界面。

![Diagram showing local Markdown and assets flowing through lark-wiki and lark-cli into Lark Docs, Wiki, Base, and Project](assets/lark-wiki-architecture.svg)

## ✨ 为什么需要它

很多知识库最后会散成三份：本地文档、飞书文档、表格和项目管理里的状态。`lark-wiki` 的目标是把它们统一到一条清晰链路中：

```text
Local Markdown + Assets
        -> lark-wiki compiler
        -> graph / lint / optional LLM
        -> Lark Docs / Wiki / Base / Project through lark-cli
```

它适合三类场景：

| 场景 | 适合内容 |
| --- | --- |
| 🧠 个人知识库 | 笔记、研究、决策、阅读记录 |
| 🧰 工作/项目知识库 | 交接、Runbook、文档、状态看板 |
| 🏢 团队运营 Wiki | 规则、制度、流程库、Base 支撑的运营数据 |

## 🧩 核心思路

- **Local-first**: `knowledge/wiki_src/**` 存放权威页面。
- **Lark-native**: `lark-cli` 连接 Docs、Wiki、Base、Project、Drive。
- **Namespace isolation**: personal/work/company 都可以用 `project::<slug>` 隔离。
- **Review before promotion**: remote drift, shared truth, generated summaries 都要可检查。
- **Optional analysis**: LLM、graph analysis、research evidence 都是增强层，不替代 source。

默认命名空间：

| Namespace | Meaning |
| --- | --- |
| `account` | portfolio home, index, governance, run log |
| `project::<slug>` | personal, team, client, department, or company workspace |
| `shared` | approved shared libraries, glossary, rules |
| `inbox` | holding area for unclassified assets |

## ⚡ Quickstart

### 1. Try the local demo first

No remote auth is required for the local starter flow.

```bash
python3 scripts/lark_wiki.py --help
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py bootstrap_namespace --namespace project::agent_workspace
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::agent_workspace
python3 scripts/lark_wiki.py build_graph --namespace project::agent_workspace
python3 scripts/lark_wiki.py lint --namespace project::agent_workspace
```

### 2. Create local config

```bash
mkdir -p state
cp examples/llm_wiki_v1.local.example.toml state/llm_wiki_v1.local.toml
```

Put credentials, seed nodes, Base tokens, and local paths only under `state/`. It is ignored by git.

### 3. Connect Lark/Feishu when ready

```bash
npm install -g @larksuite/cli@1.0.19
lark-cli config init --new
lark-cli auth login
lark-cli doctor
```

Optional:

```bash
npx skills add https://github.com/larksuite/cli -y -g
```

### 4. Add remote discovery and sync

```bash
python3 scripts/lark_wiki.py upgrade_preflight
python3 scripts/lark_wiki.py discover_feishu_docs
python3 scripts/lark_wiki.py discover_feishu_bases
python3 scripts/lark_wiki.py discover_feishu_project
python3 scripts/lark_wiki.py sync_push --namespace project::agent_workspace --limit 1
```

Command safety:

| Type | Commands |
| --- | --- |
| Local-only | `bootstrap_namespace`, `bootstrap_portfolio`, `discover_local_repo_assets`, `classify_assets`, `ingest`, `build_graph`, `lint`, `query --query <text>` |
| Remote read | `upgrade_preflight`, `discover_feishu_docs`, `discover_feishu_bases`, `discover_feishu_project`, `sync_pull` |
| Remote write | `sync_push`, `bootstrap_ops_base`, `sync_ops_base` |

## 🛠️ Common Workflows

### Personal KB

Start from `examples/personal/`:

```bash
mkdir -p state/llm_wiki.projects knowledge/wiki_src/projects/personal_kb
cp examples/personal/llm_wiki.projects.personal_kb.toml state/llm_wiki.projects/personal_kb.toml
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py bootstrap_namespace --namespace project::personal_kb
cp examples/personal/00_Home.md knowledge/wiki_src/projects/personal_kb/00_Home.md
python3 scripts/lark_wiki.py build_graph --namespace project::personal_kb
python3 scripts/lark_wiki.py lint --namespace project::personal_kb
```

### Work Project

Start from `examples/work-project/`:

Run discovery after `lark-cli auth login`. For a local-only dry run, skip the two discovery commands and start with `bootstrap_namespace`.

```bash
mkdir -p state/llm_wiki.projects knowledge/wiki_src/projects/work_hub
cp examples/work-project/llm_wiki.projects.work_hub.toml state/llm_wiki.projects/work_hub.toml
python3 scripts/lark_wiki.py discover_feishu_docs
python3 scripts/lark_wiki.py discover_feishu_bases
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py bootstrap_namespace --namespace project::work_hub
cp examples/work-project/00_Home.md knowledge/wiki_src/projects/work_hub/00_Home.md
python3 scripts/lark_wiki.py build_graph --namespace project::work_hub
python3 scripts/lark_wiki.py lint --namespace project::work_hub
```

### Team Operating Wiki

Start from `examples/company-os/`:

```bash
mkdir -p state knowledge/wiki_src/shared
cp examples/company-os/llm_wiki.portfolio.toml state/llm_wiki.portfolio.toml
cp examples/company-os/shared-library.md knowledge/wiki_src/shared/shared-library.md
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py ingest --namespace shared
python3 scripts/lark_wiki.py bootstrap_ops_base
python3 scripts/lark_wiki.py sync_ops_base
```

## 📁 Repository Map

```text
assets/                         README diagram
demo/agent_workspace_assets/     synthetic demo sources
examples/                        starter profiles and recipes
knowledge/wiki_src/              canonical wiki pages
scripts/lark_wiki.py             public CLI entrypoint
scripts/lark_wiki/               compiler, sync, lint, discovery
tests/                           public starter tests
```

Runtime output is local and ignored:

```text
state/
knowledge/raw/
knowledge/assets/
knowledge/build/
```

## ⚙️ Configuration

Config is layered from general to local:

```text
scripts/lark_wiki/defaults.toml
state/llm_wiki.portfolio.toml
state/llm_wiki.projects.toml
state/llm_wiki_v1.local.toml
state/llm_wiki.projects/*.toml
```

Use `state/llm_wiki_v1.local.toml` for local LLM and workspace settings. Use `state/llm_wiki.projects/*.toml` for per-project starter profiles loaded from `examples/`.

Minimal LLM config:

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

Provider modes:

| Mode | Use |
| --- | --- |
| `disabled` | deterministic compile and sync only |
| `mock` | local tests and CI |
| `command` | call your own JSON command provider |
| `codex_exec` | source-grounded synthesis through `codex exec` |
| `auto` | prefer `codex`, then command, else disabled |

## 🔌 Optional Integrations

The core path only needs Python and `lark-cli`. Optional sidecars are user-configured per workspace.

| Package | Role |
| --- | --- |
| `@larksuite/cli@1.0.19` | required platform connector |
| user-provided graph analysis sidecar | optional structure discovery |
| user-provided research evidence sidecar | optional evidence collection |
| LLM provider | optional synthesis and semantic lint |

Sidecar outputs are review inputs. They do not define the source of truth.

## 🧪 Verify

```bash
python3 scripts/lark_wiki.py --help
python3 -m unittest discover -s tests -v
python3 scripts/lark_wiki.py lint --namespace project::agent_workspace
```

Authenticated runtime check:

```bash
python3 scripts/lark_wiki.py upgrade_preflight
```

Cleanroom scan before public release:

```bash
rg -n "replace-with-your-private-pattern" README.md examples assets scripts tests knowledge
```

## 📚 Command Reference

```text
audit_coverage
bootstrap_namespace
bootstrap_ops_base
bootstrap_portfolio
build_graph
classify_assets
conformance_check
discover_account_assets
discover_feishu_bases
discover_feishu_docs
discover_feishu_project
discover_local_repo_assets
discover_state_lineage
ingest
lint
merge_patches
query --query <text> [--namespace project::<slug>]
snapshot_legacy
sync_ops_base
sync_pull
sync_push
upgrade_preflight
```

## 🧭 Roadmap

- Installable `lark-wiki` console command.
- More starter profiles for teams, departments, and client workspaces.
- Guided first-sync docs with screenshots.
- Easier optional sidecar setup.
- More practical templates for personal, work, and team knowledge systems.

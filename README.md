# lark-wiki

> Chinese-first docs. English notes are included where they help onboarding.

`lark-wiki` 是一个以 `lark-cli` 为主的 local-first knowledge compiler。它把本地 Markdown、文件资产和 Lark/Feishu 工作面连接起来，帮助个人、团队和公司把知识库做成可同步、可审计、可回滚的工作系统。

`lark-wiki` is a local-first knowledge compiler for Lark/Feishu. Local Markdown stays canonical; Lark Docs, Wiki, Base, and Project become collaboration and operating surfaces through `lark-cli`.

![lark-wiki architecture](assets/lark-wiki-architecture.svg)

## What It Is

`lark-wiki` 不是普通笔记模板。它是一套围绕 `lark-cli` 的知识库工程骨架：

- 本地 Markdown 是 canonical truth。
- `lark-cli` 负责连接 Lark/Feishu Docs、Wiki、Base、Project 和 Drive。
- SQLite 记录资产、页面、运行、问题、同步游标和 merge queue。
- 编译器把本地资产和远端快照整理成 namespace 内的 wiki 页面。
- lint、coverage 和 conformance check 用来守住边界。
- LLM synthesis 是可选增强层，只基于 source 做总结和语义检查。
- graph analysis 与 research evidence 是可选 sidecar，不是主真相源。

Use it for:

- Personal knowledge base: notes, references, decisions, research logs.
- Work/project knowledge base: docs, handoffs, runbooks, dashboards.
- Corporation operating wiki: shared rules, process libraries, Base-backed control planes.

## Why `lark-cli`

`lark-cli` 是这个项目的集成边界。`lark-wiki` 不直接假装自己是 Lark 平台，而是把平台能力编排起来：

- `docs`: search, fetch, create, update.
- `wiki`: spaces and node tree discovery.
- `base`: table, field, view, record inventory and upsert.
- `project`: work item snapshots where available.
- `drive`: import/comment workflows when enabled by your workspace.

The compiler stays local-first. Remote pages are mirrors and work surfaces. If local and remote diverge, the merge queue makes drift visible before promotion.

## Core Model

```text
knowledge/wiki_src/**     canonical Markdown pages
knowledge/raw/**          fetched runtime snapshots, ignored by git
knowledge/build/**        compiled graph, reports, merge queue, ignored by git
state/llm_wiki_v1.sqlite  local registry and run state, ignored by git
```

Default namespaces:

| Namespace | Purpose |
| --- | --- |
| `account` | Portfolio home, index, governance, and run log. |
| `project::<slug>` | A bounded personal, work, team, client, or company workspace. |
| `shared` | Explicitly shared libraries, glossaries, rules, and standards. |
| `inbox` | Quarantine for unclassified or uncertain assets. |

Isolation rules:

- Every asset belongs to one namespace.
- Every canonical page belongs to one namespace.
- Links and source references stay namespace-local by default.
- Cross-namespace use must be explicit.
- `inbox` content never becomes project truth automatically.

## Quickstart

### 1. Install `lark-cli`

```bash
npm install -g @larksuite/cli@1.0.19
lark-cli config init --new
lark-cli auth login
lark-cli doctor
```

Optional agent skills:

```bash
npx skills add https://github.com/larksuite/cli -y -g
```

### 2. Configure local overrides

Start from the safe public example:

```bash
mkdir -p state
cp examples/llm_wiki_v1.local.example.toml state/llm_wiki_v1.local.toml
```

For a fresh personal/work/company setup, copy one of the starter profiles from `examples/` into your local override and fill only your own seed nodes or Base tokens.

### 3. Run the local compiler

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

### 4. Add Lark/Feishu discovery when ready

```bash
python3 scripts/lark_wiki.py upgrade_preflight
python3 scripts/lark_wiki.py discover_feishu_docs
python3 scripts/lark_wiki.py discover_feishu_bases
python3 scripts/lark_wiki.py discover_feishu_project
```

### 5. Sync only after lint passes

```bash
python3 scripts/lark_wiki.py sync_push --namespace project::agent_workspace
python3 scripts/lark_wiki.py sync_pull --namespace project::agent_workspace
python3 scripts/lark_wiki.py merge_patches --namespace project::agent_workspace
python3 scripts/lark_wiki.py bootstrap_ops_base
python3 scripts/lark_wiki.py sync_ops_base
```

## Common Workflows

### Personal Knowledge Base

Use `examples/personal/` when you want a private second brain that can still mirror selected pages to Lark Wiki.

Typical flow:

```bash
python3 scripts/lark_wiki.py bootstrap_namespace --namespace project::personal_kb
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::personal_kb
python3 scripts/lark_wiki.py lint --namespace project::personal_kb
```

### Work Project Knowledge Base

Use `examples/work-project/` for project docs, handoff notes, runbooks, decision logs, and Base-backed issue tracking.

Typical flow:

```bash
python3 scripts/lark_wiki.py discover_feishu_docs
python3 scripts/lark_wiki.py discover_feishu_bases
python3 scripts/lark_wiki.py ingest --namespace project::work_hub
python3 scripts/lark_wiki.py build_graph --namespace project::work_hub
```

### Corporation Operating Wiki

Use `examples/company-os/` for account-wide governance, shared libraries, and multiple project namespaces.

Typical flow:

```bash
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py ingest --namespace shared
python3 scripts/lark_wiki.py sync_ops_base
```

## Configuration

Configuration is layered:

```text
scripts/lark_wiki/defaults.toml
state/llm_wiki.portfolio.toml
state/llm_wiki.projects.toml
state/llm_wiki.projects/*.toml
state/llm_wiki_v1.local.toml
```

Use checked-in examples for templates. Put credentials, workspace identifiers, private seed nodes, and local paths only under `state/`, which is ignored by git.

Minimal local LLM settings:

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
| `disabled` | Deterministic compile and sync only. |
| `mock` | CI and local tests. |
| `command` | Send JSON payloads to your own command. |
| `codex_exec` | Use `codex exec` for source-grounded synthesis. |
| `auto` | Prefer `codex`, then custom command, else disabled. |

## Optional Integrations

The core system only needs Python and `lark-cli`. These optional packages can extend the workflow:

Recommended versions are recorded in `scripts/lark_wiki/defaults.toml`.

| Package | Role | Rule |
| --- | --- | --- |
| `@larksuite/cli@1.0.19` | Required platform connector. | Use it for Docs, Wiki, Base, Project, and Drive access. |
| `graphifyy==0.5.0` | Optional graph analysis sidecar. | Produces structure hints; it does not define canonical truth. |
| `deepxiv-sdk==0.2.5` | Optional research evidence sidecar. | Produces research inputs; human review decides promotion. |
| LLM provider | Optional synthesis and semantic lint. | Summaries must stay source-grounded. |

Optional integrations should be configured per namespace and kept out of the default path until you need them.

## Commands

Main entrypoint:

```bash
python3 scripts/lark_wiki.py --help
```

Available commands:

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
query
snapshot_legacy
sync_ops_base
sync_pull
sync_push
upgrade_preflight
```

## Repository Layout

```text
assets/
  lark-wiki-architecture.svg
demo/
  agent_workspace_assets/
examples/
  minimal-config.toml
  personal/
  work-project/
  company-os/
knowledge/
  wiki_src/
    account/
    shared/
    inbox/
    projects/
      agent_workspace/
scripts/
  lark_wiki.py
  lark_wiki/
tests/
  test_lark_wiki.py
```

The bundled `agent_workspace` content is synthetic starter material. Replace it with your own project namespace when you set up a real workspace.

## Verification

Local checks:

```bash
python3 scripts/lark_wiki.py --help
python3 -m unittest discover -s tests -v
python3 scripts/lark_wiki.py lint --namespace project::agent_workspace
```

Runtime check when authenticated:

```bash
python3 scripts/lark_wiki.py upgrade_preflight
```

Cleanroom scan before public release:

```bash
rg -n "replace-with-your-private-pattern" README.md examples assets scripts tests knowledge
```

The scan should return no private workspace data.

## Design Principles

- Local Markdown is canonical.
- `lark-cli` is the platform boundary.
- Lark/Feishu is the work surface.
- Generated assets stay out of canonical pages unless explicitly promoted.
- Shared truth needs review, not automatic promotion.
- Personal, work, and corporation scopes share the same isolation model.

## Roadmap

- Add installable `lark-wiki` console entrypoint.
- Add more starter profiles for departments and client workspaces.
- Add screenshot-based docs for first sync setup.
- Add namespace templates for personal, team, and company operating systems.
- Make optional sidecar configuration easier to enable without changing core defaults.

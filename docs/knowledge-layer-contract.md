# Knowledge Layer Contract

This repository has five separate layers. They can feed each other, but they do not share write ownership.

## Ownership

| Layer | Owns | May write formal wiki pages? |
| --- | --- | --- |
| `llm-wiki` / `lark-wiki` | Markdown pages, SQLite state, namespaces, frontmatter, `source_ids`, `links_to`, sync metadata | Yes |
| Graphify | Generated relation graph, graph report, graph queries, paths, communities, candidate nodes | No |
| KRM / `query` / `agent_context` | Merged local + derived context for humans and agents | No direct page writes except generated query reports |
| `lark-cli` | Feishu transport: read, create, update, and sync remote documents | No knowledge inference |
| Paper Evidence Workbench | Claim, evidence, open-question drafts for paper work | No |

## Rules

- The source of truth is tracked code, docs, and `knowledge/wiki_src/**`.
- Formal wiki pages are created or updated only by lark-wiki commands that write canonical Markdown.
- Graphify reads the repo and produces generated artifacts under `graphify-out/` and `knowledge/build/graphify/`.
- Graphify output can add relation reasons, provenance, candidates, and explanations, but it must not overwrite `frontmatter.links_to`, `source_ids`, or page ownership.
- KRM merges primary local signals first: `frontmatter.links_to`, `source_ids`, namespace, and page type.
- Graphify relations are secondary signals. A merged edge records `source_layer` as `canonical`, `graphify`, or `mixed`.
- Paper Evidence Workbench drafts stay sidecar until a person promotes them into formal Markdown pages.
- `sync_push` pushes formal wiki pages only. It does not push raw Graphify artifacts or candidate intake.
- `sync_pull` brings remote changes back into local review/merge flow before they become formal pages.

## Default Workflows

For humans:

```bash
python3 scripts/lark_wiki.py inventory --namespace project::agent_workspace
python3 scripts/lark_wiki.py graphify_insights
python3 scripts/lark_wiki.py graphify_candidates --namespace project::agent_workspace
python3 scripts/lark_wiki.py query --namespace project::agent_workspace --query <text>
```

For agents:

```bash
python3 scripts/lark_wiki.py agent_context --namespace project::agent_workspace --query <text>
```

For Graphify refresh:

```bash
$graphify .
python3 scripts/lark_wiki.py graphify_import
```


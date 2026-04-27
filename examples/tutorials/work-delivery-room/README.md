# Work Delivery Room Tutorial

Use this tutorial for a project workspace that keeps delivery context, handoffs, runbooks, risks, and status notes easy to review.

## Setup

```bash
mkdir -p state/llm_wiki.projects knowledge/wiki_src/projects/delivery_room
cp examples/tutorials/work-delivery-room/llm_wiki.projects.delivery_room.toml state/llm_wiki.projects/delivery_room.toml
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::delivery_room
cp examples/tutorials/work-delivery-room/00_Home.md knowledge/wiki_src/projects/delivery_room/00_Home.md
python3 scripts/lark_wiki.py build_graph --namespace project::delivery_room
python3 scripts/lark_wiki.py lint --namespace project::delivery_room
```

## Remote sync

Run `lark-cli auth login` first. For remote writes, sync account/root before project pages.

```bash
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py build_graph --namespace account
python3 scripts/lark_wiki.py sync_push --namespace account --limit 1
python3 scripts/lark_wiki.py sync_push --namespace project::delivery_room --limit 1
```

## How to use it

- Keep durable procedures in `runbooks/weekly-handoff.md`.
- Keep active risks in `risks/risk_log.md`.
- Use Lark Docs/Wiki as the collaboration surface after review.

# Company Collaboration OS Tutorial

Use this tutorial for company-level collaboration: shared standards, team namespaces, project portfolio views, and Base-backed operating records.

## Setup

```bash
mkdir -p state knowledge/wiki_src/shared
cp examples/company-os/llm_wiki.portfolio.toml state/llm_wiki.portfolio.toml
cp examples/tutorials/company-collaboration-os/00_Home.md knowledge/wiki_src/shared/company-collaboration-home.md
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py ingest --namespace shared
python3 scripts/lark_wiki.py build_graph --namespace account
python3 scripts/lark_wiki.py build_graph --namespace shared
```

## Ops Base

`bootstrap_ops_base` and `sync_ops_base` are remote writes. Run them only after confirming the target Base.

```bash
python3 scripts/lark_wiki.py bootstrap_ops_base
python3 scripts/lark_wiki.py sync_ops_base
```

## How to use it

- Put approved rules in `standards/shared-standard.md`.
- Keep operating records in `ops/ops-records.md`.
- Promote project knowledge into `shared` only after review.

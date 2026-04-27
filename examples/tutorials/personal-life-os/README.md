# Personal Life OS Tutorial

Use this tutorial for a personal knowledge base that keeps notes, reading, decisions, and reusable snippets in one local-first workflow.

## Setup

```bash
mkdir -p state/llm_wiki.projects knowledge/wiki_src/projects/personal_life_os
cp examples/tutorials/personal-life-os/llm_wiki.projects.personal_life_os.toml state/llm_wiki.projects/personal_life_os.toml
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::personal_life_os
cp examples/tutorials/personal-life-os/00_Home.md knowledge/wiki_src/projects/personal_life_os/00_Home.md
python3 scripts/lark_wiki.py build_graph --namespace project::personal_life_os
python3 scripts/lark_wiki.py lint --namespace project::personal_life_os
```

## How to use it

- Put private notes under `docs/personal/`.
- Keep reading notes in `reading/reading-log.md`.
- Keep decisions in `decisions/decision-journal.md`.
- Promote only reviewed snippets into `shared`.

## Expected output

You get a namespace home page, an index, a run log, an asset inventory, and a local graph manifest for your personal knowledge base.

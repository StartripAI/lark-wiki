# Personal Knowledge Base Starter

Use this profile for notes, research, decisions, reading logs, and personal operating docs.

Copy the TOML into `state/llm_wiki_v1.local.toml`, then replace placeholder roots and seed nodes with your own workspace values.

```bash
python3 scripts/lark_wiki.py bootstrap_namespace --namespace project::personal_kb
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::personal_kb
python3 scripts/lark_wiki.py build_graph --namespace project::personal_kb
python3 scripts/lark_wiki.py lint --namespace project::personal_kb
```

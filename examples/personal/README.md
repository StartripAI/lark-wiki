# Personal Knowledge Base Starter

Use this profile for notes, research, decisions, reading logs, and personal operating docs.

Copy the project profile into `state/llm_wiki.projects/`, then replace placeholder roots and seed nodes with your own workspace values.

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

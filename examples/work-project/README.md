# Work Project Starter

Use this profile for a team project, client workspace, delivery room, or internal initiative.

The default flow keeps local Markdown canonical and uses Lark/Feishu Docs, Wiki, Base, and Project as work surfaces.

Run the discovery commands after `lark-cli auth login`. If no remote workspace is ready, skip discovery and start with `bootstrap_namespace`.

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

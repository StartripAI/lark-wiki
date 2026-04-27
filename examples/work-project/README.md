# Work Project Starter

Use this profile for a team project, client workspace, delivery room, or internal initiative.

The default flow keeps local Markdown canonical and uses Lark/Feishu Docs, Wiki, Base, and Project as work surfaces.

```bash
python3 scripts/lark_wiki.py discover_feishu_docs
python3 scripts/lark_wiki.py discover_feishu_bases
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::work_hub
python3 scripts/lark_wiki.py build_graph --namespace project::work_hub
python3 scripts/lark_wiki.py lint --namespace project::work_hub
```

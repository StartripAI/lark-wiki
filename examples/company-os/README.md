# Company Operating Wiki Starter

Use this profile for company-level operating knowledge: policies, standards, shared libraries, and project portfolio views.

Start with `account` and `shared`, then add project namespaces as teams adopt the workflow.

```bash
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py ingest --namespace shared
python3 scripts/lark_wiki.py build_graph --namespace account
python3 scripts/lark_wiki.py build_graph --namespace shared
python3 scripts/lark_wiki.py bootstrap_ops_base
python3 scripts/lark_wiki.py sync_ops_base
```

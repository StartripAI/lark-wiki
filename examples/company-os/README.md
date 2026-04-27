# Company Operating Wiki Starter

Use this profile for company-level operating knowledge: policies, standards, shared libraries, and project portfolio views.

Start with `account` and `shared`, then add project namespaces as teams adopt the workflow.

```bash
mkdir -p state knowledge/wiki_src/shared
cp examples/company-os/llm_wiki.portfolio.toml state/llm_wiki.portfolio.toml
cp examples/company-os/shared-library.md knowledge/wiki_src/shared/shared-library.md
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py ingest --namespace account
python3 scripts/lark_wiki.py ingest --namespace shared
python3 scripts/lark_wiki.py build_graph --namespace account
python3 scripts/lark_wiki.py build_graph --namespace shared
python3 scripts/lark_wiki.py bootstrap_ops_base
python3 scripts/lark_wiki.py sync_ops_base
```

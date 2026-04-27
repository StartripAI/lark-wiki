# Research Paper Workbench Tutorial

Use this tutorial for paper-heavy work: reading notes, claim notes, evidence tables, and related-work maps.

## Setup

```bash
mkdir -p state/llm_wiki.projects knowledge/wiki_src/projects/research_workbench
cp examples/tutorials/research-paper-workbench/llm_wiki.projects.research_workbench.toml state/llm_wiki.projects/research_workbench.toml
python3 scripts/lark_wiki.py bootstrap_portfolio
python3 scripts/lark_wiki.py discover_local_repo_assets
python3 scripts/lark_wiki.py classify_assets
python3 scripts/lark_wiki.py ingest --namespace project::research_workbench
cp examples/tutorials/research-paper-workbench/00_Home.md knowledge/wiki_src/projects/research_workbench/00_Home.md
python3 scripts/lark_wiki.py build_graph --namespace project::research_workbench
python3 scripts/lark_wiki.py lint --namespace project::research_workbench
```

## How to use it

- Keep source notes in `sources/paper-inventory.md`.
- Track claims in `claims/claim-register.md`.
- Use `concepts/related-work-map.md` to organize relationships.
- Put useful paper takeaways into `reports/evidence-review.md`.

Paper notes and relation hints are helpers. People still decide what becomes part of the final knowledge base.

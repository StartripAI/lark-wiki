# Optional Analysis Capabilities

The core `lark-wiki` workflow is local Markdown plus `lark-cli`. The strongest analysis layer is the combination of a paper evidence workbench and a knowledge relation map: one tracks evidence, the other tracks structure.

## LLM Provider

Use an LLM provider for source-grounded synthesis and semantic linting.

```toml
[llm]
provider = "auto"
model = "gpt-5.4-mini"
timeout_seconds = 180
semantic_lint_enabled = true
```

## Knowledge Relation Map

Use generated asset graphs, page/source edges, lineage, orphan-page checks, and cross-namespace references to turn scattered documents into a navigable work network. Relation hints are powerful review inputs, not authority.

## Paper Evidence Workspace

Use reviewed research notes, claim registers, evidence tables, and related-work maps to organize papers. The goal is not “summarize a PDF”; the goal is to preserve why a claim is believable, where it came from, and whether it is ready to promote into canonical pages.

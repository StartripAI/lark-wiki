# Optional Analysis Capabilities

The core `lark-wiki` workflow is local Markdown plus `lark-cli`. Optional analysis capabilities are workspace-controlled review inputs and should not replace canonical pages or human approval.

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

Use the generated asset graph and page/source edges to inspect structure, lineage, orphan pages, and cross-namespace references. Treat relation hints as review inputs, not authority.

## Paper Evidence Workspace

Use reviewed research notes, claim registers, evidence tables, and related-work maps to organize papers. Promote only human-reviewed evidence into canonical pages.

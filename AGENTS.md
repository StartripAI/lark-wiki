## Graphify

This repo uses the official Graphify workflow as a codebase and knowledge-map layer.

Rules for agents working here:

- Respect the layer contract in `docs/knowledge-layer-contract.md`: lark-wiki owns formal Markdown, Graphify owns generated relation artifacts, KRM/query/agent_context consume both, lark-cli only transports, and Paper Evidence Workbench stays sidecar until promoted.
- Start every architecture, knowledge-structure, or cross-file relationship task with `python3 scripts/lark_wiki.py agent_context --namespace project::agent_workspace`; treat it as the fixed entry point.
- Use the four blocks returned by `agent_context`: `canonical_inventory`, `derived_graph`, `candidate_intake`, and `transport_readiness`.
- Use the report paths and recommended commands returned by `agent_context` before broad grep searches.
- For deeper relationship questions, read `knowledge/build/graphify/repo/GRAPH_REPORT.md` if it exists.
- If the mirrored report is missing, read `graphify-out/GRAPH_REPORT.md` if it exists.
- If both reports are missing or clearly stale, run the official Graphify skill workflow first: `$graphify .`, then import it with `python3 scripts/lark_wiki.py graphify_import`.
- Treat `$graphify .` as the full graph-generation skill workflow. Treat the installed `graphify` binary as the query/path/explain/update CLI.
- If the shell cannot find `graphify`, `python3 scripts/lark_wiki.py graphify_status` will still show the official refresh command and the current artifact state.
- Prefer `python3 scripts/lark_wiki.py graphify_query --query <text>`, `python3 scripts/lark_wiki.py graphify_path --from <A> --to <B>`, `python3 scripts/lark_wiki.py graphify_explain --node <X>`, and `python3 scripts/lark_wiki.py query --namespace project::agent_workspace --query <text>` before broad grep searches.
- Treat `graphify-out/` and `knowledge/build/graphify/` as generated outputs. They provide relation reasons, candidates, and explanations, not canonical pages.
- Never promote Graphify candidates or Paper Evidence Workbench drafts into formal wiki pages without an explicit user request.

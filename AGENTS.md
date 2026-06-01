## Knowledge Compile — Agent-Native, No LLM Provider (hard boundary)

This repo's tooling is 100% deterministic and **never calls an LLM provider / API / model subprocess** (no API key, no `codex exec` subprocess, no `command` provider). The "LLM" is **you** — the IDE agent (Claude Code / Codex) operating this repo. The Python tool gives you structure, ingest, the internal relation graph, claim/contradiction lint, and lark-cli transport; **you** do the reading and synthesis.

The compile loop (Karpathy-style, agent-native):

1. `python3 scripts/lark_wiki.py ingest --namespace <ns>` registers raw sources and (via `compile_sources`) writes one **summary page per source** under `summaries/`, lifts each source's `Claim:` lines into the wiki, links them through a `source-summaries` hub, and scans the namespace for cross-page claim contradictions. Every `## Synthesis` section starts as an **`AGENT SYNTHESIS TASK`** placeholder.
2. **You (the agent)** open each page containing an `AGENT SYNTHESIS TASK` block, read the cited source(s), and replace the placeholder with a grounded synthesis — conclusions / evidence / contradictions / open questions — citing source keys as `(source: KEY)`. This is how knowledge **compounds**.
3. Re-run `python3 scripts/lark_wiki.py lint --namespace <ns>` to confirm no `semantic_contradiction` issues remain. The contradiction check is deterministic and always on — it needs no model.
4. **Never** wire an `llm.provider`, never shell out to a model. A lingering `AGENT SYNTHESIS TASK` block means a synthesis pass by you is still pending — that is expected, not a bug.

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

## Chinese Humanizer Gate

- For Chinese formal Markdown that will be pushed to Feishu/Lark, run `python3 scripts/humanize_zh.py --apply <path>` before `sync_push`.
- This local gate is inspired by `ai-zixun/humanizer-zh` and is for readability only: it removes translation tone, mechanical headings, empty slogans, and overly model-like structure.
- Do not describe it as AI-detection bypass. The goal is plain Chinese that a human operator can scan.
- After the humanizer pass, show the user a brief of the rewritten content before any remote write.

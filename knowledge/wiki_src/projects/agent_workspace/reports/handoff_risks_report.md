---
{
  "asset_key": "PAGE::project::agent_workspace::handoff-risks-report",
  "links_to": [
    "project::agent_workspace::index",
    "project::agent_workspace::execution-readiness-report"
  ],
  "namespace_key": "project::agent_workspace",
  "page_id": "project::agent_workspace::handoff-risks-report",
  "page_type": "Report",
  "portfolio_key": "portfolio::default",
  "source_ids": [
    "LOCAL::examples/tutorials/work-delivery-room/runbooks/weekly-handoff.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/00_Home.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/01_Index.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/02_Log.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/concepts/agent_system_map.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/entities/agent_ops_catalog.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/reports/aios4game_evidence_gap_resolver_v0_2_sync.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/reports/execution_readiness_report.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/reports/handoff_risks_report.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/sources/asset_inventory.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/sources/ops_base_registry.md",
    "LOCAL::knowledge/wiki_src/projects/agent_workspace/sources/remote_docs_registry.md"
  ],
  "sync_mode": "bidirectional_markdown_safe",
  "title": "Handoff Risks Report"
}
---

# Handoff Risks Report

## Common failure modes

- remote docs drift from local canonical markdown
- base schemas change without refreshing snapshots
- project snapshots go stale and weaken synthesis quality
- LLM prompts over-expand if asset budgets are not capped

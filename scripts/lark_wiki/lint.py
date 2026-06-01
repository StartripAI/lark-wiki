from __future__ import annotations

from collections import Counter, defaultdict
import json
import sqlite3

from .config import AppConfig
from .db import has_cross_scope_edge, record_issue
from .lark_cli import docs_fetch_full
from .llm_compile import detect_claim_contradictions
from .markdown import normalize_markdown_for_sync, read_frontmatter
from .ops_base import OPS_TABLE_SPECS, compute_ops_base_state
from .portfolio import namespaced_page_id
from .utils import relative_to_root


def _is_generated_query_page(page_id: str) -> bool:
    return "::query-" in page_id or page_id.endswith("::query")


def lint(conn: sqlite3.Connection, config: AppConfig, namespace_key: str | None = None) -> dict[str, object]:
    namespace_key = namespace_key or config.default_project_namespace
    conn.execute(
        """
        DELETE FROM issues
        WHERE namespace_key = ?
          AND issue_type IN (
            'duplicate_page_title',
            'orphan_page',
            'unclassified_asset',
            'missing_source_asset',
            'broken_page_link',
            'cross_namespace_source_reference',
            'cross_namespace_page_link',
            'inbox_asset_consumed',
            'invalid_reconstructed_manifest',
            'remote_mirror_drift',
            'ops_base_out_of_sync',
            'semantic_contradiction',
            'semantic_stale_claim',
            'semantic_missing_page',
            'semantic_missing_cross_reference'
        )
        """,
        (namespace_key,),
    )
    conn.execute("DELETE FROM issues WHERE namespace_key = ? AND issue_type = 'conformance_violation'", (namespace_key,))
    pages = conn.execute(
        "SELECT page_id, local_path FROM pages WHERE namespace_key = ?",
        (namespace_key,),
    ).fetchall()
    title_map: dict[str, list[str]] = defaultdict(list)
    incoming: Counter[str] = Counter()
    page_ids = {row["page_id"] for row in pages}
    page_bodies: list[dict[str, str]] = []
    for row in pages:
        path = config.root / row["local_path"]
        frontmatter, body = read_frontmatter(path)
        page_bodies.append({"page_id": row["page_id"], "body": body})
        title_map[frontmatter.get("title", row["page_id"])].append(row["page_id"])
        for source_id in frontmatter.get("source_ids", []):
            source_row = conn.execute("SELECT asset_key, namespace_key FROM assets WHERE asset_key = ?", (source_id,)).fetchone()
            if not source_row:
                record_issue(conn, issue_type="missing_source_asset", severity="high", page_id=row["page_id"], namespace_key=namespace_key, detail={"source_id": source_id})
                continue
            if source_row["namespace_key"] == config.inbox_namespace_key and namespace_key != config.inbox_namespace_key:
                record_issue(
                    conn,
                    issue_type="inbox_asset_consumed",
                    severity="high",
                    page_id=row["page_id"],
                    namespace_key=namespace_key,
                    detail={"source_id": source_id},
                )
            if source_row["namespace_key"] != namespace_key and not has_cross_scope_edge(
                conn,
                from_namespace_key=namespace_key,
                to_namespace_key=source_row["namespace_key"],
                edge_type="page_source",
                from_ref=row["page_id"],
                to_ref=source_id,
            ):
                record_issue(
                    conn,
                    issue_type="cross_namespace_source_reference",
                    severity="high",
                    page_id=row["page_id"],
                    namespace_key=namespace_key,
                    detail={"source_id": source_id, "source_namespace": source_row["namespace_key"]},
                )
        for linked in frontmatter.get("links_to", []):
            incoming[linked] += 1
            linked_row = conn.execute("SELECT page_id, namespace_key FROM pages WHERE page_id = ?", (linked,)).fetchone()
            if not linked_row:
                record_issue(conn, issue_type="broken_page_link", severity="medium", page_id=row["page_id"], namespace_key=namespace_key, detail={"linked_page_id": linked})
                continue
            if linked_row["namespace_key"] != namespace_key and not has_cross_scope_edge(
                conn,
                from_namespace_key=namespace_key,
                to_namespace_key=linked_row["namespace_key"],
                edge_type="page_link",
                from_ref=row["page_id"],
                to_ref=linked,
            ):
                record_issue(
                    conn,
                    issue_type="cross_namespace_page_link",
                    severity="high",
                    page_id=row["page_id"],
                    namespace_key=namespace_key,
                    detail={"linked_page_id": linked, "linked_namespace": linked_row["namespace_key"]},
                )
    for title, page_ids in title_map.items():
        if len(page_ids) > 1:
            for page_id in page_ids:
                record_issue(conn, issue_type="duplicate_page_title", severity="medium", page_id=page_id, namespace_key=namespace_key, detail={"title": title, "page_ids": page_ids})
    for row in pages:
        if row["page_id"] in {
            namespaced_page_id(namespace_key, "home"),
            namespaced_page_id(namespace_key, "index"),
            namespaced_page_id(namespace_key, "log"),
        }:
            continue
        if _is_generated_query_page(str(row["page_id"])):
            continue
        if incoming[row["page_id"]] == 0:
            record_issue(conn, issue_type="orphan_page", severity="medium", page_id=row["page_id"], namespace_key=namespace_key, detail={"page_id": row["page_id"]})
    unclassified = conn.execute(
        "SELECT asset_key, title FROM assets WHERE namespace_key = ? AND classification_status = 'unclassified'",
        (namespace_key,),
    ).fetchall()
    for row in unclassified:
        record_issue(conn, issue_type="unclassified_asset", severity="low", asset_key=row["asset_key"], namespace_key=namespace_key, detail={"title": row["title"]})

    required_manifest_keys = {
        "asset_key",
        "asset_class",
        "owner_surface",
        "publish_mode",
        "remote_url",
        "remote_id",
        "source_hash",
        "local_source_path",
    }
    reconstructed_rows = conn.execute(
        """
        SELECT asset_key, local_path
        FROM assets
        WHERE asset_class = 'manifest'
          AND json_extract(metadata_json, '$.reconstructed_stub') = 1
        """
    ).fetchall()
    invalid_reconstructed = 0
    for row in reconstructed_rows:
        manifest_path = config.root / row["local_path"]
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            payload = {}
        missing = sorted(required_manifest_keys.difference(payload.keys()))
        if missing:
            invalid_reconstructed += 1
            record_issue(
                conn,
                issue_type="invalid_reconstructed_manifest",
                severity="high",
                asset_key=row["asset_key"],
                namespace_key=namespace_key,
                detail={"missing_keys": missing, "local_path": row["local_path"]},
            )

    remote_drift_count = 0
    mirror_pages = conn.execute(
        "SELECT page_id, local_path, mirror_doc_token FROM pages WHERE namespace_key = ? AND mirror_doc_token != ''",
        (namespace_key,),
    ).fetchall()
    for row in mirror_pages:
        frontmatter, body = read_frontmatter(config.root / row["local_path"])
        remote = docs_fetch_full(config, row["mirror_doc_token"])
        if normalize_markdown_for_sync(body) != normalize_markdown_for_sync(remote.get("markdown", "")):
            remote_drift_count += 1
            record_issue(
                conn,
                issue_type="remote_mirror_drift",
                severity="high",
                page_id=row["page_id"],
                namespace_key=namespace_key,
                detail={"mirror_doc_token": row["mirror_doc_token"], "title": frontmatter.get("title", row["page_id"])},
            )

    ops_base_state = compute_ops_base_state(conn)
    ops_lag_count = 0
    for table_name in OPS_TABLE_SPECS:
        if table_name in {"runs", "issues"}:
            continue
        synced_signature = conn.execute(
            "SELECT cursor_value FROM sync_cursor WHERE cursor_key = ?",
            (f"ops_base_sync::{table_name}::signature",),
        ).fetchone()
        signature = synced_signature[0] if synced_signature else ""
        if signature != ops_base_state[table_name]["signature"]:
            ops_lag_count += 1
            record_issue(
                conn,
                issue_type="ops_base_out_of_sync",
                severity="medium",
                asset_key=f"BASE::{table_name}",
                namespace_key=config.account_namespace_key,
                detail={
                    "table_name": table_name,
                    "local_count": ops_base_state[table_name]["count"],
                    "expected_signature": ops_base_state[table_name]["signature"],
                    "synced_signature": signature,
                },
            )

    # Deterministic, provider-free contradiction check. Deeper semantic review
    # (stale claims, missing pages) is the host IDE agent's job per AGENTS.md;
    # this tool never calls a model.
    for finding in detect_claim_contradictions(page_bodies):
        record_issue(
            conn,
            issue_type="semantic_contradiction",
            severity="high",
            page_id=finding["page_ids"].split(",")[0].strip() or None,
            namespace_key=namespace_key,
            detail=finding,
        )

    issue_count = conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'open' AND namespace_key = ?", (namespace_key,)).fetchone()[0]
    missing_source_count = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE issue_type = 'missing_source_asset' AND status = 'open' AND namespace_key = ?",
        (namespace_key,),
    ).fetchone()[0]
    cross_namespace_source_count = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE issue_type = 'cross_namespace_source_reference' AND status = 'open' AND namespace_key = ?",
        (namespace_key,),
    ).fetchone()[0]
    cross_namespace_link_count = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE issue_type = 'cross_namespace_page_link' AND status = 'open' AND namespace_key = ?",
        (namespace_key,),
    ).fetchone()[0]
    inbox_asset_consumed_count = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE issue_type = 'inbox_asset_consumed' AND status = 'open' AND namespace_key = ?",
        (namespace_key,),
    ).fetchone()[0]
    report_name = "lint_report_account.md" if namespace_key == config.account_namespace_key else f"lint_report_{namespace_key.replace('::', '_')}.md"
    report_path = config.build_dir / report_name
    report_path.write_text(
        "\n".join(
            [
                "# Lint Report",
                "",
                f"- namespace: **{namespace_key}**",
                f"- open issues: **{issue_count}**",
                f"- duplicate titles: **{len([1 for items in title_map.values() if len(items) > 1])}**",
                f"- orphan pages: **{len([1 for row in pages if row['page_id'] not in {namespaced_page_id(namespace_key, 'home'), namespaced_page_id(namespace_key, 'index'), namespaced_page_id(namespace_key, 'log')} and incoming[row['page_id']] == 0])}**",
                f"- unclassified assets: **{len(unclassified)}**",
                f"- missing source assets: **{missing_source_count}**",
                f"- cross namespace source refs: **{cross_namespace_source_count}**",
                f"- cross namespace page links: **{cross_namespace_link_count}**",
                f"- inbox assets consumed: **{inbox_asset_consumed_count}**",
                f"- invalid reconstructed manifests: **{invalid_reconstructed}**",
                f"- remote mirror drift: **{remote_drift_count}**",
                f"- ops base lagging tables: **{ops_lag_count}**",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    conn.commit()
    return {"issue_count": issue_count, "report_path": relative_to_root(report_path, config.root)}

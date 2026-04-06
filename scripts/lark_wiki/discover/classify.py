from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from ..config import AppConfig
from ..db import bootstrap_namespaces, record_issue
from ..portfolio import namespace_root_relpath
from ..utils import json_dumps, now_iso, relative_to_root


LEGACY_CANONICAL_ROOT_ENTRIES = (
    "00_Home.md",
    "01_Index.md",
    "02_Log.md",
    "sources",
    "concepts",
    "entities",
    "reports",
    "legacy",
)


def cleanup_legacy_canonical_layout(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    removed_files: list[str] = []
    for entry_name in LEGACY_CANONICAL_ROOT_ENTRIES:
        target = config.wiki_src_dir / entry_name
        if not target.exists():
            continue
        if target.is_dir():
            removed_files.extend(
                relative_to_root(path, config.root)
                for path in sorted(target.rglob("*"))
                if path.is_file()
            )
            shutil.rmtree(target)
        else:
            removed_files.append(relative_to_root(target, config.root))
            target.unlink()
    if removed_files:
        placeholders = ",".join("?" for _ in removed_files)
        conn.execute(f"DELETE FROM pages WHERE local_path IN ({placeholders})", tuple(removed_files))
        conn.execute(f"DELETE FROM assets WHERE local_path IN ({placeholders})", tuple(removed_files))
        conn.commit()
    return {
        "removed_count": len(removed_files),
        "removed_paths": removed_files,
    }


def bootstrap_portfolio(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    cleanup = cleanup_legacy_canonical_layout(conn, config)
    bootstrap_namespaces(conn, config)
    rows = conn.execute(
        "SELECT namespace_key, display_name, kind, slug FROM namespaces ORDER BY namespace_key"
    ).fetchall()
    return {
        "portfolio_key": config.portfolio_key,
        "namespace_count": len(rows),
        "namespaces": [dict(row) for row in rows],
        "legacy_cleanup": cleanup,
    }


def _title_text(row: sqlite3.Row) -> str:
    title = row["title"] or ""
    metadata = row["metadata_json"] or ""
    return f"{title}\n{metadata}"


def _namespace_matches_local_path(namespace_local_roots: tuple[str, ...], local_path: str) -> bool:
    return any(local_path == root or local_path.startswith(f"{root}/") for root in namespace_local_roots)


def _derive_namespace_for_asset(config: AppConfig, row: sqlite3.Row) -> tuple[str, str]:
    local_path = row["local_path"] or ""
    asset_key = row["asset_key"] or ""
    remote_id = row["remote_id"] or ""
    title_text = _title_text(row).lower()

    if local_path.startswith("knowledge/wiki_src/"):
        for namespace_key in config.namespaces:
            root_prefix = f"knowledge/wiki_src/{namespace_root_relpath(config, namespace_key)}"
            if local_path == root_prefix or local_path.startswith(f"{root_prefix}/"):
                return namespace_key, "classified"

    for namespace_key, namespace in config.namespaces.items():
        if namespace.kind != "project":
            continue
        if local_path and _namespace_matches_local_path(namespace.local_roots, local_path):
            return namespace_key, "classified"
        if remote_id and remote_id in namespace.base_tokens:
            return namespace_key, "classified"
        if namespace.wiki_seed_nodes and remote_id in namespace.wiki_seed_nodes:
            return namespace_key, "classified"
        if namespace.title_keywords and any(keyword.lower() in title_text for keyword in namespace.title_keywords):
            return namespace_key, "classified"
        if namespace.project_env_path and local_path == relative_to_root(namespace.project_env_path, config.root):
            return namespace_key, "classified"
        if namespace.project_sync_db_path and local_path == relative_to_root(namespace.project_sync_db_path, config.root):
            return namespace_key, "classified"
        if namespace.orchestrator_db_path and local_path == relative_to_root(namespace.orchestrator_db_path, config.root):
            return namespace_key, "classified"
        if namespace.master_csv_path and local_path == relative_to_root(namespace.master_csv_path, config.root):
            return namespace_key, "classified"

    if asset_key in {"STATE::local_repo_assets_snapshot", "STATE::feishu_docs_discovery"}:
        return config.account_namespace_key, "classified"
    if asset_key.startswith("STATE::graph_manifest::"):
        graph_namespace = asset_key.removeprefix("STATE::graph_manifest::")
        if graph_namespace in config.namespaces:
            return graph_namespace, "classified"
    if asset_key == "STATE::lineage_summary":
        return config.default_project_namespace, "classified"
    if asset_key.startswith("STATE::upgrade_preflight") or asset_key.startswith("BASE::") or asset_key.startswith("STATE::ops_base"):
        return config.account_namespace_key, "classified"
    return config.inbox_namespace_key, "inbox"


def _classify_asset_row(conn: sqlite3.Connection, config: AppConfig, row: sqlite3.Row) -> tuple[str, str]:
    current_namespace = row["namespace_key"] or ""
    current_status = row["classification_status"] or ""
    if current_status == "classified" and current_namespace in config.namespaces:
        if current_namespace != config.inbox_namespace_key:
            return current_namespace, current_status
        derived_namespace, derived_status = _derive_namespace_for_asset(config, row)
        if derived_namespace != config.inbox_namespace_key or derived_status != "inbox":
            return derived_namespace, derived_status
        return current_namespace, current_status
    return _derive_namespace_for_asset(config, row)


def classify_assets(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    cleanup = cleanup_legacy_canonical_layout(conn, config)
    bootstrap_namespaces(conn, config)
    rows = conn.execute(
        """
        SELECT asset_key, title, local_path, remote_id, metadata_json
               , namespace_key, classification_status
        FROM assets
        ORDER BY asset_key
        """
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        namespace_key, status = _classify_asset_row(conn, config, row)
        conn.execute(
            """
            UPDATE assets
            SET portfolio_key = ?, namespace_key = ?, classification_status = ?
            WHERE asset_key = ?
            """,
            (config.portfolio_key, namespace_key, status, row["asset_key"]),
        )
        counts[namespace_key] = counts.get(namespace_key, 0) + 1
    conn.commit()
    return {
        "classified_count": len(rows),
        "counts": counts,
        "legacy_cleanup": cleanup,
    }


def discover_account_assets(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    from .feishu_bases import discover_feishu_bases
    from .feishu_docs import discover_feishu_docs
    from .feishu_project import discover_feishu_project
    from .local_repo import discover_local_repo_assets
    from .state_lineage import discover_state_lineage

    summary = {
        "local_repo": discover_local_repo_assets(conn, config),
        "feishu_docs": discover_feishu_docs(conn, config),
        "feishu_bases": discover_feishu_bases(conn, config),
        "feishu_project": discover_feishu_project(conn, config),
        "state_lineage": discover_state_lineage(conn, config),
    }
    summary["classification"] = classify_assets(conn, config)
    coverage_path = config.raw_dir / "coverage" / "discover_account_assets.json"
    coverage_path.write_text(json_dumps({"generated_at": now_iso(), "summary": summary}), encoding="utf-8")
    return summary


def audit_coverage(conn: sqlite3.Connection, config: AppConfig, scope: str = "account", namespace_key: str = "") -> dict[str, object]:
    params: list[object] = []
    where = ""
    if scope == "namespace" and namespace_key:
        where = "WHERE namespace_key = ?"
        params.append(namespace_key)
    rows = conn.execute(
        f"""
        SELECT asset_key, asset_class, namespace_key, classification_status, canonical_role, local_path, remote_url
        FROM assets
        {where}
        ORDER BY namespace_key, asset_key
        """,
        tuple(params),
    ).fetchall()
    undiscovered = 0
    unclassified = 0
    identity_conflict = 0
    items: list[dict[str, str]] = []
    for row in rows:
        status = "covered"
        if not row["namespace_key"]:
            undiscovered += 1
            status = "undiscovered"
        elif row["classification_status"] == "unclassified":
            unclassified += 1
            status = "unclassified"
        items.append(
            {
                "asset_key": row["asset_key"],
                "asset_class": row["asset_class"],
                "namespace_key": row["namespace_key"],
                "classification_status": row["classification_status"],
                "canonical_role": row["canonical_role"],
                "coverage_status": status,
            }
        )
    if scope == "namespace" and namespace_key:
        all_rows = conn.execute(
            """
            SELECT asset_key, title, local_path, remote_id, metadata_json, namespace_key, classification_status
            FROM assets
            ORDER BY asset_key
            """
        ).fetchall()
        for row in all_rows:
            expected_namespace, expected_status = _derive_namespace_for_asset(config, row)
            current_namespace = row["namespace_key"] or ""
            current_status = row["classification_status"] or ""
            if (
                expected_namespace == namespace_key
                and current_namespace != namespace_key
                and (not current_namespace or current_namespace == config.inbox_namespace_key or current_status != "classified")
            ):
                undiscovered += 1
                items.append(
                    {
                        "asset_key": row["asset_key"],
                        "asset_class": "expected_namespace_miss",
                        "namespace_key": current_namespace or "",
                        "classification_status": expected_status,
                        "canonical_role": "",
                        "coverage_status": "undiscovered",
                    }
                )
    page_where = ""
    page_params: list[object] = []
    if scope == "namespace" and namespace_key:
        page_where = "WHERE p.namespace_key = ?"
        page_params.append(namespace_key)
    conflict_rows = conn.execute(
        f"""
        SELECT p.page_id, p.namespace_key AS page_namespace, a.namespace_key AS asset_namespace, p.asset_key, p.local_path
        FROM pages p
        LEFT JOIN assets a ON a.asset_key = p.asset_key
        {page_where}
        """
        ,
        tuple(page_params),
    ).fetchall()
    for row in conflict_rows:
        local_path = row["local_path"] or ""
        page_namespace = row["page_namespace"] or ""
        asset_namespace = row["asset_namespace"] or ""
        if asset_namespace and asset_namespace != page_namespace:
            identity_conflict += 1
            items.append(
                {
                    "asset_key": row["asset_key"] or "",
                    "asset_class": "page_binding",
                    "namespace_key": page_namespace,
                    "classification_status": "classified",
                    "canonical_role": "canonical_page",
                    "coverage_status": "identity_conflict",
                }
            )
        if local_path.startswith("knowledge/wiki_src/") and not (
            local_path.startswith("knowledge/wiki_src/account/")
            or local_path.startswith("knowledge/wiki_src/projects/")
            or local_path.startswith("knowledge/wiki_src/shared/")
            or local_path.startswith("knowledge/wiki_src/inbox/")
        ):
            identity_conflict += 1
            items.append(
                {
                    "asset_key": row["asset_key"] or "",
                    "asset_class": "page_binding",
                    "namespace_key": page_namespace,
                    "classification_status": "classified",
                    "canonical_role": "canonical_page",
                    "coverage_status": "identity_conflict",
                }
            )
    report = {
        "scope": scope,
        "namespace_key": namespace_key,
        "asset_count": len(rows),
        "undiscovered": undiscovered,
        "identity_conflict": identity_conflict,
        "unclassified": unclassified,
        "items": items,
    }
    path = config.build_dir / f"audit_coverage_{namespace_key or scope}.json"
    path.write_text(json_dumps(report), encoding="utf-8")
    return report


def conformance_check(conn: sqlite3.Connection, config: AppConfig, scope: str = "account", namespace_key: str = "") -> dict[str, object]:
    from ..lint import lint

    audit = audit_coverage(conn, config, scope=scope, namespace_key=namespace_key)
    violations: list[dict[str, str]] = []
    if audit["undiscovered"]:
        violations.append({"type": "undiscovered_assets", "count": str(audit["undiscovered"])})
    if audit["unclassified"]:
        violations.append({"type": "unclassified_assets", "count": str(audit["unclassified"])})
    if audit["identity_conflict"]:
        violations.append({"type": "identity_conflict", "count": str(audit["identity_conflict"])})
    namespace_audits: list[dict[str, object]] = []
    if scope == "account":
        for scoped_namespace in config.namespaces:
            namespace_audit = audit_coverage(conn, config, scope="namespace", namespace_key=scoped_namespace)
            namespace_audits.append(namespace_audit)
            if namespace_audit["undiscovered"]:
                violations.append(
                    {
                        "type": "undiscovered_assets",
                        "namespace_key": scoped_namespace,
                        "count": str(namespace_audit["undiscovered"]),
                    }
                )
            if namespace_audit["unclassified"]:
                violations.append(
                    {
                        "type": "unclassified_assets",
                        "namespace_key": scoped_namespace,
                        "count": str(namespace_audit["unclassified"]),
                    }
                )
            if namespace_audit["identity_conflict"]:
                violations.append(
                    {
                        "type": "identity_conflict",
                        "namespace_key": scoped_namespace,
                        "count": str(namespace_audit["identity_conflict"]),
                    }
                )
    lint_namespaces = [namespace_key] if scope == "namespace" and namespace_key else list(config.namespaces)
    lint_results: list[dict[str, object]] = []
    for lint_namespace in lint_namespaces:
        lint_result = lint(conn, config, namespace_key=lint_namespace)
        lint_results.append({"namespace_key": lint_namespace, **lint_result})
        if lint_result["issue_count"]:
            violations.append({"type": "lint_issues", "namespace_key": lint_namespace, "count": str(lint_result["issue_count"])})
    if violations:
        for violation in violations:
            record_issue(
                conn,
                issue_type="conformance_violation",
                severity="high",
                namespace_key=namespace_key or config.account_namespace_key,
                detail=violation,
            )
    conn.commit()
    return {
        "ok": not violations,
        "violations": violations,
        "audit": audit,
        "namespace_audits": namespace_audits,
        "lint_results": lint_results,
    }

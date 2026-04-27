from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time_ns
from typing import Any

from .config import AppConfig
from .utils import now_iso, sha256_text


ASSET_CLASSES = {
    "local_file",
    "local_db",
    "wiki_doc",
    "wiki_node",
    "base_app",
    "base_table",
    "project_space",
    "project_work_item",
    "manifest",
    "state_snapshot",
    "online_doc",
}

TABLE_COLUMNS: dict[str, dict[str, str]] = {
    "namespaces": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "display_name": "TEXT NOT NULL DEFAULT ''",
        "kind": "TEXT NOT NULL DEFAULT 'project'",
        "slug": "TEXT NOT NULL DEFAULT ''",
        "isolation_mode": "TEXT NOT NULL DEFAULT 'strict'",
        "root_local_path": "TEXT NOT NULL DEFAULT ''",
        "remote_root_node_token": "TEXT NOT NULL DEFAULT ''",
        "config_json": "TEXT NOT NULL DEFAULT '{}'",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    },
    "assets": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'inbox'",
        "classification_status": "TEXT NOT NULL DEFAULT 'unclassified'",
    },
    "pages": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'inbox'",
    },
    "runs": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'account'",
        "host_pid": "TEXT NOT NULL DEFAULT ''",
    },
    "issues": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'account'",
    },
    "merge_queue": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'inbox'",
    },
    "sync_cursor": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'account'",
    },
    "legacy_redirects": {
        "portfolio_key": "TEXT NOT NULL DEFAULT 'portfolio::default'",
        "namespace_key": "TEXT NOT NULL DEFAULT 'account'",
    },
}


def ensure_dirs(config: AppConfig) -> None:
    for path in [
        config.state_dir,
        config.knowledge_root,
        config.raw_dir,
        config.wiki_src_dir,
        config.assets_dir,
        config.build_dir,
        config.merge_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    for subdir in [
        "account",
        "projects",
        "shared",
        "inbox",
    ]:
        (config.wiki_src_dir / subdir).mkdir(parents=True, exist_ok=True)
    for namespace in config.namespaces.values():
        if namespace.kind == "project":
            for subdir in ["sources", "concepts", "entities", "reports", "legacy"]:
                (config.wiki_src_dir / "projects" / namespace.slug / subdir).mkdir(parents=True, exist_ok=True)
    for subdir in ["local_repo", "feishu_docs", "feishu_bases", "feishu_project", "state_lineage", "coverage"]:
        (config.raw_dir / subdir).mkdir(parents=True, exist_ok=True)


def open_db(config: AppConfig) -> sqlite3.Connection:
    ensure_dirs(config)
    conn = sqlite3.connect(config.state_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    init_db(conn, config)
    abandon_stale_runs(conn)
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    if not _table_exists(conn, table_name):
        return
    existing = _table_columns(conn, table_name)
    for column_name, column_sql in columns.items():
        if column_name in existing:
            continue
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def init_db(conn: sqlite3.Connection, config: AppConfig) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    statements = [
        statement.strip()
        for statement in schema_path.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    index_statements = [statement for statement in statements if statement.upper().startswith("CREATE INDEX") or statement.upper().startswith("CREATE UNIQUE INDEX")]
    table_statements = [statement for statement in statements if statement not in index_statements]
    for statement in table_statements:
        conn.execute(statement)
    for table_name, columns in TABLE_COLUMNS.items():
        _ensure_columns(conn, table_name, columns)
    for statement in index_statements:
        conn.execute(statement)
    conn.commit()
    bootstrap_namespaces(conn, config)


def bootstrap_namespaces(conn: sqlite3.Connection, config: AppConfig) -> None:
    for namespace_key, namespace in config.namespaces.items():
        root_local_path = "account"
        if namespace.kind == "project":
            root_local_path = f"projects/{namespace.slug}"
        elif namespace.kind in {"shared", "inbox"}:
            root_local_path = namespace.slug
        conn.execute(
            """
            INSERT INTO namespaces (
                namespace_key, portfolio_key, display_name, kind, slug,
                isolation_mode, root_local_path, remote_root_node_token,
                config_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace_key) DO UPDATE SET
                portfolio_key=excluded.portfolio_key,
                display_name=excluded.display_name,
                kind=excluded.kind,
                slug=excluded.slug,
                isolation_mode=excluded.isolation_mode,
                root_local_path=excluded.root_local_path,
                config_json=excluded.config_json,
                updated_at=excluded.updated_at
            """,
            (
                namespace_key,
                config.portfolio_key,
                namespace.display_name,
                namespace.kind,
                namespace.slug,
                "strict",
                root_local_path,
                "",
                json.dumps(
                    {
                        "target_root_title": namespace.target_root_title,
                        "local_roots": list(namespace.local_roots),
                        "title_keywords": list(namespace.title_keywords),
                        "wiki_seed_nodes": list(namespace.wiki_seed_nodes),
                        "base_tokens": list(namespace.base_tokens),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                now_iso(),
                now_iso(),
            ),
        )
    conn.commit()


def abandon_stale_runs(conn: sqlite3.Connection, max_age_minutes: int = 10) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    stale_rows = conn.execute(
        """
        SELECT run_id, started_at, host_pid
        FROM runs
        WHERE status = 'running'
        """
    ).fetchall()
    abandoned = 0
    for row in stale_rows:
        started_at = row["started_at"] or ""
        try:
            started_dt = datetime.fromisoformat(started_at)
        except ValueError:
            started_dt = cutoff - timedelta(seconds=1)
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=timezone.utc)
        host_pid = str(row["host_pid"] or "").strip() if "host_pid" in row.keys() else ""
        pid_is_alive = False
        if host_pid.isdigit():
            try:
                os.kill(int(host_pid), 0)
                pid_is_alive = True
            except OSError:
                pid_is_alive = False
        if pid_is_alive:
            continue
        conn.execute(
            """
            UPDATE runs
            SET status = 'abandoned',
                finished_at = COALESCE(finished_at, ?),
                error_text = CASE
                    WHEN error_text = '' THEN 'stale run reconciled on open'
                    ELSE error_text
                END
            WHERE run_id = ?
            """,
            (now_iso(), row["run_id"]),
        )
        abandoned += 1
    if abandoned:
        conn.commit()
    return abandoned


def upsert_asset(
    conn: sqlite3.Connection,
    *,
    asset_key: str,
    asset_class: str,
    title: str,
    local_path: str = "",
    remote_url: str = "",
    remote_id: str = "",
    upstream_system: str = "",
    source_hash: str = "",
    canonical_role: str = "",
    sync_mode: str = "",
    portfolio_key: str = "portfolio::default",
    namespace_key: str = "inbox",
    classification_status: str = "unclassified",
    last_seen_at: str | None = None,
    last_synced_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"Unsupported asset class: {asset_class}")
    conn.execute(
        """
        INSERT INTO assets (
            asset_key, portfolio_key, namespace_key, asset_class, title, local_path, remote_url, remote_id,
            upstream_system, source_hash, canonical_role, sync_mode, classification_status, last_seen_at,
            last_synced_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_key) DO UPDATE SET
            portfolio_key=excluded.portfolio_key,
            namespace_key=excluded.namespace_key,
            asset_class=excluded.asset_class,
            title=excluded.title,
            local_path=excluded.local_path,
            remote_url=excluded.remote_url,
            remote_id=excluded.remote_id,
            upstream_system=excluded.upstream_system,
            source_hash=excluded.source_hash,
            canonical_role=excluded.canonical_role,
            sync_mode=excluded.sync_mode,
            classification_status=excluded.classification_status,
            last_seen_at=excluded.last_seen_at,
            last_synced_at=COALESCE(excluded.last_synced_at, assets.last_synced_at),
            metadata_json=excluded.metadata_json
        """,
        (
            asset_key,
            portfolio_key,
            namespace_key,
            asset_class,
            title,
            local_path,
            remote_url,
            remote_id,
            upstream_system,
            source_hash,
            canonical_role,
            sync_mode,
            classification_status,
            last_seen_at or now_iso(),
            last_synced_at,
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        ),
    )


def upsert_asset_edge(conn: sqlite3.Connection, from_key: str, to_key: str, edge_type: str, detail: dict[str, Any] | None = None) -> None:
    conn.execute(
        """
        INSERT INTO asset_edges (from_asset_key, to_asset_key, edge_type, detail_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(from_asset_key, to_asset_key, edge_type) DO UPDATE SET
            detail_json=excluded.detail_json,
            updated_at=excluded.updated_at
        """,
        (from_key, to_key, edge_type, json.dumps(detail or {}, ensure_ascii=False, sort_keys=True), now_iso()),
    )


def allow_cross_scope_edge(
    conn: sqlite3.Connection,
    *,
    portfolio_key: str,
    from_namespace_key: str,
    to_namespace_key: str,
    edge_type: str,
    from_ref: str = "",
    to_ref: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    edge_key = sha256_text("|".join([portfolio_key, from_namespace_key, to_namespace_key, edge_type, from_ref, to_ref, json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)]))
    conn.execute(
        """
        INSERT INTO cross_scope_edges (
            edge_key, portfolio_key, from_namespace_key, to_namespace_key,
            from_ref, to_ref, edge_type, detail_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(edge_key) DO UPDATE SET
            detail_json=excluded.detail_json,
            updated_at=excluded.updated_at
        """,
        (
            edge_key,
            portfolio_key,
            from_namespace_key,
            to_namespace_key,
            from_ref,
            to_ref,
            edge_type,
            json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
            now_iso(),
        ),
    )


def has_cross_scope_edge(
    conn: sqlite3.Connection,
    *,
    from_namespace_key: str,
    to_namespace_key: str,
    edge_type: str,
    from_ref: str = "",
    to_ref: str = "",
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM cross_scope_edges
        WHERE from_namespace_key = ?
          AND to_namespace_key = ?
          AND edge_type = ?
          AND (? = '' OR from_ref IN ('', ?))
          AND (? = '' OR to_ref IN ('', ?))
        LIMIT 1
        """,
        (from_namespace_key, to_namespace_key, edge_type, from_ref, from_ref, to_ref, to_ref),
    ).fetchone()
    return row is not None


def upsert_page(
    conn: sqlite3.Connection,
    *,
    page_id: str,
    page_type: str,
    asset_key: str,
    local_path: str,
    mirror_doc_token: str = "",
    mirror_node_token: str = "",
    last_local_hash: str = "",
    last_remote_hash: str = "",
    sync_mode: str = "bidirectional_markdown_safe",
    portfolio_key: str = "portfolio::default",
    namespace_key: str = "inbox",
    last_synced_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    existing = conn.execute("SELECT metadata_json FROM pages WHERE page_id = ?", (page_id,)).fetchone()
    merged_metadata: dict[str, Any] = {}
    if existing and existing["metadata_json"]:
        merged_metadata.update(json.loads(existing["metadata_json"]))
    merged_metadata.update(metadata or {})
    conn.execute(
        """
        INSERT INTO pages (
            page_id, portfolio_key, namespace_key, page_type, asset_key, local_path, mirror_doc_token, mirror_node_token,
            last_local_hash, last_remote_hash, sync_mode, last_synced_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(page_id) DO UPDATE SET
            portfolio_key=excluded.portfolio_key,
            namespace_key=excluded.namespace_key,
            page_type=excluded.page_type,
            asset_key=excluded.asset_key,
            local_path=excluded.local_path,
            mirror_doc_token=COALESCE(NULLIF(excluded.mirror_doc_token, ''), pages.mirror_doc_token),
            mirror_node_token=COALESCE(NULLIF(excluded.mirror_node_token, ''), pages.mirror_node_token),
            last_local_hash=COALESCE(NULLIF(excluded.last_local_hash, ''), pages.last_local_hash),
            last_remote_hash=COALESCE(NULLIF(excluded.last_remote_hash, ''), pages.last_remote_hash),
            sync_mode=excluded.sync_mode,
            last_synced_at=COALESCE(excluded.last_synced_at, pages.last_synced_at),
            metadata_json=excluded.metadata_json
        """,
        (
            page_id,
            portfolio_key,
            namespace_key,
            page_type,
            asset_key,
            local_path,
            mirror_doc_token,
            mirror_node_token,
            last_local_hash,
            last_remote_hash,
            sync_mode,
            last_synced_at,
            json.dumps(merged_metadata, ensure_ascii=False, sort_keys=True),
        ),
    )


def record_issue(
    conn: sqlite3.Connection,
    *,
    issue_type: str,
    severity: str,
    asset_key: str = "",
    page_id: str = "",
    portfolio_key: str = "portfolio::default",
    namespace_key: str = "account",
    detail: dict[str, Any] | None = None,
    status: str = "open",
) -> None:
    issue_key = sha256_text("|".join([portfolio_key, namespace_key, issue_type, severity, asset_key, page_id, json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)]))
    conn.execute(
        """
        INSERT INTO issues (
            issue_id, portfolio_key, namespace_key, issue_type, severity, asset_key, page_id,
            detail_json, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(issue_id) DO UPDATE SET
            status=excluded.status,
            updated_at=excluded.updated_at,
            detail_json=excluded.detail_json
        """,
        (
            issue_key,
            portfolio_key,
            namespace_key,
            issue_type,
            severity,
            asset_key,
            page_id,
            json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
            status,
            now_iso(),
            now_iso(),
        ),
    )


def close_issues(
    conn: sqlite3.Connection,
    *,
    issue_type: str,
    asset_key: str = "",
    page_id: str = "",
    namespace_key: str = "",
    detail_contains: dict[str, Any] | None = None,
) -> int:
    clauses = ["issue_type = ?", "status != 'closed'"]
    params: list[Any] = [issue_type]
    if asset_key:
        clauses.append("asset_key = ?")
        params.append(asset_key)
    if page_id:
        clauses.append("page_id = ?")
        params.append(page_id)
    if namespace_key:
        clauses.append("namespace_key = ?")
        params.append(namespace_key)
    if detail_contains:
        for key, value in detail_contains.items():
            clauses.append(f"json_extract(detail_json, '$.{key}') = ?")
            params.append(value)
    cursor = conn.execute(
        f"""
        UPDATE issues
        SET status = 'closed',
            updated_at = ?
        WHERE {' AND '.join(clauses)}
        """,
        (now_iso(), *params),
    )
    return cursor.rowcount


def set_sync_cursor(
    conn: sqlite3.Connection,
    cursor_key: str,
    cursor_value: str,
    *,
    portfolio_key: str = "portfolio::default",
    namespace_key: str = "account",
) -> None:
    conn.execute(
        """
        INSERT INTO sync_cursor (cursor_key, portfolio_key, namespace_key, cursor_value, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cursor_key) DO UPDATE SET
            portfolio_key=excluded.portfolio_key,
            namespace_key=excluded.namespace_key,
            cursor_value=excluded.cursor_value,
            updated_at=excluded.updated_at
        """,
        (cursor_key, portfolio_key, namespace_key, cursor_value, now_iso()),
    )


def get_sync_cursor(conn: sqlite3.Connection, cursor_key: str) -> str:
    row = conn.execute("SELECT cursor_value FROM sync_cursor WHERE cursor_key = ?", (cursor_key,)).fetchone()
    return row[0] if row else ""


def start_run(
    conn: sqlite3.Connection,
    command_name: str,
    *,
    portfolio_key: str = "portfolio::default",
    namespace_key: str = "account",
    summary: dict[str, Any] | None = None,
) -> str:
    conn.execute(
        """
        UPDATE runs
        SET status = 'abandoned',
            finished_at = ?,
            error_text = CASE
                WHEN error_text = '' THEN 'Superseded by a newer run in the same namespace.'
                ELSE error_text
            END
        WHERE command_name = ?
          AND namespace_key = ?
          AND status = 'running'
        """,
        (now_iso(), command_name, namespace_key),
    )
    started_at = now_iso()
    run_id = f"{namespace_key}:{command_name}:{started_at}:{time_ns()}"
    conn.execute(
        """
        INSERT INTO runs (run_id, portfolio_key, namespace_key, command_name, status, started_at, finished_at, host_pid, summary_json, error_text)
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, '')
        """,
        (
            run_id,
            portfolio_key,
            namespace_key,
            command_name,
            "running",
            started_at,
            str(os.getpid()),
            json.dumps(summary or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()
    return run_id


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    summary: dict[str, Any] | None = None,
    error_text: str = "",
) -> None:
    conn.execute(
        """
        UPDATE runs
        SET status = ?, finished_at = ?, summary_json = ?, error_text = ?
        WHERE run_id = ?
        """,
        (status, now_iso(), json.dumps(summary or {}, ensure_ascii=False, sort_keys=True), error_text, run_id),
    )
    conn.commit()


def journal_sync_event(
    conn: sqlite3.Connection,
    *,
    journal_id: str,
    portfolio_key: str,
    namespace_key: str,
    page_id: str,
    operation: str,
    phase: str,
    status: str,
    local_hash: str = "",
    remote_hash: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO sync_journal (
            journal_id, portfolio_key, namespace_key, page_id, operation, phase,
            status, local_hash, remote_hash, payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(journal_id) DO UPDATE SET
            phase=excluded.phase,
            status=excluded.status,
            local_hash=excluded.local_hash,
            remote_hash=excluded.remote_hash,
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        """,
        (
            journal_id,
            portfolio_key,
            namespace_key,
            page_id,
            operation,
            phase,
            status,
            local_hash,
            remote_hash,
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
            now_iso(),
            now_iso(),
        ),
    )

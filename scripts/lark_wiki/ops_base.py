from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .config import AppConfig
from .db import get_sync_cursor, set_sync_cursor, upsert_asset
from .lark_cli import (
    base_batch_create_records,
    base_create_field,
    base_list_fields,
    base_list_records,
    base_list_tables,
    base_upsert_record,
    pick_first,
    run_lark,
)
from .utils import now_iso, sha256_text


OPS_TABLE_SPECS: dict[str, list[str]] = {
    "sources": [
        "portfolio_key",
        "namespace_key",
        "asset_key",
        "title",
        "asset_class",
        "local_path",
        "remote_url",
        "remote_id",
        "upstream_system",
        "source_hash",
        "canonical_role",
        "sync_mode",
        "last_seen_at",
        "last_synced_at",
    ],
    "pages": [
        "portfolio_key",
        "namespace_key",
        "page_id",
        "page_type",
        "asset_key",
        "local_path",
        "mirror_doc_token",
        "mirror_node_token",
        "last_local_hash",
        "last_remote_hash",
        "sync_mode",
        "last_synced_at",
    ],
    "runs": [
        "portfolio_key",
        "namespace_key",
        "run_id",
        "command_name",
        "status",
        "started_at",
        "finished_at",
    ],
    "issues": [
        "portfolio_key",
        "namespace_key",
        "issue_id",
        "issue_type",
        "severity",
        "asset_key",
        "page_id",
        "status",
    ],
    "merge_queue": [
        "portfolio_key",
        "namespace_key",
        "merge_id",
        "asset_key",
        "page_id",
        "merge_status",
        "conflict_summary",
        "created_at",
        "resolved_at",
    ],
}

OPS_LOCAL_QUERIES: dict[str, str] = {
    "sources": """
        SELECT portfolio_key, namespace_key, asset_key, title, asset_class, local_path, remote_url, remote_id,
               upstream_system, source_hash, canonical_role, sync_mode,
               last_seen_at, COALESCE(last_synced_at, '') AS last_synced_at
        FROM assets
        ORDER BY namespace_key, asset_key
    """,
    "pages": """
        SELECT portfolio_key, namespace_key, page_id, page_type, asset_key, local_path, mirror_doc_token,
               mirror_node_token, last_local_hash, last_remote_hash, sync_mode,
               COALESCE(last_synced_at, '') AS last_synced_at
        FROM pages
        ORDER BY namespace_key, page_id
    """,
    "runs": """
        SELECT portfolio_key, namespace_key, run_id, command_name, status, started_at,
               COALESCE(finished_at, '') AS finished_at
        FROM runs
        ORDER BY namespace_key, started_at DESC, run_id DESC
    """,
    "issues": """
        SELECT portfolio_key, namespace_key, issue_id, issue_type, severity, asset_key, page_id, status
        FROM issues
        ORDER BY namespace_key, issue_id
    """,
    "merge_queue": """
        SELECT portfolio_key, namespace_key, merge_id, asset_key, page_id, merge_status, conflict_summary,
               created_at, COALESCE(resolved_at, '') AS resolved_at
        FROM merge_queue
        ORDER BY namespace_key, created_at DESC, merge_id DESC
    """,
}

OPS_PRIMARY_KEYS = {
    "sources": "asset_key",
    "pages": "page_id",
    "runs": "run_id",
    "issues": "issue_id",
    "merge_queue": "merge_id",
}


def _refresh_tables(config: AppConfig, base_token: str) -> dict[str, str]:
    return {item.get("table_name", ""): item.get("table_id", "") for item in base_list_tables(config, base_token)}


def _ensure_table(config: AppConfig, base_token: str, table_name: str, columns: list[str]) -> str:
    tables = _refresh_tables(config, base_token)
    table_id = tables.get(table_name, "")
    if not table_id:
        payload = run_lark(
            config,
            [
                "base",
                "+table-create",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--name",
                table_name,
            ],
        )
        table_id = pick_first(payload, [["data", "table", "table_id"], ["data", "table_id"]]) or _refresh_tables(config, base_token).get(table_name, "")
        if not table_id:
            raise RuntimeError(f"Unable to create ops table: {table_name}")

    existing_fields = {item.get("field_name", "") for item in base_list_fields(config, base_token, table_id)}
    for field_name in columns:
        if field_name in existing_fields:
            continue
        try:
            base_create_field(config, base_token, table_id, field_name)
        except Exception:
            pass
        refreshed = False
        for _ in range(5):
            existing_fields = {item.get("field_name", "") for item in base_list_fields(config, base_token, table_id)}
            if field_name in existing_fields:
                refreshed = True
                break
            time.sleep(0.5)
        if not refreshed:
            raise RuntimeError(f"Field did not appear after create: {table_name}.{field_name}")
    return table_id


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        return json.dumps(value, ensure_ascii=False, sort_keys=True) if any(isinstance(item, (dict, list)) for item in value) else " | ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _list_remote_records_by_key(config: AppConfig, base_token: str, table_id: str, primary_key: str) -> dict[str, dict[str, Any]]:
    offset = 0
    records_by_key: dict[str, dict[str, Any]] = {}
    while True:
        payload = base_list_records(config, base_token, table_id, limit=200, offset=offset)
        fields = payload.get("fields", []) or []
        rows = payload.get("data", []) or []
        record_ids = payload.get("record_id_list", []) or []
        if primary_key not in fields:
            return {}
        key_index = fields.index(primary_key)
        for record_id, row_values in zip(record_ids, rows):
            row_map = {field_name: _cell_to_text(value) for field_name, value in zip(fields, row_values)}
            records_by_key[_cell_to_text(row_values[key_index])] = {
                "record_id": record_id,
                "fields": row_map,
            }
        if not payload.get("has_more") or not record_ids:
            break
        offset += len(record_ids)
    return records_by_key


def _local_rows(conn: sqlite3.Connection, table_name: str) -> list[dict[str, str]]:
    rows = conn.execute(OPS_LOCAL_QUERIES[table_name]).fetchall()
    normalized: list[dict[str, str]] = []
    for row in rows:
        normalized.append({key: _cell_to_text(row[key]) for key in OPS_TABLE_SPECS[table_name]})
    return normalized


def compute_ops_base_state(conn: sqlite3.Connection) -> dict[str, dict[str, object]]:
    state: dict[str, dict[str, object]] = {}
    for table_name in OPS_TABLE_SPECS:
        rows = _local_rows(conn, table_name)
        state[table_name] = {
            "count": len(rows),
            "signature": sha256_text(json.dumps(rows, ensure_ascii=False, sort_keys=True)),
        }
    return state


def _remote_fields_equal(local_fields: dict[str, str], remote_fields: dict[str, Any], columns: list[str]) -> bool:
    for column in columns:
        if _cell_to_text(remote_fields.get(column, "")) != local_fields.get(column, ""):
            return False
    return True


def bootstrap_ops_base(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    existing_token = get_sync_cursor(conn, "ops_base_token")
    if existing_token:
        base_token = existing_token
        base_url = get_sync_cursor(conn, "ops_base_url") or f"https://example.invalid/base/{base_token}"
    else:
        payload = run_lark(config, ["base", "+base-create", "--as", "user", "--name", config.ops_base_title, "--time-zone", "Asia/Shanghai"])
        base_token = pick_first(payload, [["data", "base", "base_token"], ["data", "app_token"], ["data", "base_token"]])
        base_url = pick_first(payload, [["data", "base", "url"], ["data", "url"]]) or (f"https://example.invalid/base/{base_token}" if base_token else "")
        if not base_token:
            raise RuntimeError(f"Unable to parse base create response: {payload}")
        set_sync_cursor(conn, "ops_base_token", base_token)
        set_sync_cursor(conn, "ops_base_url", base_url)

    created_tables: dict[str, str] = {}
    for table_name, columns in OPS_TABLE_SPECS.items():
        created_tables[table_name] = _ensure_table(config, base_token, table_name, columns)

    upsert_asset(
        conn,
        asset_key=f"BASE::{base_token}",
        asset_class="base_app",
        title=config.ops_base_title,
        remote_url=base_url,
        remote_id=base_token,
        upstream_system="feishu_base",
        source_hash=sha256_text(json.dumps(created_tables, ensure_ascii=False, sort_keys=True)),
        canonical_role="ops_surface",
        sync_mode="structured_snapshot",
        portfolio_key=config.portfolio_key,
        namespace_key=config.account_namespace_key,
        classification_status="classified",
        last_synced_at=now_iso(),
        metadata={"tables": created_tables},
    )
    conn.commit()
    return {"ops_base_token": base_token, "ops_base_url": base_url, "tables": created_tables}


def sync_ops_base(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    bootstrap = bootstrap_ops_base(conn, config)
    base_token = str(bootstrap["ops_base_token"])
    table_ids = dict(bootstrap["tables"])
    local_state = compute_ops_base_state(conn)
    summary: dict[str, dict[str, object]] = {}

    for table_name, columns in OPS_TABLE_SPECS.items():
        table_id = table_ids[table_name]
        primary_key = OPS_PRIMARY_KEYS[table_name]
        remote_records = _list_remote_records_by_key(config, base_token, table_id, primary_key)
        rows = _local_rows(conn, table_name)
        create_batch: list[dict[str, str]] = []
        updates = 0
        creates = 0
        for row in rows:
            fields = {column: row.get(column, "") for column in columns}
            remote_record = remote_records.get(fields[primary_key], {})
            record_id = str(remote_record.get("record_id", "")) if remote_record else ""
            if record_id and _remote_fields_equal(fields, dict(remote_record.get("fields", {})), columns):
                continue
            if record_id:
                base_upsert_record(
                    config,
                    base_token,
                    table_id,
                    fields,
                    record_id=record_id,
                )
                updates += 1
                if updates % 20 == 0:
                    time.sleep(1)
            else:
                create_batch.append(fields)
        for idx in range(0, len(create_batch), 50):
            batch = create_batch[idx : idx + 50]
            if not batch:
                continue
            base_batch_create_records(config, base_token, table_id, batch)
            creates += len(batch)
            time.sleep(1)
        summary[table_name] = {
            "upserted": creates + updates,
            "created": creates,
            "updated": updates,
            "count": local_state[table_name]["count"],
            "signature": local_state[table_name]["signature"],
        }
        set_sync_cursor(conn, f"ops_base_sync::{table_name}::count", str(local_state[table_name]["count"]))
        set_sync_cursor(conn, f"ops_base_sync::{table_name}::signature", str(local_state[table_name]["signature"]))
    set_sync_cursor(conn, "ops_base_last_synced_at", now_iso())
    conn.commit()
    return {
        "ops_base_token": base_token,
        "ops_base_url": bootstrap["ops_base_url"],
        "tables": summary,
    }

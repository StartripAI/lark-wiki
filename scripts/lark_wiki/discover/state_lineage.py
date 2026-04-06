from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..config import AppConfig
from ..db import close_issues, record_issue, upsert_asset, upsert_asset_edge
from ..lark_cli import detect_base_token, detect_doc_token
from ..utils import json_dumps, now_iso, relative_to_root, sha256_bytes, sha256_text


def _has_table(db: sqlite3.Connection, table_name: str) -> bool:
    row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)).fetchone()
    return row is not None


def _table_columns(db: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _path_in_repo(local_path: str, config: AppConfig) -> Path | None:
    if not local_path:
        return None
    resolved = Path(local_path).resolve()
    try:
        resolved.relative_to(config.root.resolve())
    except ValueError:
        return None
    return resolved


def _load_json_value(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _materialize_manifest_stub(
    conn: sqlite3.Connection,
    config: AppConfig,
    registry_row: sqlite3.Row,
    registry_asset_key: str,
    binding: dict[str, Any] | None,
) -> Path | None:
    local_path = registry_row["local_source_path"] or ""
    source_path = _path_in_repo(local_path, config)
    if source_path is None:
        return None
    source_path.parent.mkdir(parents=True, exist_ok=True)
    binding = binding or {}
    remote_url = registry_row["remote_url"] or binding.get("remote_url", "")
    remote_id = registry_row["remote_id"] or binding.get("remote_id", "")
    payload = {
        "asset_key": registry_row["asset_key"],
        "asset_class": registry_row["asset_class"],
        "lifecycle_status": registry_row["lifecycle_status"],
        "publish_mode": registry_row["publish_mode"],
        "owner_surface": registry_row["owner_surface"],
        "local_source_path": local_path,
        "remote_url": remote_url,
        "remote_id": remote_id,
        "parent_task_key": registry_row["parent_task_key"] or "",
        "source_hash": registry_row["source_hash"] or "",
        "latest_publish_batch_id": registry_row["latest_publish_batch_id"] or "",
        "metadata_json": _load_json_value(registry_row["metadata_json"] or ""),
        "reconstructed_stub": True,
        "reconstructed_at": now_iso(),
    }
    if binding:
        payload["remote_binding"] = binding
    source_path.write_text(json_dumps(payload) + "\n", encoding="utf-8")
    rel_path = relative_to_root(source_path, config.root)
    upsert_asset(
        conn,
        asset_key=f"LOCAL::{rel_path}",
        asset_class="manifest",
        title=source_path.name,
        local_path=rel_path,
        upstream_system="state_lineage_reconstruction",
        source_hash=sha256_text(source_path.read_text(encoding="utf-8")),
        canonical_role="source_only",
        sync_mode="local_only",
        portfolio_key=config.portfolio_key,
        namespace_key=config.default_project_namespace,
        classification_status="classified",
        metadata={
            "reconstructed_stub": True,
            "registry_asset_key": registry_asset_key,
        },
    )
    close_issues(conn, issue_type="missing_registry_local_source", asset_key=registry_asset_key)
    return source_path


def discover_state_lineage(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    edges = 0
    summary: dict[str, object] = {"asset_registry": 0, "remote_binding": 0, "publish_batch": 0, "sync_state_rows": 0}

    if config.orchestrator_db and config.orchestrator_db.exists():
        upsert_asset(
            conn,
            asset_key="DB::llm_wiki_orchestrator",
            asset_class="local_db",
            title="LLM wiki orchestrator state DB",
            local_path=relative_to_root(config.orchestrator_db, config.root),
            upstream_system="local_state",
            source_hash=sha256_bytes(config.orchestrator_db.read_bytes()),
            canonical_role="state_snapshot",
            sync_mode="local_only",
            portfolio_key=config.portfolio_key,
            namespace_key=config.default_project_namespace,
            classification_status="classified",
            metadata={"tables": ["publish_batch", "asset_registry", "remote_binding", "rollback_snapshot", "operation_queue"]},
        )
        db = sqlite3.connect(config.orchestrator_db)
        db.row_factory = sqlite3.Row
        bindings_by_asset: dict[str, dict[str, Any]] = {}

        if _has_table(db, "remote_binding"):
            for row in db.execute(
                """
                SELECT binding_key, asset_key, target_surface, remote_url, remote_id,
                       publish_batch_id, status, detail_json
                FROM remote_binding
                """
            ):
                summary["remote_binding"] = int(summary["remote_binding"]) + 1
                bindings_by_asset[row["asset_key"]] = {
                    "binding_key": row["binding_key"],
                    "target_surface": row["target_surface"],
                    "remote_url": row["remote_url"] or "",
                    "remote_id": row["remote_id"] or "",
                    "publish_batch_id": row["publish_batch_id"] or "",
                    "status": row["status"] or "",
                    "detail_json": _load_json_value(row["detail_json"] or ""),
                }

        if _has_table(db, "asset_registry"):
            for row in db.execute(
                """
                SELECT asset_key, asset_class, lifecycle_status, publish_mode, owner_surface,
                       local_source_path, remote_url, remote_id, parent_task_key,
                       source_hash, latest_publish_batch_id, metadata_json
                FROM asset_registry
                """
            ):
                summary["asset_registry"] = int(summary["asset_registry"]) + 1
                local_path = row["local_source_path"] or ""
                registry_asset_key = f"REGISTRY::{row['asset_key']}"
                metadata = _load_json_value(row["metadata_json"] or "")
                resolved_local_path = _path_in_repo(local_path, config)
                local_path_in_repo = resolved_local_path is not None
                reconstructed_stub = False
                if local_path:
                    source_path = resolved_local_path if local_path_in_repo else None
                    if source_path is not None and not source_path.exists():
                        reconstructed = _materialize_manifest_stub(
                            conn,
                            config,
                            row,
                            registry_asset_key,
                            bindings_by_asset.get(row["asset_key"]),
                        )
                        source_path = reconstructed or source_path
                        reconstructed_stub = reconstructed is not None
                    if source_path is not None and source_path.exists():
                        try:
                            source_payload = json.loads(source_path.read_text(encoding="utf-8"))
                        except (OSError, json.JSONDecodeError):
                            source_payload = {}
                        reconstructed_stub = reconstructed_stub or bool(source_payload.get("reconstructed_stub"))
                    if source_path is not None and not source_path.exists():
                        record_issue(
                            conn,
                            issue_type="missing_registry_local_source",
                            severity="high",
                            asset_key=registry_asset_key,
                            detail={"local_source_path": local_path},
                        )
                    else:
                        close_issues(conn, issue_type="missing_registry_local_source", asset_key=registry_asset_key)
                upsert_asset(
                    conn,
                    asset_key=registry_asset_key,
                    asset_class="manifest" if "manifest" in row["asset_key"] else "state_snapshot",
                    title=row["asset_key"],
                    local_path=relative_to_root(resolved_local_path, config.root) if local_path_in_repo and resolved_local_path else "",
                    remote_url=row["remote_url"] or "",
                    remote_id=row["remote_id"] or "",
                    upstream_system="llm_wiki_orchestrator",
                    source_hash=row["source_hash"] or "",
                    canonical_role="state_snapshot",
                    sync_mode="local_only",
                    portfolio_key=config.portfolio_key,
                    namespace_key=config.default_project_namespace,
                    classification_status="classified",
                    metadata={
                        **(metadata if isinstance(metadata, dict) else {}),
                        **({"reconstructed_stub": True} if reconstructed_stub else {}),
                    },
                )
                if local_path_in_repo and resolved_local_path:
                    rel = relative_to_root(resolved_local_path, config.root)
                    local_asset_key = f"LOCAL::{rel}"
                    if conn.execute("SELECT 1 FROM assets WHERE asset_key = ?", (local_asset_key,)).fetchone():
                        upsert_asset_edge(conn, local_asset_key, registry_asset_key, "registered_as")
                        edges += 1

            for asset_key, binding in bindings_by_asset.items():
                registry_asset_key = f"REGISTRY::{asset_key}"
                target_key = ""
                remote_url = binding.get("remote_url", "")
                if "/base/" in remote_url:
                    token = detect_base_token(remote_url)
                    if token:
                        target_key = f"BASE::{token}"
                else:
                    doc_type, token = detect_doc_token(remote_url)
                    if token:
                        target_key = f"WIKI_NODE::{token}" if doc_type == "wiki" else f"DOC::{token}"
                if (
                    target_key
                    and conn.execute("SELECT 1 FROM assets WHERE asset_key = ?", (registry_asset_key,)).fetchone()
                    and conn.execute("SELECT 1 FROM assets WHERE asset_key = ?", (target_key,)).fetchone()
                ):
                    upsert_asset_edge(
                        conn,
                        registry_asset_key,
                        target_key,
                        "published_to",
                        {
                            "target_surface": binding.get("target_surface", ""),
                            "publish_batch_id": binding.get("publish_batch_id", ""),
                            "status": binding.get("status", ""),
                        },
                    )
                    edges += 1

        if _has_table(db, "publish_batch"):
            summary["publish_batch"] = db.execute("SELECT COUNT(*) FROM publish_batch").fetchone()[0]
        if _has_table(db, "operation_queue"):
            queue_columns = _table_columns(db, "operation_queue")
            worker_column = "worker_family" if "worker_family" in queue_columns else "worker_name" if "worker_name" in queue_columns else ""
            if worker_column:
                worker_rows = db.execute(f"SELECT {worker_column}, COUNT(*) AS c FROM operation_queue GROUP BY {worker_column}").fetchall()
                summary["worker_families"] = {row[0] or "unknown": row[1] for row in worker_rows}
            else:
                summary["worker_families"] = {}
        db.close()

    if config.project_sync_db and config.project_sync_db.exists():
        try:
            db = sqlite3.connect(config.project_sync_db)
            if _has_table(db, "sync_state"):
                summary["sync_state_rows"] = db.execute("SELECT COUNT(*) FROM sync_state").fetchone()[0]
            db.close()
        except sqlite3.DatabaseError:
            summary["sync_state_rows"] = 0

    snapshot_path = config.raw_dir / "state_lineage" / "lineage_summary.json"
    snapshot_path.write_text(json_dumps({"summary": summary, "edge_count": edges, "generated_at": now_iso()}), encoding="utf-8")
    upsert_asset(
        conn,
        asset_key="STATE::lineage_summary",
        asset_class="state_snapshot",
        title="lineage summary",
        local_path=relative_to_root(snapshot_path, config.root),
        upstream_system="local_state",
        source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
        canonical_role="state_snapshot",
        sync_mode="local_only",
        portfolio_key=config.portfolio_key,
        namespace_key=config.default_project_namespace,
        classification_status="classified",
        metadata={"summary": summary, "edge_count": edges},
    )
    conn.commit()
    return {"summary": summary, "edge_count": edges}

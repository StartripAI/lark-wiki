from __future__ import annotations

from collections import Counter
import sqlite3

from ..config import AppConfig
from ..db import record_issue, upsert_asset, upsert_asset_edge
from ..utils import json_dumps, now_iso, parse_env_file, relative_to_root, sha256_text


def discover_feishu_project(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    namespace_summaries: dict[str, object] = {}
    total_counts = Counter()

    for namespace_key, namespace in config.namespaces.items():
        if namespace.kind != "project":
            continue
        env = parse_env_file(namespace.project_env_path) if namespace.project_env_path else {}
        project_key = env.get("FEISHU_PROJECT_KEY", "") or namespace.slug
        user_key = env.get("FEISHU_PROJECT_USER_KEY", "")
        project_asset_key = f"PROJECT::{project_key or namespace.slug}"

        if namespace.project_sync_db_path and namespace.project_sync_db_path.exists():
            upsert_asset(
                conn,
                asset_key=f"DB::{namespace.slug}_feishu_project_sync_state",
                asset_class="local_db",
                title=f"{namespace.display_name} Feishu Project sync state DB",
                local_path=relative_to_root(namespace.project_sync_db_path, config.root),
                upstream_system="local_state",
                source_hash=sha256_text(str(namespace.project_sync_db_path.stat().st_mtime_ns)),
                canonical_role="state_snapshot",
                sync_mode="local_only",
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                classification_status="classified",
                metadata={"path": relative_to_root(namespace.project_sync_db_path, config.root)},
            )
            if namespace_key == config.default_project_namespace:
                upsert_asset(
                    conn,
                    asset_key="DB::feishu_project_sync_state",
                    asset_class="local_db",
                    title="Feishu Project sync state DB",
                    local_path=relative_to_root(namespace.project_sync_db_path, config.root),
                    upstream_system="local_state",
                    source_hash=sha256_text(str(namespace.project_sync_db_path.stat().st_mtime_ns)),
                    canonical_role="state_snapshot",
                    sync_mode="local_only",
                    portfolio_key=config.portfolio_key,
                    namespace_key=namespace_key,
                    classification_status="classified",
                    metadata={"path": relative_to_root(namespace.project_sync_db_path, config.root), "namespace_key": namespace_key},
                )
        upsert_asset(
            conn,
            asset_key=project_asset_key,
            asset_class="project_space",
            title=project_key or namespace.display_name,
            local_path=relative_to_root(namespace.project_env_path, config.root) if namespace.project_env_path and namespace.project_env_path.exists() else "",
            remote_id=project_key,
            upstream_system="feishu_project",
            source_hash=sha256_text(json_dumps(env)),
            canonical_role="live_state_source",
            sync_mode="structured_snapshot",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status="classified",
            metadata=env,
        )

        counts = Counter()
        samples: list[dict[str, object]] = []
        if namespace.project_sync_db_path and namespace.project_sync_db_path.exists():
            try:
                db = sqlite3.connect(namespace.project_sync_db_path)
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    """
                    SELECT external_id, work_item_type, work_item_id, source_hash,
                           last_seen_at, last_synced_at, last_status, last_error
                    FROM sync_state
                    """
                ).fetchall()
                for row in rows:
                    metadata = {key: row[key] for key in row.keys()}
                    external_id = row["external_id"]
                    asset_key = f"PROJECT_ITEM::{namespace.slug}::{external_id}"
                    upsert_asset(
                        conn,
                        asset_key=asset_key,
                        asset_class="project_work_item",
                        title=external_id,
                        local_path=relative_to_root(namespace.project_sync_db_path, config.root),
                        remote_id=row["work_item_id"] or external_id,
                        upstream_system="feishu_project_sync_state",
                        source_hash=row["source_hash"],
                        canonical_role="live_state_source",
                        sync_mode="structured_snapshot",
                        portfolio_key=config.portfolio_key,
                        namespace_key=namespace_key,
                        classification_status="classified",
                        last_seen_at=row["last_seen_at"],
                        last_synced_at=row["last_synced_at"],
                        metadata=metadata,
                    )
                    upsert_asset_edge(conn, project_asset_key, asset_key, "contains_work_item", {"work_item_type": row["work_item_type"]})
                    counts[row["work_item_type"]] += 1
                    total_counts[row["work_item_type"]] += 1
                    if len(samples) < 20:
                        samples.append(metadata)
                db.close()
            except sqlite3.DatabaseError as exc:
                record_issue(
                    conn,
                    issue_type="invalid_project_sync_db",
                    severity="high",
                    asset_key=project_asset_key,
                    namespace_key=namespace_key,
                    detail={"db_path": relative_to_root(namespace.project_sync_db_path, config.root), "error": str(exc)},
                )

        snapshot_path = config.raw_dir / "feishu_project" / f"{namespace.slug}_project_snapshot.json"
        snapshot_path.write_text(
            json_dumps(
                {
                    "namespace_key": namespace_key,
                    "project_key": project_key,
                    "user_key": user_key,
                    "counts": dict(counts),
                    "sample_items": samples,
                    "discovery_mode": "sync_state_snapshot",
                    "fetched_at": now_iso(),
                }
            ),
            encoding="utf-8",
        )
        upsert_asset(
            conn,
            asset_key=f"STATE::project_snapshot::{namespace.slug}",
            asset_class="state_snapshot",
            title=f"{namespace.display_name} project snapshot",
            local_path=relative_to_root(snapshot_path, config.root),
            upstream_system="feishu_project_sync_state",
            source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
            canonical_role="state_snapshot",
            sync_mode="local_only",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status="classified",
            metadata={"counts": dict(counts)},
        )
        if namespace_key == config.default_project_namespace:
            upsert_asset(
                conn,
                asset_key="STATE::project_snapshot",
                asset_class="state_snapshot",
                title="Feishu Project snapshot",
                local_path=relative_to_root(snapshot_path, config.root),
                upstream_system="feishu_project_sync_state",
                source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
                canonical_role="state_snapshot",
                sync_mode="local_only",
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                classification_status="classified",
                metadata={"counts": dict(counts), "namespace_key": namespace_key},
            )
        namespace_summaries[namespace_key] = {
            "project_key": project_key,
            "counts": dict(counts),
            "discovery_mode": "sync_state_snapshot",
        }

    conn.commit()
    return {"namespaces": namespace_summaries, "counts": dict(total_counts)}

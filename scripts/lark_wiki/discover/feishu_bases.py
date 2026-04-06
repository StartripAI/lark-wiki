from __future__ import annotations

import sqlite3

from ..config import AppConfig
from ..db import record_issue, upsert_asset, upsert_asset_edge
from ..lark_cli import base_list_tables, base_list_views, detect_base_token
from ..utils import FEISHU_URL_RE, json_dumps, now_iso, read_text_safe, relative_to_root, scan_local_text_urls, sha256_text, iter_repo_files


def discover_feishu_bases(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    base_urls: dict[str, str] = {}
    namespace_by_base_token: dict[str, str] = {}
    for namespace_key, namespace in config.namespaces.items():
        for token in namespace.base_tokens:
            base_urls[token] = f"https://example.invalid/base/{token}"
            namespace_by_base_token[token] = namespace_key
    for url in scan_local_text_urls(config):
        if "/base/" in url:
            token = detect_base_token(url)
            if token:
                base_urls[token] = f"https://example.invalid/base/{token}"
    for json_path in iter_repo_files(config, {".json"}):
        for url in FEISHU_URL_RE.findall(read_text_safe(json_path)):
            if "/base/" in url:
                token = detect_base_token(url)
                if token:
                    base_urls[token] = f"https://example.invalid/base/{token}"

    tables_total = 0
    discovered_bases: list[dict[str, object]] = []
    for base_token, base_url in sorted(base_urls.items()):
        try:
            tables = base_list_tables(config, base_token)
        except Exception as exc:  # pragma: no cover
            record_issue(conn, issue_type="base_discovery_failed", severity="medium", namespace_key=namespace_by_base_token.get(base_token, config.account_namespace_key), detail={"base_url": base_url, "error": str(exc)})
            continue
        namespace_key = namespace_by_base_token.get(base_token, config.inbox_namespace_key)
        base_key = f"BASE::{base_token}"
        upsert_asset(
            conn,
            asset_key=base_key,
            asset_class="base_app",
            title=base_url.rsplit("/", 1)[-1],
            remote_url=base_url,
            remote_id=base_token,
            upstream_system="feishu_base",
            source_hash=sha256_text(json_dumps(tables)),
            canonical_role="structured_source",
            sync_mode="structured_snapshot",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status="classified" if namespace_key != config.inbox_namespace_key else "inbox",
            metadata={"table_count": len(tables)},
        )
        table_rows: list[dict[str, object]] = []
        for table in tables:
            table_id = table.get("table_id") or table.get("tableId") or table.get("id")
            table_name = table.get("table_name") or table.get("name") or table_id
            if not table_id:
                continue
            views = base_list_views(config, base_token, table_id)
            table_key = f"BASE_TABLE::{base_token}::{table_id}"
            upsert_asset(
                conn,
                asset_key=table_key,
                asset_class="base_table",
                title=table_name,
                remote_url=f"{base_url}?table={table_id}",
                remote_id=table_id,
                upstream_system="feishu_base",
                source_hash=sha256_text(json_dumps({"table": table, "views": views})),
                canonical_role="structured_source",
                sync_mode="structured_snapshot",
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                classification_status="classified" if namespace_key != config.inbox_namespace_key else "inbox",
                metadata={"table": table, "views": views},
            )
            upsert_asset_edge(conn, base_key, table_key, "contains_table", {"view_count": len(views)})
            table_rows.append({"table_id": table_id, "table_name": table_name, "views": views})
            tables_total += 1
        snapshot_path = config.raw_dir / "feishu_bases" / f"{base_token}.json"
        snapshot_path.write_text(json_dumps({"base_url": base_url, "base_token": base_token, "tables": table_rows, "fetched_at": now_iso()}), encoding="utf-8")
        upsert_asset(
            conn,
            asset_key=f"STATE::base_snapshot::{base_token}",
            asset_class="state_snapshot",
            title=f"Base snapshot {base_token}",
            local_path=relative_to_root(snapshot_path, config.root),
            upstream_system="feishu_base",
            source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
            canonical_role="state_snapshot",
            sync_mode="local_only",
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status="classified" if namespace_key != config.inbox_namespace_key else "inbox",
            metadata={"base_url": base_url, "table_count": len(table_rows)},
        )
        discovered_bases.append({"base_url": base_url, "table_count": len(table_rows)})
    conn.commit()
    return {"bases": discovered_bases, "base_count": len(discovered_bases), "table_count": tables_total}

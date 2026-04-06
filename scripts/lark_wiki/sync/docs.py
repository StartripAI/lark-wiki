from __future__ import annotations

import json
import sqlite3

from ..config import AppConfig
from ..db import close_issues, get_sync_cursor, journal_sync_event, record_issue, set_sync_cursor, upsert_asset, upsert_page
from ..lark_cli import detect_doc_token, docs_fetch_full, pick_first, run_lark, wiki_get_node
from ..markdown import markdown_is_safe, normalize_markdown_for_sync, page_frontmatter, read_frontmatter
from ..portfolio import namespaced_page_id
from ..utils import json_dumps, now_iso, relative_to_root, sha256_text


def get_root_page_record(conn: sqlite3.Connection, namespace_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM pages WHERE page_id = ?", (namespaced_page_id(namespace_key, "home"),)).fetchone()


def _namespace_root_node_token(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> str:
    cursor_value = get_sync_cursor(conn, f"mirror_root_node_token::{namespace_key}")
    if cursor_value:
        return cursor_value
    row = conn.execute("SELECT remote_root_node_token FROM namespaces WHERE namespace_key = ?", (namespace_key,)).fetchone()
    if row and row["remote_root_node_token"]:
        return row["remote_root_node_token"]
    if namespace_key == config.account_namespace_key and config.portfolio_root_node:
        return config.portfolio_root_node
    return ""


def _store_namespace_root_node(conn: sqlite3.Connection, namespace_key: str, node_token: str) -> None:
    if not node_token:
        return
    conn.execute(
        "UPDATE namespaces SET remote_root_node_token = ?, updated_at = ? WHERE namespace_key = ?",
        (node_token, now_iso(), namespace_key),
    )


def _doc_token_from_node(config: AppConfig, node_token: str) -> str:
    if not node_token:
        return ""
    try:
        node = wiki_get_node(config, node_token)
    except Exception:
        return ""
    candidates = [
        node.get("obj_token", ""),
        node.get("document_id", ""),
        node.get("doc_token", ""),
        node.get("obj_id", ""),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def create_or_update_doc(
    config: AppConfig,
    title: str,
    markdown: str,
    mirror_doc_token: str = "",
    existing_node_token: str = "",
    parent_node_token: str = "",
) -> tuple[str, str, str]:
    resolved_doc_token = mirror_doc_token or _doc_token_from_node(config, existing_node_token)
    if resolved_doc_token:
        payload = run_lark(config, ["docs", "+update", "--as", "user", "--doc", resolved_doc_token, "--mode", "overwrite", "--new-title", title, "--markdown", markdown])
    elif existing_node_token:
        raise RuntimeError(f"Unable to resolve existing document token from bound node: {existing_node_token}")
    elif parent_node_token:
        payload = run_lark(config, ["docs", "+create", "--as", "user", "--wiki-node", parent_node_token, "--title", title, "--markdown", markdown])
    else:
        payload = run_lark(config, ["docs", "+create", "--as", "user", "--wiki-space", config.lark_wiki_space, "--title", title, "--markdown", markdown])
    url = pick_first(payload, [["data", "document", "url"], ["data", "docx", "url"], ["data", "doc_url"], ["data", "url"], ["data", "node", "url"]])
    doc_token = pick_first(payload, [["data", "document", "document_id"], ["data", "docx", "document_id"], ["data", "doc_id"], ["data", "token"]])
    node_token = pick_first(payload, [["data", "node", "node_token"], ["data", "node", "obj_token"], ["data", "node_token"]])
    doc_token = doc_token or resolved_doc_token
    if not node_token and url:
        doc_type, token = detect_doc_token(url)
        if doc_type == "wiki":
            node_token = token
    if not node_token:
        node_token = existing_node_token or parent_node_token
    if not url and node_token:
        url = f"https://example.invalid/wiki/{node_token}"
    return url, doc_token, node_token


def _canonical_body(path) -> tuple[dict[str, object], str, str]:
    frontmatter, body = read_frontmatter(path)
    local_text = path.read_text(encoding="utf-8")
    return frontmatter, body.strip(), local_text


def _refresh_page_asset(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    asset_key: str,
    title: str,
    local_path: str,
    source_hash: str,
    sync_mode: str,
    portfolio_key: str = "portfolio::default",
    namespace_key: str = "inbox",
    remote_url: str = "",
    remote_id: str = "",
    mirror_node_token: str = "",
) -> None:
    upsert_asset(
        conn,
        asset_key=asset_key,
        asset_class="local_file",
        title=title,
        local_path=local_path,
        remote_url=remote_url,
        remote_id=remote_id,
        upstream_system="llm_wiki_compiler",
        source_hash=source_hash,
        canonical_role="canonical_page",
        sync_mode=sync_mode,
        portfolio_key=portfolio_key,
        namespace_key=namespace_key,
        classification_status="classified",
        last_synced_at=now_iso() if remote_id or remote_url else None,
        metadata={"mirror_node_token": mirror_node_token, "remote_url": remote_url} if (mirror_node_token or remote_url) else {},
    )


def _page_sync_metadata(row: sqlite3.Row) -> dict[str, object]:
    try:
        return json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        return {}


def _last_synced_local_hash(row: sqlite3.Row, current_local_hash: str) -> str:
    metadata = _page_sync_metadata(row)
    baseline = metadata.get("last_synced_local_hash", "")
    if isinstance(baseline, str) and baseline:
        return baseline
    return row["last_local_hash"] or current_local_hash


def _infer_existing_node_token(conn: sqlite3.Connection, asset_key: str, fallback_url: str = "") -> str:
    row = conn.execute("SELECT remote_url, metadata_json FROM assets WHERE asset_key = ?", (asset_key,)).fetchone()
    candidates: list[str] = []
    if row:
        if row["remote_url"]:
            candidates.append(row["remote_url"])
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        remote_url = metadata.get("remote_url", "")
        if isinstance(remote_url, str) and remote_url:
            candidates.append(remote_url)
        node_token = metadata.get("mirror_node_token", "")
        if isinstance(node_token, str) and node_token:
            return node_token
    if fallback_url:
        candidates.append(fallback_url)
    for url in candidates:
        doc_type, token = detect_doc_token(url)
        if doc_type == "wiki" and token:
            return token
    return ""


def _rebaseline_remote_equivalent(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    title: str,
    body: str,
    current_local_hash: str,
    remote: dict[str, str],
) -> bool:
    remote_body = remote.get("markdown", "").strip()
    remote_hash = sha256_text(normalize_markdown_for_sync(remote_body))
    expected_remote_hash = sha256_text(normalize_markdown_for_sync(body))
    if remote_hash != expected_remote_hash:
        return False
    upsert_page(
        conn,
        page_id=row["page_id"],
        page_type=row["page_type"],
        asset_key=row["asset_key"],
        local_path=row["local_path"],
        mirror_doc_token=row["mirror_doc_token"],
        mirror_node_token=row["mirror_node_token"] or _infer_existing_node_token(conn, row["asset_key"]),
        last_local_hash=current_local_hash,
        last_remote_hash=remote_hash,
        sync_mode=row["sync_mode"],
        last_synced_at=now_iso(),
        portfolio_key=row["portfolio_key"],
        namespace_key=row["namespace_key"],
        metadata={"title": title, "rebaseline_mode": "remote_equivalent", "last_synced_local_hash": current_local_hash},
    )
    close_issues(conn, issue_type="merge_conflict", page_id=row["page_id"], namespace_key=row["namespace_key"])
    return True


def sync_push(conn: sqlite3.Connection, config: AppConfig, namespace_key: str, limit: int = 0) -> dict[str, object]:
    if get_root_page_record(conn, namespace_key) is None:
        raise RuntimeError("Missing home page; run ingest/build_graph first.")
    synced: list[dict[str, str]] = []
    conflicts: list[str] = []
    page_rows = conn.execute(
        """
        SELECT *
        FROM pages
        WHERE namespace_key = ?
        ORDER BY
            CASE
                WHEN page_id = ? THEN 0
                WHEN page_id = ? THEN 1
                WHEN page_id = ? THEN 2
                ELSE 3
            END,
            page_type,
            page_id
        """
        ,
        (
            namespace_key,
            namespaced_page_id(namespace_key, "home"),
            namespaced_page_id(namespace_key, "index"),
            namespaced_page_id(namespace_key, "log"),
        ),
    ).fetchall()
    root_node_token = _namespace_root_node_token(conn, config, namespace_key)
    root_doc_token = get_sync_cursor(conn, f"mirror_root_doc_token::{namespace_key}")
    account_root_node_token = _namespace_root_node_token(conn, config, config.account_namespace_key)
    for row in page_rows:
        journal_id = sha256_text(f"sync_push::{namespace_key}::{row['page_id']}::{row['last_local_hash']}")
        local_path = config.root / row["local_path"]
        frontmatter, body, current_local_text = _canonical_body(local_path)
        title = frontmatter.get("title", row["page_id"])
        if row["page_id"] == namespaced_page_id(namespace_key, "home"):
            if namespace_key == config.account_namespace_key:
                title = config.portfolio_root_title
            else:
                title = config.namespaces[namespace_key].target_root_title
        current_local_hash = sha256_text(current_local_text)
        synced_local_hash = _last_synced_local_hash(row, current_local_hash)
        body_norm = normalize_markdown_for_sync(body)
        journal_sync_event(
            conn,
            journal_id=journal_id,
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            page_id=row["page_id"],
            operation="sync_push",
            phase="fetch_remote",
            status="running",
            local_hash=current_local_hash,
            payload={"page_id": row["page_id"]},
        )
        if row["mirror_doc_token"]:
            try:
                remote = docs_fetch_full(config, row["mirror_doc_token"])
            except Exception as exc:
                record_issue(
                    conn,
                    issue_type="remote_fetch_failed",
                    severity="high",
                    asset_key=row["asset_key"],
                    page_id=row["page_id"],
                    namespace_key=namespace_key,
                    detail={"phase": "sync_push", "error": str(exc), "mirror_doc_token": row["mirror_doc_token"]},
                )
                conflicts.append(row["page_id"])
                conn.commit()
                if limit and (len(synced) + len(conflicts)) >= limit:
                    break
                continue
            remote_body = remote.get("markdown", "").strip()
            remote_hash = sha256_text(normalize_markdown_for_sync(remote_body))
            last_remote_hash = row["last_remote_hash"] or ""
            if _rebaseline_remote_equivalent(conn, row, title, body, current_local_hash, remote):
                last_remote_hash = remote_hash
            if remote_hash != last_remote_hash:
                enqueue_merge(
                    conn,
                    config,
                    page_id=row["page_id"],
                    asset_key=row["asset_key"],
                    local_base_hash=synced_local_hash,
                    remote_hash=remote_hash,
                    namespace_key=namespace_key,
                    patch_payload={
                        "page_id": row["page_id"],
                        "title": remote.get("title", title),
                        "remote_markdown": remote_body,
                        "mirror_doc_token": row["mirror_doc_token"],
                    },
                    conflict_summary="remote changed since last sync; push skipped",
                )
                conflicts.append(row["page_id"])
                conn.commit()
                if limit and (len(synced) + len(conflicts)) >= limit:
                    break
                continue
        existing_node_token = row["mirror_node_token"] or _infer_existing_node_token(conn, row["asset_key"])
        is_namespace_home = row["page_id"] == namespaced_page_id(namespace_key, "home")
        if is_namespace_home:
            parent_node_token = ""
            if namespace_key != config.account_namespace_key:
                parent_node_token = account_root_node_token
                if not parent_node_token:
                    raise RuntimeError(f"Missing account root node token; run sync_push --namespace {config.account_namespace_key} first.")
        else:
            parent_node_token = root_node_token
            if not parent_node_token:
                raise RuntimeError(f"Missing namespace root node token for {namespace_key}; sync the namespace home page first.")
        mirror_doc_token = row["mirror_doc_token"] or (root_doc_token if is_namespace_home else "")
        journal_sync_event(
            conn,
            journal_id=journal_id,
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            page_id=row["page_id"],
            operation="sync_push",
            phase="write_remote",
            status="running",
            local_hash=current_local_hash,
        )
        url, doc_token, node_token = create_or_update_doc(
            config,
            title=title,
            markdown=body,
            mirror_doc_token=mirror_doc_token,
            existing_node_token=existing_node_token,
            parent_node_token=parent_node_token,
        )
        if is_namespace_home:
            root_doc_token = doc_token or root_doc_token
            root_node_token = node_token or root_node_token
            if root_doc_token:
                set_sync_cursor(conn, f"mirror_root_doc_token::{namespace_key}", root_doc_token, portfolio_key=config.portfolio_key, namespace_key=namespace_key)
            if root_node_token:
                set_sync_cursor(conn, f"mirror_root_node_token::{namespace_key}", root_node_token, portfolio_key=config.portfolio_key, namespace_key=namespace_key)
                _store_namespace_root_node(conn, namespace_key, root_node_token)
        upsert_page(
            conn,
            page_id=row["page_id"],
            page_type=row["page_type"],
            asset_key=row["asset_key"],
            local_path=row["local_path"],
            mirror_doc_token=doc_token or row["mirror_doc_token"],
            mirror_node_token=node_token or row["mirror_node_token"] or _infer_existing_node_token(conn, row["asset_key"], url),
            last_local_hash=current_local_hash,
            last_remote_hash=sha256_text(body_norm),
            sync_mode=row["sync_mode"],
            last_synced_at=now_iso(),
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            metadata={"remote_url": url, "title": title, "last_synced_local_hash": current_local_hash},
        )
        upsert_asset(
            conn,
            asset_key=row["asset_key"],
            asset_class="local_file",
            title=title,
            local_path=row["local_path"],
            remote_url=url,
            remote_id=doc_token or row["mirror_doc_token"],
            upstream_system="llm_wiki_compiler",
            source_hash=current_local_hash,
            canonical_role="canonical_page",
            sync_mode=row["sync_mode"],
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            classification_status="classified",
            last_synced_at=now_iso(),
            metadata={"mirror_node_token": node_token or row["mirror_node_token"] or _infer_existing_node_token(conn, row["asset_key"], url), "remote_url": url},
        )
        journal_sync_event(
            conn,
            journal_id=journal_id,
            portfolio_key=config.portfolio_key,
            namespace_key=namespace_key,
            page_id=row["page_id"],
            operation="sync_push",
            phase="complete",
            status="success",
            local_hash=current_local_hash,
            remote_hash=sha256_text(body_norm),
            payload={"remote_url": url, "mirror_doc_token": doc_token},
        )
        close_issues(conn, issue_type="merge_conflict", page_id=row["page_id"], namespace_key=namespace_key)
        synced.append({"page_id": row["page_id"], "title": title, "remote_url": url, "mirror_doc_token": doc_token})
        conn.commit()
        if limit and len(synced) >= limit:
            break
    return {"synced": synced, "conflicts": conflicts, "root_node_token": root_node_token, "root_doc_token": root_doc_token, "namespace_key": namespace_key}


def enqueue_merge(
    conn: sqlite3.Connection,
    config: AppConfig,
    page_id: str,
    asset_key: str,
    local_base_hash: str,
    remote_hash: str,
    namespace_key: str,
    patch_payload: dict[str, object],
    conflict_summary: str,
) -> None:
    merge_id = sha256_text("|".join([page_id, local_base_hash, remote_hash, json.dumps(patch_payload, ensure_ascii=False, sort_keys=True)]))
    conn.execute(
        """
        INSERT OR REPLACE INTO merge_queue (
            merge_id, portfolio_key, namespace_key, asset_key, page_id, local_base_hash, remote_hash, patch_payload,
            merge_status, conflict_summary, created_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            merge_id,
            config.portfolio_key,
            namespace_key,
            asset_key,
            page_id,
            local_base_hash,
            remote_hash,
            json.dumps(patch_payload, ensure_ascii=False, sort_keys=True),
            "pending",
            conflict_summary,
            now_iso(),
        ),
    )
    record_issue(conn, issue_type="merge_conflict", severity="high", asset_key=asset_key, page_id=page_id, namespace_key=namespace_key, detail={"merge_id": merge_id, "summary": conflict_summary})
    queue_path = config.merge_dir / f"{merge_id}.json"
    queue_path.write_text(json_dumps(patch_payload), encoding="utf-8")


def sync_pull(conn: sqlite3.Connection, config: AppConfig, namespace_key: str, limit: int = 0) -> dict[str, object]:
    updated: list[str] = []
    conflicts: list[str] = []
    page_rows = conn.execute("SELECT * FROM pages WHERE namespace_key = ? AND mirror_doc_token != '' ORDER BY page_id", (namespace_key,)).fetchall()
    for row in page_rows:
        journal_id = sha256_text(f"sync_pull::{namespace_key}::{row['page_id']}::{row['mirror_doc_token']}")
        local_path = config.root / row["local_path"]
        frontmatter, _local_body = read_frontmatter(local_path)
        try:
            remote = docs_fetch_full(config, row["mirror_doc_token"])
        except Exception as exc:
            record_issue(
                conn,
                issue_type="remote_fetch_failed",
                severity="high",
                asset_key=row["asset_key"],
                page_id=row["page_id"],
                namespace_key=namespace_key,
                detail={"phase": "sync_pull", "error": str(exc), "mirror_doc_token": row["mirror_doc_token"]},
            )
            conflicts.append(row["page_id"])
            conn.commit()
            if limit and (len(updated) + len(conflicts)) >= limit:
                break
            continue
        remote_body = remote.get("markdown", "").strip()
        remote_hash = sha256_text(normalize_markdown_for_sync(remote_body))
        last_remote_hash = row["last_remote_hash"] or ""
        current_local_hash = sha256_text(local_path.read_text(encoding="utf-8"))
        last_local_hash = row["last_local_hash"] or current_local_hash
        synced_local_hash = _last_synced_local_hash(row, current_local_hash)
        if remote_hash == last_remote_hash:
            continue
        if not markdown_is_safe(remote_body):
            record_issue(
                conn,
                issue_type="unsupported_remote_markdown",
                severity="high",
                asset_key=row["asset_key"],
                page_id=row["page_id"],
                namespace_key=namespace_key,
                detail={"mirror_doc_token": row["mirror_doc_token"]},
            )
            conflicts.append(row["page_id"])
            continue
        patch_payload = {
            "page_id": row["page_id"],
            "title": remote.get("title", ""),
            "remote_markdown": remote_body,
            "mirror_doc_token": row["mirror_doc_token"],
        }
        if current_local_hash == synced_local_hash:
            new_text = page_frontmatter(
                frontmatter.get("page_id", row["page_id"]),
                frontmatter.get("title", remote.get("title", row["page_id"])),
                frontmatter.get("page_type", row["page_type"]),
                frontmatter.get("asset_key", row["asset_key"]),
                frontmatter.get("source_ids", []),
                frontmatter.get("links_to", []),
                namespace_key=frontmatter.get("namespace_key", namespace_key),
                portfolio_key=frontmatter.get("portfolio_key", config.portfolio_key),
            ) + remote_body + "\n"
            local_path.write_text(new_text, encoding="utf-8")
            upsert_page(
                conn,
                page_id=row["page_id"],
                page_type=row["page_type"],
                asset_key=row["asset_key"],
                local_path=row["local_path"],
                mirror_doc_token=row["mirror_doc_token"],
                mirror_node_token=row["mirror_node_token"],
                last_local_hash=sha256_text(new_text),
                last_remote_hash=remote_hash,
                sync_mode=row["sync_mode"],
                last_synced_at=now_iso(),
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                metadata={"pulled_from_remote": True, "last_synced_local_hash": sha256_text(new_text)},
            )
            _refresh_page_asset(
                conn,
                config,
                asset_key=row["asset_key"],
                title=frontmatter.get("title", remote.get("title", row["page_id"])),
                local_path=row["local_path"],
                source_hash=sha256_text(new_text),
                sync_mode=row["sync_mode"],
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                remote_id=row["mirror_doc_token"],
                mirror_node_token=row["mirror_node_token"],
            )
            journal_sync_event(
                conn,
                journal_id=journal_id,
                portfolio_key=config.portfolio_key,
                namespace_key=namespace_key,
                page_id=row["page_id"],
                operation="sync_pull",
                phase="complete",
                status="success",
                local_hash=sha256_text(new_text),
                remote_hash=remote_hash,
            )
            updated.append(row["page_id"])
        else:
            enqueue_merge(
                conn,
                config,
                page_id=row["page_id"],
                asset_key=row["asset_key"],
                local_base_hash=synced_local_hash,
                remote_hash=remote_hash,
                namespace_key=namespace_key,
                patch_payload=patch_payload,
                conflict_summary="local and remote changed since last sync",
            )
            conflicts.append(row["page_id"])
        conn.commit()
        if limit and (len(updated) + len(conflicts)) >= limit:
            break
    return {"updated_pages": updated, "conflicts": conflicts, "namespace_key": namespace_key}


def merge_patches(conn: sqlite3.Connection, config: AppConfig, namespace_key: str) -> dict[str, object]:
    pending = conn.execute("SELECT merge_id, page_id, conflict_summary FROM merge_queue WHERE namespace_key = ? AND merge_status = 'pending' ORDER BY created_at", (namespace_key,)).fetchall()
    summary_path = config.merge_dir / "README.md"
    lines = ["# Merge Queue", ""]
    resolved = 0
    manual = 0
    if pending:
        for row in pending:
            patch_row = conn.execute(
                "SELECT * FROM merge_queue WHERE merge_id = ?",
                (row["merge_id"],),
            ).fetchone()
            payload = json.loads(patch_row["patch_payload"])
            page = conn.execute("SELECT * FROM pages WHERE page_id = ?", (row["page_id"],)).fetchone()
            if not page:
                continue
            local_path = config.root / page["local_path"]
            frontmatter, _ = read_frontmatter(local_path)
            current_local_text = local_path.read_text(encoding="utf-8")
            current_local_hash = sha256_text(current_local_text)
            if current_local_hash == patch_row["local_base_hash"] and payload.get("remote_markdown") and markdown_is_safe(str(payload.get("remote_markdown", ""))):
                merged_text = page_frontmatter(
                    frontmatter.get("page_id", page["page_id"]),
                    frontmatter.get("title", payload.get("title", page["page_id"])),
                    frontmatter.get("page_type", page["page_type"]),
                    frontmatter.get("asset_key", page["asset_key"]),
                    frontmatter.get("source_ids", []),
                    frontmatter.get("links_to", []),
                    namespace_key=frontmatter.get("namespace_key", namespace_key),
                    portfolio_key=frontmatter.get("portfolio_key", config.portfolio_key),
                ) + payload["remote_markdown"].strip() + "\n"
                local_path.write_text(merged_text, encoding="utf-8")
                upsert_page(
                    conn,
                    page_id=page["page_id"],
                    page_type=page["page_type"],
                    asset_key=page["asset_key"],
                    local_path=page["local_path"],
                    mirror_doc_token=page["mirror_doc_token"],
                    mirror_node_token=page["mirror_node_token"],
                    last_local_hash=sha256_text(merged_text),
                    last_remote_hash=patch_row["remote_hash"],
                    sync_mode=page["sync_mode"],
                    last_synced_at=now_iso(),
                    portfolio_key=config.portfolio_key,
                    namespace_key=namespace_key,
                    metadata={"merge_id": row["merge_id"], "merge_mode": "applied_remote", "last_synced_local_hash": sha256_text(merged_text)},
                )
                _refresh_page_asset(
                    conn,
                    config,
                    asset_key=page["asset_key"],
                    title=payload.get("title", page["page_id"]),
                    local_path=page["local_path"],
                    source_hash=sha256_text(merged_text),
                    sync_mode=page["sync_mode"],
                    portfolio_key=config.portfolio_key,
                    namespace_key=namespace_key,
                    remote_id=page["mirror_doc_token"],
                    mirror_node_token=page["mirror_node_token"],
                )
                conn.execute(
                    "UPDATE merge_queue SET merge_status = 'resolved', resolved_at = ? WHERE merge_id = ?",
                    (now_iso(), row["merge_id"]),
                )
                close_issues(conn, issue_type="merge_conflict", page_id=row["page_id"], namespace_key=namespace_key, detail_contains={"merge_id": row["merge_id"]})
                resolved += 1
                lines.append(f"- `{row['merge_id']}` | `{row['page_id']}` | resolved by applying remote patch")
            elif row["conflict_summary"] == "remote changed since last sync; push skipped":
                upsert_page(
                    conn,
                    page_id=page["page_id"],
                    page_type=page["page_type"],
                    asset_key=page["asset_key"],
                    local_path=page["local_path"],
                    mirror_doc_token=page["mirror_doc_token"],
                    mirror_node_token=page["mirror_node_token"],
                    last_local_hash=current_local_hash,
                    last_remote_hash=patch_row["remote_hash"],
                    sync_mode=page["sync_mode"],
                    last_synced_at=page["last_synced_at"],
                    portfolio_key=config.portfolio_key,
                    namespace_key=namespace_key,
                    metadata={"merge_id": row["merge_id"], "merge_mode": "local_authoritative_rebaseline"},
                )
                _refresh_page_asset(
                    conn,
                    config,
                    asset_key=page["asset_key"],
                    title=frontmatter.get("title", page["page_id"]),
                    local_path=page["local_path"],
                    source_hash=current_local_hash,
                    sync_mode=page["sync_mode"],
                    portfolio_key=config.portfolio_key,
                    namespace_key=namespace_key,
                    remote_id=page["mirror_doc_token"],
                    mirror_node_token=page["mirror_node_token"],
                )
                conn.execute(
                    "UPDATE merge_queue SET merge_status = 'resolved', resolved_at = ? WHERE merge_id = ?",
                    (now_iso(), row["merge_id"]),
                )
                close_issues(conn, issue_type="merge_conflict", page_id=row["page_id"], namespace_key=namespace_key, detail_contains={"merge_id": row["merge_id"]})
                resolved += 1
                lines.append(f"- `{row['merge_id']}` | `{row['page_id']}` | resolved by rebasing remote baseline for local-authoritative push")
            else:
                manual += 1
                conflict_path = config.merge_dir / f"{row['merge_id']}.md"
                conflict_path.write_text(
                    "\n".join(
                        [
                            f"# Merge Conflict {row['merge_id']}",
                            "",
                            f"- page_id: `{row['page_id']}`",
                            f"- summary: {row['conflict_summary']}",
                            "",
                            "## Local",
                            "",
                            current_local_text,
                            "",
                            "## Remote",
                            "",
                            str(payload.get("remote_markdown", "")),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                conn.execute(
                    "UPDATE merge_queue SET merge_status = 'needs_manual_review' WHERE merge_id = ?",
                    (row["merge_id"],),
                )
                lines.append(f"- `{row['merge_id']}` | `{row['page_id']}` | requires manual review")
    else:
        lines.append("- 当前没有待处理冲突。")
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    conn.commit()
    return {
        "pending_count": len(pending),
        "resolved_count": resolved,
        "manual_review_count": manual,
        "summary_path": relative_to_root(summary_path, config.root),
        "namespace_key": namespace_key,
    }

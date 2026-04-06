from __future__ import annotations

from collections import Counter
import sqlite3
from pathlib import Path

from ..config import AppConfig
from ..db import upsert_asset
from ..utils import json_dumps, now_iso, relative_to_root, sha256_bytes, sha256_text, iter_repo_files


def local_file_asset_class(path: Path) -> str:
    if path.suffix.lower() == ".sqlite":
        return "local_db"
    if path.name.endswith("_manifest.json") or "manifest" in path.name:
        return "manifest"
    return "local_file"


def local_file_role(config: AppConfig, path: Path) -> str:
    rel = relative_to_root(path, config.root)
    if rel.startswith("archive/") or rel.startswith("archives/"):
        return "archive"
    if rel.startswith("examples/"):
        return "seed"
    if rel.startswith("demo/"):
        return "delivery"
    if rel.startswith("state/"):
        return "state_snapshot"
    if rel.startswith("knowledge/wiki_src"):
        return "canonical_page"
    return "source_only"


def discover_local_repo_assets(conn: sqlite3.Connection, config: AppConfig) -> dict[str, object]:
    counts = Counter()
    snapshot: list[dict[str, str]] = []
    for path in iter_repo_files(config, config.allowed_local_suffixes):
        if path.resolve() == config.state_db.resolve():
            continue
        rel = relative_to_root(path, config.root)
        data = path.read_bytes()
        source_hash = sha256_bytes(data)
        asset_class = local_file_asset_class(path)
        canonical_role = local_file_role(config, path)
        asset_key = f"LOCAL::{rel}"
        upsert_asset(
            conn,
            asset_key=asset_key,
            asset_class=asset_class,
            title=path.stem,
            local_path=rel,
            upstream_system="local_repo",
            source_hash=source_hash,
            canonical_role=canonical_role,
            sync_mode="local_only",
            metadata={
                "size_bytes": path.stat().st_size,
                "suffix": path.suffix.lower(),
                "relative_path": rel,
            },
        )
        snapshot.append(
            {
                "asset_key": asset_key,
                "asset_class": asset_class,
                "canonical_role": canonical_role,
                "local_path": rel,
                "source_hash": source_hash,
            }
        )
        counts[asset_class] += 1

    snapshot_path = config.raw_dir / "local_repo" / "local_repo_assets.json"
    snapshot_path.write_text(json_dumps({"generated_at": now_iso(), "counts": dict(counts), "items": snapshot}), encoding="utf-8")
    upsert_asset(
        conn,
        asset_key="STATE::local_repo_assets_snapshot",
        asset_class="state_snapshot",
        title="本地仓库资产快照",
        local_path=relative_to_root(snapshot_path, config.root),
        upstream_system="local_repo",
        source_hash=sha256_text(snapshot_path.read_text(encoding="utf-8")),
        canonical_role="state_snapshot",
        sync_mode="local_only",
        metadata={"counts": dict(counts)},
    )
    conn.commit()
    return {"counts": dict(counts), "snapshot_path": relative_to_root(snapshot_path, config.root)}

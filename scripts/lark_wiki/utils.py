from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import AppConfig


FEISHU_URL_RE = re.compile(r"https://[A-Za-z0-9.-]*feishu\.cn/(?:wiki|docx|base|slides)/[A-Za-z0-9]+(?:[^\s)\]>\"']*)?")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(text: str) -> str:
    lowered = text.strip().lower()
    replaced = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", lowered)
    return replaced.strip("-") or "untitled"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig", errors="ignore")


def iter_repo_files(config: AppConfig, suffixes: set[str] | None = None) -> Iterable[Path]:
    for path in sorted(config.root.rglob("*")):
        if not path.is_file():
            continue
        rel = relative_to_root(path, config.root)
        if any(rel == prefix or rel.startswith(f"{prefix}/") for prefix in config.excluded_prefixes):
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        yield path


def scan_local_text_urls(config: AppConfig) -> list[str]:
    urls: set[str] = set()
    for path in iter_repo_files(config, config.text_scan_suffixes):
        urls.update(FEISHU_URL_RE.findall(read_text_safe(path)))
    return sorted(urls)

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


UNSAFE_MARKDOWN_PATTERNS = [
    re.compile(r"^\s*-\s+\[[ xX]\]\s+", re.MULTILINE),
    re.compile(r"whiteboard", re.IGNORECASE),
    re.compile(r"sheet", re.IGNORECASE),
]
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def page_frontmatter(
    page_id: str,
    title: str,
    page_type: str,
    asset_key: str,
    source_ids: list[str],
    links_to: list[str],
    *,
    namespace_key: str = "inbox",
    portfolio_key: str = "portfolio::default",
) -> str:
    payload = {
        "page_id": page_id,
        "title": title,
        "page_type": page_type,
        "asset_key": asset_key,
        "source_ids": source_ids,
        "links_to": links_to,
        "namespace_key": namespace_key,
        "portfolio_key": portfolio_key,
        "sync_mode": "bidirectional_markdown_safe",
    }
    return "---\n" + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n---\n\n"


def write_canonical_page(
    base_dir: Path,
    page_id: str,
    title: str,
    page_type: str,
    rel_path: Path,
    asset_key: str,
    source_ids: list[str],
    links_to: list[str],
    body: str,
    *,
    namespace_key: str = "inbox",
    portfolio_key: str = "portfolio::default",
) -> str:
    full_path = base_dir / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    text = page_frontmatter(
        page_id,
        title,
        page_type,
        asset_key,
        source_ids,
        links_to,
        namespace_key=namespace_key,
        portfolio_key=portfolio_key,
    ) + body.strip() + "\n"
    full_path.write_text(text, encoding="utf-8")
    return text


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    _, rest = text.split("---\n", 1)
    frontmatter_raw, body = rest.split("\n---\n", 1)
    return json.loads(frontmatter_raw), body


def markdown_is_safe(markdown: str) -> bool:
    return not any(pattern.search(markdown) for pattern in UNSAFE_MARKDOWN_PATTERNS)


def normalize_markdown_for_sync(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n").strip()
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    # Feishu stores the document title separately, so fetched markdown often
    # omits the leading H1 that exists in our canonical page body.
    text = re.sub(r"^\#\s+[^\n]+\n+", "", text, count=1)
    # Feishu fetch often removes the blank line immediately after headings.
    text = re.sub(r"^(#{1,6}[^\n]*)\n\n+(?=\S)", r"\1\n", text, flags=re.MULTILINE)
    # It also commonly removes the blank line between the end of a bullet list
    # and the following paragraph.
    text = re.sub(r"^([*-]\s[^\n]+)\n\n+(?=\S)", r"\1\n", text, flags=re.MULTILINE)
    # Feishu fetch also tends to tighten paragraph-to-heading spacing.
    text = re.sub(r"(?<=\S)\n\n+(?=#{1,6}\s)", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

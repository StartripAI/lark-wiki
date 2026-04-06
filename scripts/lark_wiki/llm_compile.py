from __future__ import annotations

from dataclasses import dataclass
import json
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import AppConfig
from .utils import read_text_safe


@dataclass(frozen=True)
class AssetContext:
    asset_key: str
    title: str
    asset_class: str
    namespace_key: str
    snippet: str


def llm_provider_name(config: AppConfig) -> str:
    provider = (config.llm_provider or "disabled").strip().lower()
    if provider == "auto":
        if shutil.which("codex"):
            return "codex_exec"
        if config.llm_command:
            return "command"
        return "disabled"
    if provider == "codex_exec" and not shutil.which("codex"):
        return "disabled"
    if provider == "command" and not config.llm_command:
        return "disabled"
    return provider


def llm_enabled(config: AppConfig) -> bool:
    return llm_provider_name(config) != "disabled"


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _asset_text_from_row(config: AppConfig, row: sqlite3.Row) -> str:
    local_path = str(row["local_path"] or "")
    if local_path:
        full_path = config.root / local_path
        if full_path.exists():
            suffix = full_path.suffix.lower()
            if suffix in {".md", ".txt", ".csv", ".json", ".html"}:
                raw_text = read_text_safe(full_path)
                if suffix == ".json":
                    try:
                        payload = json.loads(raw_text)
                    except json.JSONDecodeError:
                        payload = {}
                    for key in ("markdown", "body", "text", "summary"):
                        value = payload.get(key)
                        if isinstance(value, str) and value.strip():
                            return value
                return raw_text
    metadata_json = row["metadata_json"] or ""
    if metadata_json:
        try:
            payload = json.loads(metadata_json)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            for key in ("markdown", "summary", "description", "title"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return str(row["title"] or "")


def collect_asset_context(
    conn: sqlite3.Connection,
    config: AppConfig,
    asset_keys: list[str],
) -> list[AssetContext]:
    contexts: list[AssetContext] = []
    seen: set[str] = set()
    for asset_key in asset_keys:
        if not asset_key or asset_key in seen:
            continue
        seen.add(asset_key)
        row = conn.execute(
            """
            SELECT asset_key, title, asset_class, namespace_key, local_path, metadata_json
            FROM assets
            WHERE asset_key = ?
            """,
            (asset_key,),
        ).fetchone()
        if not row:
            continue
        snippet = _truncate(_asset_text_from_row(config, row), config.llm_max_chars_per_asset)
        contexts.append(
            AssetContext(
                asset_key=row["asset_key"],
                title=row["title"] or row["asset_key"],
                asset_class=row["asset_class"] or "unknown",
                namespace_key=row["namespace_key"] or "",
                snippet=snippet,
            )
        )
        if len(contexts) >= config.llm_max_assets_per_prompt:
            break
    return contexts


def _payload_to_prompt(payload: dict[str, Any], *, expect_json: bool) -> str:
    output_instruction = (
        "Return valid JSON only, with no markdown fences or explanation."
        if expect_json
        else "Return markdown only, with no code fences or prefatory text."
    )
    return "\n".join(
        [
            "You are the grounded knowledge compiler for a local-first portfolio wiki.",
            "Use only the supplied sources. Do not fabricate facts. Prefer synthesis, contradictions, implications, and open questions.",
            "Cite asset keys inline when making non-obvious claims, e.g. `(source: ASSET_KEY)`.",
            output_instruction,
            "",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _run_codex_exec(config: AppConfig, prompt: str) -> str:
    with tempfile.TemporaryDirectory(prefix="lark-wiki-") as tmpdir:
        prompt_path = Path(tmpdir) / "prompt.txt"
        output_path = Path(tmpdir) / "output.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        cmd = [
            "codex",
            "exec",
            "-C",
            str(config.root),
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
            "-",
        ]
        if config.llm_model:
            cmd.extend(["-m", config.llm_model])
        with prompt_path.open("r", encoding="utf-8") as handle:
            subprocess.run(
                cmd,
                stdin=handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=config.llm_timeout_seconds,
                check=True,
            )
        return output_path.read_text(encoding="utf-8").strip()


def _run_command_provider(config: AppConfig, payload: dict[str, Any]) -> str:
    cmd = shlex.split(config.llm_command)
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload, ensure_ascii=False),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=config.llm_timeout_seconds,
        check=True,
    )
    return proc.stdout.strip()


def _mock_markdown(payload: dict[str, Any]) -> str:
    contexts = payload.get("contexts", []) or []
    asset_keys = [item.get("asset_key", "") for item in contexts][:3]
    theme_lines = []
    for item in contexts[:3]:
        snippet = _truncate(str(item.get("snippet", "")).replace("\n", " "), 120)
        theme_lines.append(f"- `{item.get('asset_key', '')}`：{snippet}")
    lines = [
        f"### Grounded Summary",
        f"- Page intent: {payload.get('title', 'Untitled')}",
        f"- Sources consulted: {', '.join(asset_keys) if asset_keys else 'none'}",
    ]
    if theme_lines:
        lines.extend(["", "### Evidence Highlights", *theme_lines])
    return "\n".join(lines).strip()


def _mock_semantic_lint(payload: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    claim_map: dict[str, set[tuple[str, str]]] = {}
    for page in payload.get("pages", []) or []:
        page_id = str(page.get("page_id", ""))
        body = str(page.get("body", ""))
        for match in re.finditer(r"Claim:\s*(.+?)\s*=>\s*(.+)", body):
            lhs = match.group(1).strip()
            rhs = match.group(2).strip()
            claim_map.setdefault(lhs, set()).add((rhs, page_id))
    contradictions: list[dict[str, str]] = []
    for lhs, rhs_pairs in claim_map.items():
        values = {rhs for rhs, _ in rhs_pairs}
        if len(values) > 1:
            contradictions.append(
                {
                    "claim": lhs,
                    "page_ids": ", ".join(sorted({page_id for _, page_id in rhs_pairs})),
                    "detail": "Conflicting mock claim values",
                }
            )
    return {
        "contradictions": contradictions,
        "stale_claims": [],
        "missing_pages": [],
        "missing_cross_references": [],
    }


def _invoke_text(config: AppConfig, payload: dict[str, Any]) -> str:
    provider = llm_provider_name(config)
    if provider == "disabled":
        return ""
    if provider == "mock":
        return _mock_markdown(payload)
    if provider == "command":
        return _run_command_provider(config, payload)
    if provider == "codex_exec":
        return _run_codex_exec(config, _payload_to_prompt(payload, expect_json=False))
    raise RuntimeError(f"Unsupported LLM provider: {provider}")


def _invoke_json(config: AppConfig, payload: dict[str, Any]) -> dict[str, Any]:
    provider = llm_provider_name(config)
    if provider == "disabled":
        return {}
    if provider == "mock":
        return _mock_semantic_lint(payload)
    raw = _run_command_provider(config, payload) if provider == "command" else _run_codex_exec(config, _payload_to_prompt(payload, expect_json=True))
    return json.loads(raw)


def compile_page_markdown(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
    title: str,
    page_type: str,
    base_body: str,
    source_ids: list[str],
) -> str:
    contexts = collect_asset_context(conn, config, source_ids)
    if not contexts:
        return ""
    payload = {
        "task": "page_synthesis",
        "namespace_key": namespace_key,
        "title": title,
        "page_type": page_type,
        "base_body": base_body,
        "contexts": [context.__dict__ for context in contexts],
    }
    return _invoke_text(config, payload)


def compile_query_markdown(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
    keyword: str,
    asset_keys: list[str],
) -> str:
    contexts = collect_asset_context(conn, config, asset_keys)
    if not contexts:
        return ""
    payload = {
        "task": "query_synthesis",
        "namespace_key": namespace_key,
        "keyword": keyword,
        "title": f"Query Report: {keyword}",
        "contexts": [context.__dict__ for context in contexts],
    }
    return _invoke_text(config, payload)


def semantic_lint_namespace(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    namespace_key: str,
) -> dict[str, list[dict[str, str]]]:
    if not config.llm_semantic_lint_enabled or not llm_enabled(config):
        return {}
    page_rows = conn.execute(
        """
        SELECT page_id, local_path
        FROM pages
        WHERE namespace_key = ?
        ORDER BY page_id
        LIMIT 24
        """,
        (namespace_key,),
    ).fetchall()
    pages: list[dict[str, str]] = []
    for row in page_rows:
        path = config.root / str(row["local_path"] or "")
        body = read_text_safe(path) if path.exists() else ""
        pages.append({"page_id": row["page_id"], "body": _truncate(body, config.llm_max_chars_per_asset)})
    payload = {
        "task": "semantic_lint",
        "namespace_key": namespace_key,
        "pages": pages,
        "schema": {
            "contradictions": [{"claim": "text", "page_ids": "comma-separated ids", "detail": "text"}],
            "stale_claims": [{"page_ids": "ids", "detail": "text"}],
            "missing_pages": [{"detail": "text"}],
            "missing_cross_references": [{"page_ids": "ids", "detail": "text"}],
        },
    }
    result = _invoke_json(config, payload)
    if not isinstance(result, dict):
        return {}
    return result

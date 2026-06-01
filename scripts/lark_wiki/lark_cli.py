from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from .config import AppConfig


def run_command(config: AppConfig, cmd: Sequence[str], allow_empty: bool = False) -> str:
    attempts = 8
    for attempt in range(attempts):
        try:
            completed = subprocess.run(
                list(cmd),
                cwd=str(config.root),
                check=True,
                capture_output=True,
                text=True,
            )
            stdout = completed.stdout.strip()
            if not stdout and not allow_empty:
                raise RuntimeError(f"Command produced empty stdout: {' '.join(cmd)}")
            return stdout
        except subprocess.CalledProcessError as exc:
            combined = f"{exc.stdout}\n{exc.stderr}"
            if attempt < attempts - 1 and ("99991400" in combined or "request trigger frequency limit" in combined):
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"Command failed after retries: {' '.join(cmd)}")


def run_lark(config: AppConfig, args: list[str], allow_empty: bool = False) -> dict[str, Any]:
    raw = run_command(config, ["lark-cli", *args], allow_empty=allow_empty)
    if not raw:
        return {}
    return json.loads(raw)


def pick_first(data: dict[str, Any], candidates: list[list[str]]) -> str:
    for path in candidates:
        current: Any = data
        ok = True
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                ok = False
                break
        if ok and isinstance(current, str) and current:
            return current
    return ""


def detect_base_token(url: str) -> str:
    match = re.search(r"/base/([A-Za-z0-9]+)", url)
    return match.group(1) if match else ""


def detect_doc_token(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    match = re.search(r"/(wiki|docx|slides)/([A-Za-z0-9]+)", parsed.path)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def search_docs(config: AppConfig, query: str) -> list[dict[str, Any]]:
    payload = run_lark(config, ["docs", "+search", "--as", "user", "--query", query])
    return payload.get("data", {}).get("results", []) or []


def wiki_get_node(config: AppConfig, token: str, obj_type: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"token": token}
    if obj_type:
        params["obj_type"] = obj_type
    payload = run_lark(config, ["wiki", "spaces", "get_node", "--as", "user", "--params", json.dumps(params, ensure_ascii=False)])
    return payload.get("data", {}).get("node", {}) or {}


def wiki_list_children(config: AppConfig, space_id: str, parent_node_token: str) -> list[dict[str, Any]]:
    payload = run_lark(
        config,
        [
            "wiki",
            "nodes",
            "list",
            "--as",
            "user",
            "--params",
            json.dumps({"space_id": space_id, "parent_node_token": parent_node_token, "page_size": 50}, ensure_ascii=False),
        ],
    )
    return payload.get("data", {}).get("items", []) or []


def wiki_list_spaces(config: AppConfig) -> list[dict[str, Any]]:
    payload = run_lark(
        config,
        [
            "wiki",
            "spaces",
            "list",
            "--as",
            "user",
            "--page-all",
        ],
    )
    return payload.get("data", {}).get("items", []) or payload.get("data", {}).get("spaces", []) or []


def _strip_v2_title(content: str) -> tuple[str, str]:
    match = re.match(r"\s*<title>(.*?)</title>\s*", content, flags=re.DOTALL)
    if not match:
        return "", content
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title, content[match.end() :].lstrip()


def docs_fetch_full(config: AppConfig, doc_ref: str, chunk_size: int = 2000) -> dict[str, str]:
    payload = run_lark(
        config,
        [
            "docs",
            "+fetch",
            "--api-version",
            "v2",
            "--as",
            "user",
            "--doc",
            doc_ref,
            "--doc-format",
            "markdown",
            "--format",
            "json",
        ],
    )
    data = payload.get("data", {}) or {}
    document = data.get("document", {}) or {}
    content = str(document.get("content") or "")
    title, markdown = _strip_v2_title(content)
    return {
        "doc_id": str(document.get("document_id") or data.get("doc_id") or ""),
        "title": str(document.get("title") or data.get("title") or title),
        "markdown": markdown,
    }


def base_list_tables(config: AppConfig, base_token: str) -> list[dict[str, Any]]:
    payload = run_lark(config, ["base", "+table-list", "--as", "user", "--base-token", base_token])
    return payload.get("data", {}).get("items", []) or []


def base_list_views(config: AppConfig, base_token: str, table_id: str) -> list[dict[str, Any]]:
    payload = run_lark(config, ["base", "+view-list", "--as", "user", "--base-token", base_token, "--table-id", table_id])
    return payload.get("data", {}).get("items", []) or []


def base_list_fields(config: AppConfig, base_token: str, table_id: str) -> list[dict[str, Any]]:
    payload = run_lark(config, ["base", "+field-list", "--as", "user", "--base-token", base_token, "--table-id", table_id])
    return payload.get("data", {}).get("items", []) or []


def base_create_field(config: AppConfig, base_token: str, table_id: str, field_name: str, field_type: str = "text") -> dict[str, Any]:
    return run_lark(
        config,
        [
            "base",
            "+field-create",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps({"field_name": field_name, "type": field_type}, ensure_ascii=False),
        ],
    )


def base_list_records(config: AppConfig, base_token: str, table_id: str, limit: int = 200, offset: int = 0) -> dict[str, Any]:
    payload = run_lark(
        config,
        [
            "base",
            "+record-list",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--limit",
            str(limit),
            "--offset",
            str(offset),
        ],
    )
    return payload.get("data", {}) or {}


def base_upsert_record(
    config: AppConfig,
    base_token: str,
    table_id: str,
    fields: dict[str, Any],
    record_id: str = "",
) -> dict[str, Any]:
    args = [
        "base",
        "+record-upsert",
        "--as",
        "user",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
        "--json",
        json.dumps(fields, ensure_ascii=False),
    ]
    if record_id:
        args.extend(["--record-id", record_id])
    return run_lark(config, args)


def base_batch_create_records(
    config: AppConfig,
    base_token: str,
    table_id: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {"records": [{"fields": record} for record in records]}
    return run_lark(
        config,
        [
            "api",
            "POST",
            f"/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/batch_create",
            "--as",
            "user",
            "--data",
            json.dumps(payload, ensure_ascii=False),
        ],
    )

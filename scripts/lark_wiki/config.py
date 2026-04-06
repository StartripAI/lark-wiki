from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib


@dataclass(frozen=True)
class NamespaceConfig:
    namespace_key: str
    slug: str
    display_name: str
    kind: str
    target_root_title: str
    local_roots: tuple[str, ...]
    title_keywords: tuple[str, ...]
    wiki_seed_nodes: tuple[str, ...]
    base_tokens: tuple[str, ...]
    project_env_path: Path | None
    orchestrator_db_path: Path | None
    project_sync_db_path: Path | None
    master_csv_path: Path | None
    consistency_matrix_path: Path | None


@dataclass(frozen=True)
class AppConfig:
    root: Path
    knowledge_root: Path
    raw_dir: Path
    wiki_src_dir: Path
    assets_dir: Path
    build_dir: Path
    merge_dir: Path
    state_dir: Path
    state_db: Path
    readme_path: Path
    allowed_local_suffixes: set[str]
    text_scan_suffixes: set[str]
    excluded_prefixes: tuple[str, ...]
    markdown_safe_page_types: set[str]
    llm_provider: str
    llm_model: str
    llm_command: str
    llm_timeout_seconds: int
    llm_max_assets_per_prompt: int
    llm_max_chars_per_asset: int
    llm_semantic_lint_enabled: bool
    portfolio_key: str
    portfolio_root_title: str
    account_namespace_key: str
    shared_namespace_key: str
    inbox_namespace_key: str
    default_project_namespace: str
    namespaces: dict[str, NamespaceConfig]
    ops_base_title: str
    lark_wiki_space: str
    portfolio_root_node: str
    project_env_path: Path | None
    orchestrator_db: Path | None
    project_sync_db: Path | None
    master_csv_path: Path | None
    consistency_matrix_path: Path | None
    title_keywords: tuple[str, ...]
    target_root_title: str
    current_main_wiki_node: str


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _load_overrides(repo_root: Path) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    state_dir = repo_root / "state"
    for name in ["llm_wiki.portfolio.toml", "llm_wiki.projects.toml", "llm_wiki_v1.local.toml"]:
        merged = _merge_dict(merged, _load_toml(state_dir / name))
    project_dir = state_dir / "llm_wiki.projects"
    if project_dir.exists():
        for path in sorted(project_dir.glob("*.toml")):
            project_payload = _load_toml(path)
            if project_payload:
                merged = _merge_dict(merged, {"projects": project_payload})
    return merged


def _resolve(repo_root: Path, rel_path: str) -> Path:
    return (repo_root / rel_path).resolve()


def _namespace_from_payload(repo_root: Path, namespace_key: str, payload: dict[str, Any]) -> NamespaceConfig:
    def resolve_optional(key: str) -> Path | None:
        rel_path = str(payload.get(key, "") or "").strip()
        return _resolve(repo_root, rel_path) if rel_path else None

    return NamespaceConfig(
        namespace_key=namespace_key,
        slug=str(payload.get("slug", namespace_key.split("::")[-1])),
        display_name=str(payload.get("display_name", namespace_key.split("::")[-1])),
        kind=str(payload.get("kind", "project")),
        target_root_title=str(payload.get("target_root_title", namespace_key.split("::")[-1])),
        local_roots=tuple(payload.get("local_roots", []) or []),
        title_keywords=tuple(payload.get("title_keywords", []) or []),
        wiki_seed_nodes=tuple(payload.get("wiki_seed_nodes", []) or []),
        base_tokens=tuple(payload.get("base_tokens", []) or []),
        project_env_path=resolve_optional("project_env"),
        orchestrator_db_path=resolve_optional("orchestrator_db"),
        project_sync_db_path=resolve_optional("project_sync_db"),
        master_csv_path=resolve_optional("master_csv"),
        consistency_matrix_path=resolve_optional("consistency_matrix"),
    )


def build_config(root: Path | None = None) -> AppConfig:
    repo_root = (root or _repo_root()).resolve()
    defaults_path = Path(__file__).with_name("defaults.toml")
    merged = _merge_dict(_load_toml(defaults_path), _load_overrides(repo_root))

    knowledge_root = _resolve(repo_root, merged["paths"]["knowledge_root"])
    state_dir = _resolve(repo_root, merged["paths"]["state_dir"])
    build_dir = knowledge_root / "build"
    portfolio_cfg = merged["portfolio"]
    llm_cfg = merged.get("llm", {}) or {}

    namespace_payloads = {key: value for key, value in (merged.get("namespaces", {}) or {}).items()}
    project_payloads = merged.get("projects", {}) or {}
    namespaces: dict[str, NamespaceConfig] = {}
    for key, payload in namespace_payloads.items():
        namespaces[key] = _namespace_from_payload(repo_root, key, payload)
    for key, payload in project_payloads.items():
        namespace_key = str(payload.get("namespace_key") or f"project::{key}")
        payload = {"slug": key, **payload}
        namespaces[namespace_key] = _namespace_from_payload(repo_root, namespace_key, payload)

    default_project_namespace = str(portfolio_cfg["default_project_namespace"])
    default_project = namespaces[default_project_namespace]

    return AppConfig(
        root=repo_root,
        knowledge_root=knowledge_root,
        raw_dir=knowledge_root / "raw",
        wiki_src_dir=knowledge_root / "wiki_src",
        assets_dir=knowledge_root / "assets",
        build_dir=build_dir,
        merge_dir=build_dir / "merge_queue",
        state_dir=state_dir,
        state_db=_resolve(repo_root, merged["paths"]["state_db"]),
        readme_path=_resolve(repo_root, merged["paths"]["readme"]),
        allowed_local_suffixes=set(merged["scope"]["allowed_local_suffixes"]),
        text_scan_suffixes=set(merged["scope"]["text_scan_suffixes"]),
        excluded_prefixes=tuple(merged["scope"]["excluded_prefixes"]),
        markdown_safe_page_types=set(merged["sync"]["markdown_safe_page_types"]),
        llm_provider=str(llm_cfg.get("provider", "disabled")),
        llm_model=str(llm_cfg.get("model", "gpt-5.4-mini")),
        llm_command=str(llm_cfg.get("command", "")),
        llm_timeout_seconds=int(llm_cfg.get("timeout_seconds", 180)),
        llm_max_assets_per_prompt=int(llm_cfg.get("max_assets_per_prompt", 6)),
        llm_max_chars_per_asset=int(llm_cfg.get("max_chars_per_asset", 3500)),
        llm_semantic_lint_enabled=bool(llm_cfg.get("semantic_lint_enabled", True)),
        portfolio_key=str(portfolio_cfg["portfolio_key"]),
        portfolio_root_title=str(portfolio_cfg["portfolio_root_title"]),
        account_namespace_key=str(portfolio_cfg["account_namespace_key"]),
        shared_namespace_key=str(portfolio_cfg["shared_namespace_key"]),
        inbox_namespace_key=str(portfolio_cfg["inbox_namespace_key"]),
        default_project_namespace=default_project_namespace,
        namespaces=namespaces,
        ops_base_title=str(merged["feishu"]["ops_base_title"]),
        lark_wiki_space=str(merged["feishu"]["lark_wiki_space"]),
        portfolio_root_node=str(merged["feishu"].get("portfolio_root_node", "") or ""),
        project_env_path=default_project.project_env_path,
        orchestrator_db=default_project.orchestrator_db_path,
        project_sync_db=default_project.project_sync_db_path,
        master_csv_path=default_project.master_csv_path,
        consistency_matrix_path=default_project.consistency_matrix_path,
        title_keywords=default_project.title_keywords,
        target_root_title=default_project.target_root_title,
        current_main_wiki_node=default_project.wiki_seed_nodes[0] if default_project.wiki_seed_nodes else "",
    )

from __future__ import annotations

from pathlib import Path

from .config import AppConfig


def namespace_slug(namespace_key: str) -> str:
    return namespace_key.split("::")[-1]


def namespace_root_relpath(config: AppConfig, namespace_key: str) -> str:
    if namespace_key == config.account_namespace_key:
        return "account"
    if namespace_key == config.shared_namespace_key:
        return "shared"
    if namespace_key == config.inbox_namespace_key:
        return "inbox"
    namespace = config.namespaces[namespace_key]
    return f"projects/{namespace.slug}"


def namespace_root_dir(config: AppConfig, namespace_key: str) -> Path:
    return config.wiki_src_dir / namespace_root_relpath(config, namespace_key)


def namespaced_page_id(namespace_key: str, short_id: str) -> str:
    return f"{namespace_key}::{short_id}"


def page_asset_key(namespace_key: str, short_id: str) -> str:
    return f"PAGE::{namespace_key}::{short_id}"


def namespace_display_name(config: AppConfig, namespace_key: str) -> str:
    namespace = config.namespaces.get(namespace_key)
    if namespace:
        return namespace.display_name
    return namespace_key

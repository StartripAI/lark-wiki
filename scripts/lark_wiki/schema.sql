CREATE TABLE IF NOT EXISTS namespaces (
    namespace_key TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    slug TEXT NOT NULL,
    isolation_mode TEXT NOT NULL DEFAULT 'strict',
    root_local_path TEXT NOT NULL DEFAULT '',
    remote_root_node_token TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    asset_key TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'inbox',
    asset_class TEXT NOT NULL,
    title TEXT NOT NULL,
    local_path TEXT NOT NULL DEFAULT '',
    remote_url TEXT NOT NULL DEFAULT '',
    remote_id TEXT NOT NULL DEFAULT '',
    upstream_system TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL DEFAULT '',
    canonical_role TEXT NOT NULL DEFAULT '',
    sync_mode TEXT NOT NULL DEFAULT '',
    classification_status TEXT NOT NULL DEFAULT 'unclassified',
    last_seen_at TEXT NOT NULL,
    last_synced_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS asset_edges (
    from_asset_key TEXT NOT NULL,
    to_asset_key TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (from_asset_key, to_asset_key, edge_type),
    FOREIGN KEY (from_asset_key) REFERENCES assets(asset_key) ON DELETE CASCADE,
    FOREIGN KEY (to_asset_key) REFERENCES assets(asset_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cross_scope_edges (
    edge_key TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL,
    from_namespace_key TEXT NOT NULL,
    to_namespace_key TEXT NOT NULL,
    from_ref TEXT NOT NULL DEFAULT '',
    to_ref TEXT NOT NULL DEFAULT '',
    edge_type TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    page_id TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'inbox',
    page_type TEXT NOT NULL,
    asset_key TEXT NOT NULL,
    local_path TEXT NOT NULL,
    mirror_doc_token TEXT NOT NULL DEFAULT '',
    mirror_node_token TEXT NOT NULL DEFAULT '',
    last_local_hash TEXT NOT NULL DEFAULT '',
    last_remote_hash TEXT NOT NULL DEFAULT '',
    sync_mode TEXT NOT NULL DEFAULT '',
    last_synced_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (asset_key) REFERENCES assets(asset_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'account',
    command_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    host_pid TEXT NOT NULL DEFAULT '',
    summary_json TEXT NOT NULL DEFAULT '{}',
    error_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS issues (
    issue_id TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'account',
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    asset_key TEXT NOT NULL DEFAULT '',
    page_id TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS merge_queue (
    merge_id TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'inbox',
    asset_key TEXT NOT NULL,
    page_id TEXT NOT NULL,
    local_base_hash TEXT NOT NULL,
    remote_hash TEXT NOT NULL,
    patch_payload TEXT NOT NULL,
    merge_status TEXT NOT NULL,
    conflict_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (page_id) REFERENCES pages(page_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_cursor (
    cursor_key TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'account',
    cursor_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_redirects (
    legacy_key TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'account',
    asset_key TEXT NOT NULL DEFAULT '',
    legacy_url TEXT NOT NULL DEFAULT '',
    replacement_page_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_journal (
    journal_id TEXT PRIMARY KEY,
    portfolio_key TEXT NOT NULL DEFAULT 'portfolio::default',
    namespace_key TEXT NOT NULL DEFAULT 'account',
    page_id TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    local_hash TEXT NOT NULL DEFAULT '',
    remote_hash TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_namespaces_kind ON namespaces(kind, slug);
CREATE INDEX IF NOT EXISTS idx_assets_namespace ON assets(namespace_key, asset_class, canonical_role);
CREATE INDEX IF NOT EXISTS idx_assets_remote_id ON assets(remote_id);
CREATE INDEX IF NOT EXISTS idx_asset_edges_from_type ON asset_edges(from_asset_key, edge_type);
CREATE INDEX IF NOT EXISTS idx_cross_scope_namespaces ON cross_scope_edges(from_namespace_key, to_namespace_key, edge_type);
CREATE INDEX IF NOT EXISTS idx_pages_namespace ON pages(namespace_key, page_type);
CREATE INDEX IF NOT EXISTS idx_issues_namespace_status ON issues(namespace_key, status, severity);
CREATE INDEX IF NOT EXISTS idx_merge_queue_namespace ON merge_queue(namespace_key, merge_status, page_id);
CREATE INDEX IF NOT EXISTS idx_sync_journal_namespace ON sync_journal(namespace_key, operation, status);

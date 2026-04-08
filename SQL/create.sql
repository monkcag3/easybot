
-- ==============================================
-- users table
-- ==============================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    avatar TEXT DEFAULT '',
    type TEXT DEFAULT 'user', /* 类型：auto,agent,user */
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);



-- ==============================================
-- agent_templates table
-- ==============================================
CREATE TABLE IF NOT EXISTS agent_templates(
    id INTEGER PRIMARY KEY,
    hash TEXT UNIQUE,
    name TEXT UNIQUE,
    tags TEXT,
    desc TEXT,
    is_local bool,
    is_gateway bool,
    type TEXT
);


-- ==============================================
-- agents table
-- ==============================================
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL UNIQUE,
    template_hash TEXT NOT NULL,

    llm_model TEXT, /* 模型 */
    temperature REAL DEFAULT 0.7 CHECK (temperature BETWEEN 0 AND 2), /* 温度 */
    top_p REAL DEFAULT 0.9 CHECK (top_p BETWEEN 0 AND 1), /* 采样率 */
    max_tokens INTEGER DEFAULT 8192 CHECK (max_tokens > 0), /* 最大token */
    system_prompt TEXT, /* 系统提示词 */
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)), /* 1=启用，0=禁用 */

    extra_config JSON DEFAULT '{}' CHECK (json_valid(extra_config)),

    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);


-- ==============================================
-- sessions table
-- ==============================================
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL UNIQUE,
    peer_a TEXT NOT NULL,
    peer_b TEXT NOT NULL
);

-- ==============================================
-- messages table
-- ==============================================
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- msg_id TEXT NOT NULL UNIQUE,
    session_hash TEXT NOT NULL,
    sender_hash TEXT NOT NULL,
    -- sender_type TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT DEFAULT 'text',
    send_time INTEGER DEFAULT (strftime('%s', 'now')),
    status TEXT DEFAULT 'sent'
);
CREATE INDEX IF NOT EXISTS idx_messages_session_hash ON messages (session_hash);
CREATE INDEX IF NOT EXISTS idx_messages_send_time ON messages (send_time);
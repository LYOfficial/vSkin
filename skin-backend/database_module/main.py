from .core import BaseDB
from .modules.user import UserModule
from .modules.setting import SettingModule
from .modules.texture import TextureModule
from .modules.verification import VerificationModule
from .modules.fallback import FallbackModule
from .modules.oauth import OAuthModule
from config_loader import config

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    preferred_language TEXT DEFAULT 'zh_CN',
    display_name TEXT DEFAULT '',
    avatar_hash TEXT DEFAULT NULL,
    is_admin INTEGER DEFAULT 0,
    user_group TEXT DEFAULT 'user',
    banned_until INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT UNIQUE NOT NULL,
    texture_model TEXT DEFAULT 'default',
    skin_hash TEXT,
    cape_hash TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tokens (
    access_token TEXT PRIMARY KEY,
    client_token TEXT NOT NULL,
    user_id TEXT NOT NULL,
    profile_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    server_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    ip TEXT,
    created_at INTEGER NOT NULL
);
 
CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY,
    created_by TEXT,
    used_by TEXT,
    total_uses INTEGER DEFAULT 1,
    used_count INTEGER DEFAULT 0,
    created_at INTEGER,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS user_textures (
    user_id TEXT NOT NULL,
    hash TEXT NOT NULL,
    texture_type TEXT NOT NULL,
    note TEXT DEFAULT '',
    model TEXT DEFAULT 'default',
    is_public INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(user_id, hash, texture_type),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS skin_library (
    skin_hash TEXT PRIMARY KEY,
    texture_type TEXT NOT NULL,
    is_public INTEGER DEFAULT 0,
    uploader TEXT,
    model TEXT DEFAULT 'default',
    name TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fallback_endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    priority INTEGER NOT NULL,
    session_url TEXT NOT NULL,
    account_url TEXT NOT NULL,
    services_url TEXT NOT NULL,
    cache_ttl INTEGER NOT NULL,
    skin_domains TEXT DEFAULT '',
    enable_profile INTEGER DEFAULT 1,
    enable_hasjoined INTEGER DEFAULT 1,
    enable_whitelist INTEGER DEFAULT 0,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS whitelisted_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    endpoint_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE(username, endpoint_id),
    FOREIGN KEY(endpoint_id) REFERENCES fallback_endpoints(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verification_codes (
    email TEXT,
    code TEXT NOT NULL,
    type TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY(email, type)
);

CREATE TABLE IF NOT EXISTS oauth_clients (
    app_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT DEFAULT '',
    client_secret_hash TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_codes (
    code TEXT PRIMARY KEY,
    app_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    scope TEXT DEFAULT 'basic',
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY(app_id) REFERENCES oauth_clients(app_id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    access_token TEXT PRIMARY KEY,
    refresh_token TEXT UNIQUE NOT NULL,
    app_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    scope TEXT DEFAULT 'basic',
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(app_id) REFERENCES oauth_clients(app_id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

class Database(BaseDB):
    def __init__(self, db_path="yggdrasil.db", max_connections: int = 10):
        super().__init__(db_path, max_connections)
        self.user = UserModule(self)
        self.setting = SettingModule(self)
        self.texture = TextureModule(self)
        self.verification = VerificationModule(self)
        self.fallback = FallbackModule(self)
        self.oauth = OAuthModule(self)

    async def init(self):
        """初始化表结构及执行迁移"""
        async with self.get_conn() as conn:
            # 检查 skin_library 是否已存在，用于后续判断是否需要从 user_textures 迁移数据
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='skin_library'"
            )
            skin_library_exists = await cursor.fetchone() is not None

            # 检查 fallback_endpoints 是否已存在，用于后续兼容旧库
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fallback_endpoints'"
            )
            fallback_endpoints_exists = await cursor.fetchone() is not None

            # 检查 official_whitelist 是否已存在，用于后续兼容旧库
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='official_whitelist'"
            )
            official_whitelist_exists = await cursor.fetchone() is not None

            # 创建基础表结构
            await conn.executescript(INIT_SQL)
            await conn.commit()

            # 兼容旧库：users 增加 avatar_hash 列
            cursor = await conn.execute("PRAGMA table_info(users)")
            user_columns = [row[1] for row in await cursor.fetchall()]
            if "avatar_hash" not in user_columns:
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN avatar_hash TEXT DEFAULT NULL"
                )
                await conn.commit()

            # 兼容旧库：users 增加 user_group 列并迁移历史管理员数据
            if "user_group" not in user_columns:
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN user_group TEXT DEFAULT 'user'"
                )
                await conn.execute("UPDATE users SET user_group='admin' WHERE is_admin=1")
                await conn.execute("UPDATE users SET user_group='user' WHERE is_admin=0 OR is_admin IS NULL")
                await conn.execute(
                    """
                    UPDATE users
                    SET user_group='super_admin', is_admin=1
                    WHERE id=(
                        SELECT id
                        FROM users
                        WHERE user_group='admin'
                        ORDER BY rowid ASC
                        LIMIT 1
                    )
                    """
                )
                await conn.commit()

            # 防御性修复：确保 user_group 与 is_admin 一致
            await conn.execute("UPDATE users SET user_group='admin' WHERE is_admin=1 AND (user_group IS NULL OR user_group='')")
            await conn.execute("UPDATE users SET user_group='user' WHERE (is_admin=0 OR is_admin IS NULL) AND (user_group IS NULL OR user_group='')")
            await conn.execute("UPDATE users SET user_group='admin' WHERE is_admin=1 AND user_group NOT IN ('super_admin', 'admin')")
            await conn.execute("UPDATE users SET is_admin=1 WHERE user_group IN ('super_admin', 'admin')")
            await conn.execute("UPDATE users SET is_admin=0 WHERE user_group NOT IN ('super_admin', 'admin')")

            # 保证系统中至少有一个超级管理员：若缺失，则将最早的管理员提升为超级管理员
            await conn.execute(
                """
                UPDATE users
                SET user_group='super_admin', is_admin=1
                WHERE id=(
                    SELECT id
                    FROM users
                    WHERE user_group='admin'
                    ORDER BY rowid ASC
                    LIMIT 1
                )
                AND NOT EXISTS (
                    SELECT 1 FROM users WHERE user_group='super_admin'
                )
                """
            )
            await conn.commit()

            # 兼容旧库：fallback_endpoints 增加 skin_domains 列
            cursor = await conn.execute("PRAGMA table_info(fallback_endpoints)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "skin_domains" not in columns:
                await conn.execute(
                    "ALTER TABLE fallback_endpoints ADD COLUMN skin_domains TEXT DEFAULT ''"
                )
                await conn.commit()
                mojang_domains = config.get("mojang.skin_domains", []) or []
                domains_csv = ",".join(
                    [str(item).strip() for item in mojang_domains if str(item).strip()]
                )
                await conn.execute(
                    """
                    UPDATE fallback_endpoints
                    SET skin_domains=?
                    WHERE skin_domains IS NULL OR skin_domains = ''
                    """,
                    (domains_csv,),
                )
                await conn.commit()

            # 兼容旧库：fallback_endpoints 增加 enable_profile, enable_hasjoined, enable_whitelist 列
            cursor = await conn.execute("PRAGMA table_info(fallback_endpoints)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "enable_profile" not in columns:
                await conn.execute(
                    "ALTER TABLE fallback_endpoints ADD COLUMN enable_profile INTEGER DEFAULT 1"
                )
            if "enable_hasjoined" not in columns:
                await conn.execute(
                    "ALTER TABLE fallback_endpoints ADD COLUMN enable_hasjoined INTEGER DEFAULT 1"
                )
            if "enable_whitelist" not in columns:
                await conn.execute(
                    "ALTER TABLE fallback_endpoints ADD COLUMN enable_whitelist INTEGER DEFAULT 0"
                )
            if "note" not in columns:
                await conn.execute(
                    "ALTER TABLE fallback_endpoints ADD COLUMN note TEXT DEFAULT ''"
                )
            await conn.commit()

            # 如果是新创建的 fallback_endpoints 表，从 config.yaml 迁移现有数据
            if not fallback_endpoints_exists:
                mojang = config.get("mojang", {})
                skin_domains = mojang.get("skin_domains", []) or []
                await conn.execute(
                    """
                    INSERT INTO fallback_endpoints (
                        priority, session_url, account_url, services_url, cache_ttl, skin_domains,
                        enable_profile, enable_hasjoined, enable_whitelist, note
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        mojang.get("session_url", ""),
                        mojang.get("account_url", ""),
                        mojang.get("services_url", ""),
                        int(mojang.get("cache_ttl", 60)),
                        ",".join([str(item).strip() for item in skin_domains if str(item).strip()]),
                        1,
                        1,
                        0,
                        'Mojang Official'
                    ),
                )
                await conn.commit()

            # 迁移：official_whitelist -> whitelisted_users (绑定到优先级最高的 endpoint)
            # 如果存在official_whitelist，则将其中的用户迁移到 whitelisted_users，并关联到优先级最高的 fallback_endpoints 记录
            if official_whitelist_exists:
                cursor = await conn.execute(
                    "SELECT id FROM fallback_endpoints ORDER BY priority ASC, id ASC LIMIT 1"
                )
                row = await cursor.fetchone()
                if row:
                    endpoint_id = row[0]
                    cursor = await conn.execute(
                        "SELECT username, created_at FROM official_whitelist"
                    )
                    rows = await cursor.fetchall()
                    for username, created_at in rows:
                        await conn.execute(
                            """
                            INSERT OR IGNORE INTO whitelisted_users (username, endpoint_id, created_at)
                            VALUES (?, ?, ?)
                            """,
                            (username, endpoint_id, created_at),
                        )
                    await conn.commit()
                # 迁移完成后删除旧表
                await conn.execute("DROP TABLE IF EXISTS official_whitelist")
                await conn.commit()

            # 如果是新创建的 skin_library 表，从 user_textures 迁移现有数据
            if not skin_library_exists:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO skin_library (skin_hash, texture_type, is_public, uploader, created_at)
                    SELECT hash, texture_type, 0, user_id, created_at 
                    FROM user_textures 
                    GROUP BY hash
                    """
                )
                await conn.commit()

            # 迁移：为没有显示名（用户名）的用户设置默认用户名
            await conn.execute(
                """
                UPDATE users 
                SET display_name = SUBSTR(email, 1, INSTR(email, '@') - 1)
                WHERE display_name IS NULL OR display_name = ''
                """
            )
            await conn.commit()

            # 兼容旧库：invites 新增 note 列
            cursor = await conn.execute("PRAGMA table_info(invites)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "note" not in columns:
                await conn.execute(
                    "ALTER TABLE invites ADD COLUMN note TEXT DEFAULT ''"
                )
                await conn.commit()

            # 兼容旧库：user_textures 增加 model 列
            cursor = await conn.execute("PRAGMA table_info(user_textures)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "model" not in columns:
                await conn.execute(
                    "ALTER TABLE user_textures ADD COLUMN model TEXT DEFAULT 'default'"
                )
                await conn.commit()

            # 兼容旧库：skin_library 增加 model 列
            cursor = await conn.execute("PRAGMA table_info(skin_library)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "model" not in columns:
                await conn.execute(
                    "ALTER TABLE skin_library ADD COLUMN model TEXT DEFAULT 'default'"
                )
                await conn.commit()

            # 兼容旧库：skin_library 增加 name 列
            cursor = await conn.execute("PRAGMA table_info(skin_library)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "name" not in columns:
                await conn.execute(
                    "ALTER TABLE skin_library ADD COLUMN name TEXT DEFAULT ''"
                )
                await conn.commit()
                # 从上传者的 user_textures 中同步备注作为名称
                await conn.execute(
                    """
                    UPDATE skin_library 
                    SET name = (
                        SELECT note FROM user_textures 
                        WHERE user_textures.hash = skin_library.skin_hash 
                        AND user_textures.user_id = skin_library.uploader
                        LIMIT 1
                    )
                    WHERE uploader IS NOT NULL
                    """
                )
                await conn.commit()

            # 兼容旧库：user_textures 增加 is_public 列(0:私有, 1:公开, 2:非上传者)
            cursor = await conn.execute("PRAGMA table_info(user_textures)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "is_public" not in columns:
                await conn.execute(
                    "ALTER TABLE user_textures ADD COLUMN is_public INTEGER DEFAULT 0"
                )
                await conn.commit()

            # 兼容旧库：oauth_clients 增加 client_name 列
            cursor = await conn.execute("PRAGMA table_info(oauth_clients)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "client_name" not in columns:
                await conn.execute(
                    "ALTER TABLE oauth_clients ADD COLUMN client_name TEXT DEFAULT ''"
                )
                await conn.commit()

                # 数据迁移：根据 skin_library 补全 is_public 状态
                await conn.execute(
                    """
                    UPDATE user_textures 
                    SET is_public = (
                        SELECT CASE 
                            WHEN sl.uploader = user_textures.user_id THEN sl.is_public 
                            ELSE 2 
                        END
                        FROM skin_library sl 
                        WHERE sl.skin_hash = user_textures.hash
                    )
                    WHERE hash IN (SELECT skin_hash FROM skin_library)
                    """
                )
                await conn.commit()

            # 初始化默认设置
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('microsoft_client_id', '')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('microsoft_client_secret', '')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('microsoft_redirect_uri', 'http://localhost:8000/microsoft/callback')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('fallback_strategy', 'serial')"
            )

            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('enable_skin_library', 'true')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('site_title', '皮肤站')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('home_image_urls', '')"
            )

            # SMTP Default Settings
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('email_verify_enabled', 'false')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('enable_strong_password_check', 'false')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('email_verify_ttl', '300')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_host', 'smtp.example.com')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_port', '465')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_user', 'user@example.com')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_password', 'password')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_ssl', 'true')"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_sender', 'SkinServer <no-reply@example.com>')"
            )

            await conn.commit()

        # 初始化模块缓存
        await self.setting.init()
        await self.fallback.init()

    # Proxy methods for backward compatibility or direct access if needed
    # But strictly speaking, the user asked for db.user.xxx
    # We will only expose raw connection via get_conn()

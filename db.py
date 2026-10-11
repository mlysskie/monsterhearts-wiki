"""Capa mínima de base de datos.

En Railway se usa Postgres (variable DATABASE_URL). Si DATABASE_URL no existe,
cae a SQLite local para poder probar el sitio sin instalar nada.
Todas las consultas se escriben con placeholders `%s`.
"""
import os
import sqlite3

from flask import g

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

IS_PG = DATABASE_URL.startswith("postgresql://")

if IS_PG:
    import psycopg2
    import psycopg2.extras

SQLITE_PATH = os.environ.get("SQLITE_PATH", "local.db")

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    mime TEXT NOT NULL,
    filename TEXT,
    data BYTEA NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS characters (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    skin TEXT NOT NULL DEFAULT '',
    player TEXT NOT NULL DEFAULT '',
    tagline TEXT NOT NULL DEFAULT '',
    look TEXT NOT NULL DEFAULT '',
    eyes TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    story TEXT NOT NULL DEFAULT '',
    secrets TEXT NOT NULL DEFAULT '',
    image_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    is_npc BOOLEAN NOT NULL DEFAULT FALSE,
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS strings (
    from_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    to_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL DEFAULT 1,
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (from_id, to_id)
);
CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    mood TEXT NOT NULL DEFAULT '',
    music TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    cover_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    published BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS post_images (
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    caption TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (post_id, image_id)
);
CREATE TABLE IF NOT EXISTS comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    is_master BOOLEAN NOT NULL DEFAULT FALSE,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shouts (
    id SERIAL PRIMARY KEY,
    author TEXT NOT NULL,
    is_master BOOLEAN NOT NULL DEFAULT FALSE,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS presence (
    name TEXT PRIMARY KEY,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- pueblonet: la red social del pueblo
CREATE TABLE IF NOT EXISTS net_profiles (
    id SERIAL PRIMARY KEY,
    handle TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT,
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    is_npc BOOLEAN NOT NULL DEFAULT FALSE,
    avatar_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    cover_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    bg_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    status_text TEXT NOT NULL DEFAULT '',
    mood TEXT NOT NULL DEFAULT '',
    headline TEXT NOT NULL DEFAULT '',
    age TEXT NOT NULL DEFAULT '',
    zodiac TEXT NOT NULL DEFAULT '',
    school TEXT NOT NULL DEFAULT '',
    about_me TEXT NOT NULL DEFAULT '',
    want_to_meet TEXT NOT NULL DEFAULT '',
    int_general TEXT NOT NULL DEFAULT '',
    int_music TEXT NOT NULL DEFAULT '',
    int_movies TEXT NOT NULL DEFAULT '',
    int_tv TEXT NOT NULL DEFAULT '',
    int_books TEXT NOT NULL DEFAULT '',
    int_heroes TEXT NOT NULL DEFAULT '',
    song TEXT NOT NULL DEFAULT '',
    top_friends TEXT NOT NULL DEFAULT '',
    theme TEXT NOT NULL DEFAULT 'clasico',
    style_json TEXT NOT NULL DEFAULT '{}',
    custom_css TEXT NOT NULL DEFAULT '',
    views INTEGER NOT NULL DEFAULT 0,
    last_seen TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS net_posts (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES net_profiles(id) ON DELETE CASCADE,
    body TEXT NOT NULL DEFAULT '',
    mood TEXT NOT NULL DEFAULT '',
    image_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS net_likes (
    post_id INTEGER NOT NULL REFERENCES net_posts(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES net_profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, profile_id)
);
CREATE TABLE IF NOT EXISTS net_comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES net_posts(id) ON DELETE CASCADE,
    wall_id INTEGER REFERENCES net_profiles(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES net_profiles(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS net_follows (
    follower_id INTEGER NOT NULL REFERENCES net_profiles(id) ON DELETE CASCADE,
    followee_id INTEGER NOT NULL REFERENCES net_profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (follower_id, followee_id)
);
"""

SCHEMA_SQLITE = (
    SCHEMA_PG.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    .replace("BYTEA", "BLOB")
    .replace("BOOLEAN NOT NULL DEFAULT FALSE", "INTEGER NOT NULL DEFAULT 0")
    .replace("BOOLEAN NOT NULL DEFAULT TRUE", "INTEGER NOT NULL DEFAULT 1")
)


def _connect():
    if IS_PG:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn = sqlite3.connect(SQLITE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = lambda cur, row: {d[0]: row[i] for i, d in enumerate(cur.description)}
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = _connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _sql(query):
    return query if IS_PG else query.replace("%s", "?")


def query(sql, params=(), one=False):
    cur = get_db().cursor()
    cur.execute(_sql(sql), params)
    rows = cur.fetchall() if cur.description else []
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=(), returning=False):
    """Ejecuta y hace commit. Con returning=True devuelve la primera fila."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_sql(sql), params)
    row = cur.fetchone() if returning else None
    conn.commit()
    cur.close()
    return row


def blob(data):
    return psycopg2.Binary(data) if IS_PG else sqlite3.Binary(data)


def init_db():
    conn = _connect()
    cur = conn.cursor()
    if IS_PG:
        cur.execute(SCHEMA_PG)
    else:
        cur.executescript(SCHEMA_SQLITE)
    conn.commit()
    cur.close()
    conn.close()

import os
import sqlite3
from datetime import datetime

# Load .env file if available
def load_env():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(base_dir, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

load_env()

# Detect PostgreSQL or SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

has_postgres = False
if DATABASE_URL and ("postgres://" in DATABASE_URL or "postgresql://" in DATABASE_URL):
    try:
        import psycopg
        # Normalize connection string if it has +psycopg
        clean_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        test_conn = psycopg.connect(clean_url, connect_timeout=3)
        test_conn.close()
        has_postgres = True
    except Exception as e:
        print(f"[DB Warning] PostgreSQL connection failed, falling back to SQLite: {e}")
        has_postgres = False

DB_TYPE = "postgresql" if has_postgres else "sqlite"

def get_connection():
    if DB_TYPE == "postgresql":
        import psycopg
        clean_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        return psycopg.connect(clean_url)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "igscraper.db")
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_connection()
    try:
        cur = conn.cursor()
        if DB_TYPE == "postgresql":
            cur.execute("""
            CREATE TABLE IF NOT EXISTS scraped_users (
                id SERIAL PRIMARY KEY,
                instagram_id VARCHAR(64),
                username VARCHAR(255) NOT NULL UNIQUE,
                full_name VARCHAR(255),
                category_type VARCHAR(50) DEFAULT 'Follower Biasa',
                is_private BOOLEAN DEFAULT FALSE,
                is_verified BOOLEAN DEFAULT FALSE,
                email VARCHAR(255),
                follower_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,
                follower_count_str VARCHAR(50) DEFAULT '0',
                following_count_str VARCHAR(50) DEFAULT '0',
                profile_pic_url TEXT,
                target_source VARCHAR(255),
                scrape_type VARCHAR(50) DEFAULT 'followers',
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scrape_checkpoints (
                target_username VARCHAR(255) NOT NULL,
                scrape_type VARCHAR(50) NOT NULL,
                next_max_id TEXT,
                total_scraped INTEGER DEFAULT 0,
                is_completed BOOLEAN DEFAULT FALSE,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (target_username, scrape_type)
            );
            CREATE INDEX IF NOT EXISTS idx_scraped_username ON scraped_users(username);
            CREATE INDEX IF NOT EXISTS idx_scraped_target ON scraped_users(target_source);
            """)
        else:
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS scraped_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instagram_id VARCHAR(64),
                username VARCHAR(255) NOT NULL UNIQUE,
                full_name VARCHAR(255),
                category_type VARCHAR(50) DEFAULT 'Follower Biasa',
                is_private BOOLEAN DEFAULT 0,
                is_verified BOOLEAN DEFAULT 0,
                email VARCHAR(255),
                follower_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,
                follower_count_str VARCHAR(50) DEFAULT '0',
                following_count_str VARCHAR(50) DEFAULT '0',
                profile_pic_url TEXT,
                target_source VARCHAR(255),
                scrape_type VARCHAR(50) DEFAULT 'followers',
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scrape_checkpoints (
                target_username VARCHAR(255) NOT NULL,
                scrape_type VARCHAR(50) NOT NULL,
                next_max_id TEXT,
                total_scraped INTEGER DEFAULT 0,
                is_completed BOOLEAN DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (target_username, scrape_type)
            );
            CREATE INDEX IF NOT EXISTS idx_scraped_username ON scraped_users(username);
            CREATE INDEX IF NOT EXISTS idx_scraped_target ON scraped_users(target_source);
            """)
        conn.commit()
    finally:
        conn.close()

def parse_count_to_int(val_str):
    if not val_str:
        return 0
    val = str(val_str).strip().replace(',', '').replace('.', '')
    try:
        val_upper = str(val_str).strip().upper()
        if val_upper.endswith('K'):
            num = float(val_upper[:-1].replace(',', '.'))
            return int(num * 1000)
        elif val_upper.endswith('M'):
            num = float(val_upper[:-1].replace(',', '.'))
            return int(num * 1000000)
        elif val_upper.endswith('B'):
            num = float(val_upper[:-1].replace(',', '.'))
            return int(num * 1000000000)
        return int(float(str(val_str).replace(',', '')))
    except Exception:
        return 0

def upsert_user(user, target_source="", scrape_type="followers"):
    """
    Menyimpan atau memperbarui satu akun ke database.
    Mencegah duplikasi data berdasarkan username (UNIQUE).
    """
    return upsert_batch([user], target_source=target_source, scrape_type=scrape_type)

def upsert_batch(users_list, target_source="", scrape_type="followers"):
    """
    Menyimpan atau memperbarui batch akun ke database (Deduplikasi ketat).
    """
    if not users_list:
        return 0

    conn = get_connection()
    inserted_or_updated = 0
    try:
        cur = conn.cursor()
        for u in users_list:
            username = str(u.get("username") or "").strip().lower()
            if not username:
                continue

            ig_id = str(u.get("id") or u.get("pk") or "")
            full_name = str(u.get("full_name") or "")
            is_private = bool(u.get("is_private"))
            is_verified = bool(u.get("is_verified"))
            email = u.get("email") or None

            # Determine category_type: 'Follower Biasa', 'Terverifikasi', atau 'Akun Privat (Follower Biasa)'
            category_type = u.get("category_type")
            if not category_type:
                if is_verified:
                    category_type = "Terverifikasi"
                elif is_private:
                    category_type = "Akun Privat (Follower Biasa)"
                else:
                    category_type = "Follower Biasa"

            follower_cnt_str = str(u.get("follower_count_str") or u.get("followers_count") or u.get("follower_count") or "0")
            following_cnt_str = str(u.get("following_count_str") or u.get("following_count") or "0")
            
            follower_cnt = int(u.get("follower_count") or parse_count_to_int(follower_cnt_str))
            following_cnt = int(u.get("following_count") or parse_count_to_int(following_cnt_str))

            profile_pic = str(u.get("profile_pic_url") or "")

            if DB_TYPE == "postgresql":
                cur.execute("""
                    INSERT INTO scraped_users (
                        instagram_id, username, full_name, category_type, is_private, is_verified,
                        email, follower_count, following_count, follower_count_str, following_count_str,
                        profile_pic_url, target_source, scrape_type, scraped_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (username) DO UPDATE SET
                        category_type = EXCLUDED.category_type,
                        full_name = COALESCE(EXCLUDED.full_name, scraped_users.full_name),
                        email = COALESCE(EXCLUDED.email, scraped_users.email),
                        follower_count = CASE WHEN EXCLUDED.follower_count > 0 THEN EXCLUDED.follower_count ELSE scraped_users.follower_count END,
                        following_count = CASE WHEN EXCLUDED.following_count > 0 THEN EXCLUDED.following_count ELSE scraped_users.following_count END,
                        follower_count_str = CASE WHEN EXCLUDED.follower_count_str NOT IN ('-', '0', '') THEN EXCLUDED.follower_count_str ELSE scraped_users.follower_count_str END,
                        following_count_str = CASE WHEN EXCLUDED.following_count_str NOT IN ('-', '0', '') THEN EXCLUDED.following_count_str ELSE scraped_users.following_count_str END,
                        target_source = EXCLUDED.target_source,
                        scrape_type = EXCLUDED.scrape_type;
                """, (
                    ig_id, username, full_name, category_type, is_private, is_verified,
                    email, follower_cnt, following_cnt, follower_cnt_str, following_cnt_str,
                    profile_pic, target_source, scrape_type
                ))
            else:
                cur.execute("""
                    INSERT INTO scraped_users (
                        instagram_id, username, full_name, category_type, is_private, is_verified,
                        email, follower_count, following_count, follower_count_str, following_count_str,
                        profile_pic_url, target_source, scrape_type, scraped_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(username) DO UPDATE SET
                        category_type = excluded.category_type,
                        full_name = COALESCE(excluded.full_name, scraped_users.full_name),
                        email = COALESCE(excluded.email, scraped_users.email),
                        follower_count = CASE WHEN excluded.follower_count > 0 THEN excluded.follower_count ELSE scraped_users.follower_count END,
                        following_count = CASE WHEN excluded.following_count > 0 THEN excluded.following_count ELSE scraped_users.following_count END,
                        follower_count_str = CASE WHEN excluded.follower_count_str NOT IN ('-', '0', '') THEN excluded.follower_count_str ELSE scraped_users.follower_count_str END,
                        following_count_str = CASE WHEN excluded.following_count_str NOT IN ('-', '0', '') THEN excluded.following_count_str ELSE scraped_users.following_count_str END,
                        target_source = excluded.target_source,
                        scrape_type = excluded.scrape_type;
                """, (
                    ig_id, username, full_name, category_type, 1 if is_private else 0, 1 if is_verified else 0,
                    email, follower_cnt, following_cnt, follower_cnt_str, following_cnt_str,
                    profile_pic, target_source, scrape_type
                ))
            inserted_or_updated += 1
        conn.commit()
    finally:
        conn.close()

    return inserted_or_updated

def get_stats():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM scraped_users")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM scraped_users WHERE email IS NOT NULL AND email != ''")
        with_email = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM scraped_users WHERE is_verified = TRUE" if DB_TYPE == "postgresql" else "SELECT COUNT(*) FROM scraped_users WHERE is_verified = 1")
        verified = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM scraped_users WHERE category_type LIKE '%Follower Biasa%'")
        ordinary = cur.fetchone()[0]

        return {
            "total": total,
            "with_email": with_email,
            "verified": verified,
            "ordinary": ordinary,
            "db_type": DB_TYPE
        }
    finally:
        conn.close()

def get_recent_users(limit=200, target_source=None, scrape_type=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        conds = []
        params = []
        if target_source:
            conds.append("target_source = %s" if DB_TYPE == "postgresql" else "target_source = ?")
            params.append(str(target_source).strip().lower())
        if scrape_type:
            conds.append("scrape_type = %s" if DB_TYPE == "postgresql" else "scrape_type = ?")
            params.append(str(scrape_type).strip().lower())

        where_clause = (" WHERE " + " AND ".join(conds)) if conds else ""
        query = f"SELECT username, full_name, category_type, follower_count_str, following_count_str, email, is_private, is_verified, target_source, scrape_type, scraped_at FROM scraped_users{where_clause} ORDER BY id DESC LIMIT %s" if DB_TYPE == "postgresql" else f"SELECT username, full_name, category_type, follower_count_str, following_count_str, email, is_private, is_verified, target_source, scrape_type, scraped_at FROM scraped_users{where_clause} ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cols = ["username", "full_name", "category_type", "follower_count_str", "following_count_str", "email", "is_private", "is_verified", "target_source", "scrape_type", "scraped_at"]
        results = []
        for r in rows:
            results.append({cols[i]: r[i] for i in range(len(cols))})
        return results
    finally:
        conn.close()

def get_all_for_export(target_source=None, scrape_type=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT username, full_name, category_type, follower_count_str, following_count_str, email, is_private, is_verified, target_source, scrape_type, scraped_at FROM scraped_users"
        params = []
        conds = []
        if target_source:
            conds.append("target_source = %s" if DB_TYPE == "postgresql" else "target_source = ?")
            params.append(target_source)
        if scrape_type:
            conds.append("scrape_type = %s" if DB_TYPE == "postgresql" else "scrape_type = ?")
            params.append(scrape_type)
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY id ASC"
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cols = ["username", "full_name", "category_type", "follower_count_str", "following_count_str", "email", "is_private", "is_verified", "target_source", "scrape_type", "scraped_at"]
        results = []
        for r in rows:
            results.append({cols[i]: r[i] for i in range(len(cols))})
        return results
    finally:
        conn.close()

def get_checkpoint(target_username, scrape_type="followers"):
    """Mengambil checkpoint pagination terakhir untuk target tertentu."""
    target = target_username.strip().lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT next_max_id, total_scraped, is_completed, last_updated FROM scrape_checkpoints WHERE target_username = %s AND scrape_type = %s" if DB_TYPE == "postgresql" else "SELECT next_max_id, total_scraped, is_completed, last_updated FROM scrape_checkpoints WHERE target_username = ? AND scrape_type = ?"
        cur.execute(query, (target, scrape_type))
        row = cur.fetchone()
        if row:
            return {
                "next_max_id": row[0],
                "total_scraped": row[1] or 0,
                "is_completed": bool(row[2]),
                "last_updated": str(row[3])
            }
        return None
    finally:
        conn.close()

def save_checkpoint(target_username, scrape_type="followers", next_max_id=None, total_scraped=0, is_completed=False):
    """Menyimpan atau memperbarui posisi pagination (next_max_id) untuk target."""
    target = target_username.strip().lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        if DB_TYPE == "postgresql":
            cur.execute("""
                INSERT INTO scrape_checkpoints (target_username, scrape_type, next_max_id, total_scraped, is_completed, last_updated)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (target_username, scrape_type) DO UPDATE SET
                    next_max_id = EXCLUDED.next_max_id,
                    total_scraped = EXCLUDED.total_scraped,
                    is_completed = EXCLUDED.is_completed,
                    last_updated = CURRENT_TIMESTAMP;
            """, (target, scrape_type, next_max_id, total_scraped, is_completed))
        else:
            cur.execute("""
                INSERT INTO scrape_checkpoints (target_username, scrape_type, next_max_id, total_scraped, is_completed, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (target_username, scrape_type) DO UPDATE SET
                    next_max_id = excluded.next_max_id,
                    total_scraped = excluded.total_scraped,
                    is_completed = excluded.is_completed,
                    last_updated = CURRENT_TIMESTAMP;
            """, (target, scrape_type, next_max_id, total_scraped, 1 if is_completed else 0))
        conn.commit()
    finally:
        conn.close()

def reset_checkpoint(target_username, scrape_type="followers"):
    """Mereset checkpoint agar scraping bisa diulang dari awal untuk target ini."""
    target = target_username.strip().lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "DELETE FROM scrape_checkpoints WHERE target_username = %s AND scrape_type = %s" if DB_TYPE == "postgresql" else "DELETE FROM scrape_checkpoints WHERE target_username = ? AND scrape_type = ?"
        cur.execute(query, (target, scrape_type))
        conn.commit()
    finally:
        conn.close()

def count_users_for_target(target_username, scrape_type=None):
    """Menghitung total user yang sudah tersimpan di DB untuk target ini."""
    target = target_username.strip().lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        if scrape_type:
            query = "SELECT COUNT(*) FROM scraped_users WHERE target_source = %s AND scrape_type = %s" if DB_TYPE == "postgresql" else "SELECT COUNT(*) FROM scraped_users WHERE target_source = ? AND scrape_type = ?"
            cur.execute(query, (target, scrape_type))
        else:
            query = "SELECT COUNT(*) FROM scraped_users WHERE target_source = %s" if DB_TYPE == "postgresql" else "SELECT COUNT(*) FROM scraped_users WHERE target_source = ?"
            cur.execute(query, (target,))
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()

def get_existing_ids_for_target(target_username, scrape_type=None):
    """Mengembalikan set instagram_id dan username yang sudah pernah tersimpan untuk target ini."""
    target = target_username.strip().lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        if scrape_type:
            query = "SELECT instagram_id, username FROM scraped_users WHERE target_source = %s AND scrape_type = %s" if DB_TYPE == "postgresql" else "SELECT instagram_id, username FROM scraped_users WHERE target_source = ? AND scrape_type = ?"
            cur.execute(query, (target, scrape_type))
        else:
            query = "SELECT instagram_id, username FROM scraped_users WHERE target_source = %s" if DB_TYPE == "postgresql" else "SELECT instagram_id, username FROM scraped_users WHERE target_source = ?"
            cur.execute(query, (target,))
        rows = cur.fetchall()
        id_set = set()
        for r in rows:
            if r[0]:
                id_set.add(str(r[0]))
            if r[1]:
                id_set.add(str(r[1]).lower())
        return id_set
    finally:
        conn.close()

# Initialize DB tables on import
try:
    init_db()
except Exception as e:
    print(f"[DB Init Error]: {e}")


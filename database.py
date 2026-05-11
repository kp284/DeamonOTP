import sqlite3
import os
import time
from datetime import datetime

DB_PATH = "otp_bot_final.db"

# Thread-safe connection
db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
db.execute("PRAGMA journal_mode=WAL;")
cur = db.cursor()

def setup_db():
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        referred_by INTEGER,
        total_deposited INTEGER DEFAULT 0,
        joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        banned INTEGER DEFAULT 0,
        discount INTEGER DEFAULT 0,
        terms_accepted INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS stock (
        phone TEXT PRIMARY KEY,
        session_file TEXT,
        country_name TEXT,
        country_icon TEXT DEFAULT '🌍',
        account_year INTEGER,
        category TEXT DEFAULT 'Good',
        price INTEGER,
        available INTEGER DEFAULT 1,
        twofa TEXT DEFAULT 'None',
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS auto_prices (
        country TEXT,
        year TEXT,
        price INTEGER,
        PRIMARY KEY (country, year)
    );
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        method_name TEXT,
        status TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS upi_orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount INTEGER,
        status TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        country TEXT,
        year INTEGER,
        price INTEGER,
        phone TEXT,
        otp TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS custom_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        caption TEXT,
        qr_file_id TEXT
    );
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        p_add_stock INTEGER DEFAULT 0,
        p_manage_stock INTEGER DEFAULT 0,
        p_stats INTEGER DEFAULT 0,
        p_bal INTEGER DEFAULT 0,
        p_settings INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS custom_countries (
        code TEXT PRIMARY KEY,
        name TEXT,
        flag TEXT
    );
    -- NEW TABLES FOR API/WEBSITE
    CREATE TABLE IF NOT EXISTS api_keys (
        user_id INTEGER PRIMARY KEY,
        api_key TEXT UNIQUE NOT NULL,
        secret_key TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP,
        requests_count INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS api_orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
    phone TEXT,
        country TEXT,
        year INTEGER,
        price INTEGER,
        otp TEXT,
        status TEXT,
        request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        response_time TIMESTAMP,
        api_key_used TEXT
    );
    CREATE TABLE IF NOT EXISTS api_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        api_key TEXT,
        endpoint TEXT,
        method TEXT,
        ip TEXT,
        request_data TEXT,
        response_status INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()

setup_db()

# ==================== COMMON HELPERS ====================
def is_bot_online():
    res = cur.execute("SELECT value FROM settings WHERE key='bot_status'").fetchone()
    return res[0] == 'on' if res else True

def is_admin(uid):
    if uid == ADMIN_ID: return True   # ADMIN_ID must be set externally
    row = cur.execute("SELECT user_id FROM admins WHERE user_id=?", (uid,)).fetchone()
    return bool(row)

def has_perm(uid, perm):
    if uid == ADMIN_ID: return True
    row = cur.execute(f"SELECT {perm} FROM admins WHERE user_id=?", (uid,)).fetchone()
    return bool(row and row[0] == 1)

def ensure_user(uid):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    db.commit()

def get_usdt_rate():
    res = cur.execute("SELECT value FROM settings WHERE key='usdt_rate'").fetchone()
    try: return float(res[0]) if res else 94.0
    except: return 94.0

def to_usd(inr):
    return round(inr / get_usdt_rate(), 2)

def is_user_banned(uid):
    res = cur.execute("SELECT banned FROM users WHERE user_id=?", (uid,)).fetchone()
    return res and res[0] == 1

def update_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    db.commit()

def get_user_profile(uid):
    return cur.execute("SELECT user_id, balance, total_deposited, joined_date, discount, banned FROM users WHERE user_id=?", (uid,)).fetchone()

# Country lookup
COUNTRY_CODES = {
    '1': ('USA/Canada', '🇺🇸'), '7': ('Russia', '🇷🇺'), '20': ('Egypt', '🇪🇬'),
    # ... (include all from original) ...
    '91': ('India', '🇮🇳'), '92': ('Pakistan', '🇵🇰'), '93': ('Afghanistan', '🇦🇫'),
    '94': ('Sri Lanka', '🇱🇰'), '95': ('Myanmar', '🇲🇲'), '98': ('Iran', '🇮🇷'),
    '212': ('Morocco', '🇲🇦'), '213': ('Algeria', '🇩🇿'), '234': ('Nigeria', '🇳🇬'),
    '254': ('Kenya', '🇰🇪'), '255': ('Tanzania', '🇹🇿'), '380': ('Ukraine', '🇺🇦'),
    '880': ('Bangladesh', '🇧🇩'), '964': ('Iraq', '🇮🇶'), '966': ('Saudi Arabia', '🇸🇦'),
    '971': ('UAE', '🇦🇪'), '998': ('Uzbekistan', '🇺🇿')
}

def get_flag_by_country_name(name):
    for code, (c_name, c_flag) in COUNTRY_CODES.items():
        if c_name == name: return c_flag
    try:
        row = cur.execute("SELECT flag FROM custom_countries WHERE name=?", (name,)).fetchone()
        if row: return row[0]
    except: pass
    return "🌍"

def get_country_info(phone):
    phone = str(phone).replace(' ', '').replace('+', '')
    if not phone: return "Unknown", "🌍"
    try:
        customs = cur.execute("SELECT code, name, flag FROM custom_countries").fetchall()
        customs.sort(key=lambda x: len(x[0]), reverse=True)
        for code, name, flag in customs:
            if phone.startswith(code): return name, flag
    except: pass
    for length in (3, 2, 1):
        prefix = phone[:length]
        if prefix in COUNTRY_CODES: return COUNTRY_CODES[prefix]
    return "Unknown", "🌍"
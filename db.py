import sqlite3
import time

DB_FILE = "stock.db"

def connect():
    return sqlite3.connect(DB_FILE)

def setup():
    conn = connect()
    c = conn.cursor()

    # Create stock table
    c.execute("""
    CREATE TABLE IF NOT EXISTS stock (
        box_type TEXT PRIMARY KEY,
        quantity INTEGER NOT NULL
    )
    """)

    # Create purchases table
    c.execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        user_id INTEGER,
        box_type TEXT,
        quantity INTEGER,
        timestamp INTEGER
    )
    """)

    # Create meta table for things like stock_message_id, shop status
    c.execute("""
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Initialize stock rows if not present
    for box_type in ["1mil", "10mil", "25mil"]:
        c.execute("INSERT OR IGNORE INTO stock (box_type, quantity) VALUES (?, ?)", (box_type, 0))

    # Initialize shop open state if not set
    c.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)", ("shop_open", "false"))

    conn.commit()
    conn.close()

# Stock operations
def get_stock(box_type):
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT quantity FROM stock WHERE box_type = ?", (box_type,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def get_all_stock():
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT box_type, quantity FROM stock")
    result = {box_type: quantity for box_type, quantity in c.fetchall()}
    conn.close()
    return result

def add_stock(box_type, amount):
    conn = connect()
    c = conn.cursor()
    c.execute("UPDATE stock SET quantity = quantity + ? WHERE box_type = ?", (amount, box_type))
    conn.commit()
    conn.close()

def reduce_stock(box_type, amount):
    conn = connect()
    c = conn.cursor()
    c.execute("UPDATE stock SET quantity = quantity - ? WHERE box_type = ?", (amount, box_type))
    conn.commit()
    conn.close()

# Purchase logging and limits
def log_purchase(user_id, box_type, quantity):
    conn = connect()
    c = conn.cursor()
    timestamp = int(time.time())
    c.execute("INSERT INTO purchases (user_id, box_type, quantity, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, box_type, quantity, timestamp))
    conn.commit()
    conn.close()

def get_user_limit(user_id, box_type):
    conn = connect()
    c = conn.cursor()
    now = int(time.time())
    cutoff = now - 86400  # 24 hours ago
    c.execute("""
        SELECT COALESCE(SUM(quantity), 0)
        FROM purchases
        WHERE user_id = ? AND box_type = ? AND timestamp >= ?
    """, (user_id, box_type, cutoff))
    used = c.fetchone()[0]
    conn.close()
    return max(0, 5 - used)

def get_user_cooldowns(user_id):
    """Return dict {box_type: quantity bought in last 24h}"""
    conn = connect()
    c = conn.cursor()
    now = int(time.time())
    cutoff = now - 86400
    c.execute("""
        SELECT box_type, COALESCE(SUM(quantity), 0)
        FROM purchases
        WHERE user_id = ? AND timestamp >= ?
        GROUP BY box_type
    """, (user_id, cutoff))
    result = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return result

def get_remaining_cooldown(user_id, box_type):
    """Returns a string time remaining until cooldown expires for a box type"""
    conn = connect()
    c = conn.cursor()
    now = int(time.time())
    cutoff = now - 86400
    c.execute("""
        SELECT MIN(timestamp)
        FROM purchases
        WHERE user_id = ? AND box_type = ? AND timestamp >= ?
    """, (user_id, box_type, cutoff))
    first_purchase_time = c.fetchone()[0]
    conn.close()
    if first_purchase_time is None:
        return "0s"
    elapsed = now - first_purchase_time
    remaining = 86400 - elapsed
    mins, secs = divmod(remaining, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m {secs}s"

# Cooldown reset - reset ALL cooldowns for a user
def reset_cooldowns(user_id=None):
    conn = connect()
    c = conn.cursor()
    if user_id:
        c.execute("DELETE FROM purchases WHERE user_id = ?", (user_id,))
    else:
        # reset all cooldowns
        c.execute("DELETE FROM purchases")
    conn.commit()
    conn.close()

# Stock message ID handling
def set_stock_message_id(message_id):
    conn = connect()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", ("stock_message_id", str(message_id)))
    conn.commit()
    conn.close()

def get_stock_message_id():
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT value FROM meta WHERE key = ?", ("stock_message_id",))
    result = c.fetchone()
    conn.close()
    return int(result[0]) if result else None

# Shop open/close status
def get_shop_status():
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT value FROM meta WHERE key = ?", ("shop_open",))
    result = c.fetchone()
    conn.close()
    return result[0] == "true" if result else False

def set_shop_status(value: bool):
    conn = connect()
    c = conn.cursor()
    val_str = "true" if value else "false"
    c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", ("shop_open", val_str))
    conn.commit()
    conn.close()

# Initialize DB on import
setup()

import sqlite3
import os

DB_PATH = "penny_basing.db"

def fix_schema():
    print(f"Opening database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database not found. Nothing to fix.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # We will drop and recreate since they are empty or inconsistent on the server.
    # This is safer than ALTER TABLE for completely different schemas.
    
    print("Fixing 'alerts' table...")
    cur.execute("DROP TABLE IF EXISTS alerts")
    cur.execute("""
        CREATE TABLE alerts (
            timestamp REAL,
            symbol TEXT,
            ratio REAL,
            total_bids INTEGER,
            total_asks INTEGER,
            heavy_venues INTEGER,
            direction TEXT,
            price REAL,
            vol_per_min REAL,
            range_cents REAL
        )
    """)

    print("Fixing 'live_orders' table...")
    cur.execute("DROP TABLE IF EXISTS live_orders")
    cur.execute("""
        CREATE TABLE live_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_rowid INTEGER,
            symbol TEXT,
            direction TEXT,
            side TEXT,
            qty INTEGER,
            price REAL,
            order_id TEXT,
            status_code TEXT,
            location TEXT,
            error TEXT,
            raw_response TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Fixing 'live_trades' table...")
    cur.execute("DROP TABLE IF EXISTS live_trades")
    cur.execute("""
        CREATE TABLE live_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            symbol TEXT,
            side TEXT,
            qty INTEGER,
            price REAL,
            entry_price REAL,
            pnl REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Fixing 'account_history' table...")
    cur.execute("DROP TABLE IF EXISTS account_history")
    cur.execute("""
        CREATE TABLE account_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            liquidation_value REAL,
            cash_balance REAL,
            day_pnl REAL,
            buying_power REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("Schema fix complete!")

if __name__ == "__main__":
    fix_schema()

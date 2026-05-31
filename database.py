import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "auction.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Create auction_state table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS auction_state (
            id INTEGER PRIMARY KEY,
            player_name TEXT,
            base_price INTEGER,
            current_bid INTEGER,
            highest_bidder TEXT,
            status TEXT
        )
        """)
        
        # Initialize default state row if not exists
        cursor.execute("SELECT COUNT(*) FROM auction_state WHERE id = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO auction_state (id, player_name, base_price, current_bid, highest_bidder, status)
            VALUES (1, '', 0, 0, '', 'idle')
            """)
            
        # 2. Create sold_players table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sold_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            base_price INTEGER NOT NULL,
            sold_price INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # 3. Create bid_history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bid_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            bid_amount INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()

def get_auction_state():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT player_name, base_price, current_bid, highest_bidder, status FROM auction_state WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "player_name": "",
            "base_price": 0,
            "current_bid": 0,
            "highest_bidder": "",
            "status": "idle"
        }

def update_auction_state(player_name, base_price, current_bid, highest_bidder, status):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE auction_state
        SET player_name = ?, base_price = ?, current_bid = ?, highest_bidder = ?, status = ?
        WHERE id = 1
        """, (player_name, base_price, current_bid, highest_bidder, status))
        conn.commit()

def add_bid(player_name, bid_amount, team_name):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO bid_history (player_name, bid_amount, team_name)
        VALUES (?, ?, ?)
        """, (player_name, bid_amount, team_name))
        conn.commit()

def get_bid_history(player_name):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT team_name, bid_amount, timestamp FROM bid_history
        WHERE player_name = ?
        ORDER BY id DESC
        """, (player_name,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def mark_as_sold(player_name, base_price, sold_price, team_name):
    with get_db() as conn:
        cursor = conn.cursor()
        # Add to sold players
        cursor.execute("""
        INSERT INTO sold_players (player_name, base_price, sold_price, team_name)
        VALUES (?, ?, ?, ?)
        """, (player_name, base_price, sold_price, team_name))
        
        # Reset state to idle or sold state
        cursor.execute("""
        UPDATE auction_state
        SET status = 'sold'
        WHERE id = 1
        """)
        conn.commit()

def mark_as_unsold(player_name, base_price):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE auction_state
        SET status = 'unsold'
        WHERE id = 1
        """)
        conn.commit()

def reset_auction():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE auction_state
        SET player_name = '', base_price = 0, current_bid = 0, highest_bidder = '', status = 'idle'
        WHERE id = 1
        """)
        conn.commit()

def get_all_sold_players():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT player_name, base_price, sold_price, team_name, timestamp
        FROM sold_players
        ORDER BY timestamp ASC
        """)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

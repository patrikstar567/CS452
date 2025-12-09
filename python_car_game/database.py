import sqlite3
from datetime import datetime

DB_FILE = "game_data.db"

# ---------------- DATABASE INITIALIZATION ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # Players table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL
        )
    """)

    # Stats table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            distance REAL,
            coins INTEGER DEFAULT 0,
            date_played TEXT,
            FOREIGN KEY (player_id) REFERENCES players (id)
        )
    """)

    # Purchases table (new)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            skin_name TEXT NOT NULL,
            UNIQUE(player_id, skin_name),
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    conn.commit()
    conn.close()


# Initialize DB on import
init_db()


# ---------------- PLAYER MANAGEMENT ----------------
def get_or_create_player(username: str):
    """Get a player's ID, creating a new record if needed."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT id FROM players WHERE username=?", (username,))
    row = cur.fetchone()

    if row:
        player_id = row[0]
    else:
        cur.execute("INSERT INTO players (username) VALUES (?)", (username,))
        player_id = cur.lastrowid
        conn.commit()

    conn.close()
    return player_id


# ---------------- SCORE SAVING ----------------
def save_score(player_id: int, score: int, distance: float, coins: int = 0):
    """Save a player's score and distance after each game."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO stats (player_id, score, distance, coins, date_played)
        VALUES (?, ?, ?, ?, ?)
    """, (player_id, score, distance, coins,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()


# ---------------- SHOP SYSTEM ----------------
def player_owns_skin(player_id, skin_name):
    """Check if player already owns a skin."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM purchases WHERE player_id=? AND skin_name=?", (player_id, skin_name))
    result = cur.fetchone()

    conn.close()
    return result is not None


def unlock_skin(player_id, skin_name):
    """Marks a skin as purchased/owned."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO purchases (player_id, skin_name)
        VALUES (?, ?)
    """, (player_id, skin_name))

    conn.commit()
    conn.close()


def spend_coins(player_id, amount):
    """Subtract coins from the player's total."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        UPDATE stats
        SET coins = coins - ?
        WHERE player_id=?
    """, (amount, player_id))

    conn.commit()
    conn.close()


# ---------------- STATS RETRIEVAL ----------------
def get_player_stats(player_id: int):
    """Return dictionary with high score, total games, average score, and total coins."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            COUNT(*),
            IFNULL(MAX(score), 0),
            IFNULL(AVG(score), 0),
            IFNULL(SUM(coins), 0)
        FROM stats
        WHERE player_id=?
    """, (player_id,))

    result = cur.fetchone()
    conn.close()

    games_played = result[0]
    high_score = result[1]
    avg_score = result[2]
    coins = result[3]

    return {
        "games_played": games_played,
        "high_score": high_score,
        "avg_score": avg_score,
        "coins": coins
    }

import sqlite3
def init_user_table():
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_pokemon (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        pokemon_name TEXT,
        level INTEGER,
        caught_at TEXT
    )
    """)

    conn.commit()
    conn.close()

init_user_table()

def add_bonus_columns():
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    columns = ["bonus_hp", "bonus_atk", "bonus_def", "bonus_spatk", "bonus_spdef", "bonus_speed"]

    for col in columns:
        try:
            cursor.execute(f"ALTER TABLE user_pokemon ADD COLUMN {col} INTEGER DEFAULT 0")
        except:
            pass  # kolom sudah ada

    conn.commit()
    conn.close()

add_bonus_columns()

def init_player_table():
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player (
            user_id TEXT PRIMARY KEY,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_player_table()

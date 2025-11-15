import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "alisha_bot.db"

def get_db():
    """
    Establishes a connection to the SQLite database.
    Returns a connection object with row factory for easy access.
    """
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database by creating the 'users' and 'logs' tables if they don't exist.
    Call this once when the app starts.
    """
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            password TEXT NOT NULL,  -- Hashed password for security
            med_name TEXT,
            dosage TEXT,
            med_time TEXT,
            water_goal INTEGER
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    db.commit()
    db.close()

# Optional: Function to add a user (for testing or seeding)
def add_user(name, email, phone, password, med_name, dosage, med_time, water_goal):
    """
    Adds a new user to the database with hashed password.
    """
    hashed_password = generate_password_hash(password)
    db = get_db()
    db.execute(
        "INSERT INTO users (name, email, phone, password, med_name, dosage, med_time, water_goal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, email, phone, hashed_password, med_name, dosage, med_time, water_goal)
    )
    db.commit()
    db.close()

# Optional: Function to get a user by email (for login verification)
def get_user_by_email(email):
    """
    Retrieves a user by email.
    """
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    db.close()
    return user

# Optional: Function to log an action
def log_action(user_id, action, timestamp):
    """
    Logs a user action.
    """
    db = get_db()
    db.execute(
        "INSERT INTO logs (user_id, action, timestamp) VALUES (?, ?, ?)",
        (user_id, action, timestamp)
    )
    db.commit()
    db.close()
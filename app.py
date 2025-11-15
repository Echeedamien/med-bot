import sqlite3  # Note: Switch to PostgreSQL for Vercel (update database.py)
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix  # For Vercel deployment
from database import init_db, get_db

DB_NAME = "alisha_bot.db"  # Update to PostgreSQL URL in production

# ============================================================
# ⚙️ FLASK CONFIGURATION
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # For Vercel proxy handling
init_db()  # Initialize DB on startup

# ============================================================
# 🌐 ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template("landing.html")  # Landing page as index

@app.route("/landing")
def landing():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        med_name = request.form.get("med_name")
        dosage = request.form.get("dosage")
        med_time = request.form.get("med_time")
        water_goal = request.form.get("water_goal")

        if not all([name, email, phone, password, confirm_password, med_name, dosage, med_time, water_goal]):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, phone, password, med_name, dosage, med_time, water_goal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (name, email, phone, hashed_password, med_name, dosage, med_time, water_goal)
            )
            db.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))
        finally:
            db.close()

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        db.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard", name=user["name"]))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard/<name>")
def dashboard(name):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE name=? AND id=?", (name, session["user_id"])).fetchone()
    if not user:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    
    logs = db.execute("SELECT * FROM logs WHERE user_id=?", (user["id"],)).fetchall()
    db.close()

    # Calculate next medication time
    med_time_str = user["med_time"]
    now = datetime.now()
    today_med_time = datetime.strptime(med_time_str, "%H:%M").replace(
        year=now.year, month=now.month, day=now.day
    )
    if now > today_med_time:
        next_med_time = today_med_time + timedelta(days=1)
    else:
        next_med_time = today_med_time

    diff = next_med_time - now
    hours, remainder = divmod(diff.seconds, 3600)
    minutes = remainder // 60
    next_time = f"in {hours} hour(s) and {minutes} minute(s)"

    return render_template("dashboard.html", user=user, logs=logs, next_time=next_time)

@app.route("/log/<name>", methods=["POST"])
def log_action(name):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE name=? AND id=?", (name, session["user_id"])).fetchone()
    if not user:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    
    action = request.form.get("action")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if action:
        db.execute(
            "INSERT INTO logs (user_id, action, timestamp) VALUES (?, ?, ?)",
            (user["id"], action, now)
        )
        db.commit()
        flash(f"{action.capitalize()} logged successfully!", "info")

    return redirect(url_for("dashboard", name=name))

# ============================================================
# 🚀 RUN APP
# ============================================================
if __name__ == "__main__":
    app.run()  # Simplified for Vercel (no host/port/debug)
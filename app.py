import os
import json
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================
#   VERCEL KV (UPSTASH REDIS)
# ==========================
from vercel_kv import KV

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# Load KV credentials (from Vercel environment variables)
KKV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")

if not KV_URL or not KV_TOKEN:
    kv = None
else:
    kv = KV(KV_URL, KV_TOKEN)

    kv = KV(url=KV_URL, token=KV_TOKEN)

# ---------------------------
#  KV UTILITY FUNCTIONS
# ---------------------------
def kv_get_raw(key):
    if not kv:
        return None
    try:
        return kv.get(key)
    except:
        return None

def kv_get(key):
    raw = kv_get_raw(key)
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except:
        return raw

def kv_set(key, value):
    if not kv:
        raise RuntimeError("KV not configured.")
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    kv.set(key, value)

def user_key(email):
    return f"user:{email.lower()}"

def get_user(email):
    return kv_get(user_key(email))

def save_user(user):
    kv_set(user_key(user["email"]), user)

def add_log(email, action):
    user = get_user(email)
    if not user:
        return
    logs = user.get("logs", [])
    logs.append({
        "action": action,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    user["logs"] = logs
    save_user(user)

# ---------------------------
#   ROUTES
# ---------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/landing")
def landing():
    return render_template("index.html")

# ---------------------------
#   REGISTER
# ---------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email").lower()
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        med_name = request.form.get("med_name")
        dosage = request.form.get("dosage")
        med_time = request.form.get("med_time")
        water_goal = request.form.get("water_goal")

        if not all([name, email, phone, password, confirm, med_name, dosage, med_time, water_goal]):
            flash("Please fill all fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        # Check if user exists
        if get_user(email):
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        # Create user object
        user = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": generate_password_hash(password),
            "med_name": med_name,
            "dosage": dosage,
            "med_time": med_time,
            "water_goal": int(water_goal),
            "logs": []
        }

        save_user(user)
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# ---------------------------
#   LOGIN
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower()
        password = request.form.get("password")

        user = get_user(email)

        if user and check_password_hash(user["password"], password):
            session["user_email"] = user["email"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

# ---------------------------
#   LOGOUT
# ---------------------------
@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))

# ---------------------------
#   DASHBOARD
# ---------------------------
@app.route("/dashboard")
def dashboard():
    if "user_email" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    user = get_user(session["user_email"])
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    logs = user.get("logs", [])

    # Medication timer
    med_time_str = user.get("med_time")
    next_time = "Unavailable"

    try:
        now = datetime.now()
        today_med = datetime.strptime(med_time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)

        if now > today_med:
            next_med = today_med + timedelta(days=1)
        else:
            next_med = today_med

        diff = next_med - now
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        next_time = f"in {hours} hour(s) and {minutes} minute(s)"

    except:
        next_time = "Invalid time"

    return render_template("dashboard.html", user=user, logs=logs, next_time=next_time)

# ---------------------------
#   LOG ACTION
# ---------------------------
@app.route("/log", methods=["POST"])
def log_action():
    if "user_email" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    action = request.form.get("action")

    if action:
        add_log(session["user_email"], action)
        flash(f"{action.capitalize()} logged!", "success")

    return redirect(url_for("dashboard"))

# ---------------------------
#   LOCAL RUN
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import firebase_admin
from firebase_admin import credentials, firestore
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# ============================================================
# ⚙️ FLASK CONFIGURATION
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# ============================================================
# 🔥 FIREBASE INITIALIZATION
# ============================================================
firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")

if not firebase_creds_json:
    raise ValueError("❌ FIREBASE_CREDENTIALS environment variable not set")

creds_dict = json.loads(firebase_creds_json)
cred = credentials.Certificate(creds_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ============================================================
# 📧 SENDGRID (OPTIONAL)
# ============================================================
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "your-email@example.com")

def send_email(to_email, subject, content):
    """Sends email via SendGrid."""
    if not SENDGRID_API_KEY:
        print("⚠️ SendGrid disabled: no API key set")
        return
    
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        message = Mail(from_email=FROM_EMAIL, to_emails=to_email,
                       subject=subject, html_content=content)
        sg.send(message)
        print(f"📧 Email sent to {to_email}")
    except Exception as e:
        print("❌ Failed to send email:", e)

# ============================================================
# 🌐 ROUTES — LANDING
# ============================================================
@app.route("/")
def home():
    return render_template("landing.html")

# ============================================================
# 📝 REGISTER
# ============================================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        med_name = request.form.get("med_name")
        dosage = request.form.get("dosage")
        med_time = request.form.get("med_time")
        water_goal = request.form.get("water_goal")

        if not all([name, email, phone, password, confirm, med_name, dosage, med_time, water_goal]):
            flash("All fields are required", "danger")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match", "danger")
            return redirect(url_for("register"))

        # Check if email exists
        existing = db.collection("users").where("email", "==", email).limit(1).get()
        if existing:
            flash("Email already exists", "danger")
            return redirect(url_for("register"))

        hashed = generate_password_hash(password)

        new_user = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "med_name": med_name,
            "dosage": dosage,
            "med_time": med_time,
            "water_goal": int(water_goal)
        }

        user_ref = db.collection("users").add(new_user)
        user_id = user_ref[1].id

        # Optional Welcome Email
        send_email(email, "Welcome!", f"<p>Hello {name}, welcome to MadMedBot!</p>")

        flash("Registered successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# ============================================================
# 🔐 LOGIN
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user_docs = db.collection("users").where("email", "==", email).limit(1).get()
        user = None

        for doc in user_docs:
            user = doc.to_dict()
            user["id"] = doc.id

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard", user_id=user["id"]))

        flash("Invalid email or password", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")

# ============================================================
# 🚪 LOGOUT
# ============================================================
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))

# ============================================================
# 🏠 DASHBOARD
# ============================================================
@app.route("/dashboard/<user_id>")
def dashboard(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    # Fetch user
    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        flash("User not found", "danger")
        return redirect(url_for("login"))

    user = doc.to_dict()
    user["id"] = doc.id

    # Fetch Logs
    logs = db.collection("logs").where("user_id", "==", user_id).get()
    log_list = [log.to_dict() for log in logs]

    # Medication Time Calculation
    now = datetime.now()
    med_time = datetime.strptime(user["med_time"], "%H:%M").replace(
        year=now.year, month=now.month, day=now.day
    )
    if now > med_time:
        med_time += timedelta(days=1)

    diff = med_time - now
    hours, rem = divmod(diff.seconds, 3600)
    minutes = rem // 60

    next_time = f"in {hours} hour(s) and {minutes} minute(s)"

    return render_template("dashboard.html", user=user, logs=log_list, next_time=next_time)

# ============================================================
# 📝 LOG ACTION
# ============================================================
@app.route("/log/<user_id>", methods=["POST"])
def log_action(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    action = request.form.get("action")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if action:
        db.collection("logs").add({
            "user_id": user_id,
            "action": action,
            "timestamp": timestamp
        })

    flash("Action logged!", "info")
    return redirect(url_for("dashboard", user_id=user_id))

# ============================================================
# ✏️ EDIT PROFILE
# ============================================================
@app.route("/edit_profile/<user_id>", methods=["GET", "POST"])
def edit_profile(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        flash("User not found.", "danger")
        return redirect(url_for("dashboard", user_id=user_id))

    user = doc.to_dict()
    user["id"] = doc.id

    if request.method == "POST":
        update_data = {
            "name": request.form.get("name"),
            "phone": request.form.get("phone"),
            "med_name": request.form.get("med_name"),
            "dosage": request.form.get("dosage"),
            "med_time": request.form.get("med_time"),
            "water_goal": int(request.form.get("water_goal"))
        }

        db.collection("users").document(user_id).update(update_data)

        flash("Profile updated!", "success")
        return redirect(url_for("dashboard", user_id=user_id))

    return render_template("edit_profile.html", user=user)

# ============================================================
# 📜 VIEW FULL HISTORY
# ============================================================
@app.route("/view_history/<user_id>")
def view_history(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    logs = db.collection("logs").where("user_id", "==", user_id).get()
    log_list = [log.to_dict() for log in logs]

    return render_template("view_history.html", logs=log_list)

# ============================================================
# 🚀 RUN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)
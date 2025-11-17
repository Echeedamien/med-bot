import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

# Optional email providers
try:
    import resend
except Exception:
    resend = None

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except Exception:
    SendGridAPIClient = None
    Mail = None

# Optional Firebase imports
import firebase_admin
from firebase_admin import credentials, firestore

# --------------------------
# App configuration
# --------------------------
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # helps behind proxies like Vercel
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")  # override in Vercel env

# --------------------------
# Firestore (Firebase) init
# --------------------------
FIREBASE_CREDS_JSON = os.environ.get("FIREBASE_CREDENTIALS")

if not FIREBASE_CREDS_JSON:
    raise RuntimeError("FIREBASE_CREDENTIALS environment variable is required (JSON string).")

try:
    creds_dict = json.loads(FIREBASE_CREDS_JSON)
except Exception as e:
    raise RuntimeError("FIREBASE_CREDENTIALS must be valid JSON.") from e

cred = credentials.Certificate(creds_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --------------------------
# Email helpers (Resend preferred, fallback to SendGrid)
# --------------------------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "no-reply@example.com")  # change to a verified sender if required

def send_email_resend(to_email: str, subject: str, html: str) -> bool:
    """Send email with Resend (if available)."""
    if not RESEND_API_KEY or not resend:
        return False
    try:
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": f"MedBot <{FROM_EMAIL}>",
            "to": to_email,
            "subject": subject,
            "html": html
        })
        app.logger.info("Email sent (Resend) to %s", to_email)
        return True
    except Exception as e:
        app.logger.exception("Resend email error: %s", e)
        return False

def send_email_sendgrid(to_email: str, subject: str, html: str) -> bool:
    """Send email with SendGrid (if available)."""
    if not SENDGRID_API_KEY or not SendGridAPIClient or not Mail:
        return False
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        message = Mail(from_email=FROM_EMAIL, to_emails=to_email, subject=subject, html_content=html)
        sg.send(message)
        app.logger.info("Email sent (SendGrid) to %s", to_email)
        return True
    except Exception as e:
        app.logger.exception("SendGrid email error: %s", e)
        return False

def send_email(to_email: str, subject: str, html: str) -> bool:
    """Unified helper: try Resend first, then SendGrid, otherwise no-op."""
    if RESEND_API_KEY and resend:
        ok = send_email_resend(to_email, subject, html)
        if ok:
            return True
    if SENDGRID_API_KEY and SendGridAPIClient:
        ok = send_email_sendgrid(to_email, subject, html)
        if ok:
            return True
    app.logger.info("Email not sent: no provider configured or both failed.")
    return False

# --------------------------
# Helpers
# --------------------------
def _get_user_doc(user_id: str):
    """Return (doc_snapshot, data_dict) or (None, None)"""
    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        return None, None
    data = doc.to_dict()
    data["id"] = doc.id
    return doc, data

# --------------------------
# Routes
# --------------------------
@app.route("/")
def home():
    return render_template("landing.html")

# Register
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        med_name = request.form.get("med_name", "").strip()
        dosage = request.form.get("dosage", "").strip()
        med_time = request.form.get("med_time", "").strip()  # expected HH:MM
        water_goal = request.form.get("water_goal", "").strip()

        # Basic validation
        if not all([name, email, phone, password, confirm_password, med_name, dosage, med_time, water_goal]):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        # Ensure med_time format is valid (HH:MM)
        try:
            datetime.strptime(med_time, "%H:%M")
        except ValueError:
            flash("Medication time must be in HH:MM format.", "danger")
            return redirect(url_for("register"))

        # water_goal -> int safe conversion
        try:
            water_goal_int = int(water_goal)
        except Exception:
            water_goal_int = 0

        # Check existing email
        existing = db.collection("users").where("email", "==", email).limit(1).get()
        if existing:
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        hashed = generate_password_hash(password)
        user_obj = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed,
            "med_name": med_name,
            "dosage": dosage,
            "med_time": med_time,
            "water_goal": water_goal_int
        }

        ref = db.collection("users").add(user_obj)  # returns (write_result, ref)
        user_id = ref[1].id

        # Optional welcome email
        try:
            send_email(email, "Welcome to MedBot", f"<p>Hi {name}, welcome to MedBot.</p>")
        except Exception as e:
            app.logger.exception("Welcome email failed: %s", e)

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user_docs = db.collection("users").where("email", "==", email).limit(1).get()
        user = None
        for doc in user_docs:
            user = doc.to_dict()
            user["id"] = doc.id

        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        # login success
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user.get('name', '')}!", "success")
        return redirect(url_for("dashboard", user_id=user["id"]))

    return render_template("login.html")

# Logout
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

# Dashboard
@app.route("/dashboard/<user_id>")
def dashboard(user_id):
    # login check
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    # ensure user is viewing their own dashboard
    if session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    doc, user = _get_user_doc(user_id)
    if not doc:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    # fetch logs
    log_docs = db.collection("logs").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).get()
    logs = [ld.to_dict() for ld in log_docs]

    # next medication time calculation
    med_time_str = user.get("med_time", "09:00")
    now = datetime.now()
    try:
        scheduled_today = datetime.strptime(med_time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
    except Exception:
        scheduled_today = now + timedelta(hours=24)  # fallback

    if now > scheduled_today:
        next_med = scheduled_today + timedelta(days=1)
    else:
        next_med = scheduled_today

    diff = next_med - now
    hours, remainder = divmod(diff.seconds, 3600)
    minutes = remainder // 60
    next_time = f"in {hours} hour(s) and {minutes} minute(s)"

    return render_template("dashboard.html", user=user, logs=logs, next_time=next_time)

# Log action
@app.route("/log/<user_id>", methods=["POST"])
def log_action(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    action = request.form.get("action", "").strip()
    if not action:
        flash("Select an action before logging.", "danger")
        return redirect(url_for("dashboard", user_id=user_id))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.collection("logs").add({
        "user_id": user_id,
        "action": action,
        "timestamp": timestamp
    })

    flash("Action logged successfully!", "success")
    return redirect(url_for("dashboard", user_id=user_id))

# Edit profile (GET + POST)
@app.route("/edit_profile/<user_id>", methods=["GET", "POST"])
def edit_profile(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    doc, user = _get_user_doc(user_id)
    if not doc:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        med_name = request.form.get("med_name", "").strip()
        dosage = request.form.get("dosage", "").strip()
        med_time = request.form.get("med_time", "").strip()
        water_goal = request.form.get("water_goal", "").strip()

        try:
            water_goal_int = int(water_goal) if water_goal else user.get("water_goal", 0)
        except Exception:
            water_goal_int = user.get("water_goal", 0)

        update = {
            "name": name or user.get("name"),
            "phone": phone or user.get("phone"),
            "med_name": med_name or user.get("med_name"),
            "dosage": dosage or user.get("dosage"),
            "med_time": med_time or user.get("med_time"),
            "water_goal": water_goal_int
        }

        db.collection("users").document(user_id).update(update)
        flash("Profile updated.", "success")
        return redirect(url_for("dashboard", user_id=user_id))

    return render_template("edit_profile.html", user=user)

# View history
@app.route("/view_history/<user_id>")
def view_history(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    logs_docs = db.collection("logs").where("user_id", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).get()
    logs = [ld.to_dict() for ld in logs_docs]
    return render_template("view_history.html", logs=logs)

# Optional: manual reminder
@app.route("/send_reminder/<user_id>")
def send_reminder(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    doc, user = _get_user_doc(user_id)
    if not doc:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    # attempt to send email (best-effort)
    email = user.get("email")
    if email:
        send_email(email, "Medication Reminder", f"<p>Hi {user.get('name')}, time for your medication ({user.get('med_name')}).</p>")
        flash("Reminder sent (if email provider configured).", "info")
    else:
        flash("No email found for user.", "danger")

    return redirect(url_for("dashboard", user_id=user_id))

# Health check route (optional)
@app.route("/_health")
def health():
    return "OK", 200

# --------------------------
# Run app locally
# --------------------------
if __name__ == "__main__":
    # For local dev only; in production (Vercel) the platform runs the app
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
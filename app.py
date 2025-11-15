import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import firebase_admin
from firebase_admin import credentials, firestore
from sendgrid import SendGridAPIClient  # Added for emails
from sendgrid.helpers.mail import Mail  # Added for emails

# ============================================================
# ⚙️ FLASK CONFIGURATION
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # For Vercel

# Initialize Firebase
firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
if firebase_creds_json:
    creds_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(creds_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()  # Firestore client
else:
    raise ValueError("FIREBASE_CREDENTIALS environment variable not set")

# SendGrid Setup (Added)
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "your-email@example.com")  # Your verified SendGrid email

def send_email(to_email, subject, content):
    """Send email via SendGrid."""
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(message)
        print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# ============================================================
# 🌐 ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template("landing.html")

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

        # Check if email exists
        user_ref = db.collection('users').where('email', '==', email).limit(1).get()
        if user_ref:
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        user_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'password': hashed_password,
            'med_name': med_name,
            'dosage': dosage,
            'med_time': med_time,
            'water_goal': int(water_goal)
        }
        db.collection('users').add(user_data)
        
        # Send welcome email (Added)
        send_email(email, "Welcome to MadMedBot!", f"<p>Hi {name}, welcome! Your medication time is {med_time}.</p>")
        
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user_docs = db.collection('users').where('email', '==', email).limit(1).get()
        user = None
        for doc in user_docs:
            user = doc.to_dict()
            user['id'] = doc.id  # Add doc ID as user ID

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard", user_id=user["id"]))

        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard/<user_id>")
def dashboard(user_id):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    
    # Load the logged-in user doc
    user_doc = db.collection('users').document(session["user_id"]).get()
    if not user_doc.exists:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    
    user = user_doc.to_dict()
    user['id'] = user_doc.id

    # Fetch logs
    logs = db.collection('logs').where('user_id', '==', user['id']).get()
    log_list = [log.to_dict() for log in logs]

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

    return render_template("dashboard.html", user=user, logs=log_list, next_time=next_time)

@app.route("/log/<name>", methods=["POST"])
def log_action(name):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))
    
    user_doc = db.collection('users').document(session["user_id"]).get()
    if not user_doc.exists:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    
    user = user_doc.to_dict()
    if session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    
    action = request.form.get("action")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if action:
        log_data = {
            'user_id': user['id'],
            'action': action,
            'timestamp': now
        }
        db.collection('logs').add(log_data)
        flash(f"{action.capitalize()} logged successfully!", "info")

    return redirect(url_for("dashboard", name=name))

# Optional: Manual reminder route (Added)
@app.route("/send_reminder/<user_id>")
def send_reminder(user_id):
    if "user_id" not in session or session["user_id"] != user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        user = user_doc.to_dict()
        send_email(user['email'], "Medication Reminder", f"<p>Hi {user['name']}, time for your {user.get('med_name', 'medication')}!</p>")
        flash("Reminder sent!", "info")
    return redirect(url_for("dashboard", user_id=user_id))

# ============================================================
# 🚀 RUN APP
# ============================================================
if __name__ == "__main__":
    app.run()
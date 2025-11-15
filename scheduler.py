import sqlite3
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import os
import time

DB_NAME = "alisha_bot.db"

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def send_email(to_email, subject, body):
    """Send email to a user."""
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def has_taken_medication(user_id):
    """Check if the user has logged medication in the last 24 hours."""
    db = get_db()
    today = datetime.now().date()
    logs = db.execute(
        "SELECT * FROM logs WHERE user_id = ? AND action = 'medication' AND timestamp >= ?",
        (user_id, today.strftime("%Y-%m-%d")),
    ).fetchall()
    db.close()
    return len(logs) > 0

def check_reminders():
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    db.close()

    now = datetime.now()

    for user in users:
        user_id = user["id"]
        med_time_str = user["med_time"]
        med_time_today = datetime.strptime(med_time_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )

        # Move to tomorrow if today's med time passed
        if now > med_time_today:
            med_time_today += timedelta(days=1)

        time_remaining = med_time_today - now
        hours_until = int(time_remaining.total_seconds() // 3600)

        # If user already took medication, skip
        if has_taken_medication(user_id):
            print(f"🟢 {user['name']} already took medication. Skipping reminders.")
            continue

        if hours_until > 0:
            # Send hourly reminders until med time
            for hour in range(hours_until, 0, -1):
                if has_taken_medication(user_id):
                    print(f"✅ {user['name']} took their medication — stopping reminders.")
                    break

                subject = "⏰ Medication Reminder"
                body = (
                    f"Hi {user['name']}, your next medication ({user['med_name']} - {user['dosage']}) "
                    f"is scheduled for {user['med_time']}.\n\n"
                    f"⏳ {hour} hour(s) left. Please prepare to take your medication on time!"
                )
                send_email(user["email"], subject, body)

                # Wait an hour, but stop early if they log medication
                print(f"⏸ Sleeping 1 hour before next reminder for {user['name']}...")
                time.sleep(3600)

        elif time_remaining.total_seconds() <= 3600 and not has_taken_medication(user_id):
            # Final reminder when it's time
            subject = "💊 Time to Take Your Medication!"
            body = (
                f"Hi {user['name']}!\n\nIt's time to take your {user['med_name']} ({user['dosage']}).\n"
                f"Please stay consistent with your routine."
            )
            send_email(user["email"], subject, body)

if __name__ == "__main__":
    check_reminders()
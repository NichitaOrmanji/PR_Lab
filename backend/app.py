import os
import smtplib
import imaplib
import poplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import psycopg2
import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "tododb")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "postgres")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

POP3_HOST = os.environ.get("POP3_HOST", "pop.gmail.com")
POP3_PORT = int(os.environ.get("POP3_PORT", "995"))


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


def fetch_all_tasks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, description, done, created_at FROM tasks ORDER BY id")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [
        {"id": r[0], "title": r[1], "description": r[2], "done": r[3], "created_at": str(r[4])}
        for r in rows
    ]




@app.route("/tasks", methods=["GET"])
def get_tasks():
    return jsonify(fetch_all_tasks())


@app.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, description, done, created_at FROM tasks WHERE id=%s", (task_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"id": r[0], "title": r[1], "description": r[2], "done": r[3], "created_at": str(r[4])})


@app.route("/tasks", methods=["POST"])
def create_task():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (title, description) VALUES (%s, %s) RETURNING id",
        (data["title"], data.get("description", ""))
    )
    new_id = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    socketio.emit("tasks_updated", fetch_all_tasks())
    return jsonify({"message": "Task created", "id": new_id}), 201


@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.get_json()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM tasks WHERE id=%s", (task_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error": "Task not found"}), 404
    cur.execute(
        "UPDATE tasks SET title=%s, description=%s, done=%s WHERE id=%s",
        (data.get("title"), data.get("description"), data.get("done", False), task_id)
    )
    conn.commit(); cur.close(); conn.close()
    socketio.emit("tasks_updated", fetch_all_tasks())
    return jsonify({"message": "Task updated"})


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id=%s RETURNING id", (task_id,))
    deleted = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Task not found"}), 404
    socketio.emit("tasks_updated", fetch_all_tasks())
    return jsonify({"message": "Task deleted"})




@socketio.on("connect")
def on_connect():
    print("Client connected")
    socketio.emit("tasks_updated", fetch_all_tasks())


@socketio.on("disconnect")
def on_disconnect():
    print("Client disconnected")




@app.route("/email/send", methods=["POST"])
def send_email():
    data = request.get_json()
    to_addr = data.get("to")
    subject = data.get("subject", "Task notification")
    body = data.get("body", "")

    if not to_addr:
        return jsonify({"error": "Recipient email is required"}), 400

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_addr, msg.as_string())

        return jsonify({"message": f"Email sent to {to_addr}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/email/inbox/imap", methods=["GET"])
def get_inbox_imap():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(SMTP_USER, SMTP_PASS)
        mail.select("inbox")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()
        last_ids = ids[-5:] if len(ids) >= 5 else ids

        messages = []
        for uid in reversed(last_ids):
            _, msg_data = mail.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            messages.append({
                "from": msg.get("From"),
                "subject": msg.get("Subject"),
                "date": msg.get("Date")
            })

        mail.logout()
        return jsonify({"protocol": "IMAP", "messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/email/inbox/pop3", methods=["GET"])
def get_inbox_pop3():
    try:
        mailbox = poplib.POP3_SSL(POP3_HOST, POP3_PORT)
        mailbox.user(SMTP_USER)
        mailbox.pass_(SMTP_PASS)

        num_messages = len(mailbox.list()[1])
        messages = []

        for i in range(max(1, num_messages - 4), num_messages + 1):
            raw = b"\n".join(mailbox.retr(i)[1])
            msg = email.message_from_bytes(raw)
            messages.append({
                "from": msg.get("From"),
                "subject": msg.get("Subject"),
                "date": msg.get("Date")
            })

        mailbox.quit()
        return jsonify({"protocol": "POP3", "messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

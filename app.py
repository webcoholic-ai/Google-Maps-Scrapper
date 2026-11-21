import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "leads.db"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")

LOCALITIES = [
    "Vaishali Nagar", "Malviya Nagar", "C-Scheme", "Jagatpura",
    "Ajmer Road", "TonK Road", " Mansarovar", "Raja Park",
    "Shyam Nagar", "Civil Lines", "Other Jaipur",
]

SERVICES = [
    "Real Estate Agent", "Interior Designer", "Modular Kitchen",
    "Architect", "Civil Contractor", "Furniture", "Electrical",
    "Plumbing", "Painting", "Vastu Consultant", "Property Lawyer",
    "Packers & Movers", "Home Loan / Finance",
]


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                service TEXT NOT NOT NULL,
                locality TEXT NOT NULL,
                budget TEXT NOT NULL,
                timeline TEXT NOT NULL,
                requirement TEXT,
                consent INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'New',
                source TEXT NOT NULL DEFAULT 'Website',
                created_at TEXT NOT NULL
            )
        """)


def score_lead(data):
    score = 20
    if data.get("phone", ""):
        score += 20
    if data.get("budget") not in ("", "Not sure"):
        score += 20
    if data.get("timeline") in ("Immediately", "Within 1 month", "1–3 months"):
        score += 20
    if data.get("locality"):
        score += 10
    if data.get("requirement", "").strip():
        score += 10
    return min(score, 100)


@app.route("/")
def index():
    return render_template("index.html", localities=LOCALITIES, services=SERVICES)


@app.route("/api/leads", methods=["POST"])
def create_lead():
    data = request.get_json(silent=True) or request.form
    required = ("name", "phone", "service", "locality", "budget", "timeline")
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return jsonify({"success": False, "message": "Please complete all required fields."}), 400

    phone = "".join(ch for ch in str(data["phone"]) if ch.isdigit())
    if len(phone) < 10:
        return jsonify({"success": False, "message": "Please enter a valid 10-digit phone number."}), 400

    if str(data.get("consent")) not in ("1", "true", "on", "yes"):
        return jsonify({"success": False, "message": "Consent is required before we can contact you."}), 400

    lead = dict(
        name=str(data["name"]).strip(),
        phone=phone,
        service=str(data["service"]).strip(),
        locality=str(data["locality"]).strip(),
        budget=str(data["budget"]).strip(),
        timeline=str(data["timeline"]).strip(),
        requirement=str(data.get("requirement", "")).strip(),
        consent=1,
        score=score_lead(data),
        source="Website",
        created_at=datetime.utcnow().isoformat(timespec="seconds"),
    )

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO leads
            (name, phone, service, locality, budget, timeline, requirement, consent, score, source, created_at)
            VALUES (:name, :phone, :service, :locality, :budget, :timeline, :requirement, :consent, :score, :source, :created_at)
        """, lead)
        lead_id = cursor.lastrowid

    return jsonify({"success": True, "leadId": lead_id, "message": "Thank you! A Jaipur specialist will contact you shortly."})


@app.route("/dashboard")
def dashboard():
    service = request.args.get("service", "")
    locality = request.args.get("locality", "")
    status = request.args.get("status", "")

    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    if service:
        query += " AND service = ?"
        params.append(service)
    if locality:
        query += " AND locality = ?"
        params.append(locality)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY score DESC, id DESC"

    with get_db() as db:
        leads = db.execute(query, params).fetchall()
        stats = db.execute("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN status='New' THEN 1 ELSE 0 END), 0) AS new,
                   COALESCE(SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END), 0) AS hot
            FROM leads
        """).fetchone()

    return render_template(
        "dashboard.html", leads=leads, stats=stats,
        services=SERVICES, localities=LOCALITIES,
        selected={"service": service, "locality": locality, "status": status},
    )


@app.post("/dashboard/leads/<int:lead_id>/status")
def update_status(lead_id):
    status = request.form.get("status", "New")
    allowed = {"New", "Contacted", "Qualified", "Converted", "Closed"}
    if status not in allowed:
        return jsonify({"success": False}), 400
    with get_db() as db:
        db.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
    return jsonify({"success": True})


@app.get("/api/stats")
def stats():
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) total, SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) hot FROM leads").fetchone()
    return jsonify(dict(row))


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

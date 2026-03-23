"""
app.py — Flask entry point
Local:  python app.py
Render: gunicorn "app:create_app()"
"""
from flask import Flask, render_template, redirect, url_for
from models import create_db, seed_time_slots, seed_constraints
from api.routes import api
import os

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "timetable-dev-secret")

    # On Render, use /tmp for SQLite (writable directory)
    # Locally it just uses the project folder
    if os.environ.get("RENDER"):
        db_path = "sqlite:////tmp/timetable.db"
    else:
        db_path = "sqlite:///timetable.db"

    engine, Session = create_db(db_path)
    app.config["Session"] = Session

    # Auto-seed on startup
    s = Session()
    seed_time_slots(s)
    seed_constraints(s)
    s.close()

    app.register_blueprint(api, url_prefix="/api")

    @app.route("/")
    def index(): return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard(): return render_template("dashboard.html", page="dashboard")

    @app.route("/data-entry")
    def data_entry(): return render_template("data_entry.html", page="data_entry")

    @app.route("/constraints")
    def constraints(): return render_template("constraints.html", page="constraints")

    @app.route("/run-scheduler")
    def run_scheduler(): return render_template("run_scheduler.html", page="run_scheduler")

    @app.route("/timetable")
    def timetable(): return render_template("timetable_view.html", page="timetable")

    @app.route("/export")
    def export(): return render_template("export.html", page="export")

    return app

# This line is what gunicorn needs
application = create_app()

if __name__ == "__main__":
    app = create_app()
    print("\nTimetableAI → http://localhost:5000\n")
    app.run(debug=True, port=5000)
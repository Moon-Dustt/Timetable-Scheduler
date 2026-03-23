"""
app.py — Flask entry point
Run: python app.py
Open: http://localhost:5000
"""
from flask import Flask, render_template, redirect, url_for
from models import create_db, seed_time_slots, seed_constraints
from api.routes import api
import os

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "timetable-secret-2024")

    engine, Session = create_db()
    app.config["Session"] = Session

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

if __name__ == "__main__":
    app = create_app()
    print("\nTimetableAI → http://localhost:5000\n")
    app.run(debug=True, port=5000)
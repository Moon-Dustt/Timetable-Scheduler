"""
api/routes.py — All API endpoints
"""
import csv, io, json, re
from flask import Blueprint, request, jsonify, current_app, Response
from models import (Course, Lecturer, Room, StudentGroup, TimeSlot,
                    Constraint, ScheduleEntry, RoomType, ConstraintType)
from algorithms.genetic import GeneticAlgorithm

api = Blueprint("api", __name__)

def db():
    return current_app.config["Session"]()

def norm(s):
    return re.sub(r"[\s\-_]", "", s).upper()

def course_dict(c):
    spw = max(1, round(c.hours_per_week / c.session_duration))
    return {
        "id": c.id, "code": c.code, "name": c.name,
        "department": c.department, "level": c.level,
        "hours_per_week": c.hours_per_week,
        "session_duration": c.session_duration,
        "sessions_per_week": spw,
        "enrolled_count": c.enrolled_count,
        "requires_lab": c.requires_lab,
    }

def lecturer_dict(l):
    return {
        "id": l.id, "name": l.name, "email": l.email,
        "department": l.department, "max_hours_day": l.max_hours_day,
        "courses": [{"id": c.id, "code": c.code, "name": c.name} for c in l.courses],
    }

def room_dict(r):
    return {
        "id": r.id, "name": r.name, "building": r.building,
        "capacity": r.capacity, "room_type": r.room_type.value,
        "has_projector": r.has_projector, "has_computers": r.has_computers,
    }

def group_dict(g):
    return {
        "id": g.id, "name": g.name, "size": g.size,
        "level": g.level, "program": g.program,
        "courses": [{"id": c.id, "code": c.code} for c in g.courses],
    }

# ── Dashboard ────────────────────────────────────────────────
@api.route("/dashboard")
def dashboard():
    s = db()
    try:
        return jsonify({
            "courses":      s.query(Course).count(),
            "lecturers":    s.query(Lecturer).count(),
            "rooms":        s.query(Room).count(),
            "groups":       s.query(StudentGroup).count(),
            "time_slots":   s.query(TimeSlot).count(),
            "entries":      s.query(ScheduleEntry).filter_by(is_final=True).count(),
            "has_schedule": s.query(ScheduleEntry).filter_by(is_final=True).count() > 0,
            "levels":       sorted(set(c.level for c in s.query(Course).all())),
        })
    finally: s.close()

# ── Courses ──────────────────────────────────────────────────
@api.route("/courses")
def get_courses():
    s = db()
    try:
        return jsonify([course_dict(c) for c in s.query(Course).all()])
    finally: s.close()

@api.route("/courses", methods=["POST"])
def add_course():
    s = db()
    try:
        d    = request.get_json(force=True) or {}
        code = str(d.get("code", "")).strip().upper()
        name = str(d.get("name", "")).strip()
        dept = str(d.get("department", "")).strip()
        if not code: return jsonify({"error": "Course code is required"}), 400
        if not name: return jsonify({"error": "Course name is required"}), 400
        if not dept: return jsonify({"error": "Department is required"}), 400
        if s.query(Course).filter_by(code=code).first():
            return jsonify({"error": f"Code '{code}' already exists"}), 409
        c = Course(
            code             = code, name=name, department=dept,
            level            = int(d.get("level", 100)),
            hours_per_week   = int(d.get("hours_per_week", 4)),
            session_duration = int(d.get("session_duration", 2)),
            enrolled_count   = int(d.get("enrolled_count", 30)),
            requires_lab     = bool(d.get("requires_lab", False)),
        )
        s.add(c); s.commit()
        return jsonify(course_dict(c)), 201
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/courses/<int:cid>", methods=["PUT"])
def edit_course(cid):
    s = db()
    try:
        c = s.query(Course).get(cid)
        if not c: return jsonify({"error": "Not found"}), 404
        d = request.get_json(force=True) or {}
        if d.get("code"):             c.code             = str(d["code"]).strip().upper()
        if d.get("name"):             c.name             = str(d["name"]).strip()
        if d.get("department"):       c.department       = str(d["department"]).strip()
        if d.get("level"):            c.level            = int(d["level"])
        if d.get("hours_per_week"):   c.hours_per_week   = int(d["hours_per_week"])
        if d.get("session_duration"): c.session_duration = int(d["session_duration"])
        if d.get("enrolled_count"):   c.enrolled_count   = int(d["enrolled_count"])
        if "requires_lab" in d:       c.requires_lab     = bool(d["requires_lab"])
        s.commit()
        return jsonify(course_dict(c))
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/courses/<int:cid>", methods=["DELETE"])
def del_course(cid):
    s = db()
    try:
        c = s.query(Course).get(cid)
        if not c: return jsonify({"error": "Not found"}), 404
        s.delete(c); s.commit()
        return jsonify({"ok": True})
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

# ── Lecturers ─────────────────────────────────────────────────
@api.route("/lecturers")
def get_lecturers():
    s = db()
    try:
        return jsonify([lecturer_dict(l) for l in s.query(Lecturer).all()])
    finally: s.close()

@api.route("/lecturers", methods=["POST"])
def add_lecturer():
    s = db()
    try:
        d    = request.get_json(force=True) or {}
        name = str(d.get("name", "")).strip()
        dept = str(d.get("department", "")).strip()
        if not name: return jsonify({"error": "Name is required"}), 400
        if not dept: return jsonify({"error": "Department is required"}), 400
        l = Lecturer(
            name          = name,
            email         = str(d.get("email", "")).strip() or None,
            department    = dept,
            max_hours_day = int(d.get("max_hours_day", 6)),
            availability  = [],
        )
        s.add(l); s.flush()
        codes    = [c.strip() for c in str(d.get("course_codes","")).split(",") if c.strip()]
        notfound = []
        if codes:
            all_c = s.query(Course).all()
            matched = []
            for code in codes:
                found = next((c for c in all_c if norm(c.code) == norm(code)), None)
                if found: matched.append(found)
                else: notfound.append(code)
            if matched: l.courses = matched
        s.commit()
        r = lecturer_dict(l)
        r["not_found"] = notfound
        return jsonify(r), 201
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/lecturers/<int:lid>", methods=["PUT"])
def edit_lecturer(lid):
    s = db()
    try:
        l = s.query(Lecturer).get(lid)
        if not l: return jsonify({"error": "Not found"}), 404
        d = request.get_json(force=True) or {}
        if d.get("name"):          l.name          = str(d["name"]).strip()
        if "email" in d:           l.email         = str(d["email"]).strip() or None
        if d.get("department"):    l.department    = str(d["department"]).strip()
        if d.get("max_hours_day"): l.max_hours_day = int(d["max_hours_day"])
        if "course_codes" in d:
            codes = [c.strip() for c in str(d["course_codes"]).split(",") if c.strip()]
            if codes:
                all_c   = s.query(Course).all()
                matched = [c for c in all_c if any(norm(c.code) == norm(x) for x in codes)]
                l.courses = matched
        s.commit()
        return jsonify(lecturer_dict(l))
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/lecturers/<int:lid>", methods=["DELETE"])
def del_lecturer(lid):
    s = db()
    try:
        l = s.query(Lecturer).get(lid)
        if not l: return jsonify({"error": "Not found"}), 404
        s.delete(l); s.commit()
        return jsonify({"ok": True})
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

# ── Rooms ──────────────────────────────────────────────────────
@api.route("/rooms")
def get_rooms():
    s = db()
    try:
        return jsonify([room_dict(r) for r in s.query(Room).all()])
    finally: s.close()

@api.route("/rooms", methods=["POST"])
def add_room():
    s = db()
    try:
        d    = request.get_json(force=True) or {}
        name = str(d.get("name", "")).strip()
        if not name: return jsonify({"error": "Room name is required"}), 400
        if s.query(Room).filter_by(name=name).first():
            return jsonify({"error": f"Room '{name}' already exists"}), 409
        r = Room(
            name          = name,
            building      = str(d.get("building", "")).strip() or None,
            capacity      = int(d.get("capacity", 30)),
            room_type     = RoomType(d.get("room_type", "lecture_hall")),
            has_projector = bool(d.get("has_projector", True)),
            has_computers = bool(d.get("has_computers", False)),
        )
        s.add(r); s.commit()
        return jsonify(room_dict(r)), 201
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/rooms/<int:rid>", methods=["PUT"])
def edit_room(rid):
    s = db()
    try:
        r = s.query(Room).get(rid)
        if not r: return jsonify({"error": "Not found"}), 404
        d = request.get_json(force=True) or {}
        if d.get("name"):      r.name          = str(d["name"]).strip()
        if d.get("building"):  r.building      = str(d["building"]).strip()
        if d.get("capacity"):  r.capacity      = int(d["capacity"])
        if d.get("room_type"): r.room_type     = RoomType(d["room_type"])
        if "has_projector" in d: r.has_projector = bool(d["has_projector"])
        if "has_computers" in d: r.has_computers = bool(d["has_computers"])
        s.commit()
        return jsonify(room_dict(r))
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/rooms/<int:rid>", methods=["DELETE"])
def del_room(rid):
    s = db()
    try:
        r = s.query(Room).get(rid)
        if not r: return jsonify({"error": "Not found"}), 404
        s.delete(r); s.commit()
        return jsonify({"ok": True})
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

# ── Student Groups ─────────────────────────────────────────────
@api.route("/groups")
def get_groups():
    s = db()
    try:
        return jsonify([group_dict(g) for g in s.query(StudentGroup).all()])
    finally: s.close()

@api.route("/groups", methods=["POST"])
def add_group():
    s = db()
    try:
        d    = request.get_json(force=True) or {}
        name = str(d.get("name", "")).strip()
        if not name: return jsonify({"error": "Group name is required"}), 400
        g = StudentGroup(
            name    = name,
            size    = int(d.get("size", 1)),
            level   = int(d.get("level", 100)),
            program = str(d.get("program", "")).strip() or None,
        )
        codes = [c.strip() for c in str(d.get("course_codes","")).split(",") if c.strip()]
        if codes:
            all_c    = s.query(Course).all()
            g.courses = [c for c in all_c if any(norm(c.code) == norm(x) for x in codes)]
        s.add(g); s.commit()
        return jsonify(group_dict(g)), 201
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/groups/<int:gid>", methods=["PUT"])
def edit_group(gid):
    s = db()
    try:
        g = s.query(StudentGroup).get(gid)
        if not g: return jsonify({"error": "Not found"}), 404
        d = request.get_json(force=True) or {}
        if d.get("name"):    g.name    = str(d["name"]).strip()
        if d.get("size"):    g.size    = int(d["size"])
        if d.get("level"):   g.level   = int(d["level"])
        if d.get("program"): g.program = str(d["program"]).strip()
        if "course_codes" in d:
            codes = [c.strip() for c in str(d["course_codes"]).split(",") if c.strip()]
            if codes:
                all_c    = s.query(Course).all()
                g.courses = [c for c in all_c if any(norm(c.code) == norm(x) for x in codes)]
        s.commit()
        return jsonify(group_dict(g))
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

@api.route("/groups/<int:gid>", methods=["DELETE"])
def del_group(gid):
    s = db()
    try:
        g = s.query(StudentGroup).get(gid)
        if not g: return jsonify({"error": "Not found"}), 404
        s.delete(g); s.commit()
        return jsonify({"ok": True})
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

# ── Constraints ───────────────────────────────────────────────
@api.route("/constraints")
def get_constraints():
    s = db()
    try:
        return jsonify([{
            "id": c.id, "name": c.name, "description": c.description,
            "type": c.constraint_type.value, "weight": c.penalty_weight,
            "active": c.is_active,
        } for c in s.query(Constraint).all()])
    finally: s.close()

@api.route("/constraints/<int:cid>", methods=["PATCH"])
def update_constraint(cid):
    s = db()
    try:
        c = s.query(Constraint).get(cid)
        if not c: return jsonify({"error": "Not found"}), 404
        d = request.get_json(force=True) or {}
        if "weight" in d: c.penalty_weight = float(d["weight"])
        if "active" in d: c.is_active      = bool(d["active"])
        s.commit()
        return jsonify({"ok": True})
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

# ── Scheduler ─────────────────────────────────────────────────
@api.route("/run", methods=["POST"])
def run_scheduler():
    s = db()
    try:
        d = request.get_json(force=True) or {}
        if not s.query(Course).count():   return jsonify({"error": "No courses found"}), 400
        if not s.query(Lecturer).count(): return jsonify({"error": "No lecturers found"}), 400
        if not s.query(Room).count():     return jsonify({"error": "No rooms found"}), 400

        ga = GeneticAlgorithm(s,
            population_size = int(d.get("population_size", 30)),
            max_generations = int(d.get("max_generations", 100)),
            mutation_rate   = float(d.get("mutation_rate", 0.12)),
            target_score    = float(d.get("target_score", 9000)),
        )
        schedule, ga_score, _ = ga.run(verbose=False)
        final_score, is_valid = ga.get_score(schedule)
        ga.save_best(schedule)

        return jsonify({
            "ok":             True,
            "final_score":    round(final_score, 1),
            "is_valid":       is_valid,
            "hard_violations": 0 if is_valid else 1,
            "entries":        len(schedule),
        })
    except Exception as e:
        s.rollback(); return jsonify({"error": str(e)}), 500
    finally: s.close()

# ── Schedule ──────────────────────────────────────────────────
@api.route("/schedule")
def get_schedule():
    s = db()
    try:
        entries = s.query(ScheduleEntry).filter_by(is_final=True).all()
        return jsonify([{
            "id":       e.id,
            "course":   {
                "id": e.course.id, "code": e.course.code,
                "name": e.course.name, "level": e.course.level,
                "session_duration": e.course.session_duration,
            },
            "lecturer": {"id": e.lecturer.id, "name": e.lecturer.name},
            "room":     {"id": e.room.id, "name": e.room.name, "capacity": e.room.capacity},
            "slot": {
                "id": e.time_slot.id, "day": e.time_slot.day.value,
                "start": e.time_slot.start_time, "end": e.time_slot.end_time,
                "index": e.time_slot.slot_index,
            },
        } for e in entries])
    finally: s.close()

@api.route("/schedule/status")
def schedule_status():
    s = db()
    try:
        count = s.query(ScheduleEntry).filter_by(is_final=True).count()
        return jsonify({"has_schedule": count > 0, "count": count})
    finally: s.close()

# ── Export ────────────────────────────────────────────────────
@api.route("/export/csv")
def export_csv():
    s = db()
    try:
        entries = s.query(ScheduleEntry).filter_by(is_final=True).all()
        buf = io.StringIO()
        w   = csv.writer(buf)
        w.writerow(["Level","Course","Code","Lecturer","Room","Capacity","Day","Start","End"])
        for e in entries:
            w.writerow([
                e.course.level, e.course.name, e.course.code,
                e.lecturer.name, e.room.name, e.room.capacity,
                e.time_slot.day.value, e.time_slot.start_time, e.time_slot.end_time,
            ])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=timetable.csv"})
    finally: s.close()

@api.route("/export/json")
def export_json():
    s = db()
    try:
        entries = s.query(ScheduleEntry).filter_by(is_final=True).all()
        data = [{
            "level": e.course.level, "course": e.course.name,
            "code": e.course.code, "lecturer": e.lecturer.name,
            "room": e.room.name, "room_capacity": e.room.capacity,
            "day": e.time_slot.day.value,
            "start": e.time_slot.start_time, "end": e.time_slot.end_time,
        } for e in entries]
        return Response(json.dumps(data, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=timetable.json"})
    finally: s.close()
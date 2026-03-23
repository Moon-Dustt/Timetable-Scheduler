"""
models.py — Database models for AI Timetable Scheduler
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    ForeignKey, Table, JSON, Float, Enum, CheckConstraint
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
import enum

Base = declarative_base()

# ── Many-to-many joins ──────────────────────────────────────
group_course = Table("group_course", Base.metadata,
    Column("group_id",  Integer, ForeignKey("student_groups.id"), primary_key=True),
    Column("course_id", Integer, ForeignKey("courses.id"),        primary_key=True),
)
lecturer_course = Table("lecturer_course", Base.metadata,
    Column("lecturer_id", Integer, ForeignKey("lecturers.id"), primary_key=True),
    Column("course_id",   Integer, ForeignKey("courses.id"),   primary_key=True),
)

# ── Enums ───────────────────────────────────────────────────
class RoomType(str, enum.Enum):
    LECTURE_HALL = "lecture_hall"
    SEMINAR_ROOM = "seminar_room"
    LAB          = "lab"
    TUTORIAL     = "tutorial"

class Day(str, enum.Enum):
    MONDAY    = "Monday"
    TUESDAY   = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY  = "Thursday"
    FRIDAY    = "Friday"

class ConstraintType(str, enum.Enum):
    HARD = "hard"
    SOFT = "soft"

# ── Models ──────────────────────────────────────────────────
class Lecturer(Base):
    __tablename__    = "lecturers"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(100), nullable=False)
    email            = Column(String(150), unique=True, nullable=True)
    department       = Column(String(100), nullable=False)
    max_hours_day    = Column(Integer, default=6)
    availability     = Column(JSON, default=list)
    courses          = relationship("Course", secondary=lecturer_course, back_populates="lecturers")
    schedule_entries = relationship("ScheduleEntry", back_populates="lecturer")

class Room(Base):
    __tablename__    = "rooms"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(50), nullable=False, unique=True)
    building         = Column(String(100), nullable=True)
    capacity         = Column(Integer, nullable=False)
    room_type        = Column(Enum(RoomType), nullable=False, default=RoomType.LECTURE_HALL)
    has_projector    = Column(Boolean, default=True)
    has_computers    = Column(Boolean, default=False)
    __table_args__   = (CheckConstraint("capacity > 0"),)
    schedule_entries = relationship("ScheduleEntry", back_populates="room")

class Course(Base):
    __tablename__    = "courses"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    code             = Column(String(20),  nullable=False, unique=True)
    name             = Column(String(150), nullable=False)
    department       = Column(String(100), nullable=False)
    level            = Column(Integer, default=100)        # 100, 200, 300, 400, 500, 600
    hours_per_week   = Column(Integer, nullable=False, default=4)   # total hours per week
    session_duration = Column(Integer, nullable=False, default=2)   # hours per single class
    enrolled_count   = Column(Integer, nullable=False, default=30)
    requires_lab     = Column(Boolean, default=False)
    lecturers        = relationship("Lecturer", secondary=lecturer_course, back_populates="courses")
    student_groups   = relationship("StudentGroup", secondary=group_course, back_populates="courses")
    schedule_entries = relationship("ScheduleEntry", back_populates="course")

    @property
    def sessions_per_week(self):
        return max(1, round(self.hours_per_week / self.session_duration))

class StudentGroup(Base):
    __tablename__  = "student_groups"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String(100), nullable=False, unique=True)
    size           = Column(Integer, nullable=False)
    level          = Column(Integer, nullable=True)   # 100, 200, 300, 400, 500, 600
    program        = Column(String(100), nullable=True)
    __table_args__ = (CheckConstraint("size > 0"),)
    courses        = relationship("Course", secondary=group_course, back_populates="student_groups")

class TimeSlot(Base):
    __tablename__    = "time_slots"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    day              = Column(Enum(Day), nullable=False)
    start_time       = Column(String(5), nullable=False)   # "08:00"
    end_time         = Column(String(5), nullable=False)   # "09:00"
    slot_index       = Column(Integer,   nullable=False)
    is_blocked       = Column(Boolean,   default=False)
    schedule_entries = relationship("ScheduleEntry", back_populates="time_slot")

class ScheduleEntry(Base):
    __tablename__  = "schedule_entries"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    course_id      = Column(Integer, ForeignKey("courses.id"),    nullable=False)
    lecturer_id    = Column(Integer, ForeignKey("lecturers.id"),  nullable=False)
    room_id        = Column(Integer, ForeignKey("rooms.id"),      nullable=False)
    time_slot_id   = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    is_final       = Column(Boolean, default=False)
    course    = relationship("Course",    back_populates="schedule_entries")
    lecturer  = relationship("Lecturer",  back_populates="schedule_entries")
    room      = relationship("Room",      back_populates="schedule_entries")
    time_slot = relationship("TimeSlot",  back_populates="schedule_entries")

class Constraint(Base):
    __tablename__   = "constraints"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(150), nullable=False, unique=True)
    description     = Column(String(500))
    constraint_type = Column(Enum(ConstraintType), nullable=False)
    penalty_weight  = Column(Float, default=1.0)
    is_active       = Column(Boolean, default=True)

# ── Helpers ─────────────────────────────────────────────────
def create_db(db_url="sqlite:///timetable.db"):
    engine  = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session

def seed_time_slots(session):
    if session.query(TimeSlot).count() > 0:
        return
    days  = list(Day)
    # 1-hour slots from 08:00 to 16:00 (school closes at 16:00)
    hours = [(f"{h:02d}:00", f"{h+1:02d}:00") for h in range(8, 16)]
    idx   = 0
    for day in days:
        for start, end in hours:
            session.add(TimeSlot(day=day, start_time=start, end_time=end, slot_index=idx))
            idx += 1
    session.commit()
    print(f"Seeded {idx} time slots (08:00–16:00, 1-hour blocks).")

def seed_constraints(session):
    if session.query(Constraint).count() > 0:
        return
    items = [
        ("no_lecturer_clash",     "Lecturer cannot teach two classes at the same time.",       ConstraintType.HARD, 1000),
        ("no_room_clash",         "Room cannot host two classes at the same time.",             ConstraintType.HARD, 1000),
        ("no_student_clash",      "Student group cannot attend two classes at the same time.", ConstraintType.HARD, 1000),
        ("room_capacity",         "Room must fit all enrolled students.",                      ConstraintType.HARD, 1000),
        ("room_type_match",       "Lab courses must be assigned to a lab room.",               ConstraintType.HARD, 1000),
        ("lecturer_availability", "Lecturer must be available in the assigned slot.",          ConstraintType.HARD, 1000),
        ("course_frequency",      "Course must be scheduled the correct number of times.",     ConstraintType.HARD, 1000),
        ("no_early_morning",      "Avoid scheduling before 09:00.",                           ConstraintType.SOFT, 5),
        ("no_late_classes",       "Avoid scheduling after 15:00 (school closes at 16:00).",   ConstraintType.SOFT, 5),
        ("spread_course_days",    "Spread course sessions across different days.",             ConstraintType.SOFT, 10),
        ("minimize_gaps",         "Minimize idle gaps between classes for student groups.",    ConstraintType.SOFT, 8),
        ("max_hours_per_day",     "Respect lecturer maximum teaching hours per day.",          ConstraintType.SOFT, 15),
    ]
    for name, desc, ctype, weight in items:
        session.add(Constraint(name=name, description=desc,
                               constraint_type=ctype, penalty_weight=weight))
    session.commit()
    print(f"Seeded {len(items)} constraints.")

if __name__ == "__main__":
    engine, Session = create_db()
    s = Session()
    seed_time_slots(s)
    seed_constraints(s)
    print("Database ready.")
    s.close()
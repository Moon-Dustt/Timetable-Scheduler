"""
constraints.py — Scores a schedule out of 10,000
Higher = better. Any hard violation = score 0.
"""

from collections import defaultdict
from models import ScheduleEntry, RoomType


class ConstraintChecker:
    HARD  = 1000
    SOFT  = {"gap": 8, "early": 5, "late": 5, "spread": 10, "daily": 15}

    def __init__(self, session):
        self.session = session

    def evaluate(self, entries):
        report = {"hard": [], "soft": [], "hard_penalty": 0, "soft_penalty": 0, "is_valid": True}
        self._hard(entries, report)
        self._soft(entries, report)
        penalty = report["hard_penalty"] + report["soft_penalty"]
        score   = 0 if report["hard_penalty"] > 0 else max(0, 10000 - penalty)
        if report["hard_penalty"] > 0:
            report["is_valid"] = False
        report["score"] = score
        return score, report

    def _add_hard(self, report, msg):
        report["hard"].append(msg)
        report["hard_penalty"] += self.HARD

    def _hard(self, entries, report):
        # 1. Lecturer clash
        seen = defaultdict(list)
        for e in entries:
            seen[(e.lecturer_id, e.time_slot_id)].append(e)
        for k, v in seen.items():
            if len(v) > 1:
                self._add_hard(report, f"Lecturer {k[0]} double-booked at slot {k[1]}")

        # 2. Room clash
        seen = defaultdict(list)
        for e in entries:
            seen[(e.room_id, e.time_slot_id)].append(e)
        for k, v in seen.items():
            if len(v) > 1:
                self._add_hard(report, f"Room {k[0]} double-booked at slot {k[1]}")

        # 3. Student group clash
        slot_map = defaultdict(list)
        for e in entries:
            gids = frozenset(g.id for g in e.course.student_groups)
            slot_map[e.time_slot_id].append((e, gids))
        for slot_id, pairs in slot_map.items():
            for i in range(len(pairs)):
                for j in range(i+1, len(pairs)):
                    shared = pairs[i][1] & pairs[j][1]
                    if shared:
                        self._add_hard(report, f"Group clash at slot {slot_id}")

        # 4. Room capacity
        for e in entries:
            if e.room.capacity < e.course.enrolled_count:
                self._add_hard(report, f"Room {e.room.name} too small for {e.course.code}")

        # 5. Room type
        for e in entries:
            if e.course.requires_lab and e.room.room_type != RoomType.LAB:
                self._add_hard(report, f"{e.course.code} needs lab, got {e.room.room_type}")

        # 6. Lecturer availability
        for e in entries:
            avail = e.lecturer.availability or []
            if avail and e.time_slot_id not in avail:
                self._add_hard(report, f"{e.lecturer.name} unavailable at slot {e.time_slot_id}")

        # 7. Course frequency
        counts = defaultdict(int)
        for e in entries:
            counts[e.course_id] += 1
        for e in entries:
            actual   = counts[e.course.id]
            expected = e.course.hours_per_week
            if actual != expected:
                self._add_hard(report, f"{e.course.code} scheduled {actual}x, needs {expected}x")

    def _soft(self, entries, report):
        def add(key, msg):
            report["soft"].append(msg)
            report["soft_penalty"] += self.SOFT[key]

        for e in entries:
            if e.time_slot.start_time < "09:00":
                add("early", f"{e.course.code} before 09:00")
            if e.time_slot.start_time >= "17:00":
                add("late", f"{e.course.code} after 17:00")

        # Spread
        course_days = defaultdict(list)
        for e in entries:
            course_days[e.course_id].append(e.time_slot.day)
        for cid, days in course_days.items():
            day_counts = defaultdict(int)
            for d in days:
                day_counts[d] += 1
            for d, cnt in day_counts.items():
                if cnt > 1:
                    add("spread", f"Course {cid} has {cnt} sessions on {d}")

        # Gaps
        group_slots = defaultdict(lambda: defaultdict(list))
        for e in entries:
            for g in e.course.student_groups:
                group_slots[g.id][e.time_slot.day].append(e.time_slot.slot_index)
        for gid, days in group_slots.items():
            for day, idxs in days.items():
                idxs.sort()
                for i in range(1, len(idxs)):
                    gap = idxs[i] - idxs[i-1] - 1
                    if gap > 0:
                        add("gap", f"Group {gid} has {gap}-slot gap on {day}")

        # Lecturer daily hours
        lec_day = defaultdict(lambda: defaultdict(int))
        for e in entries:
            lec_day[e.lecturer_id][e.time_slot.day] += 1
        checked = set()
        for e in entries:
            if e.lecturer_id in checked:
                continue
            checked.add(e.lecturer_id)
            for day, hrs in lec_day[e.lecturer_id].items():
                if hrs > e.lecturer.max_hours_day:
                    add("daily", f"{e.lecturer.name} has {hrs}h on {day}")
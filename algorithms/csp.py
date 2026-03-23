"""
algorithms/csp.py — Repairs hard constraint violations
"""

import random
from collections import defaultdict
from models import ScheduleEntry, Room, TimeSlot, RoomType
from constraints import ConstraintChecker


class CSPSolver:
    MAX_ATTEMPTS = 300

    def __init__(self, session):
        self.session    = session
        self.checker    = ConstraintChecker(session)
        self.rooms      = session.query(Room).all()
        self.time_slots = session.query(TimeSlot).all()
        self.lab_rooms  = [r for r in self.rooms if r.room_type == RoomType.LAB]

    def repair(self, schedule, verbose=False):
        _, report = self.checker.evaluate(schedule)
        if report["is_valid"]:
            return schedule, True

        for attempt in range(self.MAX_ATTEMPTS):
            _, report = self.checker.evaluate(schedule)
            if report["is_valid"]:
                if verbose: print(f"CSP: repaired in {attempt} attempts")
                return schedule, True
            if report["hard"]:
                self._fix(schedule, report["hard"][0])

        _, final = self.checker.evaluate(schedule)
        return schedule, final["is_valid"]

    def _fix(self, schedule, violation):
        if "double-booked" in violation and "Lecturer" in violation:
            self._fix_clash(schedule, "lecturer")
        elif "double-booked" in violation and "Room" in violation:
            self._fix_clash(schedule, "room")
        elif "Group clash" in violation:
            self._fix_group_clash(schedule)
        elif "too small" in violation:
            self._fix_capacity(schedule)
        elif "needs lab" in violation:
            self._fix_room_type(schedule)
        elif "unavailable" in violation:
            self._fix_availability(schedule)
        else:
            # random nudge for other violations
            e = random.choice(schedule)
            s = random.choice(self.time_slots)
            e.time_slot = s; e.time_slot_id = s.id

    def _fix_clash(self, schedule, kind):
        seen = defaultdict(list)
        for i, e in enumerate(schedule):
            key = (e.lecturer_id, e.time_slot_id) if kind == "lecturer" else (e.room_id, e.time_slot_id)
            seen[key].append(i)
        clashes = [v for v in seen.values() if len(v) > 1]
        if not clashes: return
        idxs = random.choice(clashes)
        idx  = random.choice(idxs[1:])
        slot = self._free_slot(schedule, schedule[idx], idx)
        if slot:
            schedule[idx].time_slot    = slot
            schedule[idx].time_slot_id = slot.id

    def _fix_group_clash(self, schedule):
        slot_map = defaultdict(list)
        for i, e in enumerate(schedule):
            gids = frozenset(g.id for g in e.course.student_groups)
            slot_map[e.time_slot_id].append((i, gids))
        for pairs in slot_map.values():
            for a in range(len(pairs)):
                for b in range(a+1, len(pairs)):
                    if pairs[a][1] & pairs[b][1]:
                        idx  = pairs[b][0]
                        slot = self._free_slot(schedule, schedule[idx], idx, check_groups=True)
                        if slot:
                            schedule[idx].time_slot    = slot
                            schedule[idx].time_slot_id = slot.id
                        return

    def _fix_capacity(self, schedule):
        for e in schedule:
            if e.room.capacity < e.course.enrolled_count:
                bigger = [r for r in self.rooms if r.capacity >= e.course.enrolled_count]
                if bigger:
                    r = random.choice(bigger); e.room = r; e.room_id = r.id

    def _fix_room_type(self, schedule):
        for e in schedule:
            if e.course.requires_lab and e.room.room_type != RoomType.LAB:
                if self.lab_rooms:
                    r = random.choice(self.lab_rooms); e.room = r; e.room_id = r.id

    def _fix_availability(self, schedule):
        for e in schedule:
            avail = e.lecturer.availability or []
            if avail and e.time_slot_id not in avail:
                ok = [s for s in self.time_slots if s.id in avail]
                if ok:
                    s = random.choice(ok); e.time_slot = s; e.time_slot_id = s.id

    def _free_slot(self, schedule, entry, exclude_idx, check_groups=False):
        busy_lec   = {(e.lecturer_id, e.time_slot_id) for i, e in enumerate(schedule) if i != exclude_idx}
        busy_room  = {(e.room_id,     e.time_slot_id) for i, e in enumerate(schedule) if i != exclude_idx}
        grp_slots  = defaultdict(set)
        if check_groups:
            for i, e in enumerate(schedule):
                if i != exclude_idx:
                    for g in e.course.student_groups:
                        grp_slots[g.id].add(e.time_slot_id)
        entry_grps = {g.id for g in entry.course.student_groups}
        candidates = list(self.time_slots)
        random.shuffle(candidates)
        for s in candidates:
            if (entry.lecturer_id, s.id) in busy_lec: continue
            if (entry.room_id,     s.id) in busy_room: continue
            avail = entry.lecturer.availability or []
            if avail and s.id not in avail: continue
            if check_groups and any(s.id in grp_slots[g] for g in entry_grps): continue
            return s
        return None
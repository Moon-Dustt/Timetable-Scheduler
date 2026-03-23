"""
algorithms/genetic.py
Uses plain dicts during evolution — no SQLAlchemy state issues.
Supports session_duration so multi-hour classes block consecutive slots.
"""

import random
from models import ScheduleEntry, Course, Lecturer, Room, TimeSlot, RoomType


def _score(schedule, CM, RM, SM):
    """Score a schedule (list of dicts). Returns (score, is_valid)."""
    HARD    = 1000
    penalty = 0
    lec_slots    = {}
    room_slots   = {}
    group_slots  = {}
    course_count = {}

    for e in schedule:
        cid, lid, rid, sid = e["course_id"], e["lecturer_id"], e["room_id"], e["slot_id"]
        dur = CM[cid]["session_duration"]

        # Block all slots covered by this session
        base_idx = SM[sid]["index"]
        for offset in range(dur):
            actual_sid = SM[sid]["day_slot_ids"][base_idx + offset] if base_idx + offset < len(SM[sid]["day_slot_ids"]) else sid

            lk = (lid, actual_sid)
            lec_slots[lk] = lec_slots.get(lk, 0) + 1

            rk = (rid, actual_sid)
            room_slots[rk] = room_slots.get(rk, 0) + 1

            for gid in CM[cid]["group_ids"]:
                gk = (gid, actual_sid)
                group_slots[gk] = group_slots.get(gk, 0) + 1

        course_count[cid] = course_count.get(cid, 0) + 1

    # Hard: clashes
    for v in lec_slots.values():
        if v > 1: penalty += HARD * (v - 1)
    for v in room_slots.values():
        if v > 1: penalty += HARD * (v - 1)
    for v in group_slots.values():
        if v > 1: penalty += HARD * (v - 1)

    # Hard: capacity & room type
    for e in schedule:
        c = CM[e["course_id"]]; r = RM[e["room_id"]]
        if r["capacity"] < c["enrolled_count"]: penalty += HARD
        if c["requires_lab"] and not r["is_lab"]: penalty += HARD

    # Hard: course frequency
    for cid, c in CM.items():
        actual   = course_count.get(cid, 0)
        expected = c["sessions_per_week"]
        if actual != expected:
            penalty += HARD * abs(actual - expected)

    # Soft: early / late
    for e in schedule:
        start = SM[e["slot_id"]]["start"]
        if start < "09:00":  penalty += 5
        if start >= "15:00": penalty += 5

    # Soft: spread days
    cd = {}
    for e in schedule:
        cid = e["course_id"]
        day = SM[e["slot_id"]]["day"]
        if cid not in cd: cd[cid] = {}
        cd[cid][day] = cd[cid].get(day, 0) + 1
    for days in cd.values():
        for cnt in days.values():
            if cnt > 1: penalty += 10 * (cnt - 1)

    score    = max(0, 10000 - penalty)
    is_valid = penalty < HARD
    return score, is_valid


class GeneticAlgorithm:

    def __init__(self, session, population_size=30, max_generations=100,
                 mutation_rate=0.12, elite_size=3, target_score=9000):
        self.session         = session
        self.population_size = population_size
        self.max_generations = max_generations
        self.mutation_rate   = mutation_rate
        self.elite_size      = elite_size
        self.target_score    = target_score

        courses   = session.query(Course).all()
        lecturers = session.query(Lecturer).all()
        rooms     = session.query(Room).all()
        slots     = session.query(TimeSlot).all()

        if not courses:   raise ValueError("No courses found. Add courses first.")
        if not lecturers: raise ValueError("No lecturers found. Add lecturers first.")
        if not rooms:     raise ValueError("No rooms found. Add rooms first.")
        if not slots:     raise ValueError("No time slots found. Restart the server.")

        # Group slot IDs by day for consecutive-slot blocking
        day_slots = {}
        for s in slots:
            d = s.day.value
            if d not in day_slots: day_slots[d] = []
            day_slots[d].append((s.slot_index, s.id))
        for d in day_slots:
            day_slots[d].sort()

        self.SM = {}
        for s in slots:
            ordered = [sid for _, sid in day_slots[s.day.value]]
            self.SM[s.id] = {
                "id": s.id, "day": s.day.value,
                "start": s.start_time, "end": s.end_time,
                "index": s.slot_index,
                "day_slot_ids": ordered,
            }

        self.CM = {}
        for c in courses:
            spw = max(1, round(c.hours_per_week / c.session_duration))
            self.CM[c.id] = {
                "id": c.id, "code": c.code, "level": c.level,
                "hours_per_week": c.hours_per_week,
                "session_duration": c.session_duration,
                "sessions_per_week": spw,
                "enrolled_count": c.enrolled_count,
                "requires_lab": c.requires_lab,
                "group_ids":    [g.id for g in c.student_groups],
                "lecturer_ids": [l.id for l in c.lecturers],
            }

        self.RM = {r.id: {
            "id": r.id, "name": r.name,
            "capacity": r.capacity,
            "is_lab":   r.room_type == RoomType.LAB,
        } for r in rooms}

        self.LM = {l.id: {
            "id": l.id, "name": l.name,
            "max_hours_day": l.max_hours_day,
        } for l in lecturers}

        all_lecturer_ids = list(self.LM.keys())
        all_room_ids     = list(self.RM.keys())
        lab_ids          = [r.id for r in rooms if r.room_type == RoomType.LAB]
        non_lab_ids      = [r.id for r in rooms if r.room_type != RoomType.LAB]
        all_slot_ids     = list(self.SM.keys())

        # Valid start slots — must leave room for session_duration
        self.course_slots = {}
        for cid, c in self.CM.items():
            dur    = c["session_duration"]
            valid  = []
            for d, ordered in day_slots.items():
                for i, (_, sid) in enumerate(ordered):
                    if i + dur <= len(ordered):
                        valid.append(sid)
            self.course_slots[cid] = valid or all_slot_ids

        self.course_lecturers = {cid: c["lecturer_ids"] or all_lecturer_ids
                                  for cid, c in self.CM.items()}

        self.course_rooms = {}
        for cid, c in self.CM.items():
            pool  = lab_ids if c["requires_lab"] else non_lab_ids
            if not pool: pool = all_room_ids
            sized = [rid for rid in pool if self.RM[rid]["capacity"] >= c["enrolled_count"]]
            self.course_rooms[cid] = sized or pool or all_room_ids

    def run(self, verbose=True):
        if verbose:
            print(f"GA: {len(self.CM)} courses | pop={self.population_size} | gen={self.max_generations}")

        pop           = [self._rand() for _ in range(self.population_size)]
        best_score    = -1
        best_schedule = None
        history       = []

        for gen in range(1, self.max_generations + 1):
            scored = [(self._eval(s), s) for s in pop]
            scored.sort(key=lambda x: x[0][0], reverse=True)

            top_score = scored[0][0][0]
            avg       = sum(x[0][0] for x in scored) / len(scored)
            history.append((gen, top_score, avg))

            if top_score > best_score:
                best_score    = top_score
                best_schedule = [e.copy() for e in scored[0][1]]

            if verbose and (gen % 20 == 0 or gen == 1):
                print(f"  Gen {gen:>4} | Best: {top_score:.0f} | Avg: {avg:.0f}")

            if best_score >= self.target_score:
                if verbose: print(f"  Target reached at gen {gen}")
                break

            elites   = [s for _, s in scored[:self.elite_size]]
            next_pop = list(elites)
            while len(next_pop) < self.population_size:
                p1 = self._tournament(scored)
                p2 = self._tournament(scored)
                next_pop.append(self._mutate(self._cross(p1, p2)))
            pop = next_pop

        if best_schedule is None:
            best_schedule = scored[0][1] if scored else pop[0]
            best_score    = scored[0][0][0] if scored else 0

        if verbose: print(f"GA done. Best: {best_score:.0f}")
        return best_schedule, best_score, history

    def get_score(self, schedule):
        return _score(schedule, self.CM, self.RM, self.SM)

    def save_best(self, schedule):
        self.session.query(ScheduleEntry).filter_by(is_final=True).delete()
        for e in schedule:
            self.session.add(ScheduleEntry(
                course_id    = e["course_id"],
                lecturer_id  = e["lecturer_id"],
                room_id      = e["room_id"],
                time_slot_id = e["slot_id"],
                is_final     = True,
            ))
        self.session.commit()

    def _eval(self, s):
        return _score(s, self.CM, self.RM, self.SM)

    def _rand(self):
        entries = []
        for cid, c in self.CM.items():
            lecs  = self.course_lecturers[cid]
            rooms = self.course_rooms[cid]
            slots = self.course_slots[cid]
            for _ in range(c["sessions_per_week"]):
                entries.append({
                    "course_id":   cid,
                    "lecturer_id": random.choice(lecs),
                    "room_id":     random.choice(rooms),
                    "slot_id":     random.choice(slots),
                })
        return entries

    def _tournament(self, scored, k=4):
        return max(random.sample(scored, min(k, len(scored))), key=lambda x: x[0][0])[1]

    def _cross(self, p1, p2):
        if not p1: return [e.copy() for e in p2]
        pt = random.randint(1, len(p1) - 1)
        return [e.copy() for e in p1[:pt]] + [e.copy() for e in p2[pt:]]

    def _mutate(self, schedule):
        for e in schedule:
            if random.random() < self.mutation_rate:
                move = random.choice(["slot", "room", "lecturer"])
                if move == "slot":
                    e["slot_id"] = random.choice(self.course_slots[e["course_id"]])
                elif move == "room":
                    e["room_id"] = random.choice(self.course_rooms[e["course_id"]])
                else:
                    e["lecturer_id"] = random.choice(self.course_lecturers[e["course_id"]])
        return schedule
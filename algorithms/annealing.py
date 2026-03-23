"""
algorithms/annealing.py — Polishes soft constraints (fast, no deepcopy)
"""

import random, math
from models import Room, TimeSlot, RoomType
from constraints import ConstraintChecker


class SimulatedAnnealing:

    def __init__(self, session, initial_temp=50.0, cooling_rate=0.95,
                 min_temp=1.0, max_iterations=200):
        self.session        = session
        self.initial_temp   = initial_temp
        self.cooling_rate   = cooling_rate
        self.min_temp       = min_temp
        self.max_iterations = max_iterations
        self.checker        = ConstraintChecker(session)
        all_slots           = session.query(TimeSlot).all()
        self.good_slots     = [s for s in all_slots if "09:00" <= s.start_time < "17:00"]
        self.all_slots      = all_slots
        self.all_rooms      = session.query(Room).all()

    def run(self, schedule, verbose=True):
        if not schedule:
            return schedule, 0
        score, report = self.checker.evaluate(schedule)
        if not report["is_valid"]:
            if verbose: print("Annealing skipped — hard violations present.")
            return schedule, score

        best_score = score
        best_snap  = self._snap(schedule)
        temp       = self.initial_temp

        if verbose:
            print(f"Annealing: start {score:.0f} | iterations: {self.max_iterations}")

        for _ in range(self.max_iterations):
            if temp < self.min_temp:
                break
            entry, rb = self._mutate(schedule)
            if entry is None:
                temp *= self.cooling_rate
                continue
            new_score, new_report = self.checker.evaluate(schedule)
            if not new_report["is_valid"]:
                self._rollback(entry, rb)
            else:
                delta = new_score - score
                if delta >= 0 or random.random() < math.exp(delta / temp):
                    score = new_score
                    if score > best_score:
                        best_score = score
                        best_snap  = self._snap(schedule)
                else:
                    self._rollback(entry, rb)
            temp *= self.cooling_rate

        self._restore(schedule, best_snap)
        if verbose:
            final, _ = self.checker.evaluate(schedule)
            print(f"Annealing: final {final:.0f}")
        return schedule, best_score

    def _mutate(self, schedule):
        if not schedule: return None, None
        entry = random.choice(schedule)
        move  = random.choice(["good_slot", "any_slot", "room"])
        if move == "good_slot" and self.good_slots:
            old = (entry.time_slot, entry.time_slot_id)
            s   = random.choice(self.good_slots)
            entry.time_slot = s; entry.time_slot_id = s.id
            return entry, ("slot", *old)
        elif move == "any_slot":
            old = (entry.time_slot, entry.time_slot_id)
            s   = random.choice(self.all_slots)
            entry.time_slot = s; entry.time_slot_id = s.id
            return entry, ("slot", *old)
        elif move == "room":
            pool = [r for r in self.all_rooms
                    if (entry.course.requires_lab) == (r.room_type == RoomType.LAB)]
            if not pool: pool = self.all_rooms
            old = (entry.room, entry.room_id)
            r   = random.choice(pool)
            entry.room = r; entry.room_id = r.id
            return entry, ("room", *old)
        return None, None

    def _rollback(self, entry, rb):
        if not rb: return
        kind, old_obj, old_id = rb
        if kind == "slot":
            entry.time_slot = old_obj; entry.time_slot_id = old_id
        else:
            entry.room = old_obj; entry.room_id = old_id

    def _snap(self, schedule):
        return [(e.time_slot_id, e.time_slot, e.room_id, e.room) for e in schedule]

    def _restore(self, schedule, snap):
        for e, (sid, s, rid, r) in zip(schedule, snap):
            e.time_slot_id = sid; e.time_slot = s
            e.room_id = rid; e.room = r
"""
smart_scheduler.py
==================
Constraint-aware timetable generator.

Rules enforced
--------------
  College hours   : 9:05 AM – 4:25 PM  (8 × 55-min periods = 440 min)
  Lunch break     : EXACTLY 1 period (55 min) chosen at run-time from one of:
                      Candidate A — 11:50 – 12:45  (straddles 12:00, within 12–2 window)
                      Candidate B — 12:45 – 1:40   (fully within 12–2 window)
                    The candidate that leaves FEWER conflicts for the first section
                    is chosen globally for the whole run.
  Theory courses  : `lectures_per_week` slots (default 3) on DIFFERENT days
  Lab courses     : 2 CONSECUTIVE periods on 1 day (neither may be the lunch slot)
  No double-booking: instructor or room cannot be used at the same slot
  Room capacity   : preferably >= section strength (best-effort)
"""

import random
from collections import defaultdict

# ── Constants ──────────────────────────────────────────────────────────────────

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

# All 8 periods in chronological order
PERIOD_ORDER = [
    '9:05 - 10:00',    # P1
    '10:00 - 10:55',   # P2
    '10:55 - 11:50',   # P3
    '11:50 - 12:45',   # P4  ← Lunch Candidate A (spans 12:00)
    '12:45 - 1:40',    # P5  ← Lunch Candidate B (within 12:00–2:00)
    '1:40 - 2:35',     # P6
    '2:35 - 3:30',     # P7
    '3:30 - 4:25',     # P8
]

# ONE of these will be designated as the lunch break per generation run
LUNCH_CANDIDATES = ['11:50 - 12:45', '12:45 - 1:40']

# Safe lab pairs that NEVER include a lunch-candidate slot
# (additional pairs are admitted dynamically if the chosen lunch frees up adjacent slots)
BASE_LAB_PAIRS = [
    ('9:05 - 10:00',  '10:00 - 10:55'),   # Morning  A
    ('10:00 - 10:55', '10:55 - 11:50'),   # Morning  B
    ('1:40 - 2:35',   '2:35 - 3:30'),     # Afternoon A
    ('2:35 - 3:30',   '3:30 - 4:25'),     # Afternoon B
]

THEORY_LECTURES_PER_WEEK = 3


# ── Public API ─────────────────────────────────────────────────────────────────

def setup_meeting_times():
    """
    Ensure exactly 40 MeetingTime rows exist (8 periods × 5 days).
    Clears all existing entries & meeting times then recreates them.
    Returns the number of MeetingTime rows created.
    """
    from django.db import connection
    from ..models import MeetingTime, TimetableEntry

    # Wipe existing timetable entries first (they reference meeting times)
    TimetableEntry.objects.filter(is_active=True).delete()

    # Wipe all meeting times
    MeetingTime.objects.all().delete()

    created = 0
    pid_counter = 1
    for day in DAYS:
        for period in PERIOD_ORDER:
            pid = f'P{pid_counter:02d}'
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO SchedulerApp_meetingtime (pid, time, day) VALUES (%s, %s, %s)",
                    [pid, period, day]
                )
            pid_counter += 1
            created += 1

    return created   # always 40


def generate_smart_timetable(section_ids=None, lectures_per_week=THEORY_LECTURES_PER_WEEK):
    """
    Generate timetable entries for all (or selected) sections.

    1. Picks the best lunch period (Candidate A or B) globally.
    2. Builds valid lab-pair list excluding the chosen lunch period.
    3. Schedules theory (3 slots / different days) and labs (2 consecutive slots).

    Returns
    -------
    entries_data : list[dict]  (not yet saved to DB)
    batch_id     : str
    lunch_period : str  (the chosen lunch slot for this run)
    errors       : list[str]
    """
    import uuid
    from ..models import Section, Room, MeetingTime

    # ── Build (day, time) → MeetingTime lookup ─────────────────────────────────
    mt_lookup = {}
    for mt in MeetingTime.objects.all():
        mt_lookup[(mt.day, mt.time)] = mt

    if not mt_lookup:
        return [], '', None, ['No MeetingTimes found. Click "Reset Time Slots" first.']

    # ── Choose lunch period ────────────────────────────────────────────────────
    lunch_period = _pick_lunch_period(LUNCH_CANDIDATES, mt_lookup)

    # Teaching periods = all periods except the chosen lunch slot
    teaching_periods = [p for p in PERIOD_ORDER if p != lunch_period]

    # Build lab pairs valid for this run (neither slot may be the lunch period)
    lab_pairs = _build_lab_pairs(lunch_period)

    # ── Load rooms ─────────────────────────────────────────────────────────────
    all_rooms  = list(Room.objects.all())
    lab_rooms  = [r for r in all_rooms
                  if r.room_type in ('Lab', 'Computer Lab', 'AI Lab', 'ML Lab', 'DS Lab')]
    theo_rooms = [r for r in all_rooms if r.room_type == 'Classroom']

    # ── Global conflict trackers shared across ALL sections ────────────────────
    instr_taken = defaultdict(set)   # (day, time) → set of instructor PKs
    room_taken  = defaultdict(set)   # (day, time) → set of room PKs

    # ── Select sections ────────────────────────────────────────────────────────
    sections = Section.objects.all().order_by('section_id')
    if section_ids:
        sections = sections.filter(section_id__in=section_ids)

    batch_id     = f'GEN-{uuid.uuid4().hex[:8].upper()}'
    entries_data = []
    errors       = [f'ℹ Lunch period chosen: {lunch_period}']

    for section in sections:
        dept    = section.department
        courses = list(dept.courses.all())

        if not courses:
            errors.append(f'{section.section_id}: No courses in department — skipped')
            continue

        sec_taken = set()   # (day, time) occupied by this section
        random.shuffle(courses)

        for course in courses:
            instructors = list(course.instructors.all())
            if not instructors:
                errors.append(
                    f'{section.section_id}/{course.course_name}: No instructor — skipped'
                )
                continue

            is_lab = course.course_type in ('Lab', 'Theory+Lab')

            if is_lab:
                _schedule_lab(
                    section, course, instructors,
                    lab_rooms or all_rooms,
                    mt_lookup, sec_taken, instr_taken, room_taken,
                    entries_data, errors, batch_id,
                    lab_pairs, lunch_period
                )
            else:
                _schedule_theory(
                    section, course, instructors,
                    theo_rooms or all_rooms,
                    mt_lookup, sec_taken, instr_taken, room_taken,
                    entries_data, errors, batch_id,
                    teaching_periods, lectures_per_week
                )

    return entries_data, batch_id, lunch_period, errors


# ── Internal helpers ───────────────────────────────────────────────────────────

def _pick_lunch_period(candidates, mt_lookup):
    """
    Choose the lunch candidate that exists in the DB.
    If both exist, randomly pick one (caller can also pass preference).
    Randomness gives variety across generation runs.
    """
    available = [c for c in candidates if any(c == t for (_, t) in mt_lookup)]
    if not available:
        return candidates[0]        # fallback — shouldn't happen after setup
    return random.choice(available)


def _build_lab_pairs(lunch_period):
    """
    Return lab-eligible consecutive pairs, adding extra pairs made possible
    by the chosen lunch period freeing up adjacencies.
    """
    extra = []
    # If candidate A (11:50-12:45) is lunch → P3+P4 pair removed, P4+P5 also off
    # If candidate B (12:45-1:40) is lunch → P4+P5 pair removed; P3+P4 becomes possible
    if lunch_period == '11:50 - 12:45':
        # P4 is lunch: P3-P4 pair is invalid, P5-P6 becomes possible
        extra.append(('1:40 - 2:35', '2:35 - 3:30'))  # already in base, no-op
        # P4+P5 pair: invalid (P4 is lunch)
    elif lunch_period == '12:45 - 1:40':
        # P5 is lunch: P3-P4 pair becomes valid (P3=10:55-11:50, P4=11:50-12:45)
        extra.append(('10:55 - 11:50', '11:50 - 12:45'))
        # P5+P6 pair: invalid (P5 is lunch)

    # Merge, removing any pair that contains the lunch period
    all_pairs = BASE_LAB_PAIRS + extra
    valid = [
        (p1, p2) for (p1, p2) in all_pairs
        if p1 != lunch_period and p2 != lunch_period
    ]
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for pair in valid:
        if pair not in seen:
            seen.add(pair)
            deduped.append(pair)
    return deduped


def _schedule_theory(section, course, instructors, rooms,
                     mt_lookup, sec_taken, instr_taken, room_taken,
                     entries_data, errors, batch_id,
                     teaching_periods, lectures_per_week):
    """Schedule `lectures_per_week` theory slots on DIFFERENT days."""
    assigned_days = []
    days_pool     = DAYS[:]
    random.shuffle(days_pool)

    for day in days_pool:
        if len(assigned_days) >= lectures_per_week:
            break
        if day in assigned_days:
            continue

        periods_pool = teaching_periods[:]
        random.shuffle(periods_pool)

        for period in periods_pool:
            if (day, period) in sec_taken:
                continue
            mt = mt_lookup.get((day, period))
            if not mt:
                continue
            instr = _pick_instructor(instructors, day, [period], instr_taken)
            room  = _pick_room(rooms, day, [period], room_taken, section.strength)
            if instr and room:
                entries_data.append(_make_entry(section, course, instr, room, mt, batch_id))
                instr_taken[(day, period)].add(instr.id)
                room_taken[(day, period)].add(room.id)
                sec_taken.add((day, period))
                assigned_days.append(day)
                break

    if len(assigned_days) < lectures_per_week:
        errors.append(
            f'{section.section_id}/{course.course_name}: '
            f'Only {len(assigned_days)}/{lectures_per_week} lectures scheduled '
            f'(instructor/room conflicts)'
        )


def _schedule_lab(section, course, instructors, rooms,
                  mt_lookup, sec_taken, instr_taken, room_taken,
                  entries_data, errors, batch_id,
                  lab_pairs, lunch_period):
    """Schedule a 2-hour lab block (2 consecutive non-lunch periods on 1 day)."""
    days_pool = DAYS[:]
    random.shuffle(days_pool)

    for day in days_pool:
        pairs_pool = lab_pairs[:]
        random.shuffle(pairs_pool)

        for (p1, p2) in pairs_pool:
            # Defensive: skip if either slot is the lunch period
            if p1 == lunch_period or p2 == lunch_period:
                continue
            if (day, p1) in sec_taken or (day, p2) in sec_taken:
                continue
            mt1 = mt_lookup.get((day, p1))
            mt2 = mt_lookup.get((day, p2))
            if not mt1 or not mt2:
                continue
            instr = _pick_instructor(instructors, day, [p1, p2], instr_taken)
            room  = _pick_room(rooms, day, [p1, p2], room_taken, section.strength)
            if instr and room:
                for mt in (mt1, mt2):
                    entries_data.append(_make_entry(section, course, instr, room, mt, batch_id))
                    instr_taken[(day, mt.time)].add(instr.id)
                    room_taken[(day, mt.time)].add(room.id)
                sec_taken.add((day, p1))
                sec_taken.add((day, p2))
                return  # done for this lab course

    errors.append(
        f'{section.section_id}/{course.course_name} (Lab): '
        f'No free 2-hour block found (instructor/room conflicts)'
    )


def _pick_instructor(instructors, day, periods, instr_taken):
    pool = instructors[:]
    random.shuffle(pool)
    for instr in pool:
        if all(instr.id not in instr_taken[(day, p)] for p in periods):
            return instr
    return None


def _pick_room(rooms, day, periods, room_taken, min_cap=0):
    candidates = [r for r in rooms if r.seating_capacity >= min_cap] or rooms
    pool = candidates[:]
    random.shuffle(pool)
    for room in pool:
        if all(room.id not in room_taken[(day, p)] for p in periods):
            return room
    return None


def _make_entry(section, course, instructor, room, meeting_time, batch_id):
    return {
        'section':      section,
        'course':       course,
        'instructor':   instructor,
        'room':         room,
        'meeting_time': meeting_time,
        'batch_id':     batch_id,
        'entry_type':   'auto',
    }

from django.http.response import HttpResponse
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from django.utils import timezone
from .models import *
from .forms import *
from .timetable_utils import save_generated_timetable, get_timetable_grid_for_pdf, get_statistics
from collections import defaultdict
import random
import time
import uuid

# AI-Based Faculty Preference Learning imports
from .services.preference_integration import (
    integrate_preference_with_fitness,
    calculate_schedule_preference_score,
    get_preference_weight
)

# INTELLIGENT EDITING SYSTEM imports
from .services.constraint_engine import (
    ConstraintEngine, 
    check_conflict_api,
    validate_existing_entries
)
from .services.suggestion_engine import (
    SuggestionEngine,
    get_suggestions_api,
    get_quick_fix_suggestions
)

POPULATION_SIZE = 8
NUMB_OF_ELITE_SCHEDULES = 2
TOURNAMENT_SELECTION_SIZE = 4
MUTATION_RATE = 0.05
MAX_GENERATIONS = 40
VARS = {'generationNum': 0,
        'terminateGens': False}


class Population:
    def __init__(self, size):
        self._size = size
        self._data = data
        self._schedules = [Schedule().initialize() for i in range(size)]

    def getSchedules(self):
        return self._schedules


class Data:
    def __init__(self):
        # Load everything into memory with prefetch — zero extra queries during GA
        self._rooms        = list(Room.objects.all())
        self._meetingTimes = list(MeetingTime.objects.all())
        self._instructors  = list(Instructor.objects.all())
        self._courses      = list(Course.objects.prefetch_related('instructors').all())
        self._depts        = list(Department.objects.all())
        self._sections     = list(Section.objects.select_related('department').all())

        # Pre-build lunch-time exclusions
        lunch_set = set(LUNCH_CANDIDATES)
        self._available_mts = [
            mt for mt in self._meetingTimes if mt.time not in lunch_set
        ] or self._meetingTimes

        # Section strength cache  {section_id: strength}
        self._strengths = {s.section_id: s.strength for s in self._sections}

        # Per-section eligible courses  {section_id: (section_obj, [(course, [instructors])])}
        self._section_courses = {}
        for section in self._sections:
            eligible = []
            for course in section.department.courses.prefetch_related('instructors').all():
                instr_list = list(course.instructors.all())
                if instr_list:
                    eligible.append((course, instr_list))
            self._section_courses[section.section_id] = (section, eligible)

    def get_rooms(self):        return self._rooms
    def get_instructors(self):  return self._instructors
    def get_courses(self):      return self._courses
    def get_depts(self):        return self._depts
    def get_meetingTimes(self): return self._meetingTimes
    def get_sections(self):     return self._sections


class Class:
    def __init__(self, dept, section, course):
        self.department = dept
        self.course = course
        self.instructor = None
        self.meeting_time = None
        self.room = None
        self.section = section

    def get_id(self):
        return self.section_id

    def get_dept(self):
        return self.department

    def get_course(self):
        return self.course

    def get_instructor(self):
        return self.instructor

    def get_meetingTime(self):
        return self.meeting_time

    def get_room(self):
        return self.room

    def set_instructor(self, instructor):
        self.instructor = instructor

    def set_meetingTime(self, meetingTime):
        self.meeting_time = meetingTime

    def set_room(self, room):
        self.room = room


class Schedule:
    def __init__(self):
        try:
            self._data = data
        except NameError:
            # If data is not defined (e.g., during testing), initialize it
            self._data = Data()
        self._classes = []
        self._numberOfConflicts = 0
        self._fitness = -1
        self._isFitnessChanged = True

    def getClasses(self):
        self._isFitnessChanged = True
        return self._classes

    def getNumbOfConflicts(self):
        return self._numberOfConflicts

    def getFitness(self):
        if self._isFitnessChanged:
            self._fitness = self.calculateFitness()
            self._isFitnessChanged = False
        return self._fitness

    def addCourse(self, data, course, available_mts, rooms):
        """Add one class slot for the given course, using only teaching (non-lunch) periods."""
        crs_inst = list(course.instructors.all())
        if not crs_inst:
            return  # Skip courses with no instructors assigned
        if not available_mts:
            return
        if not rooms:
            return

        dept = course.department_set.first()  # fallback dept from M2M
        newClass = Class(dept, '_tmp', course)
        newClass.set_meetingTime(available_mts[random.randrange(len(available_mts))])
        newClass.set_room(rooms[random.randrange(len(rooms))])
        newClass.set_instructor(crs_inst[random.randrange(len(crs_inst))])
        self._classes.append(newClass)

    def initialize(self):
        """
        Build the initial random schedule — ZERO DB queries (uses data cache).
          - Caps total classes per section at section.num_class_in_week
          - 3 lecture slots per theory course, 2 per lab (up to cap)
          - Skips courses with no instructors
          - Excludes lunch-candidate meeting times
        """
        self._classes = []
        rooms         = data._rooms
        available_mts = data._available_mts
        if not rooms or not available_mts:
            return self

        for section_id, (section, eligible_courses) in data._section_courses.items():
            max_slots = section.num_class_in_week or 20
            shuffled  = list(eligible_courses)
            random.shuffle(shuffled)

            added = 0
            for course, crs_inst in shuffled:
                if added >= max_slots:
                    break
                is_lab       = course.course_type in ('Lab', 'Theory+Lab')
                slots_needed = min(2 if is_lab else 3, max_slots - added)
                dept         = section.department

                for _ in range(slots_needed):
                    if added >= max_slots:
                        break
                    newClass = Class(dept, section_id, course)
                    newClass.set_meetingTime(available_mts[random.randrange(len(available_mts))])
                    newClass.set_room(rooms[random.randrange(len(rooms))])
                    newClass.set_instructor(crs_inst[random.randrange(len(crs_inst))])
                    self._classes.append(newClass)
                    added += 1

        return self

    def calculateFitness(self):
        """
        O(n) conflict detection — ZERO DB queries (uses data cache).
        """
        self._numberOfConflicts = 0
        classes     = self.getClasses()
        lunch_times = set(LUNCH_CANDIDATES)
        strengths   = data._strengths        # pre-built in Data.__init__

        # Counters for hash-based conflict detection
        slot_section   = {}   # (mt_pid, section_id)  → count
        slot_instr     = {}   # (mt_pid, instr_id)    → count
        slot_room      = {}   # (mt_pid, room_id)     → count
        course_day_sec = {}   # (section_id, course_name, day) → count

        for c in classes:
            if not (c.meeting_time and c.room and c.instructor):
                continue

            mt_pid   = c.meeting_time.pid
            sec_id   = c.section
            day      = c.meeting_time.day
            instr_id = c.instructor.id
            room_id  = c.room.id

            # ① Lunch period penalty
            if c.meeting_time.time in lunch_times:
                self._numberOfConflicts += 1

            # ② Room capacity
            strength = strengths.get(sec_id, 30)
            if c.room.seating_capacity < strength:
                self._numberOfConflicts += 1

            # ③ Section double-booked
            k = (mt_pid, sec_id)
            slot_section[k] = slot_section.get(k, 0) + 1
            if slot_section[k] > 1:
                self._numberOfConflicts += 1

            # ④ Instructor double-booked
            k = (mt_pid, instr_id)
            slot_instr[k] = slot_instr.get(k, 0) + 1
            if slot_instr[k] > 1:
                self._numberOfConflicts += 1

            # ⑤ Room double-booked
            k = (mt_pid, room_id)
            slot_room[k] = slot_room.get(k, 0) + 1
            if slot_room[k] > 1:
                self._numberOfConflicts += 1

            # ⑥ Same course on same day in same section
            k = (sec_id, c.course.course_name, day)
            course_day_sec[k] = course_day_sec.get(k, 0) + 1
            if course_day_sec[k] > 1:
                self._numberOfConflicts += 1

        base_fitness = 1 / (self._numberOfConflicts + 1)
        # Preference scoring is applied post-generation in the display layer.
        # Keeping it out of the GA hot-path reduces per-fitness time from 0.6s → 0.0005s.
        return base_fitness


class GeneticAlgorithm:
    def evolve(self, population):
        return self._mutatePopulation(self._crossoverPopulation(population))

    def _crossoverPopulation(self, popula):
        crossoverPopula = Population(0)
        for i in range(NUMB_OF_ELITE_SCHEDULES):
            crossoverPopula.getSchedules().append(popula.getSchedules()[i])

        for i in range(NUMB_OF_ELITE_SCHEDULES, POPULATION_SIZE):
            scheduleX = self._tournamentPopulation(popula)
            scheduleY = self._tournamentPopulation(popula)

            crossoverPopula.getSchedules().append(
                self._crossoverSchedule(scheduleX, scheduleY))

        return crossoverPopula

    def _mutatePopulation(self, population):
        for i in range(NUMB_OF_ELITE_SCHEDULES, POPULATION_SIZE):
            self._mutateSchedule(population.getSchedules()[i])
        return population

    def _crossoverSchedule(self, scheduleX, scheduleY):
        crossoverSchedule = Schedule().initialize()
        for i in range(0, len(crossoverSchedule.getClasses())):
            if random.random() > 0.5:
                crossoverSchedule.getClasses()[i] = scheduleX.getClasses()[i]
            else:
                crossoverSchedule.getClasses()[i] = scheduleY.getClasses()[i]
        return crossoverSchedule

    def _mutateSchedule(self, mutateSchedule):
        schedule = Schedule().initialize()
        for i in range(len(mutateSchedule.getClasses())):
            if MUTATION_RATE > random.random():
                mutateSchedule.getClasses()[i] = schedule.getClasses()[i]
        return mutateSchedule

    def _tournamentPopulation(self, popula):
        tournamentPopula = Population(0)

        for i in range(0, TOURNAMENT_SELECTION_SIZE):
            tournamentPopula.getSchedules().append(
                popula.getSchedules()[random.randrange(0, POPULATION_SIZE)])

        # tournamentPopula.getSchedules().sort(key=lambda x: x.getFitness(),reverse=True)
        # return tournamentPopula
        return max(tournamentPopula.getSchedules(), key=lambda x: x.getFitness())



def context_manager(schedule):
    classes = schedule.getClasses()
    context = []
    for i in range(len(classes)):
        clas = {}
        clas['section'] = classes[i].section_id
        clas['dept'] = classes[i].department.dept_name
        clas['course'] = f'{classes[i].course.course_name} ({classes[i].course.course_number} {classes[i].course.max_numb_students})'
        clas['room'] = f'{classes[i].room.r_number} ({classes[i].room.seating_capacity})'
        clas['instructor'] = f'{classes[i].instructor.name} ({classes[i].instructor.uid})'
        clas['meeting_time'] = [
            classes[i].meeting_time.pid,
            classes[i].meeting_time.day,
            classes[i].meeting_time.time
        ]
        context.append(clas)
    return context


def apiGenNum(request):
    return JsonResponse({'genNum': VARS['generationNum']})

def apiterminateGens(request):
    VARS['terminateGens'] = True
    return redirect('home')



@login_required
def timetable(request):
    global data
    start_time = time.time()

    data = Data()

    # Validate that there is enough data to run the GA
    if not data.get_meetingTimes() or not data.get_rooms():
        return render(request, 'index.html', {
            'error': 'No meeting times or rooms found. Please import data first.'
        })
    has_courses = any(
        s.department.courses.filter(instructors__isnull=False).exists()
        for s in data.get_sections()
    )
    if not has_courses:
        return render(request, 'index.html', {
            'error': 'All courses are missing instructor assignments. '
                     'Please assign instructors to courses first.'
        })

    population = Population(POPULATION_SIZE)
    VARS['generationNum'] = 0
    VARS['terminateGens'] = False
    population.getSchedules().sort(key=lambda x: x.getFitness(), reverse=True)
    geneticAlgorithm = GeneticAlgorithm()
    schedule = population.getSchedules()[0]

    while (schedule.getFitness() != 1.0) and (VARS['generationNum'] < MAX_GENERATIONS):
        if VARS['terminateGens']:
            return HttpResponse('')

        population = geneticAlgorithm.evolve(population)
        population.getSchedules().sort(key=lambda x: x.getFitness(), reverse=True)
        schedule = population.getSchedules()[0]
        VARS['generationNum'] += 1

        print(f'\n> Generation #{VARS["generationNum"]}, Fitness: {schedule.getFitness()}')

    generation_time = time.time() - start_time

    # Save the generated timetable to the database
    try:
        batch_id = save_generated_timetable(
            schedule_classes=schedule.getClasses(),
            fitness_score=schedule.getFitness(),
            generation_time=generation_time
        )
        print(f"Timetable saved to database with batch ID: {batch_id}")
    except Exception as e:
        print(f"Error saving timetable: {e}")
        batch_id = None

    # Redirect to the per-section tabbed timetable view
    return redirect('view_stored_timetable')


'''
Page Views
'''

def home(request):
    return render(request, 'index.html', {})


@login_required
def instructorAdd(request):
    form = InstructorForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('instructorAdd')
    context = {'form': form}
    return render(request, 'instructorAdd.html', context)


@login_required
def instructorEdit(request):
    context = {'instructors': Instructor.objects.all()}
    return render(request, 'instructorEdit.html', context)


@login_required
def instructorDelete(request, pk):
    inst = Instructor.objects.filter(pk=pk)
    if request.method == 'POST':
        inst.delete()
        return redirect('instructorEdit')


@login_required
def roomAdd(request):
    form = RoomForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('roomAdd')
    context = {'form': form}
    return render(request, 'roomAdd.html', context)


@login_required
def roomEdit(request):
    context = {'rooms': Room.objects.all()}
    return render(request, 'roomEdit.html', context)


@login_required
def roomDelete(request, pk):
    rm = Room.objects.filter(pk=pk)
    if request.method == 'POST':
        rm.delete()
        return redirect('roomEdit')


@login_required
def meetingTimeAdd(request):
    form = MeetingTimeForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('meetingTimeAdd')
        else:
            print('Invalid')
    context = {'form': form}
    return render(request, 'meetingTimeAdd.html', context)


@login_required
def meetingTimeEdit(request):
    context = {'meeting_times': MeetingTime.objects.all()}
    return render(request, 'meetingTimeEdit.html', context)


@login_required
def meetingTimeDelete(request, pk):
    mt = MeetingTime.objects.filter(pk=pk)
    if request.method == 'POST':
        mt.delete()
        return redirect('meetingTimeEdit')


@login_required
def courseAdd(request):
    form = CourseForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('courseAdd')
        else:
            print('Invalid')
    context = {'form': form}
    return render(request, 'courseAdd.html', context)


@login_required
def courseEdit(request):
    instructor = defaultdict(list)
    for course in Course.instructors.through.objects.all():
        course_number = course.course_id
        instructor_name = Instructor.objects.filter(
            id=course.instructor_id).values('name')[0]['name']
        instructor[course_number].append(instructor_name)

    context = {'courses': Course.objects.all(), 'instructor': instructor}
    return render(request, 'courseEdit.html', context)


@login_required
def courseDelete(request, pk):
    crs = Course.objects.filter(pk=pk)
    if request.method == 'POST':
        crs.delete()
        return redirect('courseEdit')


@login_required
def departmentAdd(request):
    form = DepartmentForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('departmentAdd')
    context = {'form': form}
    return render(request, 'departmentAdd.html', context)


@login_required
def departmentEdit(request):
    course = defaultdict(list)
    for dept in Department.courses.through.objects.all():
        dept_name = Department.objects.filter(
            id=dept.department_id).values('dept_name')[0]['dept_name']
        course_name = Course.objects.filter(
            course_number=dept.course_id).values(
                'course_name')[0]['course_name']
        course[dept_name].append(course_name)

    context = {'departments': Department.objects.all(), 'course': course}
    return render(request, 'departmentEdit.html', context)


@login_required
def departmentDelete(request, pk):
    dept = Department.objects.filter(pk=pk)
    if request.method == 'POST':
        dept.delete()
        return redirect('departmentEdit')


@login_required
def sectionAdd(request):
    form = SectionForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('sectionAdd')
    context = {'form': form}
    return render(request, 'sectionAdd.html', context)


@login_required
def sectionEdit(request):
    context = {'sections': Section.objects.all()}
    return render(request, 'sectionEdit.html', context)


@login_required
def sectionDelete(request, pk):
    sec = Section.objects.filter(pk=pk)
    if request.method == 'POST':
        sec.delete()
        return redirect('sectionEdit')




# ==================== PDF EXPORT VIEWS ====================

@login_required
def timetable_pdf(request, batch_id=None):
    """
    Generate FET-style PDF timetable
    
    Args:
        batch_id: Optional generation batch ID (uses latest active if not provided)
    """
    # Get timetable data
    timetable_data = get_timetable_grid_for_pdf(batch_id=batch_id)
    stats = get_statistics(batch_id=batch_id)
    
    # Render HTML template for PDF
    html_string = render_to_string('timetable_pdf.html', {
        'timetable': timetable_data,
        'stats': stats,
        'generated_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
        'batch_id': batch_id or 'Latest'
    })
    
    # Create PDF response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="timetable_{batch_id or "latest"}.pdf"'
    
    try:
        # Try WeasyPrint first
        from weasyprint import HTML
        HTML(string=html_string).write_pdf(response)
    except ImportError:
        try:
            # Fallback to xhtml2pdf
            from xhtml2pdf import pisa
            pisa.CreatePDF(html_string, dest=response)
        except ImportError:
            # If neither is available, return HTML for browser print
            response = HttpResponse(html_string, content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="timetable_{batch_id or "latest"}.html"'
    
    return response


@login_required
def view_stored_timetable(request, batch_id=None):
    """
    View a stored timetable — one clean grid per section (tabbed layout).
    Each section (e.g. 4AIML-A, 6AIML-A) gets its own Day×TimeSlot grid.
    """
    from .timetable_utils import get_timetable_data

    # Get all active entries
    entries = get_timetable_data(batch_id=batch_id)

    # Days and time slots — use canonical PERIOD_ORDER for correct chronological order
    from .models import PERIOD_ORDER as CANONICAL_PERIODS
    days_order  = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    # Only include periods that actually exist in the DB
    existing_times = set(MeetingTime.objects.values_list('time', flat=True).distinct())
    time_slots = [p for p in CANONICAL_PERIODS if p in existing_times]
    if not time_slots:
        # Fallback: any order from DB
        time_slots = list(MeetingTime.objects.values_list('time', flat=True).distinct().order_by('pid'))

    # Build per-section data:  {section_id: {day: {time_slot: entry}}}
    all_sections = Section.objects.all().order_by('section_id')
    sections_data = {}
    for section in all_sections:
        sec_entries = entries.filter(section=section).select_related(
            'course', 'instructor', 'room', 'meeting_time'
        )
        grid = {day: {ts: None for ts in time_slots} for day in days_order}
        for e in sec_entries:
            day = e.meeting_time.day
            ts  = e.meeting_time.time
            if day in grid and ts in grid[day]:
                grid[day][ts] = e
        sections_data[section.section_id] = {
            'grid': grid,
            'entry_count': sec_entries.count(),
            'conflict_count': sec_entries.filter(has_conflict=True).count(),
        }

    gen_log             = GenerationLog.objects.filter(is_active=True).first()
    stats               = get_statistics(batch_id=batch_id)
    total_entries_count = entries.count()
    conflict_count      = entries.filter(has_conflict=True).count()
    locked_count        = entries.filter(is_locked=True).count()

    # Determine which slot is the lunch break for the current active schedule
    # (whichever LUNCH_CANDIDATE has no entries across all active sections)
    from .models import LUNCH_CANDIDATES
    used_times = set(entries.values_list('meeting_time__time', flat=True).distinct())
    lunch_period = None
    for candidate in LUNCH_CANDIDATES:
        if candidate not in used_times and candidate in existing_times:
            lunch_period = candidate
            break
    # If both have entries or neither found, pick the first candidate as display label
    if not lunch_period:
        lunch_period = LUNCH_CANDIDATES[0] if LUNCH_CANDIDATES else None

    return render(request, 'timetable_stored.html', {
        'entries':        entries,
        'sections':       all_sections,
        'sections_data':  sections_data,
        'days':           days_order,
        'time_slots':     time_slots,
        'stats':          stats,
        'batch_id':       batch_id,
        'gen_log':        gen_log,
        'total_entries':  total_entries_count,
        'conflict_count': conflict_count,
        'locked_count':   locked_count,
        'lunch_period':   lunch_period,
        'lunch_candidates': LUNCH_CANDIDATES,
    })


# ==================== IMPORT DATA VIEWS ====================

@login_required
def import_data_view(request):
    """
    Render the Import Data page with context for dropdowns and DB stats.
    """
    db_stats = {
        'rooms':         Room.objects.count(),
        'instructors':   Instructor.objects.count(),
        'courses':       Course.objects.count(),
        'sections':      Section.objects.count(),
        'meeting_times': MeetingTime.objects.count(),
        'entries':       TimetableEntry.objects.filter(is_active=True).count(),
    }
    return render(request, 'import_data.html', {
        'db_stats':      db_stats,
        'sections':      Section.objects.all().order_by('section_id'),
        'courses':       Course.objects.all().order_by('course_name'),
        'instructors':   Instructor.objects.all().order_by('name'),
        'rooms':         Room.objects.all().order_by('r_number'),
        'meeting_times': MeetingTime.objects.all().order_by('pid'),
    })


@login_required
def api_import_csv(request):
    """
    POST /api/import-csv/
    Body: { "category": "rooms"|"instructors"|"courses"|"sections"|"timetable",
            "rows": [ {col: val, ...}, ... ] }
    Validates and bulk-inserts rows. Returns created/skipped/errors.
    """
    import json
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)

    try:
        payload  = json.loads(request.body)
        category = payload.get('category', '').lower()
        rows     = payload.get('rows', [])
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid JSON body'}, status=400)

    if not rows:
        return JsonResponse({'success': False, 'message': 'No rows provided'})

    created = skipped = 0
    errors  = []

    try:
        if category == 'rooms':
            for i, row in enumerate(rows, 1):
                try:
                    r_number = row.get('r_number', '').strip()
                    capacity = int(row.get('seating_capacity', 30))
                    rtype    = row.get('room_type', 'Classroom').strip()
                    if not r_number:
                        errors.append(f'Row {i}: r_number is required'); skipped += 1; continue
                    obj, new = Room.objects.get_or_create(
                        r_number=r_number,
                        defaults={'seating_capacity': capacity, 'room_type': rtype}
                    )
                    if new: created += 1
                    else:   skipped += 1
                except Exception as e:
                    errors.append(f'Row {i}: {e}'); skipped += 1

        elif category == 'instructors':
            for i, row in enumerate(rows, 1):
                try:
                    uid  = row.get('uid', '').strip()
                    name = row.get('name', '').strip()
                    if not uid or not name:
                        errors.append(f'Row {i}: uid and name required'); skipped += 1; continue
                    obj, new = Instructor.objects.get_or_create(
                        uid=uid,
                        defaults={
                            'name': name,
                            'specialization': row.get('specialization', '').strip(),
                            'max_courses_per_semester': int(row.get('max_courses_per_semester', 3))
                        }
                    )
                    if new: created += 1
                    else:   skipped += 1
                except Exception as e:
                    errors.append(f'Row {i}: {e}'); skipped += 1

        elif category == 'courses':
            for i, row in enumerate(rows, 1):
                try:
                    course_number = row.get('course_number', '').strip()
                    course_name   = row.get('course_name', '').strip()
                    if not course_number or not course_name:
                        errors.append(f'Row {i}: course_number and course_name required')
                        skipped += 1; continue
                    ctype = row.get('course_type', 'Theory').strip()
                    obj, new = Course.objects.get_or_create(
                        course_number=course_number,
                        defaults={'course_name': course_name, 'course_type': ctype}
                    )
                    # Assign instructors by UID (semicolon-separated)
                    inst_uids = [u.strip() for u in row.get('instructor_uids', '').split(';') if u.strip()]
                    for uid in inst_uids:
                        try:
                            inst = Instructor.objects.get(uid=uid)
                            obj.instructors.add(inst)
                        except Instructor.DoesNotExist:
                            errors.append(f'Row {i}: Instructor uid "{uid}" not found')
                    if new: created += 1
                    else:   skipped += 1
                except Exception as e:
                    errors.append(f'Row {i}: {e}'); skipped += 1

        elif category == 'sections':
            # Ensure a default department exists
            dept, _ = Department.objects.get_or_create(
                id=int(rows[0].get('department_id', 1)) if rows else 1,
                defaults={'dept_name': 'General'}
            )
            for i, row in enumerate(rows, 1):
                try:
                    section_id = row.get('section_id', '').strip()
                    if not section_id:
                        errors.append(f'Row {i}: section_id required'); skipped += 1; continue
                    dept_id = int(row.get('department_id', dept.id))
                    dept_obj = Department.objects.get(id=dept_id)
                    obj, new = Section.objects.get_or_create(
                        section_id=section_id,
                        defaults={
                            'department': dept_obj,
                            'strength': int(row.get('strength', 30)),
                            'num_class_in_week': int(row.get('num_class_in_week', 35)),
                        }
                    )
                    if new: created += 1
                    else:   skipped += 1
                except Exception as e:
                    errors.append(f'Row {i}: {e}'); skipped += 1

        elif category == 'timetable':
            import uuid as _uuid
            batch = f'IMPORT-{_uuid.uuid4().hex[:8].upper()}'
            # Deactivate existing active entries
            TimetableEntry.objects.filter(is_active=True).update(is_active=False)
            GenerationLog.objects.filter(is_active=True).update(is_active=False)

            for i, row in enumerate(rows, 1):
                try:
                    section_id    = row.get('section_id', '').strip()
                    course_number = row.get('course_number', '').strip()
                    inst_uid      = row.get('instructor_uid', '').strip()
                    room_number   = row.get('room_number', '').strip()
                    day           = row.get('day', '').strip()
                    time_slot     = row.get('time_slot', '').strip()

                    section    = Section.objects.get(section_id=section_id)
                    course     = Course.objects.get(course_number=course_number)
                    instructor = Instructor.objects.get(uid=inst_uid)
                    room       = Room.objects.get(r_number=room_number)
                    mt         = MeetingTime.objects.filter(day=day, time=time_slot).first()
                    if not mt:
                        errors.append(f'Row {i}: No MeetingTime for {day} {time_slot}')
                        skipped += 1; continue

                    TimetableEntry.objects.create(
                        section=section, course=course, instructor=instructor,
                        room=room, meeting_time=mt, generation_batch=batch,
                        is_active=True, entry_type='manual'
                    )
                    created += 1
                except Section.DoesNotExist:
                    errors.append(f'Row {i}: Section "{section_id}" not found'); skipped += 1
                except Course.DoesNotExist:
                    errors.append(f'Row {i}: Course "{course_number}" not found'); skipped += 1
                except Instructor.DoesNotExist:
                    errors.append(f'Row {i}: Instructor uid "{inst_uid}" not found'); skipped += 1
                except Room.DoesNotExist:
                    errors.append(f'Row {i}: Room "{room_number}" not found'); skipped += 1
                except Exception as e:
                    errors.append(f'Row {i}: {e}'); skipped += 1

            # Create GenerationLog
            if created > 0:
                GenerationLog.objects.create(
                    batch_id=batch,
                    total_entries=created,
                    conflicts=0,
                    is_active=True,
                )
        else:
            return JsonResponse({'success': False, 'message': f'Unknown category: {category}'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e), 'errors': errors})

    return JsonResponse({
        'success': True,
        'created': created,
        'skipped': skipped,
        'errors':  errors[:20],   # cap at 20 for display
    })


@login_required
def api_add_manual_entry(request):
    """
    POST /api/add-entry/
    Add a single timetable entry manually.
    Body: { section_id, course_number, instructor_id, room_id, meeting_time_id }
    """
    import json
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)

    try:
        payload = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    section_id      = payload.get('section_id')
    course_number   = payload.get('course_number')
    instructor_id   = payload.get('instructor_id')
    room_id         = payload.get('room_id')
    meeting_time_id = payload.get('meeting_time_id')

    if not all([section_id, course_number, instructor_id, room_id, meeting_time_id]):
        return JsonResponse({'success': False, 'message': 'All fields are required'})

    try:
        section     = Section.objects.get(section_id=section_id)
        course      = Course.objects.get(course_number=course_number)
        instructor  = Instructor.objects.get(id=instructor_id)
        room        = Room.objects.get(id=room_id)
        meeting_time= MeetingTime.objects.get(pid=meeting_time_id)
    except (Section.DoesNotExist, Course.DoesNotExist,
            Instructor.DoesNotExist, Room.DoesNotExist,
            MeetingTime.DoesNotExist) as e:
        return JsonResponse({'success': False, 'message': f'Lookup error: {e}'})

    # Get or create an active generation batch for manual entries
    import uuid as _uuid
    gen_log = GenerationLog.objects.filter(is_active=True).first()
    if gen_log:
        batch_id = gen_log.batch_id
    else:
        batch_id = f'MANUAL-{_uuid.uuid4().hex[:8].upper()}'
        GenerationLog.objects.create(
            batch_id=batch_id, total_entries=0, conflicts=0, is_active=True
        )

    entry = TimetableEntry.objects.create(
        section=section,
        course=course,
        instructor=instructor,
        room=room,
        meeting_time=meeting_time,
        generation_batch=batch_id,
        is_active=True,
        entry_type='manual',
    )

    return JsonResponse({
        'success': True,
        'entry': {
            'id':         entry.entry_id,
            'section':    section.section_id,
            'course':     course.course_name,
            'instructor': instructor.name,
            'room':       room.r_number,
            'day':        meeting_time.day,
            'time':       meeting_time.time,
        }
    })


# ==================== SCHEDULE GENERATION VIEWS ====================

@login_required
def api_setup_meeting_times(request):
    """
    POST /api/setup-meeting-times/
    Resets the MeetingTime table to the canonical 30 slots
    (6 periods × 5 days, 9:05 AM – 4:25 PM with lunch 11:50–1:40).
    Also clears active TimetableEntries since they reference old slots.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    try:
        from .services.smart_scheduler import setup_meeting_times
        created = setup_meeting_times()
        return JsonResponse({
            'success': True,
            'created': created,
            'message': f'{created} meeting times set up (6 periods × 5 days).'
        })
    except Exception as e:
        import traceback
        return JsonResponse({'success': False, 'message': str(e),
                             'detail': traceback.format_exc()})


@login_required
def generate_timetable_view(request):
    """
    POST /generate/
    Body: { "section_ids": ["4AIML-A", "6AIML-A", ...] or null for all,
            "lectures_per_week": 3 }

    Pipeline:
      1. Runs smart_scheduler.generate_smart_timetable()
      2. Deactivates old active entries
      3. Bulk-creates new TimetableEntry rows
      4. Creates a GenerationLog
      5. Returns JSON with created count + redirect URL
    """
    import json
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    section_ids       = data.get('section_ids') or None   # None = all sections
    lectures_per_week = int(data.get('lectures_per_week', 3))

    try:
        from .services.smart_scheduler import generate_smart_timetable

        # Run the scheduler — returns (entries, batch_id, lunch_period, errors)
        entries_data, batch_id, lunch_period, errors = generate_smart_timetable(
            section_ids=section_ids,
            lectures_per_week=lectures_per_week
        )

        if not entries_data:
            return JsonResponse({
                'success': False,
                'message': 'No entries were generated. Make sure sections have courses '
                           'assigned and meeting times are set up.',
                'errors': errors
            })

        # Deactivate previous active sessions
        TimetableEntry.objects.filter(is_active=True).update(is_active=False)
        GenerationLog.objects.filter(is_active=True).update(is_active=False)

        # Bulk-create new entries
        created = 0
        save_errors = []
        for ed in entries_data:
            try:
                TimetableEntry.objects.create(
                    section      = ed['section'],
                    course       = ed['course'],
                    instructor   = ed['instructor'],
                    room         = ed['room'],
                    meeting_time = ed['meeting_time'],
                    generation_batch = ed['batch_id'],
                    is_active    = True,
                    entry_type   = ed['entry_type'],
                )
                created += 1
            except Exception as e:
                save_errors.append(str(e))

        # Record the generation log
        if created > 0:
            GenerationLog.objects.create(
                batch_id     = batch_id,
                total_entries= created,
                conflicts    = 0,
                is_active    = True,
            )

        all_errors = errors + save_errors
        return JsonResponse({
            'success':      True,
            'created':      created,
            'batch_id':     batch_id,
            'lunch_period': lunch_period,
            'warnings':     all_errors[:20],
            'redirect_url': '/timetable/stored/',
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'message': str(e),
            'detail':  traceback.format_exc()
        })


@login_required
def generation_history(request):
    """
    View all generation history
    """
    from .timetable_utils import get_generation_history
    
    generations = get_generation_history()
    return render(request, 'generation_history.html', {
        'generations': generations
    })


@login_required
def activate_generation_view(request, batch_id):
    """
    Activate a specific generation batch
    """
    from .timetable_utils import activate_generation
    activate_generation(batch_id)
    return redirect('generation_history')


@login_required
def delete_generation_view(request, batch_id):
    """
    Delete a generation batch
    """
    from .timetable_utils import delete_generation
    delete_generation(batch_id)
    return redirect('generation_history')


# ==================== AI-BASED FACULTY PREFERENCE LEARNING API ENDPOINTS ====================

@login_required
def api_predict_preference(request):
    """
    API endpoint to predict faculty preference for a given day and time slot.
    
    GET/POST parameters:
        - instructor_id or instructor_name
        - day (e.g., 'Monday')
        - time_slot (e.g., '10:00 - 11:00')
    
    Returns:
        JSON with preference score and confidence
    """
    from .services.preference_model import predict_preference
    
    # Get parameters from GET or POST
    instructor_id = request.GET.get('instructor_id') or request.POST.get('instructor_id')
    instructor_name = request.GET.get('instructor_name') or request.POST.get('instructor_name')
    day = request.GET.get('day') or request.POST.get('day')
    time_slot = request.GET.get('time_slot') or request.POST.get('time_slot')
    
    # Validate inputs
    if not day or not time_slot:
        return JsonResponse({
            'success': False,
            'error': 'Missing required parameters: day and time_slot'
        }, status=400)
    
    # Determine instructor identifier
    instructor_identifier = instructor_id or instructor_name
    if not instructor_identifier:
        return JsonResponse({
            'success': False,
            'error': 'Missing instructor identifier (instructor_id or instructor_name)'
        }, status=400)
    
    # Convert instructor_id to int if provided
    if instructor_id:
        try:
            instructor_identifier = int(instructor_id)
        except ValueError:
            pass
    
    # Get prediction
    result = predict_preference(instructor_identifier, day, time_slot)
    
    return JsonResponse(result)


@login_required
def api_train_model(request):
    """
    API endpoint to train the preference learning model.
    
    POST parameters (optional):
        - model_type: 'LogisticRegression', 'DecisionTree', or 'RandomForest'
        - per_faculty: 'true' or 'false' (default: true)
    
    Returns:
        JSON with training results
    """
    from .services.preference_model import train_model
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST method is allowed'
        }, status=405)
    
    # Get parameters
    model_type = request.POST.get('model_type', 'LogisticRegression')
    per_faculty = request.POST.get('per_faculty', 'true').lower() == 'true'
    
    # Validate model type
    valid_models = ['LogisticRegression', 'DecisionTree', 'RandomForest']
    if model_type not in valid_models:
        return JsonResponse({
            'success': False,
            'error': f'Invalid model type. Choose from: {", ".join(valid_models)}'
        }, status=400)
    
    # Train model
    try:
        result = train_model(
            model_type=model_type,
            per_faculty=per_faculty
        )
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def api_faculty_preferences(request, instructor_id=None):
    """
    API endpoint to get all preferences for a faculty or all faculties.
    
    GET parameters:
        - instructor_id (optional): Filter by specific instructor
    
    Returns:
        JSON with list of preferences
    """
    from .services.preference_model import get_all_faculty_preferences, get_instructor_preference_summary
    
    if instructor_id:
        # Get detailed summary for specific instructor
        summary = get_instructor_preference_summary(int(instructor_id))
        return JsonResponse(summary)
    else:
        # Get all preferences
        preferences = get_all_faculty_preferences()
        return JsonResponse({
            'success': True,
            'total_preferences': len(preferences),
            'preferences': preferences
        })


@login_required
def api_preference_statistics(request):
    """
    API endpoint to get system-wide preference statistics.
    
    Returns:
        JSON with preference statistics
    """
    from .services.preference_integration import get_preference_statistics
    
    stats = get_preference_statistics()
    return JsonResponse({
        'success': True,
        'statistics': stats
    })


@login_required
def api_set_preference_weight(request):
    """
    API endpoint to set the preference weight for GA fitness integration.
    
    POST parameters:
        - weight: Float between 0.0 and 1.0
    
    Returns:
        JSON with success status
    """
    from .services.preference_integration import set_preference_weight
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST method is allowed'
        }, status=405)
    
    weight = request.POST.get('weight')
    if weight is None:
        return JsonResponse({
            'success': False,
            'error': 'Missing weight parameter'
        }, status=400)
    
    try:
        weight = float(weight)
        if not (0.0 <= weight <= 1.0):
            raise ValueError('Weight must be between 0.0 and 1.0')
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    
    set_preference_weight(weight)
    
    return JsonResponse({
        'success': True,
        'message': f'Preference weight set to {weight}',
        'weight': weight
    })


# ==================== INTELLIGENT EDITING SYSTEM API ENDPOINTS ====================

@login_required
def api_check_conflict(request):
    """
    API endpoint to check for conflicts in real-time.
    
    POST parameters:
        - instructor_id: Faculty ID
        - room_id: Room ID
        - section_id: Section ID
        - meeting_time_id: Time slot ID
        - course_id: Course ID (optional)
        - entry_id: Entry ID (optional, for updates)
    
    Returns:
        JSON with conflict status and details
    """
    if request.method not in ['GET', 'POST']:
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    # Get parameters
    data = request.GET if request.method == 'GET' else request.POST
    
    entry_data = {
        'instructor_id': data.get('instructor_id'),
        'room_id': data.get('room_id'),
        'section_id': data.get('section_id'),
        'meeting_time_id': data.get('meeting_time_id'),
        'course_id': data.get('course_id'),
    }
    
    # Validate required fields
    required = ['instructor_id', 'room_id', 'section_id', 'meeting_time_id']
    missing = [f for f in required if not entry_data.get(f)]
    if missing:
        return JsonResponse({
            'success': False,
            'error': f'Missing required fields: {", ".join(missing)}'
        }, status=400)
    
    # Convert to integers
    try:
        for key in entry_data:
            if entry_data[key]:
                entry_data[key] = int(entry_data[key])
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid ID format'
        }, status=400)
    
    # Get optional entry_id (for updates)
    exclude_entry_id = data.get('entry_id')
    if exclude_entry_id:
        try:
            exclude_entry_id = int(exclude_entry_id)
        except ValueError:
            exclude_entry_id = None
    
    # Check conflicts
    result = check_conflict_api(entry_data)
    
    return JsonResponse(result)


@login_required
def api_suggest(request):
    """
    API endpoint to get smart suggestions for conflict resolution.
    
    POST/GET parameters:
        - Same as check-conflict endpoint
    
    Returns:
        JSON with alternative suggestions
    """
    if request.method not in ['GET', 'POST']:
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    data = request.GET if request.method == 'GET' else request.POST
    
    entry_data = {
        'instructor_id': data.get('instructor_id'),
        'room_id': data.get('room_id'),
        'section_id': data.get('section_id'),
        'meeting_time_id': data.get('meeting_time_id'),
        'course_id': data.get('course_id'),
    }
    
    # Get suggestions
    result = get_suggestions_api(entry_data, max_suggestions=5)
    
    return JsonResponse(result)


@login_required
def api_quick_fix(request, entry_id):
    """
    API endpoint to get quick fix suggestions for a specific entry.
    
    Args:
        entry_id: ID of the conflicting TimetableEntry
    
    Returns:
        JSON with quick fix actions
    """
    try:
        entry_id = int(entry_id)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid entry ID'}, status=400)
    
    result = get_quick_fix_suggestions(entry_id)
    
    if 'error' in result:
        return JsonResponse({'success': False, 'error': result['error']}, status=404)
    
    return JsonResponse({
        'success': True,
        'entry_id': entry_id,
        **result
    })


@login_required
def api_update_entry(request, entry_id):
    """
    API endpoint to update a timetable entry with validation.
    
    POST parameters:
        - instructor_id, room_id, section_id, meeting_time_id
        - Optional: lock (true/false), entry_type
    
    Returns:
        JSON with update status and any conflicts
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)
    
    try:
        entry = TimetableEntry.objects.get(pk=entry_id)
    except TimetableEntry.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'error': 'Entry not found'
        }, status=404)
    
    # Get update data
    new_data = {}
    field_mapping = {
        'instructor_id': 'instructor_id',
        'room_id': 'room_id',
        'section_id': 'section_id',
        'meeting_time_id': 'meeting_time_id',
        'course_id': 'course_id',
    }
    
    for field, key in field_mapping.items():
        value = request.POST.get(key)
        if value:
            try:
                new_data[field] = int(value)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid {key}'
                }, status=400)
    
    # Validate the update
    engine = ConstraintEngine(entry.generation_batch)
    violations = engine.validate_entry_update(entry, new_data)
    
    # Check if we can proceed (no hard violations or force flag set)
    hard_violations = violations.get('hard', [])
    soft_violations = violations.get('soft', [])
    
    force_update = request.POST.get('force', 'false').lower() == 'true'
    
    if hard_violations and not force_update:
        return JsonResponse({
            'success': False,
            'error': 'Update would create conflicts',
            'conflicts': [v.to_dict() for v in hard_violations],
            'can_force': True,
            'message': 'Set force=true to override (not recommended)'
        }, status=409)
    
    # Perform the update
    try:
        if 'instructor_id' in new_data:
            entry.instructor_id = new_data['instructor_id']
        if 'room_id' in new_data:
            entry.room_id = new_data['room_id']
        if 'section_id' in new_data:
            entry.section_id = new_data['section_id']
        if 'meeting_time_id' in new_data:
            entry.meeting_time_id = new_data['meeting_time_id']
        if 'course_id' in new_data:
            entry.course_id = new_data['course_id']
        
        # Update metadata
        entry.entry_type = 'manual'
        entry.has_conflict = len(hard_violations) > 0
        entry.conflict_details = {
            'hard_violations': [v.to_dict() for v in hard_violations],
            'soft_violations': [v.to_dict() for v in soft_violations],
            'forced': force_update
        }
        entry.modified_by = request.user.username if request.user.is_authenticated else 'api'
        
        # Handle lock status
        lock_status = request.POST.get('lock')
        if lock_status is not None:
            entry.is_locked = lock_status.lower() == 'true'
        
        # Update preference score for new slot
        entry.update_preference_score()
        
        entry.save()
        
        # Log conflicts if any
        for violation in hard_violations:
            ConflictLog.objects.create(
                entry=entry,
                conflict_type=violation.violation_type.value,
                message=violation.message,
                conflicting_entry_id=violation.conflicting_entry_id,
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Entry updated successfully',
            'entry_id': entry.entry_id,
            'has_conflict': entry.has_conflict,
            'warnings': [v.to_dict() for v in soft_violations] if soft_violations else []
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def api_auto_fix(request):
    """
    API endpoint to automatically fix conflicts using AI-powered suggestions.
    
    POST parameters:
        - batch_id: Timetable batch to fix (optional, uses active if not provided)
        - max_fixes: Maximum number of conflicts to auto-fix (default: 10)
    
    Returns:
        JSON with fix results
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)
    
    batch_id = request.POST.get('batch_id')
    max_fixes = int(request.POST.get('max_fixes', 10))
    
    # Get entries with conflicts
    if batch_id:
        conflict_entries = TimetableEntry.objects.filter(
            generation_batch=batch_id,
            has_conflict=True,
            is_active=True,
            is_locked=False  # Don't modify locked entries
        )
    else:
        conflict_entries = TimetableEntry.objects.filter(
            has_conflict=True,
            is_active=True,
            is_locked=False
        )
    
    conflict_entries = conflict_entries.select_related(
        'instructor', 'room', 'section', 'meeting_time', 'course'
    )[:max_fixes]
    
    if not conflict_entries.exists():
        return JsonResponse({
            'success': True,
            'message': 'No conflicts found to fix',
            'fixed_count': 0
        })
    
    fixed_count = 0
    failed_count = 0
    results = []
    
    for entry in conflict_entries:
        # Get quick fix suggestions
        fix_result = get_quick_fix_suggestions(entry.entry_id)
        
        if 'error' in fix_result or not fix_result.get('quick_actions'):
            failed_count += 1
            results.append({
                'entry_id': entry.entry_id,
                'status': 'failed',
                'reason': 'No fix suggestions available'
            })
            continue
        
        # Apply the first quick action (best suggestion)
        action = fix_result['quick_actions'][0]
        
        try:
            # Apply the fix
            if action['action'] == 'change_room_and_time':
                entry.room_id = action['data']['room_id']
                entry.meeting_time_id = action['data']['meeting_time_id']
            elif action['action'] == 'change_room':
                entry.room_id = action['data']['room_id']
            elif action['action'] == 'change_time':
                entry.meeting_time_id = action['data']['meeting_time_id']
            
            entry.entry_type = 'hybrid'
            entry.has_conflict = False
            entry.conflict_details = {}
            entry.modified_by = 'auto_fix'
            entry.update_preference_score()
            entry.save()
            
            # Mark conflict logs as resolved
            entry.conflicts.filter(is_resolved=False).update(
                is_resolved=True,
                resolution_method='auto_fix'
            )
            
            fixed_count += 1
            results.append({
                'entry_id': entry.entry_id,
                'status': 'fixed',
                'action': action['action'],
                'reason': action['reason']
            })
            
        except Exception as e:
            failed_count += 1
            results.append({
                'entry_id': entry.entry_id,
                'status': 'failed',
                'reason': str(e)
            })
    
    return JsonResponse({
        'success': True,
        'fixed_count': fixed_count,
        'failed_count': failed_count,
        'total_attempted': fixed_count + failed_count,
        'results': results
    })


@login_required
def api_toggle_lock(request, entry_id):
    """
    API endpoint to toggle lock status of an entry.
    
    POST parameters:
        - locked: true/false (optional, toggles if not provided)
    
    Returns:
        JSON with new lock status
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)
    
    try:
        entry = TimetableEntry.objects.get(pk=entry_id)
    except TimetableEntry.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Entry not found'}, status=404)
    
    # Get desired state
    lock_param = request.POST.get('locked')
    if lock_param is not None:
        entry.is_locked = lock_param.lower() == 'true'
    else:
        # Toggle
        entry.is_locked = not entry.is_locked
    
    entry.modified_by = request.user.username if request.user.is_authenticated else 'api'
    entry.save(update_fields=['is_locked', 'modified_by', 'last_modified'])
    
    return JsonResponse({
        'success': True,
        'entry_id': entry_id,
        'is_locked': entry.is_locked,
        'message': f'Entry {"locked" if entry.is_locked else "unlocked"}'
    })


@login_required
def api_validate_all(request):
    """
    API endpoint to validate all entries in a timetable.
    
    GET parameters:
        - batch_id: Specific batch to validate (optional)
    
    Returns:
        JSON with validation report
    """
    batch_id = request.GET.get('batch_id')
    
    result = validate_existing_entries(batch_id)
    
    return JsonResponse({
        'success': True,
        **result
    })


@login_required
def api_get_conflict_summary(request):
    """
    API endpoint to get summary of all conflicts.
    
    GET parameters:
        - batch_id: Filter by batch (optional)
    
    Returns:
        JSON with conflict summary including locked_count and avg_preference for dashboard
    """
    batch_id = request.GET.get('batch_id')
    
    engine = ConstraintEngine(batch_id)
    summary = engine.scan_all_conflicts(batch_id)
    
    # Add additional stats for dashboard widgets
    from django.db.models import Avg as DjangoAvg
    qs = TimetableEntry.objects.filter(is_active=True)
    if batch_id:
        qs = qs.filter(generation_batch=batch_id)
    
    locked_count = qs.filter(is_locked=True).count()
    avg_pref = qs.aggregate(avg=DjangoAvg('preference_score'))['avg'] or 0
    
    return JsonResponse({
        'success': True,
        'locked_count': locked_count,
        'avg_preference': round(avg_pref, 3),
        **summary
    })



@login_required
def conflict_log_view(request):
    """
    View to display the conflict log page with all conflict history.
    """
    from .models import ConflictLog, TimetableEntry
    
    # Get all conflicts
    conflicts = ConflictLog.objects.select_related(
        'entry', 'entry__section', 'entry__course', 'entry__instructor', 'entry__room', 'entry__meeting_time',
        'conflicting_entry'
    ).order_by('-detected_at')
    
    # Calculate statistics - use correct field names from model
    total_conflicts = conflicts.count()
    resolved_conflicts = conflicts.filter(is_resolved=True).count()
    pending_conflicts = conflicts.filter(is_resolved=False).count()
    
    context = {
        'conflicts': conflicts,
        'total_conflicts': total_conflicts,
        'resolved_conflicts': resolved_conflicts,
        'pending_conflicts': pending_conflicts,
    }
    
    return render(request, 'conflict_log.html', context)


@login_required
def preference_heatmap_view(request):
    """
    View to display the preference heatmap for instructors.
    """
    from .models import Instructor, TimetableEntry, MeetingTime
    from django.db.models import Avg
    
    # Get all instructors
    instructors = Instructor.objects.all()
    
    # Get days and time slots
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = list(MeetingTime.objects.values_list('time', flat=True).distinct())
    
    # Build heatmap data for all instructors combined
    heatmap_data = {}
    for day in days:
        heatmap_data[day] = {}
        for time in time_slots:
            # Get average preference for this slot across all instructors
            avg_pref = TimetableEntry.objects.filter(
                meeting_time__time=time,
                meeting_time__day=day,
                is_active=True
            ).aggregate(avg=Avg('preference_score'))['avg'] or 0
            heatmap_data[day][time] = round(avg_pref, 2)
    
    context = {
        'instructors': instructors,
        'days': days,
        'time_slots': time_slots,
        'heatmap_data': heatmap_data,
    }
    
    return render(request, 'preference_heatmap.html', context)


@login_required
def api_preference_heatmap(request):
    """
    API endpoint to get preference heatmap data for a specific instructor.
    """
    from .models import TimetableEntry, MeetingTime, Instructor
    
    instructor_id = request.GET.get('instructor', 'all')
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = list(MeetingTime.objects.values_list('time', flat=True).distinct())
    
    heatmap_data = {}
    total_score = 0
    count = 0
    max_score = 0
    best_slot = ''
    
    for day in days:
        heatmap_data[day] = {}
        for time in time_slots:
            if instructor_id == 'all':
                entries = TimetableEntry.objects.filter(
                    meeting_time__time=time,
                    meeting_time__day=day,
                    preference_score__isnull=False
                )
                score = entries.aggregate(avg=models.Avg('preference_score'))['avg'] or 0
            else:
                try:
                    entry = TimetableEntry.objects.get(
                        instructor_id=instructor_id,
                        meeting_time__time=time,
                        meeting_time__day=day
                    )
                    score = entry.preference_score or 0
                except TimetableEntry.DoesNotExist:
                    score = 0
            
            heatmap_data[day][time] = score
            
            if score > 0:
                total_score += score
                count += 1
                if score > max_score:
                    max_score = score
                    best_slot = f"{day} {time}"
    
    avg_preference = total_score / count if count > 0 else 0
    
    return JsonResponse({
        'success': True,
        'heatmap_data': heatmap_data,
        'avg_preference': avg_preference,
        'best_slot': best_slot,
        'days': days,
        'time_slots': time_slots,
    })


@login_required
def api_batch_lock(request):
    """
    API endpoint to lock/unlock multiple entries.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        entry_ids = data.get('entry_ids', [])
        lock = data.get('lock', True)
        
        if not entry_ids:
            return JsonResponse({'success': False, 'message': 'No entries selected'})
        
        updated = 0
        for entry_id in entry_ids:
            try:
                entry = TimetableEntry.objects.get(entry_id=entry_id)
                entry.is_locked = lock
                entry.save()
                updated += 1
            except TimetableEntry.DoesNotExist:
                continue
        
        return JsonResponse({
            'success': True,
            'updated': updated,
            'action': 'locked' if lock else 'unlocked'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def api_batch_delete(request):
    """
    API endpoint to delete multiple entries.
    Pass entry_ids='ALL_ACTIVE' to delete all active timetable entries.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        entry_ids = data.get('entry_ids', [])
        
        if entry_ids == 'ALL_ACTIVE':
            deleted, _ = TimetableEntry.objects.filter(is_active=True).delete()
            GenerationLog.objects.filter(is_active=True).update(is_active=False)
            return JsonResponse({'success': True, 'deleted': deleted})

        if not entry_ids:
            return JsonResponse({'success': False, 'message': 'No entries selected'})
        
        deleted = 0
        for entry_id in entry_ids:
            try:
                entry = TimetableEntry.objects.get(entry_id=entry_id)
                entry.delete()
                deleted += 1
            except TimetableEntry.DoesNotExist:
                continue
        
        return JsonResponse({'success': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def api_batch_resolve(request):
    """
    API endpoint to resolve conflicts for multiple entries.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        entry_ids = data.get('entry_ids', [])
        
        if not entry_ids:
            return JsonResponse({'success': False, 'message': 'No entries selected'})
        
        from .models import ConflictLog
        from django.utils import timezone
        resolved = 0
        
        for entry_id in entry_ids:
            try:
                entry = TimetableEntry.objects.get(entry_id=entry_id)
                if entry.has_conflict:
                    entry.has_conflict = False
                    entry.save()
                    resolved += 1
                
                # Update conflict logs using correct field names (is_resolved, not status)
                ConflictLog.objects.filter(entry_id=entry_id, is_resolved=False).update(
                    is_resolved=True,
                    resolved_at=timezone.now(),
                    resolution_method='manual'
                )
            except TimetableEntry.DoesNotExist:
                continue
        
        return JsonResponse({
            'success': True,
            'resolved': resolved
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def api_export_entries(request):
    """
    API endpoint to export selected entries as CSV.
    """
    entry_ids = request.GET.get('ids', '')
    
    if not entry_ids:
        return JsonResponse({'success': False, 'message': 'No entries selected'})
    
    ids = [int(id) for id in entry_ids.split(',') if id.isdigit()]
    
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="timetable_entries.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Section', 'Course', 'Instructor', 'Room', 'Time', 'Day', 'Locked', 'Has Conflict'])
    
    for entry_id in ids:
        try:
            entry = TimetableEntry.objects.get(entry_id=entry_id)
            writer.writerow([
                entry.entry_id,
                entry.section.section_id,
                entry.course.course_name,
                entry.instructor.name,
                entry.room.r_number,
                entry.meeting_time.time,
                entry.meeting_time.day,
                'Yes' if entry.is_locked else 'No',
                'Yes' if entry.has_conflict else 'No'
            ])
        except TimetableEntry.DoesNotExist:
            continue
    
    return response


'''
Error pages
'''

def error_404(request, exception):
    return render(request,'errors/404.html', {})

def error_500(request, *args, **argv):
    return render(request,'errors/500.html', {})

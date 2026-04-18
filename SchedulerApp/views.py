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

POPULATION_SIZE = 30
NUMB_OF_ELITE_SCHEDULES = 2
TOURNAMENT_SELECTION_SIZE = 8
MUTATION_RATE = 0.05
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
        self._rooms = Room.objects.all()
        self._meetingTimes = MeetingTime.objects.all()
        self._instructors = Instructor.objects.all()
        self._courses = Course.objects.all()
        self._depts = Department.objects.all()
        self._sections = Section.objects.all()

    def get_rooms(self):
        return self._rooms

    def get_instructors(self):
        return self._instructors

    def get_courses(self):
        return self._courses

    def get_depts(self):
        return self._depts

    def get_meetingTimes(self):
        return self._meetingTimes

    def get_sections(self):
        return self._sections


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

    def addCourse(self, data, course, courses, dept, section):
        newClass = Class(dept, section.section_id, course)

        newClass.set_meetingTime(
            data.get_meetingTimes()[random.randrange(0, len(data.get_meetingTimes()))])

        newClass.set_room(
            data.get_rooms()[random.randrange(0, len(data.get_rooms()))])

        crs_inst = course.instructors.all()
        newClass.set_instructor(
            crs_inst[random.randrange(0, len(crs_inst))])

        self._classes.append(newClass)

    def initialize(self):
        sections = Section.objects.all()
        for section in sections:
            dept = section.department
            n = section.num_class_in_week

            if n > len(data.get_meetingTimes()):
                n = len(data.get_meetingTimes())

            courses = dept.courses.all()
            if len(courses) > 0:  
                # Distribute courses evenly across available slots
                course_list = list(courses)
                for i in range(n // len(course_list)):
                    for course in course_list:
                        self.addCourse(data, course, course_list, dept, section)

                # Add remaining courses
                for course in course_list[:n % len(course_list)]:
                    self.addCourse(data, course, course_list, dept, section)

        return self

    def calculateFitness(self):
        self._numberOfConflicts = 0
        classes = self.getClasses()

        for i in range(len(classes)):
            # Get section strength from database
            try:
                section_obj = Section.objects.get(section_id=classes[i].section)
                section_strength = section_obj.strength
            except Section.DoesNotExist:
                section_strength = 30  # Default strength

            # Room capacity check: Room capacity must be >= section strength
            if classes[i].room and classes[i].room.seating_capacity < section_strength:
                self._numberOfConflicts += 1

            for j in range(i + 1, len(classes)):
                # Same course on same day
                if (classes[i].course.course_name == classes[j].course.course_name and \
                    str(classes[i].meeting_time).split()[1] == str(classes[j].meeting_time).split()[1]):
                    self._numberOfConflicts += 1

                # Teacher with lectures in different timetable at same time
                if (classes[i].section != classes[j].section and \
                    classes[i].meeting_time == classes[j].meeting_time and \
                    classes[i].instructor == classes[j].instructor):
                    self._numberOfConflicts += 1

                # Duplicate time in a department
                if (classes[i].section == classes[j].section and \
                    classes[i].meeting_time == classes[j].meeting_time):
                    self._numberOfConflicts += 1

                # Room conflict: Same room at same time slot
                if (classes[i].room == classes[j].room and \
                    classes[i].meeting_time == classes[j].meeting_time):
                    self._numberOfConflicts += 1

        # Calculate base fitness from conflicts (original formula)
        base_fitness = 1 / (self._numberOfConflicts + 1)
        
        # AI-BASED FACULTY PREFERENCE LEARNING INTEGRATION
        # Calculate preference score for the entire schedule
        try:
            preference_stats = calculate_schedule_preference_score(classes)
            preference_score = preference_stats['weighted_score']
            
            # Get current preference weight setting
            preference_weight = get_preference_weight()
            
            # Integrate preference into final fitness
            # Formula: Final Fitness = Base Fitness + (Preference Score * Weight * Scaling Factor)
            # The scaling factor ensures preference doesn't override hard constraints
            scaling_factor = base_fitness  # Scale preference impact by base fitness
            
            final_fitness = base_fitness + (preference_score * preference_weight * scaling_factor)
            
            return final_fitness
        except Exception as e:
            # If preference calculation fails, fall back to base fitness
            # This ensures the system remains functional even without ML data
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
    population = Population(POPULATION_SIZE)
    VARS['generationNum'] = 0
    VARS['terminateGens'] = False
    population.getSchedules().sort(key=lambda x: x.getFitness(), reverse=True)
    geneticAlgorithm = GeneticAlgorithm()
    schedule = population.getSchedules()[0]

    while (schedule.getFitness() != 1.0) and (VARS['generationNum'] < 100):
        if VARS['terminateGens']:
            return HttpResponse('')

        population = geneticAlgorithm.evolve(population)
        population.getSchedules().sort(key=lambda x: x.getFitness(), reverse=True)
        schedule = population.getSchedules()[0]
        VARS['generationNum'] += 1

        print(f'\n> Generation #{VARS["generationNum"]}, Fitness: {schedule.getFitness()}')

    generation_time = time.time() - start_time
    
    # Save the generated timetable to database
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

    return render(
        request, 'timetable.html', {
            'schedule': schedule.getClasses(),
            'sections': data.get_sections(),
            'times': data.get_meetingTimes(),
            'timeSlots': TIME_SLOTS,
            'weekDays': DAYS_OF_WEEK,
            'generation_info': {
                'batch_id': batch_id,
                'fitness': schedule.getFitness(),
                'generations': VARS['generationNum'],
                'time': round(generation_time, 2)
            }
        })


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
    View a stored timetable from database (FET-style grid)
    """
    from .timetable_utils import get_timetable_data, group_timetable_for_display
    
    # Get entries
    entries = get_timetable_data(batch_id=batch_id)
    
    # Group for display
    grouped_data = group_timetable_for_display(entries=entries)
    
    # Get all days and time slots for the grid
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    time_slots = list(MeetingTime.objects.values_list('time', flat=True).distinct().order_by('pid'))
    
    # Get statistics
    stats = get_statistics(batch_id=batch_id)
    
    return render(request, 'timetable_stored.html', {
        'grouped_data': grouped_data,
        'days': days_order,
        'time_slots': time_slots,
        'stats': stats,
        'batch_id': batch_id,
        'total_entries': entries.count()
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
        JSON with conflict summary
    """
    batch_id = request.GET.get('batch_id')
    
    engine = ConstraintEngine(batch_id)
    summary = engine.scan_all_conflicts(batch_id)
    
    return JsonResponse({
        'success': True,
        **summary
    })


@login_required
def conflict_log_view(request):
    """
    View to display the conflict log page with all conflict history.
    """
    from .models import ConflictLog, TimetableEntry
    
    # Get all conflicts
    conflicts = ConflictLog.objects.all().order_by('-detected_at')
    
    # Calculate statistics
    total_conflicts = conflicts.count()
    resolved_conflicts = conflicts.filter(status='resolved').count()
    pending_conflicts = conflicts.filter(status='pending').count()
    
    # Enrich conflict data with entry details
    enriched_conflicts = []
    for conflict in conflicts:
        try:
            entry = TimetableEntry.objects.get(entry_id=conflict.entry_id)
            conflict.entry_details = entry
        except TimetableEntry.DoesNotExist:
            conflict.entry_details = None
        enriched_conflicts.append(conflict)
    
    context = {
        'conflicts': enriched_conflicts,
        'total_conflicts': total_conflicts,
        'resolved_conflicts': resolved_conflicts,
        'pending_conflicts': pending_conflicts,
    }
    
    return render(request, 'conflict_log.html', context)


'''
Error pages
'''

def error_404(request, exception):
    return render(request,'errors/404.html', {})

def error_500(request, *args, **argv):
    return render(request,'errors/500.html', {})

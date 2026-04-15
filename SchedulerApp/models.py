from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save, post_delete


TIME_SLOTS = (
    ('8:45 - 9:45'  , '8:45 - 9:45'),
    ('10:00 - 11:00', '10:00 - 11:00'),
    ('11:00 - 12:00', '11:00 - 12:00'),
    ('1:00 - 2:00'  , '1:00 - 2:00'),
    ('2:15 - 3:15'  , '2:15 - 3:15'),
)

# TIME_SLOTS = (
#     ('9:30 - 10:30', '9:30 - 10:30'),
#     ('10:30 - 11:30', '10:30 - 11:30'),
#     ('11:30 - 12:30', '11:30 - 12:30'),
#     ('12:30 - 1:30', '12:30 - 1:30'),
#     ('2:30 - 3:30', '2:30 - 3:30'),
#     ('3:30 - 4:30', '3:30 - 4:30'),
#     ('4:30 - 5:30', '4:30 - 5:30'),
# )

DAYS_OF_WEEK = (
    ('Monday', 'Monday'),
    ('Tuesday', 'Tuesday'),
    ('Wednesday', 'Wednesday'),
    ('Thursday', 'Thursday'),
    ('Friday', 'Friday'),
)
    # ('Saturday', 'Saturday'),


class Room(models.Model):
    r_number = models.CharField(max_length=6)
    seating_capacity = models.IntegerField(default=0)
    room_type = models.CharField(max_length=20, default='Classroom', choices=[
        ('Classroom', 'Classroom'),
        ('Lab', 'Lab'),
        ('Computer Lab', 'Computer Lab'),
        ('AI Lab', 'AI Lab'),
        ('ML Lab', 'ML Lab'),
        ('DS Lab', 'DS Lab'),
    ])
    equipment_available = models.CharField(max_length=200, blank=True, help_text="Available equipment in this room")

    def __str__(self):
        return f'{self.r_number} ({self.room_type})'


class Instructor(models.Model):
    uid = models.CharField(max_length=6)
    name = models.CharField(max_length=25)
    specialization = models.CharField(max_length=50, blank=True, help_text="AI/ML specialization area")
    max_courses_per_semester = models.IntegerField(default=3, help_text="Maximum courses this instructor can handle")

    def __str__(self):
        return f'{self.uid} {self.name}'


class MeetingTime(models.Model):
    pid = models.CharField(max_length=4, primary_key=True)
    time = models.CharField(max_length=50,
                            choices=TIME_SLOTS,
                            default='11:30 - 12:30')
    day = models.CharField(max_length=15, choices=DAYS_OF_WEEK)

    def __str__(self):
        return f'{self.pid} {self.day} {self.time}'


class Course(models.Model):
    course_number = models.CharField(max_length=5, primary_key=True)
    course_name = models.CharField(max_length=40)
    course_type = models.CharField(max_length=20, default='Theory', choices=[
        ('Theory', 'Theory'),
        ('Lab', 'Lab'),
        ('Theory+Lab', 'Theory + Lab'),
    ])
    equipment_required = models.CharField(max_length=100, blank=True, help_text="Required equipment for AI/ML courses")
    instructors = models.ManyToManyField(Instructor)

    def __str__(self):
        return f'{self.course_number} {self.course_name}'


class Department(models.Model):
    dept_name = models.CharField(max_length=50)
    courses = models.ManyToManyField(Course)

    @property
    def get_courses(self):
        return self.courses

    def __str__(self):
        return self.dept_name


class Section(models.Model):
    section_id = models.CharField(max_length=25, primary_key=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    num_class_in_week = models.IntegerField(default=0)
    lectures_per_semester = models.IntegerField(default=0, help_text="Number of lectures per semester for this section")
    strength = models.IntegerField(default=30, help_text="Number of students in this section")
    course = models.ForeignKey(Course,
                               on_delete=models.CASCADE,
                               blank=True,
                               null=True)
    meeting_time = models.ForeignKey(MeetingTime,
                                     on_delete=models.CASCADE,
                                     blank=True,
                                     null=True)
    room = models.ForeignKey(Room,
                             on_delete=models.CASCADE,
                             blank=True,
                             null=True)
    instructor = models.ForeignKey(Instructor,
                                   on_delete=models.CASCADE,
                                   blank=True,
                                   null=True)

    def set_room(self, room):
        section = Section.objects.get(pk=self.section_id)
        section.room = room
        section.save()

    def set_meetingTime(self, meetingTime):
        section = Section.objects.get(pk=self.section_id)
        section.meeting_time = meetingTime
        section.save()

    def set_instructor(self, instructor):
        section = Section.objects.get(pk=self.section_id)
        section.instructor = instructor
        section.save()


# ==================== NEW MODELS FOR PDF EXPORT & FET-STYLE TIMETABLE ====================

class TimetableEntry(models.Model):
    """
    Stores a single entry in the generated timetable (FET-style)
    This model stores the GA-generated schedule permanently
    Enhanced for intelligent editing with conflict tracking and locking
    """
    ENTRY_TYPES = (
        ('auto', 'Auto Generated'),
        ('manual', 'Manual Entry'),
        ('hybrid', 'Hybrid (Auto + Manual Adjust)'),
    )
    
    entry_id = models.AutoField(primary_key=True)
    
    # References to existing models
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    meeting_time = models.ForeignKey(MeetingTime, on_delete=models.CASCADE)
    
    # Additional metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    generation_batch = models.CharField(max_length=50, default='default', help_text="Batch ID for this generation run")
    is_active = models.BooleanField(default=True, help_text="Is this entry currently active")
    
    # INTELLIGENT EDITING FIELDS
    entry_type = models.CharField(
        max_length=20, 
        choices=ENTRY_TYPES, 
        default='auto',
        help_text="How this entry was created"
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked entries are preserved during partial regeneration"
    )
    has_conflict = models.BooleanField(
        default=False,
        help_text="Whether this entry has a conflict with others"
    )
    conflict_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON field storing conflict information"
    )
    last_modified = models.DateTimeField(auto_now=True)
    modified_by = models.CharField(max_length=50, blank=True, null=True, help_text="User who last modified")
    
    # AI PREFERENCE SCORE (cached for performance)
    preference_score = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Cached preference score for this faculty-day-time combination"
    )
    
    class Meta:
        ordering = ['meeting_time__day', 'meeting_time__time', 'section__section_id']
        unique_together = [
            ['meeting_time', 'room'],  # Room can't have two classes at same time
            ['meeting_time', 'instructor'],  # Faculty can't teach two classes at same time
            ['meeting_time', 'section'],  # Section can't have two classes at same time
        ]
        indexes = [
            models.Index(fields=['generation_batch', 'is_active']),
            models.Index(fields=['has_conflict']),
            models.Index(fields=['is_locked']),
            models.Index(fields=['instructor', 'meeting_time']),
        ]
    
    def __str__(self):
        return f"{self.section.section_id} | {self.meeting_time} | {self.course.course_name}"
    
    @property
    def display_cell_content(self):
        """
        Returns formatted content for FET-style timetable cell
        Format: 
        4AIML-A1 - MLT LAB
        NS - LAB-415
        """
        lines = [
            f"{self.section.section_id} - {self.course.course_name}",
            f"{self.instructor.name} - {self.room.r_number}"
        ]
        return "\n".join(lines)
    
    @property
    def day(self):
        return self.meeting_time.day
    
    @property
    def time_slot(self):
        return self.meeting_time.time
    
    @property
    def status_indicator(self):
        """Returns status for UI indicators"""
        if self.has_conflict:
            return 'conflict'
        elif self.is_locked:
            return 'locked'
        elif self.entry_type == 'manual':
            return 'manual'
        return 'ok'
    
    def update_preference_score(self):
        """Update cached preference score based on AI model"""
        try:
            from .services.preference_model import predict_preference
            result = predict_preference(self.instructor.id, self.day, self.time_slot)
            self.preference_score = result.get('preference_score', 0.5)
            self.save(update_fields=['preference_score'])
        except Exception:
            pass  # Keep existing score if update fails


class ConflictLog(models.Model):
    """
    Tracks conflicts detected in the timetable for intelligent editing
    """
    CONFLICT_TYPES = (
        ('room_conflict', 'Room Double Booking'),
        ('faculty_conflict', 'Faculty Double Booking'),
        ('section_conflict', 'Section Double Booking'),
        ('capacity_violation', 'Room Capacity Insufficient'),
        ('same_course_same_day', 'Same Course Multiple Times Same Day'),
        ('consecutive_classes', 'Too Many Consecutive Classes'),
    )
    
    conflict_id = models.AutoField(primary_key=True)
    entry = models.ForeignKey(
        TimetableEntry, 
        on_delete=models.CASCADE,
        related_name='conflicts'
    )
    conflict_type = models.CharField(max_length=30, choices=CONFLICT_TYPES)
    message = models.TextField()
    
    # Conflicting with which other entry (if applicable)
    conflicting_entry = models.ForeignKey(
        TimetableEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conflicting_with'
    )
    
    # Conflict details
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    resolution_method = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('manual', 'Manual Fix'),
            ('auto_fix', 'Auto Fix'),
            ('regenerate', 'Full Regeneration'),
        ]
    )
    
    class Meta:
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['entry', 'is_resolved']),
            models.Index(fields=['conflict_type']),
        ]
    
    def __str__(self):
        return f"{self.conflict_type} - {self.entry}"
    
    def mark_resolved(self, method='manual'):
        """Mark this conflict as resolved"""
        from django.utils import timezone
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolution_method = method
        self.save()


class GenerationLog(models.Model):
    """
    Logs each timetable generation run for history tracking
    """
    batch_id = models.CharField(max_length=50, primary_key=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generation_time_seconds = models.FloatField(default=0.0)
    fitness_score = models.FloatField(default=0.0)
    total_entries = models.IntegerField(default=0)
    conflicts = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Only one generation should be active")
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"Batch {self.batch_id} - {self.generated_at.strftime('%Y-%m-%d %H:%M')}"


# ==================== AI-BASED FACULTY PREFERENCE LEARNING MODELS ====================

class HistoricalTimetableData(models.Model):
    """
    Stores historical timetable data for ML training.
    Each record represents one class assignment in a past timetable.
    """
    record_id = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='historical_assignments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='historical_assignments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='historical_assignments')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='historical_assignments')
    meeting_time = models.ForeignKey(MeetingTime, on_delete=models.CASCADE, related_name='historical_assignments')
    day = models.CharField(max_length=15, choices=DAYS_OF_WEEK)
    time_slot = models.CharField(max_length=50)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    source_generation_batch = models.CharField(max_length=50, blank=True, null=True, 
                                                help_text="Generation batch ID this data came from")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Historical Timetable Data'
        verbose_name_plural = 'Historical Timetable Data'
        
        # Create index for efficient querying during training
        indexes = [
            models.Index(fields=['instructor', 'day', 'time_slot']),
            models.Index(fields=['source_generation_batch']),
        ]
    
    def __str__(self):
        return f"{self.instructor.name} | {self.day} {self.time_slot} | {self.course.course_name}"


class FacultyPreference(models.Model):
    """
    Stores learned faculty preferences for time slots.
    This is populated by the ML model after training on historical data.
    """
    preference_id = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='preferences')
    
    # Preferred day and time
    preferred_day = models.CharField(max_length=15, choices=DAYS_OF_WEEK)
    preferred_time = models.CharField(max_length=50)
    
    # ML-derived preference score (0 to 1)
    preference_score = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="ML-learned preference score (0 = low preference, 1 = high preference)"
    )
    
    # Additional metadata
    confidence = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Model confidence in this prediction"
    )
    frequency_count = models.IntegerField(
        default=0,
        help_text="How many times instructor has been assigned this slot historically"
    )
    
    # Model versioning
    model_version = models.CharField(max_length=20, default='1.0', help_text="Version of ML model used")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['instructor', '-preference_score']
        verbose_name = 'Faculty Preference'
        verbose_name_plural = 'Faculty Preferences'
        
        # Ensure unique preferences per instructor/day/time combination
        unique_together = ['instructor', 'preferred_day', 'preferred_time']
        
        indexes = [
            models.Index(fields=['instructor', 'preferred_day']),
            models.Index(fields=['preference_score']),
        ]
    
    def __str__(self):
        return f"{self.instructor.name} prefers {self.preferred_day} {self.preferred_time} (score: {self.preference_score:.2f})"


class MLModelMetadata(models.Model):
    """
    Stores metadata about trained ML models for versioning and tracking.
    """
    model_id = models.AutoField(primary_key=True)
    model_version = models.CharField(max_length=20, unique=True)
    model_path = models.CharField(max_length=255, help_text="Path to saved model file")
    model_type = models.CharField(max_length=50, default='LogisticRegression', 
                                   choices=[
                                       ('LogisticRegression', 'Logistic Regression'),
                                       ('DecisionTree', 'Decision Tree'),
                                       ('RandomForest', 'Random Forest'),
                                   ])
    
    # Training metadata
    training_date = models.DateTimeField(auto_now_add=True)
    training_samples = models.IntegerField(default=0, help_text="Number of samples used for training")
    accuracy = models.FloatField(null=True, blank=True, help_text="Model accuracy on validation set")
    
    # Feature information
    feature_columns = models.JSONField(default=list, help_text="List of feature column names used")
    
    # Whether this is the currently active model
    is_active = models.BooleanField(default=False, help_text="Currently active model for predictions")
    
    class Meta:
        ordering = ['-training_date']
        verbose_name = 'ML Model Metadata'
        verbose_name_plural = 'ML Model Metadata'
    
    def __str__(self):
        return f"Model {self.model_version} ({self.model_type}) - {'Active' if self.is_active else 'Inactive'}"


'''
class Data(models.Manager):
    def __init__(self):
        self._rooms = Room.objects.all()
        self._meetingTimes = MeetingTime.objects.all()
        self._instructors = Instructor.objects.all()
        self._courses = Course.objects.all()
        self._depts = Department.objects.all()

    def get_rooms(self): return self._rooms

    def get_instructors(self): return self._instructors

    def get_courses(self): return self._courses

    def get_depts(self): return self._depts

    def get_meetingTimes(self): return self._meetingTimes

    def get_numberOfClasses(self): return self._numberOfClasses

'''

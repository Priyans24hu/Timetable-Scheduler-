"""
Comprehensive Database Models for FET-Style Timetable System
This module contains all models needed for storing and managing timetable data
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


# ==================== TIME SLOTS ====================
class TimeSlot(models.Model):
    """
    Represents a time slot in the timetable
    Example: Monday, 09:05-10:00
    """
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
    ]
    
    slot_id = models.CharField(max_length=10, primary_key=True, help_text="Unique identifier like 'M1', 'T2'")
    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    display_order = models.IntegerField(default=0, help_text="Order for displaying slots")
    
    class Meta:
        ordering = ['day', 'start_time']
        unique_together = ['day', 'start_time', 'end_time']
    
    def __str__(self):
        return f"{self.day} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"
    
    @property
    def time_range(self):
        return f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"


# ==================== SUBJECTS ====================
class Subject(models.Model):
    """
    Represents a subject/course in the curriculum
    """
    SUBJECT_TYPES = [
        ('Theory', 'Theory'),
        ('Lab', 'Lab'),
        ('Tutorial', 'Tutorial'),
        ('Project', 'Project'),
    ]
    
    code = models.CharField(max_length=20, primary_key=True, help_text="Subject code like 'CS301'")
    name = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=20, choices=SUBJECT_TYPES, default='Theory')
    credits = models.IntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(6)])
    semester = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(8)])
    
    class Meta:
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


# ==================== FACULTY ====================
class Faculty(models.Model):
    """
    Represents a faculty member/teacher
    """
    faculty_id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    specialization = models.CharField(max_length=100, blank=True)
    max_hours_per_week = models.IntegerField(default=20)
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Faculty'
    
    def __str__(self):
        return f"{self.faculty_id} - {self.name}"


# ==================== ROOMS ====================
class Room(models.Model):
    """
    Represents a classroom or lab
    """
    ROOM_TYPES = [
        ('Classroom', 'Classroom'),
        ('Lab', 'Lab'),
        ('Seminar Hall', 'Seminar Hall'),
        ('Workshop', 'Workshop'),
    ]
    
    room_number = models.CharField(max_length=20, primary_key=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='Classroom')
    capacity = models.IntegerField(default=40, validators=[MinValueValidator(10)])
    building = models.CharField(max_length=50, blank=True)
    floor = models.IntegerField(default=1)
    equipment = models.TextField(blank=True, help_text="Available equipment")
    
    class Meta:
        ordering = ['room_number']
    
    def __str__(self):
        return f"{self.room_number} ({self.room_type})"


# ==================== SECTIONS ====================
class Section(models.Model):
    """
    Represents a student section (e.g., 4AIML-A1, SE-B)
    """
    section_id = models.CharField(max_length=20, primary_key=True, help_text="Section code like '4AIML-A1'")
    name = models.CharField(max_length=50)
    semester = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(8)])
    department = models.CharField(max_length=50, blank=True)
    strength = models.IntegerField(default=40, validators=[MinValueValidator(1)])
    
    # For lab splitting (A1, A2, A3)
    parent_section = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='sub_sections',
        help_text="Parent section for lab batches"
    )
    batch_number = models.IntegerField(default=1, help_text="Batch number for labs (1, 2, 3)")
    
    class Meta:
        ordering = ['section_id']
    
    def __str__(self):
        return f"{self.section_id} - {self.name}"
    
    @property
    def is_lab_batch(self):
        return self.parent_section is not None


# ==================== TIMETABLE ENTRY ====================
class TimetableEntry(models.Model):
    """
    Stores a single entry in the generated timetable
    This is the main table that stores the GA-generated schedule
    """
    entry_id = models.AutoField(primary_key=True)
    
    # Foreign Keys to related entities
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    
    # Additional metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    generation_batch = models.CharField(max_length=50, help_text="Batch ID for this generation run")
    is_lab_session = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['timeslot__day', 'timeslot__start_time', 'section__section_id']
        unique_together = [
            ['timeslot', 'room'],  # Room can't have two classes at same time
            ['timeslot', 'faculty'],  # Faculty can't teach two classes at same time
            ['timeslot', 'section'],  # Section can't have two classes at same time
        ]
    
    def __str__(self):
        return f"{self.section.section_id} | {self.timeslot} | {self.subject.code} | {self.room.room_number}"
    
    @property
    def display_format(self):
        """
        Returns formatted string for display in timetable cell
        Format: "4AIML-A1 - MLT LAB\nNS - LAB-415"
        """
        lines = [
            f"{self.section.section_id} - {self.subject.name}",
            f"{self.faculty.name[:2]} - {self.room.room_number}"
        ]
        return "\n".join(lines)


# ==================== GENERATION LOG ====================
class GenerationLog(models.Model):
    """
    Logs each timetable generation run
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


# ==================== CONFLICT RECORD ====================
class ConflictRecord(models.Model):
    """
    Records any conflicts found during generation
    """
    CONFLICT_TYPES = [
        ('ROOM', 'Room Conflict'),
        ('FACULTY', 'Faculty Conflict'),
        ('SECTION', 'Section Conflict'),
        ('CAPACITY', 'Capacity Mismatch'),
    ]
    
    generation = models.ForeignKey(GenerationLog, on_delete=models.CASCADE)
    conflict_type = models.CharField(max_length=20, choices=CONFLICT_TYPES)
    description = models.TextField()
    entry1 = models.ForeignKey(TimetableEntry, on_delete=models.CASCADE, related_name='conflict_1')
    entry2 = models.ForeignKey(TimetableEntry, on_delete=models.CASCADE, related_name='conflict_2', null=True, blank=True)
    
    def __str__(self):
        return f"{self.conflict_type}: {self.description[:50]}"

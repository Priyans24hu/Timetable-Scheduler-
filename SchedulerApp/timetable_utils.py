"""
Timetable Utilities for Saving and Managing Generated Schedules
This module provides functions to:
1. Save generated timetable to database
2. Retrieve timetable data with grouping
3. Generate PDF exports
"""

import uuid
import time
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from collections import defaultdict
from .models import (
    TimetableEntry, GenerationLog, Section, Course, Instructor, Room, MeetingTime,
    HistoricalTimetableData
)


def save_generated_timetable(schedule_classes, fitness_score=0.0, generation_time=0.0):
    """
    Save a generated timetable from GA to the database
    
    Args:
        schedule_classes: List of Class objects from the genetic algorithm
        fitness_score: Fitness score of the generated schedule
        generation_time: Time taken to generate (in seconds)
    
    Returns:
        batch_id: Unique identifier for this generation
    """
    batch_id = f"GEN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    with transaction.atomic():
        # Mark previous generations as inactive
        TimetableEntry.objects.filter(is_active=True).update(is_active=False)
        GenerationLog.objects.filter(is_active=True).update(is_active=False)
        
        # Create new generation log
        total_entries = 0
        conflicts = 0
        
        for class_obj in schedule_classes:
            try:
                # Get or create the related objects
                section = Section.objects.get(section_id=class_obj.section)
                course = class_obj.course
                instructor = class_obj.instructor
                room = class_obj.room
                meeting_time = class_obj.meeting_time
                
                # Create timetable entry
                entry = TimetableEntry.objects.create(
                    section=section,
                    course=course,
                    instructor=instructor,
                    room=room,
                    meeting_time=meeting_time,
                    generation_batch=batch_id,
                    is_active=True
                )
                total_entries += 1
                
            except Exception as e:
                conflicts += 1
                print(f"Error saving entry: {e}")
                continue
        
        # Create generation log
        GenerationLog.objects.create(
            batch_id=batch_id,
            generation_time_seconds=generation_time,
            fitness_score=fitness_score,
            total_entries=total_entries,
            conflicts=conflicts,
            is_active=True,
        )
        
        # SAVE HISTORICAL DATA FOR ML TRAINING
        # This data will be used to train the preference learning model
        for class_obj in schedule_classes:
            try:
                section = Section.objects.get(section_id=class_obj.section)
                course = class_obj.course
                instructor = class_obj.instructor
                room = class_obj.room
                meeting_time = class_obj.meeting_time
                
                # Create historical data record
                HistoricalTimetableData.objects.create(
                    instructor=instructor,
                    course=course,
                    section=section,
                    room=room,
                    meeting_time=meeting_time,
                    day=meeting_time.day,
                    time_slot=meeting_time.time,
                    source_generation_batch=batch_id
                )
            except Exception as e:
                # Log but don't fail if historical data saving fails
                print(f"Warning: Could not save historical data for class: {e}")
                continue
    
    return batch_id


def get_timetable_data(batch_id=None, section_id=None, day=None):
    """
    Retrieve timetable data with optional filtering
    
    Args:
        batch_id: Filter by generation batch (None = use active)
        section_id: Filter by specific section
        day: Filter by day (Monday, Tuesday, etc.)
    
    Returns:
        QuerySet of TimetableEntry objects
    """
    queryset = TimetableEntry.objects.select_related(
        'section', 'course', 'instructor', 'room', 'meeting_time'
    )
    
    if batch_id:
        queryset = queryset.filter(generation_batch=batch_id, is_active=True)
    else:
        # Get from the most recent active generation
        latest_gen = GenerationLog.objects.filter(is_active=True).first()
        if latest_gen:
            queryset = queryset.filter(generation_batch=latest_gen.batch_id, is_active=True)
        else:
            queryset = queryset.filter(is_active=True)
    
    if section_id:
        queryset = queryset.filter(section__section_id=section_id)
    
    if day:
        queryset = queryset.filter(meeting_time__day=day)
    
    return queryset.order_by('meeting_time__day', 'meeting_time__time', 'section__section_id')


def group_timetable_for_display(entries=None, batch_id=None):
    """
    Group timetable entries for FET-style display
    Structure: Day -> Time Slot -> [List of entries]
    
    Args:
        entries: QuerySet or list of TimetableEntry objects (optional)
        batch_id: Generation batch ID (if entries not provided)
    
    Returns:
        Dictionary: {
            'Monday': {
                '8:45 - 9:45': [entry1, entry2, ...],
                '10:00 - 11:00': [...]
            },
            'Tuesday': {...}
        }
    """
    if entries is None:
        entries = get_timetable_data(batch_id=batch_id)
    
    # Initialize structure
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    grouped = {day: {} for day in days_order}
    
    # Get all unique time slots
    time_slots = MeetingTime.objects.values_list('time', flat=True).distinct().order_by('pid')
    
    for entry in entries:
        day = entry.meeting_time.day
        time = entry.meeting_time.time
        
        if time not in grouped[day]:
            grouped[day][time] = []
        
        grouped[day][time].append(entry)
    
    return grouped


def get_timetable_grid_for_pdf(batch_id=None):
    """
    Prepare data for PDF generation in grid format
    Returns data structured for template rendering
    
    Returns:
        Dictionary with:
        - days: List of days
        - time_slots: List of time slots
        - grid: 2D array [time_slot][day] = list of entries
    """
    entries = get_timetable_data(batch_id=batch_id)
    
    # Get unique days and time slots
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    time_slots = list(MeetingTime.objects.values_list('time', flat=True).distinct().order_by('pid'))
    
    # Create grid
    grid = {}
    for time_slot in time_slots:
        grid[time_slot] = {}
        for day in days:
            grid[time_slot][day] = []
    
    # Populate grid
    for entry in entries:
        day = entry.meeting_time.day
        time = entry.meeting_time.time
        if time in grid and day in grid[time]:
            grid[time][day].append(entry)
    
    return {
        'days': days,
        'time_slots': time_slots,
        'grid': grid
    }


def get_section_wise_timetable(section_id, batch_id=None):
    """
    Get timetable for a specific section organized by day and time
    
    Args:
        section_id: Section ID (e.g., '4AIML-A1')
        batch_id: Generation batch (optional)
    
    Returns:
        Dictionary: {day: {time_slot: entry}}
    """
    entries = get_timetable_data(batch_id=batch_id, section_id=section_id)
    
    timetable = defaultdict(dict)
    
    for entry in entries:
        day = entry.meeting_time.day
        time = entry.meeting_time.time
        timetable[day][time] = entry
    
    return dict(timetable)


def get_generation_history():
    """
    Get list of all generation runs
    
    Returns:
        List of GenerationLog objects
    """
    return GenerationLog.objects.all().order_by('-generated_at')


def activate_generation(batch_id):
    """
    Activate a specific generation batch and deactivate others
    
    Args:
        batch_id: Batch ID to activate
    """
    with transaction.atomic():
        GenerationLog.objects.filter(is_active=True).update(is_active=False)
        TimetableEntry.objects.filter(is_active=True).update(is_active=False)
        
        GenerationLog.objects.filter(batch_id=batch_id).update(is_active=True)
        TimetableEntry.objects.filter(generation_batch=batch_id).update(is_active=True)


def delete_generation(batch_id):
    """
    Delete a generation and all its entries
    
    Args:
        batch_id: Batch ID to delete
    """
    with transaction.atomic():
        TimetableEntry.objects.filter(generation_batch=batch_id).delete()
        GenerationLog.objects.filter(batch_id=batch_id).delete()


def get_statistics(batch_id=None):
    """
    Get statistics about a generation
    
    Returns:
        Dictionary with statistics
    """
    if batch_id:
        entries = TimetableEntry.objects.filter(generation_batch=batch_id)
        gen_log = GenerationLog.objects.filter(batch_id=batch_id).first()
    else:
        entries = TimetableEntry.objects.filter(is_active=True)
        gen_log = GenerationLog.objects.filter(is_active=True).first()
    
    stats = {
        'total_entries': entries.count(),
        'total_sections': entries.values('section').distinct().count(),
        'total_courses': entries.values('course').distinct().count(),
        'total_faculty': entries.values('instructor').distinct().count(),
        'total_rooms_used': entries.values('room').distinct().count(),
        'fitness_score': gen_log.fitness_score if gen_log else 0.0,
        'generation_time': gen_log.generation_time_seconds if gen_log else 0.0,
        'conflicts': gen_log.conflicts if gen_log else 0,
    }
    
    return stats

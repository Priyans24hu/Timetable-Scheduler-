"""
Constraint Engine for Intelligent Timetable Editing

This module provides:
- Hard constraint validation (faculty, room, section conflicts)
- Soft constraint checking (preferences, workload balance)
- Real-time conflict detection
- Constraint violation reporting with detailed messages
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from django.db.models import Q

from ..models import (
    TimetableEntry, Instructor, Room, MeetingTime, 
    Section, ConflictLog, Course
)


class ConstraintType(Enum):
    """Types of constraints in the system"""
    HARD = "hard"
    SOFT = "soft"


class ViolationType(Enum):
    """Types of constraint violations"""
    ROOM_CONFLICT = "room_conflict"
    FACULTY_CONFLICT = "faculty_conflict"
    SECTION_CONFLICT = "section_conflict"
    CAPACITY_VIOLATION = "capacity_violation"
    SAME_COURSE_SAME_DAY = "same_course_same_day"
    CONSECUTIVE_CLASSES = "consecutive_classes"
    FACULTY_PREFERENCE_LOW = "faculty_preference_low"
    WORKLOAD_IMBALANCE = "workload_imbalance"


@dataclass
class ConstraintViolation:
    """Represents a single constraint violation"""
    violation_type: ViolationType
    message: str
    severity: str  # 'critical', 'warning', 'info'
    entry_id: Optional[int] = None
    conflicting_entry_id: Optional[int] = None
    details: Dict[str, Any] = None
    
    def to_dict(self) -> Dict:
        return {
            'type': self.violation_type.value,
            'message': self.message,
            'severity': self.severity,
            'entry_id': self.entry_id,
            'conflicting_entry_id': self.conflicting_entry_id,
            'details': self.details or {}
        }


class ConstraintEngine:
    """
    Core constraint checking engine for timetable validation.
    Provides both hard and soft constraint validation.
    """
    
    def __init__(self, batch_id: Optional[str] = None):
        """
        Initialize constraint engine.
        
        Args:
            batch_id: Optional batch ID to check against specific generation
        """
        self.batch_id = batch_id
        self.violations: List[ConstraintViolation] = []
        self._cache = {}
    
    def _get_entries_to_check(self, exclude_entry_id: Optional[int] = None) -> List[TimetableEntry]:
        """Get active entries for conflict checking"""
        queryset = TimetableEntry.objects.filter(is_active=True)
        
        if self.batch_id:
            queryset = queryset.filter(generation_batch=self.batch_id)
        
        if exclude_entry_id:
            queryset = queryset.exclude(entry_id=exclude_entry_id)
        
        return list(queryset.select_related(
            'instructor', 'room', 'section', 'meeting_time', 'course'
        ))
    
    def check_hard_constraints(
        self, 
        entry_data: Dict[str, any],
        exclude_entry_id: Optional[int] = None
    ) -> List[ConstraintViolation]:
        """
        Check hard constraints that must not be violated.
        
        Args:
            entry_data: Dictionary with entry information
                Required: instructor_id, room_id, section_id, meeting_time_id
                Optional: course_id
            exclude_entry_id: Exclude this entry from conflict check (for updates)
            
        Returns:
            List of hard constraint violations (empty if all ok)
        """
        violations = []
        
        # Extract IDs from entry data
        instructor_id = entry_data.get('instructor_id')
        room_id = entry_data.get('room_id')
        section_id = entry_data.get('section_id')
        meeting_time_id = entry_data.get('meeting_time_id')
        course_id = entry_data.get('course_id')
        
        if not all([instructor_id, room_id, section_id, meeting_time_id]):
            violations.append(ConstraintViolation(
                violation_type=ViolationType.FACULTY_CONFLICT,
                message="Missing required fields for conflict check",
                severity='critical',
                details={'missing_fields': entry_data}
            ))
            return violations
        
        # Get the meeting time object
        try:
            meeting_time = MeetingTime.objects.get(pk=meeting_time_id)
        except MeetingTime.DoesNotExist:
            violations.append(ConstraintViolation(
                violation_type=ViolationType.FACULTY_CONFLICT,
                message=f"Invalid meeting time ID: {meeting_time_id}",
                severity='critical'
            ))
            return violations
        
        # Get existing entries to check against
        existing_entries = self._get_entries_to_check(exclude_entry_id)
        
        # Check 1: Faculty Double Booking
        faculty_conflict = self._check_faculty_conflict(
            instructor_id, meeting_time, existing_entries
        )
        if faculty_conflict:
            violations.append(faculty_conflict)
        
        # Check 2: Room Double Booking
        room_conflict = self._check_room_conflict(
            room_id, meeting_time, existing_entries
        )
        if room_conflict:
            violations.append(room_conflict)
        
        # Check 3: Section Double Booking
        section_conflict = self._check_section_conflict(
            section_id, meeting_time, existing_entries
        )
        if section_conflict:
            violations.append(section_conflict)
        
        # Check 4: Room Capacity
        capacity_violation = self._check_room_capacity(
            room_id, section_id
        )
        if capacity_violation:
            violations.append(capacity_violation)
        
        # Check 5: Same Course Same Day (if course_id provided)
        if course_id:
            same_course_violation = self._check_same_course_same_day(
                course_id, meeting_time, existing_entries
            )
            if same_course_violation:
                violations.append(same_course_violation)
        
        return violations
    
    def _check_faculty_conflict(
        self,
        instructor_id: int,
        meeting_time: MeetingTime,
        existing_entries: List[TimetableEntry]
    ) -> Optional[ConstraintViolation]:
        """Check if faculty is already teaching at this time"""
        for entry in existing_entries:
            if (entry.instructor_id == instructor_id and 
                entry.meeting_time_id == meeting_time.pk):
                return ConstraintViolation(
                    violation_type=ViolationType.FACULTY_CONFLICT,
                    message=(f"Faculty {entry.instructor.name} is already teaching "
                            f"{entry.course.course_name} for {entry.section.section_id} "
                            f"at {meeting_time.day} {meeting_time.time}"),
                    severity='critical',
                    entry_id=None,  # New entry
                    conflicting_entry_id=entry.entry_id,
                    details={
                        'faculty_name': entry.instructor.name,
                        'existing_course': entry.course.course_name,
                        'existing_section': entry.section.section_id,
                        'day': meeting_time.day,
                        'time': meeting_time.time
                    }
                )
        return None
    
    def _check_room_conflict(
        self,
        room_id: int,
        meeting_time: MeetingTime,
        existing_entries: List[TimetableEntry]
    ) -> Optional[ConstraintViolation]:
        """Check if room is already occupied at this time"""
        for entry in existing_entries:
            if (entry.room_id == room_id and 
                entry.meeting_time_id == meeting_time.pk):
                return ConstraintViolation(
                    violation_type=ViolationType.ROOM_CONFLICT,
                    message=(f"Room {entry.room.r_number} is already occupied by "
                            f"{entry.course.course_name} ({entry.section.section_id}) "
                            f"at {meeting_time.day} {meeting_time.time}"),
                    severity='critical',
                    entry_id=None,
                    conflicting_entry_id=entry.entry_id,
                    details={
                        'room_number': entry.room.r_number,
                        'existing_course': entry.course.course_name,
                        'existing_section': entry.section.section_id,
                        'day': meeting_time.day,
                        'time': meeting_time.time
                    }
                )
        return None
    
    def _check_section_conflict(
        self,
        section_id: int,
        meeting_time: MeetingTime,
        existing_entries: List[TimetableEntry]
    ) -> Optional[ConstraintViolation]:
        """Check if section already has a class at this time"""
        for entry in existing_entries:
            if (entry.section_id == section_id and 
                entry.meeting_time_id == meeting_time.pk):
                return ConstraintViolation(
                    violation_type=ViolationType.SECTION_CONFLICT,
                    message=(f"Section {entry.section.section_id} already has "
                            f"{entry.course.course_name} at "
                            f"{meeting_time.day} {meeting_time.time}"),
                    severity='critical',
                    entry_id=None,
                    conflicting_entry_id=entry.entry_id,
                    details={
                        'section_id': entry.section.section_id,
                        'existing_course': entry.course.course_name,
                        'day': meeting_time.day,
                        'time': meeting_time.time
                    }
                )
        return None
    
    def _check_room_capacity(
        self,
        room_id: int,
        section_id: int
    ) -> Optional[ConstraintViolation]:
        """Check if room capacity is sufficient for section strength"""
        try:
            room = Room.objects.get(pk=room_id)
            section = Section.objects.get(pk=section_id)
            
            if room.seating_capacity < section.strength:
                return ConstraintViolation(
                    violation_type=ViolationType.CAPACITY_VIOLATION,
                    message=(f"Room {room.r_number} capacity ({room.seating_capacity}) "
                            f"is less than section {section.section_id} strength "
                            f"({section.strength})"),
                    severity='critical',
                    details={
                        'room_number': room.r_number,
                        'room_capacity': room.seating_capacity,
                        'section_id': section.section_id,
                        'section_strength': section.strength,
                        'shortfall': section.strength - room.seating_capacity
                    }
                )
        except (Room.DoesNotExist, Section.DoesNotExist):
            return ConstraintViolation(
                violation_type=ViolationType.CAPACITY_VIOLATION,
                message="Invalid room or section ID for capacity check",
                severity='warning'
            )
        return None
    
    def _check_same_course_same_day(
        self,
        course_id: int,
        meeting_time: MeetingTime,
        existing_entries: List[TimetableEntry]
    ) -> Optional[ConstraintViolation]:
        """Check if same course is scheduled multiple times on same day"""
        for entry in existing_entries:
            if (entry.course_id == course_id and 
                entry.meeting_time.day == meeting_time.day):
                return ConstraintViolation(
                    violation_type=ViolationType.SAME_COURSE_SAME_DAY,
                    message=(f"Course {entry.course.course_name} is already scheduled "
                            f"on {meeting_time.day} for {entry.section.section_id} "
                            f"at {entry.meeting_time.time}"),
                    severity='warning',  # Soft constraint
                    conflicting_entry_id=entry.entry_id,
                    details={
                        'course_name': entry.course.course_name,
                        'day': meeting_time.day,
                        'existing_time': entry.meeting_time.time
                    }
                )
        return None
    
    def check_soft_constraints(
        self,
        entry_data: Dict[str, any],
        exclude_entry_id: Optional[int] = None
    ) -> List[ConstraintViolation]:
        """
        Check soft constraints (preferences, optimization goals).
        These are warnings, not critical errors.
        
        Args:
            entry_data: Dictionary with entry information
            exclude_entry_id: Exclude this entry from checks
            
        Returns:
            List of soft constraint violations (warnings)
        """
        violations = []
        
        instructor_id = entry_data.get('instructor_id')
        meeting_time_id = entry_data.get('meeting_time_id')
        
        # Check faculty preference (if AI preference learning available)
        if instructor_id and meeting_time_id:
            preference_violation = self._check_faculty_preference(
                instructor_id, meeting_time_id
            )
            if preference_violation:
                violations.append(preference_violation)
        
        # Check consecutive classes
        if instructor_id and meeting_time_id:
            consecutive_violation = self._check_consecutive_classes(
                instructor_id, meeting_time_id, exclude_entry_id
            )
            if consecutive_violation:
                violations.append(consecutive_violation)
        
        return violations
    
    def _check_faculty_preference(
        self,
        instructor_id: int,
        meeting_time_id: int
    ) -> Optional[ConstraintViolation]:
        """Check if time slot matches faculty preference (AI-based)"""
        try:
            from .preference_model import predict_preference
            meeting_time = MeetingTime.objects.get(pk=meeting_time_id)
            
            result = predict_preference(instructor_id, meeting_time.day, meeting_time.time)
            score = result.get('preference_score', 0.5)
            
            if score < 0.3:  # Low preference threshold
                return ConstraintViolation(
                    violation_type=ViolationType.FACULTY_PREFERENCE_LOW,
                    message=(f"This time slot has low preference score ({score:.2f}) "
                            f"for the selected faculty"),
                    severity='warning',
                    details={
                        'preference_score': score,
                        'confidence': result.get('confidence', 0),
                        'day': meeting_time.day,
                        'time': meeting_time.time
                    }
                )
        except Exception:
            pass  # Don't fail if preference checking fails
        
        return None
    
    def _check_consecutive_classes(
        self,
        instructor_id: int,
        meeting_time_id: int,
        exclude_entry_id: Optional[int] = None
    ) -> Optional[ConstraintViolation]:
        """Check if faculty has too many consecutive classes"""
        try:
            meeting_time = MeetingTime.objects.get(pk=meeting_time_id)
            
            # Get faculty's existing classes on this day
            same_day_entries = TimetableEntry.objects.filter(
                instructor_id=instructor_id,
                meeting_time__day=meeting_time.day,
                is_active=True
            ).exclude(entry_id=exclude_entry_id or -1)
            
            # If already has 3+ classes this day, warn about workload
            if same_day_entries.count() >= 3:
                return ConstraintViolation(
                    violation_type=ViolationType.CONSECUTIVE_CLASSES,
                    message=(f"Faculty already has {same_day_entries.count()} classes "
                            f"scheduled on {meeting_time.day}. Adding more may cause "
                            f"excessive workload."),
                    severity='warning',
                    details={
                        'day': meeting_time.day,
                        'existing_classes': same_day_entries.count(),
                        'existing_entries': [
                            {'course': e.course.course_name, 'time': e.meeting_time.time}
                            for e in same_day_entries[:5]
                        ]
                    }
                )
        except Exception:
            pass
        
        return None
    
    def check_all_constraints(
        self,
        entry_data: Dict[str, any],
        exclude_entry_id: Optional[int] = None
    ) -> Dict[str, List[ConstraintViolation]]:
        """
        Check both hard and soft constraints.
        
        Returns:
            Dictionary with 'hard' and 'soft' violation lists
        """
        return {
            'hard': self.check_hard_constraints(entry_data, exclude_entry_id),
            'soft': self.check_soft_constraints(entry_data, exclude_entry_id)
        }
    
    def has_conflicts(
        self,
        entry_data: Dict[str, any],
        exclude_entry_id: Optional[int] = None
    ) -> bool:
        """Quick check if entry has any hard constraint violations"""
        hard_violations = self.check_hard_constraints(entry_data, exclude_entry_id)
        return len(hard_violations) > 0
    
    def validate_entry_update(
        self,
        entry: TimetableEntry,
        new_data: Dict[str, any]
    ) -> Dict[str, List[ConstraintViolation]]:
        """
        Validate an update to an existing entry.
        
        Args:
            entry: Existing TimetableEntry being updated
            new_data: Dictionary with new values (instructor_id, room_id, etc.)
            
        Returns:
            Dictionary with 'hard' and 'soft' violations
        """
        # Build complete entry data from existing + new values
        entry_data = {
            'instructor_id': new_data.get('instructor_id', entry.instructor_id),
            'room_id': new_data.get('room_id', entry.room_id),
            'section_id': new_data.get('section_id', entry.section_id),
            'meeting_time_id': new_data.get('meeting_time_id', entry.meeting_time_id),
            'course_id': new_data.get('course_id', entry.course_id),
        }
        
        return self.check_all_constraints(entry_data, exclude_entry_id=entry.entry_id)
    
    def scan_all_conflicts(self, batch_id: Optional[str] = None) -> Dict[str, any]:
        """
        Scan entire timetable for all conflicts.
        
        Returns:
            Summary of all conflicts found
        """
        if batch_id:
            entries = TimetableEntry.objects.filter(
                generation_batch=batch_id, is_active=True
            )
        else:
            entries = TimetableEntry.objects.filter(is_active=True)
        
        entries = entries.select_related(
            'instructor', 'room', 'section', 'meeting_time', 'course'
        )
        
        all_violations = []
        conflict_entries = []
        
        for entry in entries:
            entry_data = {
                'instructor_id': entry.instructor_id,
                'room_id': entry.room_id,
                'section_id': entry.section_id,
                'meeting_time_id': entry.meeting_time_id,
                'course_id': entry.course_id,
            }
            
            violations = self.check_hard_constraints(
                entry_data, exclude_entry_id=entry.entry_id
            )
            
            if violations:
                all_violations.extend(violations)
                conflict_entries.append(entry.entry_id)
        
        return {
            'total_entries': entries.count(),
            'conflict_count': len(set(conflict_entries)),
            'violation_count': len(all_violations),
            'violations': [v.to_dict() for v in all_violations],
            'conflict_entry_ids': list(set(conflict_entries))
        }


def check_conflict_api(entry_data: Dict[str, any]) -> Dict[str, any]:
    """
    API-friendly wrapper for conflict checking.
    
    Args:
        entry_data: Dictionary with entry information
        
    Returns:
        Standardized API response
    """
    engine = ConstraintEngine()
    
    hard_violations = engine.check_hard_constraints(entry_data)
    soft_violations = engine.check_soft_constraints(entry_data)
    
    has_conflict = len(hard_violations) > 0
    
    return {
        'has_conflict': has_conflict,
        'can_save': len(hard_violations) == 0,  # Can save if no hard conflicts
        'conflicts': {
            'hard': [v.to_dict() for v in hard_violations],
            'soft': [v.to_dict() for v in soft_violations],
        },
        'summary': {
            'hard_count': len(hard_violations),
            'soft_count': len(soft_violations),
            'total_issues': len(hard_violations) + len(soft_violations)
        }
    }


def validate_existing_entries(batch_id: Optional[str] = None) -> Dict[str, any]:
    """
    Validate all existing entries and update conflict flags.
    
    Returns:
        Validation report
    """
    engine = ConstraintEngine(batch_id)
    
    if batch_id:
        entries = TimetableEntry.objects.filter(
            generation_batch=batch_id, is_active=True
        )
    else:
        entries = TimetableEntry.objects.filter(is_active=True)
    
    results = {
        'total_checked': 0,
        'conflicts_found': 0,
        'entries_updated': []
    }
    
    for entry in entries:
        results['total_checked'] += 1
        
        entry_data = {
            'instructor_id': entry.instructor_id,
            'room_id': entry.room_id,
            'section_id': entry.section_id,
            'meeting_time_id': entry.meeting_time_id,
            'course_id': entry.course_id,
        }
        
        violations = engine.check_hard_constraints(
            entry_data, exclude_entry_id=entry.entry_id
        )
        
        # Update entry conflict status
        had_conflict = entry.has_conflict
        has_conflict_now = len(violations) > 0
        
        if has_conflict_now != had_conflict:
            entry.has_conflict = has_conflict_now
            entry.conflict_details = {
                'violations': [v.to_dict() for v in violations],
                'checked_at': str(datetime.now())
            }
            entry.save(update_fields=['has_conflict', 'conflict_details'])
            results['entries_updated'].append(entry.entry_id)
        
        if has_conflict_now:
            results['conflicts_found'] += 1
            
            # Log conflicts
            for violation in violations:
                ConflictLog.objects.get_or_create(
                    entry=entry,
                    conflict_type=violation.violation_type.value,
                    defaults={
                        'message': violation.message,
                        'conflicting_entry_id': violation.conflicting_entry_id,
                    }
                )
    
    return results


from datetime import datetime

"""
Suggestion Engine for Intelligent Timetable Editing

This module provides:
- Smart alternative suggestions when conflicts occur
- AI preference-based slot ranking
- Room and time slot recommendations
- Reason-based explanations for suggestions
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict
import random

from django.db.models import Q, Count

from ..models import (
    TimetableEntry, Instructor, Room, MeetingTime, 
    Section, Course, FacultyPreference
)
from .constraint_engine import ConstraintEngine, ConstraintViolation
from .preference_model import predict_preference, bulk_predict_preferences


@dataclass
class Suggestion:
    """Represents a single suggestion with scoring and reasoning"""
    suggestion_type: str  # 'room', 'time_slot', 'faculty', 'room_and_time'
    value: Any  # The suggested value (room object, meeting_time object, etc.)
    score: float  # Overall quality score (0-1)
    
    # Component scores
    availability_score: float  # How available is this option
    preference_score: float  # Faculty preference score (AI-based)
    balance_score: float  # Workload balance score
    
    # Explanation
    reason: str  # Human-readable explanation
    details: Dict[str, Any]  # Additional details
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response"""
        result = {
            'type': self.suggestion_type,
            'score': round(self.score, 3),
            'scores': {
                'availability': round(self.availability_score, 3),
                'preference': round(self.preference_score, 3),
                'balance': round(self.balance_score, 3),
            },
            'reason': self.reason,
            'details': self.details
        }
        
        # Add value details based on type
        if self.suggestion_type == 'room':
            result['room'] = {
                'id': self.value.id,
                'number': self.value.r_number,
                'capacity': self.value.seating_capacity,
                'type': self.value.room_type,
            }
        elif self.suggestion_type == 'time_slot':
            result['time_slot'] = {
                'id': self.value.pid,
                'day': self.value.day,
                'time': self.value.time,
            }
        elif self.suggestion_type == 'faculty':
            result['faculty'] = {
                'id': self.value.id,
                'name': self.value.name,
                'uid': self.value.uid,
            }
        elif self.suggestion_type == 'room_and_time':
            room, meeting_time = self.value
            result['room'] = {
                'id': room.id,
                'number': room.r_number,
                'capacity': room.seating_capacity,
            }
            result['time_slot'] = {
                'id': meeting_time.pid,
                'day': meeting_time.day,
                'time': meeting_time.time,
            }
        
        return result


class SuggestionEngine:
    """
    Intelligent suggestion engine for timetable editing.
    Provides context-aware alternatives with AI preference integration.
    """
    
    def __init__(self, batch_id: Optional[str] = None):
        self.batch_id = batch_id
        self.constraint_engine = ConstraintEngine(batch_id)
        self._availability_cache = {}
    
    def suggest_alternatives(
        self,
        entry_data: Dict[str, any],
        conflict_violations: List[ConstraintViolation],
        max_suggestions: int = 5
    ) -> Dict[str, List[Suggestion]]:
        """
        Generate smart alternatives based on conflict type.
        
        Args:
            entry_data: Current problematic entry data
            conflict_violations: List of detected conflicts
            max_suggestions: Maximum number of suggestions per type
            
        Returns:
            Dictionary with suggestions categorized by type
        """
        suggestions = {
            'rooms': [],
            'time_slots': [],
            'faculty': [],
            'combinations': [],
        }
        
        # Analyze what type of conflicts we have
        has_room_conflict = any(
            v.violation_type.value == 'room_conflict' 
            for v in conflict_violations
        )
        has_faculty_conflict = any(
            v.violation_type.value == 'faculty_conflict'
            for v in conflict_violations
        )
        has_section_conflict = any(
            v.violation_type.value == 'section_conflict'
            for v in conflict_violations
        )
        
        instructor_id = entry_data.get('instructor_id')
        room_id = entry_data.get('room_id')
        section_id = entry_data.get('section_id')
        meeting_time_id = entry_data.get('meeting_time_id')
        course_id = entry_data.get('course_id')
        
        # Generate suggestions based on conflict type
        if has_room_conflict or has_faculty_conflict or has_section_conflict:
            # Suggest alternative time slots
            suggestions['time_slots'] = self._suggest_time_slots(
                instructor_id=instructor_id,
                room_id=room_id,
                section_id=section_id,
                exclude_time_id=meeting_time_id,
                max_suggestions=max_suggestions
            )
            
            # Suggest alternative rooms
            suggestions['rooms'] = self._suggest_rooms(
                section_id=section_id,
                exclude_room_id=room_id,
                meeting_time_id=meeting_time_id,
                max_suggestions=max_suggestions
            )
        
        if has_faculty_conflict:
            # Suggest alternative faculty who can teach this course
            suggestions['faculty'] = self._suggest_alternative_faculty(
                course_id=course_id,
                exclude_faculty_id=instructor_id,
                meeting_time_id=meeting_time_id,
                max_suggestions=max_suggestions
            )
        
        # Always suggest some room+time combinations (best overall options)
        suggestions['combinations'] = self._suggest_room_time_combinations(
            instructor_id=instructor_id,
            section_id=section_id,
            exclude_room_id=room_id,
            exclude_time_id=meeting_time_id,
            max_suggestions=max_suggestions
        )
        
        return suggestions
    
    def _suggest_time_slots(
        self,
        instructor_id: int,
        room_id: int,
        section_id: int,
        exclude_time_id: Optional[int] = None,
        max_suggestions: int = 5
    ) -> List[Suggestion]:
        """Suggest alternative time slots with preference scoring"""
        suggestions = []
        
        # Get all available time slots
        all_time_slots = MeetingTime.objects.all()
        
        # Get instructor for preference checking
        try:
            instructor = Instructor.objects.get(pk=instructor_id)
        except Instructor.DoesNotExist:
            return suggestions
        
        for time_slot in all_time_slots:
            if exclude_time_id and time_slot.pid == exclude_time_id:
                continue
            
            # Check if this slot is available for all resources
            entry_data = {
                'instructor_id': instructor_id,
                'room_id': room_id,
                'section_id': section_id,
                'meeting_time_id': time_slot.pid,
            }
            
            # Check for conflicts
            has_conflict = self.constraint_engine.has_conflicts(entry_data)
            
            if has_conflict:
                continue
            
            # Get preference score from AI model
            pref_result = predict_preference(instructor_id, time_slot.day, time_slot.time)
            preference_score = pref_result.get('preference_score', 0.5)
            
            # Calculate availability score (higher if less crowded for faculty)
            faculty_classes = TimetableEntry.objects.filter(
                instructor_id=instructor_id,
                meeting_time__day=time_slot.day,
                is_active=True
            ).count()
            
            availability_score = max(0.3, 1.0 - (faculty_classes * 0.15))
            
            # Calculate balance score (prefer spreading classes)
            balance_score = 0.5  # Default
            if faculty_classes == 0:
                balance_score = 1.0  # Empty day is good for balance
            elif faculty_classes >= 3:
                balance_score = 0.3  # Too many classes this day
            
            # Overall score (weighted combination)
            overall_score = (
                preference_score * 0.4 +
                availability_score * 0.3 +
                balance_score * 0.3
            )
            
            # Generate reason
            reason_parts = []
            if preference_score > 0.7:
                reason_parts.append("High faculty preference")
            elif preference_score < 0.3:
                reason_parts.append("Low faculty preference")
            
            if availability_score > 0.8:
                reason_parts.append("Good availability")
            
            if faculty_classes == 0:
                reason_parts.append("No other classes this day")
            
            reason = "; ".join(reason_parts) if reason_parts else "Available slot"
            
            suggestion = Suggestion(
                suggestion_type='time_slot',
                value=time_slot,
                score=overall_score,
                availability_score=availability_score,
                preference_score=preference_score,
                balance_score=balance_score,
                reason=reason,
                details={
                    'faculty_classes_same_day': faculty_classes,
                    'confidence': pref_result.get('confidence', 0),
                    'source': pref_result.get('source', 'unknown')
                }
            )
            suggestions.append(suggestion)
        
        # Sort by score and limit
        suggestions.sort(key=lambda x: x.score, reverse=True)
        return suggestions[:max_suggestions]
    
    def _suggest_rooms(
        self,
        section_id: int,
        exclude_room_id: Optional[int] = None,
        meeting_time_id: Optional[int] = None,
        max_suggestions: int = 5
    ) -> List[Suggestion]:
        """Suggest alternative rooms that are available"""
        suggestions = []
        
        # Get section for capacity checking
        try:
            section = Section.objects.get(pk=section_id)
        except Section.DoesNotExist:
            return suggestions
        
        # Get all rooms with sufficient capacity
        rooms = Room.objects.filter(seating_capacity__gte=section.strength)
        
        for room in rooms:
            if exclude_room_id and room.id == exclude_room_id:
                continue
            
            # Check availability at specific time (if provided)
            if meeting_time_id:
                is_occupied = TimetableEntry.objects.filter(
                    room=room,
                    meeting_time_id=meeting_time_id,
                    is_active=True
                ).exists()
                
                if is_occupied:
                    availability_score = 0.0
                else:
                    availability_score = 1.0
            else:
                # General availability (how often is this room used)
                usage_count = TimetableEntry.objects.filter(
                    room=room, is_active=True
                ).count()
                availability_score = max(0.3, 1.0 - (usage_count * 0.05))
            
            # Capacity match score (better if closer to needs)
            capacity_diff = room.seating_capacity - section.strength
            if capacity_diff <= 5:
                capacity_score = 1.0  # Perfect fit
            elif capacity_diff <= 15:
                capacity_score = 0.7  # Good fit
            else:
                capacity_score = 0.5  # Room too big
            
            # Calculate overall score
            overall_score = (
                availability_score * 0.6 +
                capacity_score * 0.4
            )
            
            # Generate reason
            if availability_score == 1.0:
                reason = "Room is available at requested time"
            elif availability_score == 0.0:
                continue  # Skip occupied rooms
            else:
                reason = f"Room available; Capacity: {room.seating_capacity} seats"
            
            if capacity_score == 1.0:
                reason += " (Perfect size)"
            
            suggestion = Suggestion(
                suggestion_type='room',
                value=room,
                score=overall_score,
                availability_score=availability_score,
                preference_score=0.5,  # Neutral for rooms
                balance_score=capacity_score,
                reason=reason,
                details={
                    'capacity_match': capacity_diff,
                    'room_type': room.room_type
                }
            )
            suggestions.append(suggestion)
        
        # Sort by score
        suggestions.sort(key=lambda x: x.score, reverse=True)
        return suggestions[:max_suggestions]
    
    def _suggest_alternative_faculty(
        self,
        course_id: int,
        exclude_faculty_id: int,
        meeting_time_id: int,
        max_suggestions: int = 5
    ) -> List[Suggestion]:
        """Suggest alternative faculty who can teach this course"""
        suggestions = []
        
        try:
            course = Course.objects.get(pk=course_id)
            meeting_time = MeetingTime.objects.get(pk=meeting_time_id)
        except (Course.DoesNotExist, MeetingTime.DoesNotExist):
            return suggestions
        
        # Get all instructors who can teach this course
        eligible_instructors = course.instructors.exclude(id=exclude_faculty_id)
        
        for instructor in eligible_instructors:
            # Check if instructor is available at this time
            is_busy = TimetableEntry.objects.filter(
                instructor=instructor,
                meeting_time_id=meeting_time_id,
                is_active=True
            ).exists()
            
            if is_busy:
                availability_score = 0.0
            else:
                availability_score = 1.0
            
            # Check instructor workload
            current_load = TimetableEntry.objects.filter(
                instructor=instructor, is_active=True
            ).count()
            
            # Prefer instructors with lighter workload
            if current_load <= 3:
                balance_score = 1.0
            elif current_load <= 6:
                balance_score = 0.7
            else:
                balance_score = 0.4
            
            # Get preference for this slot
            pref_result = predict_preference(instructor.id, meeting_time.day, meeting_time.time)
            preference_score = pref_result.get('preference_score', 0.5)
            
            # Calculate overall score
            if availability_score == 0:
                overall_score = 0  # Not available, skip
            else:
                overall_score = (
                    availability_score * 0.5 +
                    balance_score * 0.3 +
                    preference_score * 0.2
                )
            
            if overall_score == 0:
                continue
            
            # Generate reason
            reason_parts = ["Can teach this course"]
            if availability_score == 1.0:
                reason_parts.append("Available at this time")
            if balance_score > 0.7:
                reason_parts.append(f"Light workload ({current_load} classes)")
            if preference_score > 0.7:
                reason_parts.append("Prefers this time slot")
            
            suggestion = Suggestion(
                suggestion_type='faculty',
                value=instructor,
                score=overall_score,
                availability_score=availability_score,
                preference_score=preference_score,
                balance_score=balance_score,
                reason="; ".join(reason_parts),
                details={
                    'current_workload': current_load,
                    'specialization': instructor.specialization
                }
            )
            suggestions.append(suggestion)
        
        # Sort by score
        suggestions.sort(key=lambda x: x.score, reverse=True)
        return suggestions[:max_suggestions]
    
    def _suggest_room_time_combinations(
        self,
        instructor_id: int,
        section_id: int,
        exclude_room_id: Optional[int] = None,
        exclude_time_id: Optional[int] = None,
        max_suggestions: int = 5
    ) -> List[Suggestion]:
        """Suggest best room+time combinations (highest overall score)"""
        suggestions = []
        
        # Get section for capacity
        try:
            section = Section.objects.get(pk=section_id)
        except Section.DoesNotExist:
            return suggestions
        
        # Get available rooms
        rooms = Room.objects.filter(seating_capacity__gte=section.strength)
        if exclude_room_id:
            rooms = rooms.exclude(id=exclude_room_id)
        
        # Get all time slots
        time_slots = MeetingTime.objects.all()
        if exclude_time_id:
            time_slots = time_slots.exclude(pid=exclude_time_id)
        
        # Try combinations
        for room in rooms[:10]:  # Limit rooms for performance
            for time_slot in time_slots:
                entry_data = {
                    'instructor_id': instructor_id,
                    'room_id': room.id,
                    'section_id': section_id,
                    'meeting_time_id': time_slot.pid,
                }
                
                # Skip if conflicts
                if self.constraint_engine.has_conflicts(entry_data):
                    continue
                
                # Get preference score
                pref_result = predict_preference(instructor_id, time_slot.day, time_slot.time)
                preference_score = pref_result.get('preference_score', 0.5)
                
                # Calculate scores
                availability_score = 1.0  # Already verified no conflicts
                
                # Capacity fit
                capacity_diff = room.seating_capacity - section.strength
                balance_score = 1.0 if capacity_diff <= 10 else 0.7
                
                # Overall score (emphasize preference)
                overall_score = (
                    preference_score * 0.5 +
                    availability_score * 0.3 +
                    balance_score * 0.2
                )
                
                # Generate reason
                reason_parts = ["No conflicts"]
                if preference_score > 0.7:
                    reason_parts.append("High faculty preference")
                if capacity_diff <= 5:
                    reason_parts.append("Perfect room size")
                
                suggestion = Suggestion(
                    suggestion_type='room_and_time',
                    value=(room, time_slot),
                    score=overall_score,
                    availability_score=availability_score,
                    preference_score=preference_score,
                    balance_score=balance_score,
                    reason="; ".join(reason_parts),
                    details={
                        'room_capacity': room.seating_capacity,
                        'section_strength': section.strength,
                        'day': time_slot.day,
                        'time': time_slot.time
                    }
                )
                suggestions.append(suggestion)
                
                if len(suggestions) >= max_suggestions * 3:
                    break
            
            if len(suggestions) >= max_suggestions * 3:
                break
        
        # Sort by score and return best
        suggestions.sort(key=lambda x: x.score, reverse=True)
        return suggestions[:max_suggestions]
    
    def get_preference_heatmap(
        self,
        instructor_id: int,
        days: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Generate preference heatmap for a faculty across all time slots.
        Useful for UI visualization.
        
        Returns:
            Dictionary with days as keys, list of slot preferences as values
        """
        if days is None:
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        
        time_slots = MeetingTime.objects.values_list('time', flat=True).distinct()
        
        heatmap = {}
        for day in days:
            day_slots = []
            for time in time_slots:
                result = predict_preference(instructor_id, day, time)
                
                # Determine color indicator
                score = result.get('preference_score', 0.5)
                if score >= 0.7:
                    indicator = 'green'  # Preferred
                elif score >= 0.4:
                    indicator = 'yellow'  # Neutral
                else:
                    indicator = 'red'  # Avoid
                
                day_slots.append({
                    'day': day,
                    'time': time,
                    'preference_score': score,
                    'confidence': result.get('confidence', 0),
                    'indicator': indicator,
                    'reason': 'High preference' if score >= 0.7 else (
                        'Low preference' if score < 0.4 else 'Neutral'
                    )
                })
            
            heatmap[day] = day_slots
        
        return heatmap


def get_suggestions_api(
    entry_data: Dict[str, any],
    max_suggestions: int = 5
) -> Dict[str, any]:
    """
    API-friendly wrapper for getting suggestions.
    
    Args:
        entry_data: Current entry data
        max_suggestions: Maximum suggestions per category
        
    Returns:
        Standardized API response with suggestions
    """
    engine = SuggestionEngine()
    constraint_engine = ConstraintEngine()
    
    # First check for conflicts
    hard_violations = constraint_engine.check_hard_constraints(entry_data)
    
    # Get suggestions
    suggestions = engine.suggest_alternatives(
        entry_data=entry_data,
        conflict_violations=hard_violations,
        max_suggestions=max_suggestions
    )
    
    # Convert to API format
    return {
        'has_conflict': len(hard_violations) > 0,
        'conflicts': [v.to_dict() for v in hard_violations],
        'suggestions': {
            'rooms': [s.to_dict() for s in suggestions['rooms']],
            'time_slots': [s.to_dict() for s in suggestions['time_slots']],
            'faculty': [s.to_dict() for s in suggestions['faculty']],
            'combinations': [s.to_dict() for s in suggestions['combinations']],
        },
        'total_suggestions': (
            len(suggestions['rooms']) +
            len(suggestions['time_slots']) +
            len(suggestions['faculty']) +
            len(suggestions['combinations'])
        ),
        'ai_powered': True  # Indicates preference-based suggestions
    }


def get_quick_fix_suggestions(entry_id: int) -> Dict[str, any]:
    """
    Get immediate fix suggestions for a conflicting entry.
    
    Args:
        entry_id: ID of the TimetableEntry with conflict
        
    Returns:
        Quick fix options
    """
    try:
        entry = TimetableEntry.objects.select_related(
            'instructor', 'room', 'section', 'meeting_time', 'course'
        ).get(pk=entry_id)
    except TimetableEntry.DoesNotExist:
        return {'error': 'Entry not found'}
    
    # Build entry data
    entry_data = {
        'instructor_id': entry.instructor_id,
        'room_id': entry.room_id,
        'section_id': entry.section_id,
        'meeting_time_id': entry.meeting_time_id,
        'course_id': entry.course_id,
    }
    
    # Get suggestions
    result = get_suggestions_api(entry_data, max_suggestions=3)
    
    # Add quick actions
    result['quick_actions'] = []
    
    # Best room+time combination
    if result['suggestions']['combinations']:
        best_combo = result['suggestions']['combinations'][0]
        result['quick_actions'].append({
            'action': 'change_room_and_time',
            'label': f"Move to {best_combo['room']['number']} at {best_combo['time_slot']['day']} {best_combo['time_slot']['time']}",
            'data': {
                'room_id': best_combo['room']['id'],
                'meeting_time_id': best_combo['time_slot']['id']
            },
            'reason': best_combo['reason']
        })
    
    # Alternative room at same time
    if result['suggestions']['rooms']:
        alt_room = result['suggestions']['rooms'][0]
        result['quick_actions'].append({
            'action': 'change_room',
            'label': f"Switch to room {alt_room['room']['number']}",
            'data': {'room_id': alt_room['room']['id']},
            'reason': alt_room['reason']
        })
    
    # Alternative time in same room
    if result['suggestions']['time_slots']:
        alt_time = result['suggestions']['time_slots'][0]
        result['quick_actions'].append({
            'action': 'change_time',
            'label': f"Reschedule to {alt_time['time_slot']['day']} {alt_time['time_slot']['time']}",
            'data': {'meeting_time_id': alt_time['time_slot']['id']},
            'reason': alt_time['reason']
        })
    
    return result

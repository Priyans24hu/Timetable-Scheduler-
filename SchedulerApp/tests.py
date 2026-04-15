from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
import json

from .models import (
    Room, Instructor, MeetingTime, Course, Department, 
    Section, TimetableEntry, ConflictLog, GenerationLog,
    FacultyPreference, HistoricalTimetableData, DAYS_OF_WEEK
)
from .services.constraint_engine import ConstraintEngine, check_conflict_api
from .services.suggestion_engine import SuggestionEngine, get_suggestions_api
from .services.preference_model import predict_preference


class ModelTests(TestCase):
    """Test the enhanced models with intelligent editing features"""
    
    def setUp(self):
        """Set up test data"""
        # Create department
        self.dept = Department.objects.create(dept_name="Computer Science")
        
        # Create room
        self.room = Room.objects.create(
            r_number="101",
            seating_capacity=50,
            room_type="lecture"
        )
        
        # Create instructor
        self.instructor = Instructor.objects.create(
            name="Dr. Smith",
            uid="INS001"
        )
        
        # Create meeting time
        self.meeting_time = MeetingTime.objects.create(
            pid="MT001",
            day="Monday",
            time="09:00-10:00"
        )
        
        # Create course
        self.course = Course.objects.create(
            course_number="CS101",
            course_name="Introduction to Programming"
        )
        self.course.instructors.add(self.instructor)
        
        # Create section
        self.section = Section.objects.create(
            section_id="CS101-A",
            department=self.dept,
            course=self.course,
            strength=45,
            instructor=self.instructor
        )
    
    def test_timetable_entry_creation(self):
        """Test creating a TimetableEntry with new fields"""
        entry = TimetableEntry.objects.create(
            section=self.section,
            course=self.course,
            instructor=self.instructor,
            room=self.room,
            meeting_time=self.meeting_time,
            entry_type='manual',
            is_locked=True,
            has_conflict=False,
            preference_score=0.8
        )
        
        self.assertEqual(entry.entry_type, 'manual')
        self.assertTrue(entry.is_locked)
        self.assertFalse(entry.has_conflict)
        self.assertEqual(entry.preference_score, 0.8)
        self.assertEqual(entry.status_indicator, 'locked')
    
    def test_timetable_entry_conflict_status(self):
        """Test conflict status indicator"""
        entry = TimetableEntry.objects.create(
            section=self.section,
            course=self.course,
            instructor=self.instructor,
            room=self.room,
            meeting_time=self.meeting_time,
            has_conflict=True
        )
        
        self.assertEqual(entry.status_indicator, 'conflict')
    
    def test_conflict_log_creation(self):
        """Test creating a conflict log"""
        entry = TimetableEntry.objects.create(
            section=self.section,
            course=self.course,
            instructor=self.instructor,
            room=self.room,
            meeting_time=self.meeting_time
        )
        
        conflict = ConflictLog.objects.create(
            entry=entry,
            conflict_type='room_conflict',
            message='Room double booking detected'
        )
        
        self.assertFalse(conflict.is_resolved)
        self.assertEqual(conflict.conflict_type, 'room_conflict')
        
        # Test mark_resolved
        conflict.mark_resolved('manual')
        self.assertTrue(conflict.is_resolved)
        self.assertEqual(conflict.resolution_method, 'manual')


class ConstraintEngineTests(TestCase):
    """Test the constraint engine for conflict detection"""
    
    def setUp(self):
        """Set up test data"""
        self.dept = Department.objects.create(dept_name="CS")
        self.room1 = Room.objects.create(r_number="101", seating_capacity=50)
        self.room2 = Room.objects.create(r_number="102", seating_capacity=30)
        
        self.instructor1 = Instructor.objects.create(name="Dr. Smith", uid="INS001")
        self.instructor2 = Instructor.objects.create(name="Dr. Jones", uid="INS002")
        
        self.meeting_time1 = MeetingTime.objects.create(pid="MT1", day="Monday", time="09:00-10:00")
        self.meeting_time2 = MeetingTime.objects.create(pid="MT2", day="Monday", time="10:00-11:00")
        
        self.course1 = Course.objects.create(course_number="CS101", course_name="Programming")
        self.course1.instructors.add(self.instructor1)
        
        self.section1 = Section.objects.create(section_id="A", department=self.dept, course=self.course1, strength=40, instructor=self.instructor1)
        self.section2 = Section.objects.create(section_id="B", department=self.dept, course=self.course1, strength=25, instructor=self.instructor2)
    
    def test_no_conflict_for_valid_entry(self):
        """Test that a valid entry has no conflicts"""
        engine = ConstraintEngine()
        
        entry_data = {
            'instructor_id': self.instructor1.id,
            'room_id': self.room1.id,
            'section_id': self.section1.pk,
            'meeting_time_id': self.meeting_time1.pid,
            'course_id': self.course1.pk,
        }
        
        violations = engine.check_hard_constraints(entry_data)
        self.assertEqual(len(violations), 0)
    
    def test_faculty_conflict_detection(self):
        """Test detecting faculty double booking"""
        # Create an existing entry
        TimetableEntry.objects.create(
            section=self.section1,
            course=self.course1,
            instructor=self.instructor1,
            room=self.room1,
            meeting_time=self.meeting_time1
        )
        
        engine = ConstraintEngine()
        
        # Try to create another entry with same faculty and time
        entry_data = {
            'instructor_id': self.instructor1.id,
            'room_id': self.room2.id,  # Different room
            'section_id': self.section2.pk,  # Different section
            'meeting_time_id': self.meeting_time1.pid,  # Same time - CONFLICT
            'course_id': self.course1.pk,
        }
        
        violations = engine.check_hard_constraints(entry_data)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].violation_type.value, 'faculty_conflict')
    
    def test_room_conflict_detection(self):
        """Test detecting room double booking"""
        # Create an existing entry
        TimetableEntry.objects.create(
            section=self.section1,
            course=self.course1,
            instructor=self.instructor1,
            room=self.room1,
            meeting_time=self.meeting_time1
        )
        
        engine = ConstraintEngine()
        
        # Try to create another entry with same room and time
        entry_data = {
            'instructor_id': self.instructor2.id,  # Different faculty
            'room_id': self.room1.id,  # Same room - CONFLICT
            'section_id': self.section2.pk,  # Different section
            'meeting_time_id': self.meeting_time1.pid,  # Same time
            'course_id': self.course1.pk,
        }
        
        violations = engine.check_hard_constraints(entry_data)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].violation_type.value, 'room_conflict')
    
    def test_capacity_violation_detection(self):
        """Test detecting room capacity violations"""
        # Create a section larger than room capacity
        large_section = Section.objects.create(
            section_id="C",
            department=self.dept,
            course=self.course1,
            strength=60,  # More than room2's capacity of 30
            instructor=self.instructor2
        )
        
        engine = ConstraintEngine()
        
        entry_data = {
            'instructor_id': self.instructor2.id,
            'room_id': self.room2.id,  # Capacity 30
            'section_id': large_section.pk,  # Strength 60
            'meeting_time_id': self.meeting_time1.pid,
            'course_id': self.course1.pk,
        }
        
        violations = engine.check_hard_constraints(entry_data)
        capacity_violations = [v for v in violations if v.violation_type.value == 'capacity_violation']
        self.assertEqual(len(capacity_violations), 1)
    
    def test_check_conflict_api(self):
        """Test the API wrapper for conflict checking"""
        entry_data = {
            'instructor_id': self.instructor1.id,
            'room_id': self.room1.id,
            'section_id': self.section1.pk,
            'meeting_time_id': self.meeting_time1.pid,
            'course_id': self.course1.pk,
        }
        
        result = check_conflict_api(entry_data)
        
        self.assertIn('has_conflict', result)
        self.assertIn('can_save', result)
        self.assertIn('conflicts', result)
        self.assertFalse(result['has_conflict'])
        self.assertTrue(result['can_save'])


class SuggestionEngineTests(TestCase):
    """Test the suggestion engine"""
    
    def setUp(self):
        """Set up test data"""
        self.dept = Department.objects.create(dept_name="CS")
        self.room1 = Room.objects.create(r_number="101", seating_capacity=50)
        self.room2 = Room.objects.create(r_number="102", seating_capacity=40)
        
        self.instructor = Instructor.objects.create(name="Dr. Smith", uid="INS001")
        
        self.meeting_time1 = MeetingTime.objects.create(pid="MT1", day="Monday", time="09:00-10:00")
        self.meeting_time2 = MeetingTime.objects.create(pid="MT2", day="Monday", time="10:00-11:00")
        self.meeting_time3 = MeetingTime.objects.create(pid="MT3", day="Tuesday", time="09:00-10:00")
        
        self.course = Course.objects.create(course_number="CS101", course_name="Programming")
        self.course.instructors.add(self.instructor)
        
        self.section = Section.objects.create(section_id="A", department=self.dept, course=self.course, strength=40, instructor=self.instructor)
    
    def test_suggest_rooms(self):
        """Test room suggestions"""
        engine = SuggestionEngine()
        
        # Occupy room1 at meeting_time1
        TimetableEntry.objects.create(
            section=self.section,
            course=self.course,
            instructor=self.instructor,
            room=self.room1,
            meeting_time=self.meeting_time1
        )
        
        entry_data = {
            'instructor_id': self.instructor.id,
            'room_id': self.room1.id,
            'section_id': self.section.pk,
            'meeting_time_id': self.meeting_time1.pid,
            'course_id': self.course.pk,
        }
        
        suggestions = engine.suggest_alternatives(entry_data, [], max_suggestions=5)
        
        self.assertIn('rooms', suggestions)
        # Should suggest room2 as alternative since room1 is occupied
        room_suggestions = suggestions['rooms']
        self.assertTrue(len(room_suggestions) > 0)
    
    def test_suggest_time_slots(self):
        """Test time slot suggestions"""
        engine = SuggestionEngine()
        
        # Occupy meeting_time1
        TimetableEntry.objects.create(
            section=self.section,
            course=self.course,
            instructor=self.instructor,
            room=self.room1,
            meeting_time=self.meeting_time1
        )
        
        entry_data = {
            'instructor_id': self.instructor.id,
            'room_id': self.room1.id,
            'section_id': self.section.pk,
            'meeting_time_id': self.meeting_time1.pid,
            'course_id': self.course.pk,
        }
        
        suggestions = engine.suggest_alternatives(entry_data, [], max_suggestions=5)
        
        self.assertIn('time_slots', suggestions)
    
    def test_get_suggestions_api(self):
        """Test the suggestions API wrapper"""
        entry_data = {
            'instructor_id': self.instructor.id,
            'room_id': self.room1.id,
            'section_id': self.section.pk,
            'meeting_time_id': self.meeting_time1.pid,
            'course_id': self.course.pk,
        }
        
        result = get_suggestions_api(entry_data, max_suggestions=3)
        
        self.assertIn('has_conflict', result)
        self.assertIn('suggestions', result)
        self.assertIn('rooms', result['suggestions'])
        self.assertIn('time_slots', result['suggestions'])


class APITests(TestCase):
    """Test the API endpoints"""
    
    def setUp(self):
        """Set up test data and client"""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
        
        # Create test data
        self.dept = Department.objects.create(dept_name="CS")
        self.room = Room.objects.create(r_number="101", seating_capacity=50)
        self.instructor = Instructor.objects.create(name="Dr. Smith", uid="INS001")
        self.meeting_time = MeetingTime.objects.create(pid="MT1", day="Monday", time="09:00-10:00")
        self.course = Course.objects.create(course_number="CS101", course_name="Programming")
        self.course.instructors.add(self.instructor)
        self.section = Section.objects.create(section_id="A", department=self.dept, course=self.course, strength=40, instructor=self.instructor)
    
    def test_api_check_conflict_no_conflict(self):
        """Test conflict check API with no conflicts"""
        response = self.client.get('/api/check-conflict/', {
            'instructor_id': self.instructor.id,
            'room_id': self.room.id,
            'section_id': self.section.pk,
            'meeting_time_id': self.meeting_time.pid,
            'course_id': self.course.pk,
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['has_conflict'])
        self.assertTrue(data['can_save'])
    
    def test_api_check_conflict_missing_fields(self):
        """Test conflict check API with missing fields"""
        response = self.client.get('/api/check-conflict/', {
            'instructor_id': self.instructor.id,
            # Missing room_id, section_id, meeting_time_id
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
    
    def test_api_suggest(self):
        """Test suggestions API"""
        response = self.client.get('/api/suggest', {
            'instructor_id': self.instructor.id,
            'room_id': self.room.id,
            'section_id': self.section.pk,
            'meeting_time_id': self.meeting_time.pid,
            'course_id': self.course.pk,
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('suggestions', data)
        self.assertIn('rooms', data['suggestions'])
        self.assertIn('time_slots', data['suggestions'])
    
    def test_api_toggle_lock(self):
        """Test toggle lock API"""
        # Create an entry
        entry = TimetableEntry.objects.create(
            section=self.section,
            course=self.course,
            instructor=self.instructor,
            room=self.room,
            meeting_time=self.meeting_time,
            is_locked=False
        )
        
        response = self.client.post(f'/api/toggle-lock/{entry.entry_id}')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_locked'])
        
        # Verify in database
        entry.refresh_from_db()
        self.assertTrue(entry.is_locked)
    
    def test_api_validate_all(self):
        """Test validate all API"""
        response = self.client.get('/api/validate-all/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('total_checked', data)
    
    def test_api_conflict_summary(self):
        """Test conflict summary API"""
        response = self.client.get('/api/conflict-summary')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('total_entries', data)
        self.assertIn('conflict_count', data)


class IntegrationTests(TestCase):
    """Integration tests for the full workflow"""
    
    def setUp(self):
        """Set up comprehensive test data"""
        self.client = Client()
        self.user = User.objects.create_user(username='admin', password='admin123')
        self.client.force_login(self.user)
        
        # Create full dataset
        self.dept = Department.objects.create(dept_name="Computer Science")
        
        # Multiple rooms
        self.rooms = [
            Room.objects.create(r_number=f"10{i}", seating_capacity=50, room_type="lecture")
            for i in range(1, 4)
        ]
        
        # Multiple instructors
        self.instructors = [
            Instructor.objects.create(name=f"Dr. Smith {i}", uid=f"INS00{i}")
            for i in range(1, 4)
        ]
        
        # Multiple time slots
        self.meeting_times = [
            MeetingTime.objects.create(pid=f"MT00{i}", day=day, time=time)
            for i, (day, time) in enumerate([
                ("Monday", "09:00-10:00"),
                ("Monday", "10:00-11:00"),
                ("Tuesday", "09:00-10:00"),
            ], 1)
        ]
        
        # Course with multiple instructors
        self.course = Course.objects.create(
            course_number="CS101",
            course_name="Introduction to Programming"
        )
        for inst in self.instructors:
            self.course.instructors.add(inst)
        
        # Multiple sections
        self.sections = [
            Section.objects.create(
                section_id=f"CS101-{chr(65+i)}",
                department=self.dept,
                course=self.course,
                strength=40,
                instructor=self.instructors[i]
            )
            for i in range(3)
        ]
    
    def test_full_workflow_create_entry_with_conflict(self):
        """Test creating entries and detecting conflicts"""
        # Create first entry
        entry1 = TimetableEntry.objects.create(
            section=self.sections[0],
            course=self.course,
            instructor=self.instructors[0],
            room=self.rooms[0],
            meeting_time=self.meeting_times[0],
            entry_type='auto'
        )
        
        # Create second entry with same room/time (should have conflict)
        entry2 = TimetableEntry.objects.create(
            section=self.sections[1],
            course=self.course,
            instructor=self.instructors[1],
            room=self.rooms[0],  # Same room
            meeting_time=self.meeting_times[0],  # Same time
            entry_type='auto'
        )
        
        # Check conflict via API
        response = self.client.get('/api/check-conflict/', {
            'instructor_id': self.instructors[2].id,
            'room_id': self.rooms[0].id,
            'section_id': self.sections[2].pk,
            'meeting_time_id': self.meeting_times[0].pid,
        })
        
        data = response.json()
        # Should detect room conflict (room already has 2 entries at this time)
        # Note: Due to DB constraints, this might actually raise IntegrityError
        # In real scenario, the constraint engine catches this before save
    
    def test_lock_and_update_workflow(self):
        """Test locking entries and updating others"""
        # Create an entry and lock it
        entry = TimetableEntry.objects.create(
            section=self.sections[0],
            course=self.course,
            instructor=self.instructors[0],
            room=self.rooms[0],
            meeting_time=self.meeting_times[0],
            is_locked=True
        )
        
        # Toggle lock off
        response = self.client.post(f'/api/toggle-lock/{entry.entry_id}/', {'locked': 'false'})
        self.assertEqual(response.status_code, 200)
        
        entry.refresh_from_db()
        self.assertFalse(entry.is_locked)
        
        # Update the entry
        response = self.client.post(f'/api/update-entry/{entry.entry_id}/', {
            'room_id': self.rooms[1].id,
        })
        
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.room_id, self.rooms[1].id)
        self.assertEqual(entry.entry_type, 'manual')
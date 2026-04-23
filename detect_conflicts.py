"""
Script to run conflict detection and populate ConflictLog table from existing timetable data
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Scheduler.settings')
import django
django.setup()

from SchedulerApp.services.constraint_engine import validate_existing_entries, ConstraintEngine
from SchedulerApp.models import TimetableEntry, ConflictLog

print("Running conflict detection...")
result = validate_existing_entries()
print("Conflicts found:", result['conflicts_found'])
print("Total checked:", result['total_checked'])
print("Entries updated:", len(result['entries_updated']))

print()
print("ConflictLog count:", ConflictLog.objects.count())
print("Entries with has_conflict:", TimetableEntry.objects.filter(has_conflict=True, is_active=True).count())

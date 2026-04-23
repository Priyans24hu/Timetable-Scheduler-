import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Scheduler.settings')
import django
django.setup()
from SchedulerApp.models import *
from django.db.models import Count

print('GenerationLogs:')
for gl in GenerationLog.objects.all():
    entries_count = TimetableEntry.objects.filter(generation_batch=gl.batch_id).count()
    print(f'  {gl.batch_id} | is_active={gl.is_active} | entries={entries_count}')

print()
print('TimetableEntry active batches:')
batches = TimetableEntry.objects.filter(is_active=True).values('generation_batch').annotate(count=Count('entry_id'))
for b in batches:
    print(f'  batch: {b["generation_batch"]}, entries: {b["count"]}')

print()
print('ConflictLog count:', ConflictLog.objects.count())
print('Entries with has_conflict=True:', TimetableEntry.objects.filter(has_conflict=True).count())

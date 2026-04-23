import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Scheduler.settings')
import django
django.setup()

from SchedulerApp.models import ConflictLog, TimetableEntry
from django.db import connection

print("ConflictLog count:", ConflictLog.objects.count())

# Raw SQL query
with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM SchedulerApp_conflictlog")
    raw_count = cursor.fetchone()[0]
    print("Raw SQL ConflictLog count:", raw_count)
    
    cursor.execute("SELECT * FROM SchedulerApp_conflictlog LIMIT 3")
    rows = cursor.fetchall()
    for row in rows:
        print("Row:", row)
    
    # Check table schema
    cursor.execute("PRAGMA table_info(SchedulerApp_conflictlog)")
    schema = cursor.fetchall()
    print("\nSchema:", schema)

print("\nFirst conflict log entry:")
conflicts = ConflictLog.objects.all()
print("Queryset count:", conflicts.count())
if conflicts.exists():
    c = conflicts.first()
    print("Conflict:", c, c.conflict_type, c.is_resolved)

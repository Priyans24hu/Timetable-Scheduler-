"""
Example Usage Script for AI-Based Faculty Preference Learning

This script demonstrates how to use the new ML-based preference learning system.
Run this from Django shell: python manage.py shell < example_usage.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Scheduler.settings')
django.setup()

# ============================================
# EXAMPLE 1: Training the Model
# ============================================

print("=" * 60)
print("EXAMPLE 1: Training the Preference Learning Model")
print("=" * 60)

from SchedulerApp.services.preference_model import train_model

# Train model with default settings (Logistic Regression, per-faculty)
result = train_model()

print(f"Training Result: {result}")
print(f"Models Trained: {result.get('models_trained', 0)}")
print(f"Model Version: {result.get('model_version', 'N/A')}")

if result.get('global_metrics'):
    print(f"Global Model Accuracy: {result['global_metrics'].get('accuracy', 0):.2%}")


# ============================================
# EXAMPLE 2: Making Predictions
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 2: Predicting Faculty Preferences")
print("=" * 60)

from SchedulerApp.services.preference_model import predict_preference

# Get all instructors
from SchedulerApp.models import Instructor
instructors = Instructor.objects.all()

# Test predictions for each instructor
for instructor in instructors[:3]:  # First 3 instructors
    print(f"\n--- Predictions for {instructor.name} ---")
    
    # Predict for Monday morning
    result_mon = predict_preference(instructor.id, "Monday", "10:00 - 11:00")
    print(f"  Monday 10:00-11:00: Score={result_mon['preference_score']:.2f}, "
          f"Confidence={result_mon['confidence']:.2f}")
    
    # Predict for Friday afternoon
    result_fri = predict_preference(instructor.id, "Friday", "2:15 - 3:15")
    print(f"  Friday 2:15-3:15: Score={result_fri['preference_score']:.2f}, "
          f"Confidence={result_fri['confidence']:.2f}")


# ============================================
# EXAMPLE 3: Feature Engineering
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 3: Feature Engineering")
print("=" * 60)

from SchedulerApp.services.feature_engineering import (
    encode_day, 
    get_time_period, 
    encode_time_slot,
    extract_features
)

# Day encoding
day_code = encode_day("Wednesday")
print(f"Wednesday encoded as: {day_code}")  # Output: 2

# Time period categorization
period = get_time_period("10:00 - 11:00")
print(f"10:00 - 11:00 period: {period}")  # Output: morning

# Full feature extraction
features = extract_features(
    instructor_id=1,
    day="Monday",
    time_slot="10:00 - 11:00"
)
print(f"\nExtracted Features:")
for key, value in features.items():
    print(f"  {key}: {value}")


# ============================================
# EXAMPLE 4: Preference Statistics
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 4: System-Wide Preference Statistics")
print("=" * 60)

from SchedulerApp.services.preference_integration import get_preference_statistics

stats = get_preference_statistics()
print(f"Total Instructors: {stats['total_instructors']}")
print(f"Instructors with Preferences: {stats['instructors_with_preferences']}")
print(f"Coverage: {stats['coverage_percent']:.1f}%")
print(f"Average Preference Score: {stats['average_preference_score']:.2f}")
print(f"Current Preference Weight: {stats['preference_weight']}")


# ============================================
# EXAMPLE 5: Bulk Predictions
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 5: Bulk Predictions for Faculty")
print("=" * 60)

from SchedulerApp.services.preference_model import bulk_predict_preferences

# Define day-time slots to predict
day_time_slots = [
    ("Monday", "10:00 - 11:00"),
    ("Tuesday", "10:00 - 11:00"),
    ("Wednesday", "10:00 - 11:00"),
    ("Thursday", "10:00 - 11:00"),
    ("Friday", "10:00 - 11:00"),
]

if instructors.exists():
    instructor = instructors.first()
    results = bulk_predict_preferences(instructor.id, day_time_slots)
    
    print(f"\nPredictions for {instructor.name} at 10:00-11:00 across week:")
    for r in results:
        print(f"  {r['day']}: Score={r['preference_score']:.2f}")


# ============================================
# EXAMPLE 6: Check Faculty Preference Summary
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 6: Faculty Preference Summary")
print("=" * 60)

from SchedulerApp.services.preference_model import get_instructor_preference_summary

if instructors.exists():
    instructor = instructors.first()
    summary = get_instructor_preference_summary(instructor.id)
    
    print(f"\nPreference Summary for {summary.get('instructor_name', 'N/A')}:")
    print(f"  Has Preferences: {summary.get('has_preferences', False)}")
    
    if summary.get('has_preferences'):
        print(f"  Total Preferences: {summary['total_preferences']}")
        print(f"  Average Score: {summary['average_score']:.2f}")
        
        if summary.get('top_preferences'):
            print(f"  Top Preferred Slot:")
            top = summary['top_preferences'][0]
            print(f"    {top['day']} {top['time_slot']} (Score: {top['score']:.2f})")


# ============================================
# EXAMPLE 7: Setting Preference Weight
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 7: Setting Preference Weight for GA")
print("=" * 60)

from SchedulerApp.services.preference_integration import (
    set_preference_weight, 
    get_preference_weight
)

# Check current weight
current_weight = get_preference_weight()
print(f"Current Preference Weight: {current_weight}")

# Set new weight
new_weight = 0.2
set_preference_weight(new_weight)
print(f"Set Preference Weight to: {new_weight}")

# Verify
verified_weight = get_preference_weight()
print(f"Verified Preference Weight: {verified_weight}")


# ============================================
# EXAMPLE 8: Check Historical Data
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 8: Historical Timetable Data")
print("=" * 60)

from SchedulerApp.models import HistoricalTimetableData

historical_count = HistoricalTimetableData.objects.count()
print(f"Total Historical Records: {historical_count}")

if historical_count > 0:
    # Show sample
    sample = HistoricalTimetableData.objects.first()
    print(f"\nSample Record:")
    print(f"  Instructor: {sample.instructor.name}")
    print(f"  Day: {sample.day}")
    print(f"  Time: {sample.time_slot}")
    print(f"  Course: {sample.course.course_name}")


# ============================================
# EXAMPLE 9: Calculate Schedule Preference Score
# ============================================

print("\n" + "=" * 60)
print("EXAMPLE 9: Calculate Preference Score for Schedule")
print("=" * 60)

from SchedulerApp.services.preference_integration import calculate_schedule_preference_score
from SchedulerApp.views import Schedule, data

# Create a sample schedule and calculate preference score
# Note: This requires an initialized schedule from GA
# This is a conceptual example

print("Note: Run this after GA generates a schedule")
print("Usage: calculate_schedule_preference_score(schedule.getClasses())")
print("Returns: {'average_score': 0.65, 'weighted_score': 0.70, ...}")


# ============================================
# Summary
# ============================================

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print("""
The AI-Based Faculty Preference Learning system is now integrated!

Key Features:
1. Automatic data collection from timetable generations
2. ML model training with scikit-learn
3. Preference prediction API
4. GA fitness function integration
5. Django Admin interface for monitoring

Next Steps:
1. Generate some timetables to collect historical data
2. Train the model: POST /api/train-model/
3. Set preference weight: POST /api/set-preference-weight/
4. Generate optimized timetable with preference consideration

For detailed documentation, see: AI_PREFERENCE_LEARNING_GUIDE.md
""")

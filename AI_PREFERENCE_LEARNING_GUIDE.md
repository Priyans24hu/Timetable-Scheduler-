# AI-Based Faculty Preference Learning System

## Overview

This enhanced timetable scheduling system now includes AI-based faculty preference learning using machine learning. The system learns from historical timetable data to predict and optimize faculty time slot preferences, resulting in more personalized and intelligent timetables.

## Architecture

```
┌──────────────────────┐
│   Django Backend     │
└─────────┬────────────┘
          │
┌─────────┼─────────────┐
│         │             │
▼         ▼             ▼
Database   GA Engine   ML Model
(SQLite)   (Custom)   (sklearn)
│         │             │
└──────► Preference Service ◄──────┐
                          │        │
                          ▼        │
                Optimized Timetable  │
                                     │
                    ┌────────────────┘
                    │
            Historical Data
```

## Components

### 1. New Models (in `models.py`)

#### HistoricalTimetableData
- Stores past timetable assignments for ML training
- Tracks: Instructor, Course, Section, Room, Day, Time Slot
- Automatically populated when timetables are generated

#### FacultyPreference
- Stores learned preferences after ML training
- Fields: preference_score (0-1), confidence, frequency_count
- Updated whenever model is retrained

#### MLModelMetadata
- Tracks trained model versions and performance
- Stores: model_type, accuracy, training_samples, feature_columns

### 2. ML Service (`services/`)

#### preference_model.py
- `train_model()`: Train preference learning model on historical data
- `predict_preference()`: Predict preference score for faculty-day-time
- `PreferencePredictor`: Class wrapper for ML models

#### feature_engineering.py
- Day encoding (Mon-Fri → 0-4)
- Time slot categorization (morning/mid/afternoon)
- Frequency-based feature extraction
- Data preprocessing for training

#### preference_integration.py
- `calculate_preference_score()`: Calculate scores for schedule classes
- `integrate_preference_with_fitness()`: Merge with GA fitness function
- `get_preference_statistics()`: System-wide preference metrics

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- scikit-learn>=1.3.0
- pandas>=2.0.0
- numpy>=1.24.0
- joblib>=1.3.0

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Create ML Models Directory

The directory `ml_models/` is automatically created for storing trained models.

## Usage Guide

### Step 1: Generate Timetables (Data Collection)

Generate timetables as usual. The system automatically saves data to `HistoricalTimetableData`:

```
1. Go to Timetable Generation page
2. Click "Generate Timetable"
3. Historical data is automatically stored
```

**Note:** You need at least 5-10 historical assignments per faculty for effective training.

### Step 2: Train the Model

#### Via API:
```bash
# Train with default settings (Logistic Regression)
curl -X POST http://localhost:8000/api/train-model/

# Train with specific model type
curl -X POST http://localhost:8000/api/train-model/ \
  -d "model_type=DecisionTree" \
  -d "per_faculty=true"

# Train global model only
curl -X POST http://localhost:8000/api/train-model/ \
  -d "per_faculty=false"
```

**Model Types:**
- `LogisticRegression` (default, fast, interpretable)
- `DecisionTree` (handles non-linear patterns)
- `RandomForest` (ensemble, higher accuracy)

#### Via Django Admin:
1. Go to Django Admin → ML Model Metadata
2. No direct training UI, use API or management command

### Step 3: Check Predictions

#### Predict Single Preference:
```bash
curl "http://localhost:8000/api/predict-preference/?instructor_id=1&day=Monday&time_slot=10:00%20-%2011:00"
```

**Response:**
```json
{
  "success": true,
  "preference_score": 0.85,
  "confidence": 0.92,
  "source": "ml_model",
  "model_type": "LogisticRegression"
}
```

#### Get Faculty Preferences:
```bash
# All preferences for one faculty
curl http://localhost:8000/api/faculty-preferences/1/

# All preferences in system
curl http://localhost:8000/api/faculty-preferences/
```

### Step 4: Adjust Preference Weight

Control how much preference affects the GA:

```bash
# Set weight to 0.2 (20% influence on fitness)
curl -X POST http://localhost:8000/api/set-preference-weight/ \
  -d "weight=0.2"
```

**Weight Guidelines:**
- `0.0` - No preference consideration (original GA behavior)
- `0.1-0.2` - Balanced (recommended)
- `0.3-0.5` - Strong preference optimization
- `>0.5` - Preference may override hard constraints (not recommended)

### Step 5: Generate Optimized Timetable

1. Train model (if new data available)
2. Set appropriate weight
3. Generate timetable as usual
4. The GA fitness function now includes preference scores

## API Reference

### Prediction APIs

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/api/predict-preference/` | GET/POST | instructor_id, day, time_slot | Predict preference score |
| `/api/faculty-preferences/` | GET | - | Get all preferences |
| `/api/faculty-preferences/<id>/` | GET | instructor_id | Get faculty summary |
| `/api/preference-statistics/` | GET | - | System-wide statistics |

### Training APIs

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/api/train-model/` | POST | model_type, per_faculty | Train ML model |
| `/api/set-preference-weight/` | POST | weight (0-1) | Set GA preference weight |

## How It Works

### Feature Engineering

The system extracts these features for ML:

```
Feature                    | Example
---------------------------|--------
day_encoded                | Monday=0, Tuesday=1, ...
start_hour                 | 10:00 → 10.0
is_morning                 | 8-11 AM → 1, else 0
is_mid                     | 11-2 PM → 1, else 0
is_afternoon               | 2-6 PM → 1, else 0
freq_instructor_day        | % of teaching on this day
freq_instructor_time       | % of teaching at this time
freq_instructor_day_time   | % of teaching at this exact slot
```

### Training Process

1. **Data Collection:** Extract historical assignments
2. **Label Generation:** High frequency = high preference (label=1)
3. **Feature Extraction:** Encode days, times, frequencies
4. **Model Training:** Train classifier per faculty or globally
5. **Evaluation:** Calculate accuracy, precision, recall
6. **Persistence:** Save model with joblib, store metadata

### Fitness Integration

The GA fitness function is enhanced:

```python
# Original fitness
base_fitness = 1 / (conflicts + 1)

# With preference integration
final_fitness = base_fitness + (preference_score * weight * base_fitness)
```

**Constraints:**
- Hard constraints (conflicts) always take priority
- Preference is a bonus, not a requirement
- System works without ML data (fallback to neutral scores)

## Example Predictions

### Example 1: High Preference
```json
{
  "instructor": "Dr. Smith",
  "day": "Monday",
  "time_slot": "10:00 - 11:00",
  "preference_score": 0.85,
  "confidence": 0.92,
  "interpretation": "High preference - frequently assigned this slot"
}
```

### Example 2: Low Preference
```json
{
  "instructor": "Dr. Smith",
  "day": "Friday",
  "time_slot": "2:15 - 3:15",
  "preference_score": 0.25,
  "confidence": 0.78,
  "interpretation": "Low preference - rarely assigned this slot"
}
```

### Example 3: Neutral (No Data)
```json
{
  "instructor": "Dr. Jones",
  "day": "Wednesday",
  "time_slot": "11:00 - 12:00",
  "preference_score": 0.50,
  "confidence": 0.30,
  "interpretation": "Neutral - insufficient historical data"
}
```

## Management Commands (Optional)

You can create Django management commands for easier CLI usage:

```python
# In management/commands/train_preferences.py
from django.core.management.base import BaseCommand
from SchedulerApp.services.preference_model import train_model

class Command(BaseCommand):
    help = 'Train faculty preference learning model'

    def handle(self, *args, **options):
        result = train_model()
        self.stdout.write(self.style.SUCCESS(f"Trained {result['models_trained']} models"))
```

## Monitoring & Maintenance

### Check Model Performance

```bash
curl http://localhost:8000/api/preference-statistics/
```

**Response:**
```json
{
  "total_instructors": 15,
  "instructors_with_preferences": 12,
  "coverage_percent": 80.0,
  "average_preference_score": 0.62,
  "preference_weight": 0.15
}
```

### When to Retrain

- After generating 5+ new timetables
- When new faculty added
- When faculty report schedule issues
- Monthly scheduled retraining (recommended)

## Troubleshooting

### Issue: Low prediction confidence
**Solution:** Collect more historical data. Need at least 5 samples per faculty.

### Issue: Model training fails
**Solution:** Check that HistoricalTimetableData has sufficient entries:
```python
from SchedulerApp.models import HistoricalTimetableData
print(HistoricalTimetableData.objects.count())  # Should be > 20
```

### Issue: Preferences not affecting timetable
**Solution:** 
1. Check preference weight: `curl /api/preference-statistics/`
2. Ensure model is trained: `curl /api/train-model/`
3. Verify model is active in Django Admin → ML Model Metadata

## Viva Questions & Answers

### Q1: What ML algorithm is used?
**A:** Logistic Regression (default) or Decision Tree/Random Forest. Choice depends on data complexity and interpretability needs.

### Q2: How is preference learned?
**A:** From historical timetable data. If faculty frequently teaches at a specific day/time, the model learns it as a preference.

### Q3: Does this affect hard constraints?
**A:** No. Hard constraints (room conflicts, instructor double-booking) are always resolved first. Preference is a soft optimization.

### Q4: What if there's no historical data?
**A:** System falls back to rule-based scoring using frequency counts, or neutral scores (0.5) if no data at all.

### Q5: How do you prevent overfitting?
**A:** Minimum sample thresholds, cross-validation, and confidence scores. Low-confidence predictions don't heavily influence the GA.

## Files Added/Modified

### New Files:
- `SchedulerApp/services/__init__.py`
- `SchedulerApp/services/preference_model.py` - ML training & prediction
- `SchedulerApp/services/feature_engineering.py` - Feature extraction
- `SchedulerApp/services/preference_integration.py` - GA integration
- `ml_models/` - Trained model storage

### Modified Files:
- `requirements.txt` - Added ML dependencies
- `SchedulerApp/models.py` - Added 3 new models
- `SchedulerApp/views.py` - Enhanced GA fitness + 5 new API endpoints
- `SchedulerApp/urls.py` - Added 6 new API routes
- `SchedulerApp/admin.py` - Registered new models
- `SchedulerApp/timetable_utils.py` - Historical data saving

## Performance Considerations

- Model training: ~1-5 seconds per faculty (depending on data size)
- Prediction: ~10ms per query (cached for 1 hour)
- GA fitness calculation: Minimal overhead (<5% increase)
- Storage: ~100KB per trained model

## Future Enhancements

- Deep learning models (neural networks) for complex patterns
- Real-time preference feedback from faculty
- Multi-objective optimization (preferences + room preferences)
- Explainable AI (SHAP values for predictions)
- Automated retraining scheduling

---

**For technical support or questions, refer to the code comments in the service files.**

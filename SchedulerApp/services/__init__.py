"""
Services module for Intelligent Timetable Scheduling.

This module contains:
- preference_model.py: ML model training and prediction (AI Preference Learning)
- feature_engineering.py: Feature extraction and preprocessing
- preference_integration.py: Integration with Genetic Algorithm
- constraint_engine.py: Hard/soft constraint validation and conflict detection
- suggestion_engine.py: Smart alternatives and recommendations
"""

from .preference_model import (
    train_model,
    predict_preference,
    get_active_model,
    PreferencePredictor,
    get_all_faculty_preferences,
    bulk_predict_preferences
)

from .feature_engineering import (
    extract_features,
    encode_day,
    encode_time_slot,
    get_time_period,
    prepare_training_data
)

from .preference_integration import (
    calculate_preference_score,
    integrate_preference_with_fitness,
    get_preference_weight,
    set_preference_weight,
    calculate_schedule_preference_score,
    get_preference_statistics,
    get_instructor_preference_summary
)

from .constraint_engine import (
    ConstraintEngine,
    ConstraintViolation,
    check_conflict_api,
    validate_existing_entries,
    ConstraintType,
    ViolationType
)

from .suggestion_engine import (
    SuggestionEngine,
    Suggestion,
    get_suggestions_api,
    get_quick_fix_suggestions
)

__all__ = [
    # AI Preference Learning
    'train_model',
    'predict_preference',
    'get_active_model',
    'PreferencePredictor',
    'get_all_faculty_preferences',
    'bulk_predict_preferences',
    'extract_features',
    'encode_day',
    'encode_time_slot',
    'get_time_period',
    'prepare_training_data',
    'calculate_preference_score',
    'integrate_preference_with_fitness',
    'get_preference_weight',
    'set_preference_weight',
    'calculate_schedule_preference_score',
    'get_preference_statistics',
    'get_instructor_preference_summary',
    # Constraint Engine
    'ConstraintEngine',
    'ConstraintViolation',
    'check_conflict_api',
    'validate_existing_entries',
    'ConstraintType',
    'ViolationType',
    # Suggestion Engine
    'SuggestionEngine',
    'Suggestion',
    'get_suggestions_api',
    'get_quick_fix_suggestions',
]

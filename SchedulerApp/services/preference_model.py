"""
Preference Model Module for Faculty Preference Learning

This module provides:
- Model training on historical timetable data
- Preference prediction for faculty-day-time combinations
- Model persistence using joblib
- Support for per-faculty and global models
"""

import os
import joblib
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from pathlib import Path

# Scikit-learn imports
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler

# Django imports
from django.conf import settings

# Local imports
from ..models import (
    Instructor, 
    MeetingTime, 
    HistoricalTimetableData, 
    FacultyPreference, 
    MLModelMetadata
)
from .feature_engineering import (
    extract_features, 
    prepare_training_data, 
    create_global_features,
    encode_day,
    get_time_period
)


# Default model directory
DEFAULT_MODEL_DIR = Path(settings.BASE_DIR) / 'ml_models'


def get_model_dir() -> Path:
    """Get or create the model directory."""
    model_dir = DEFAULT_MODEL_DIR
    model_dir.mkdir(exist_ok=True)
    return model_dir


class PreferencePredictor:
    """
    Wrapper class for preference prediction models.
    Supports both per-faculty and global models.
    """
    
    def __init__(self, model_type: str = 'LogisticRegression'):
        """
        Initialize the predictor.
        
        Args:
            model_type: Type of model ('LogisticRegression', 'DecisionTree', 'RandomForest')
        """
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_columns = None
        
    def _create_model(self):
        """Create the underlying ML model."""
        if self.model_type == 'LogisticRegression':
            return LogisticRegression(
                max_iter=1000,
                class_weight='balanced',
                random_state=42
            )
        elif self.model_type == 'DecisionTree':
            return DecisionTreeClassifier(
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42
            )
        elif self.model_type == 'RandomForest':
            return RandomForestClassifier(
                n_estimators=100,
                max_depth=15,
                min_samples_split=5,
                random_state=42
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
    
    def train(self, X: pd.DataFrame, y: pd.Series, feature_columns: List[str]) -> Dict[str, float]:
        """
        Train the model on provided data.
        
        Args:
            X: Feature DataFrame
            y: Target Series
            feature_columns: List of feature column names
            
        Returns:
            Dictionary with training metrics
        """
        if X.empty or y.empty or len(X) < 5:
            raise ValueError("Insufficient data for training (minimum 5 samples required)")
        
        # Store feature columns
        self.feature_columns = feature_columns
        
        # Split data for validation
        if len(X) >= 10:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y if len(np.unique(y)) > 1 else None
            )
        else:
            X_train, X_test, y_train, y_test = X, X, y, y
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Create and train model
        self.model = self._create_model()
        self.model.fit(X_train_scaled, y_train)
        
        # Calculate metrics
        y_pred = self.model.predict(X_test_scaled)
        
        metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1_score': f1_score(y_test, y_pred, zero_division=0),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
        }
        
        self.is_trained = True
        return metrics
    
    def predict(self, features: np.ndarray) -> Tuple[float, float]:
        """
        Predict preference score.
        
        Args:
            features: Feature array (1 x n_features)
            
        Returns:
            Tuple of (preference_score, confidence)
        """
        if not self.is_trained or self.model is None:
            return 0.5, 0.0  # Default neutral score with low confidence
        
        # Scale features
        features_scaled = self.scaler.transform(features)
        
        # Get probability of positive class (preference = 1)
        probabilities = self.model.predict_proba(features_scaled)[0]
        
        # Preference score = probability of positive class
        preference_score = probabilities[1]
        
        # Confidence = max probability (how certain is the model)
        confidence = np.max(probabilities)
        
        return float(preference_score), float(confidence)
    
    def save(self, filepath: str):
        """Save model to file."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'feature_columns': self.feature_columns,
            'is_trained': self.is_trained,
        }
        joblib.dump(model_data, filepath)
    
    def load(self, filepath: str):
        """Load model from file."""
        model_data = joblib.load(filepath)
        
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.model_type = model_data['model_type']
        self.feature_columns = model_data['feature_columns']
        self.is_trained = model_data['is_trained']


def train_model(
    model_type: str = 'LogisticRegression',
    min_samples_per_instructor: int = 5,
    per_faculty: bool = True
) -> Dict[str, any]:
    """
    Train preference learning model(s) on historical data.
    
    Args:
        model_type: Type of model to use
        min_samples_per_instructor: Minimum samples needed for per-faculty training
        per_faculty: Whether to train per-faculty models (True) or global model (False)
        
    Returns:
        Dictionary with training results and metadata
    """
    # Fetch historical data from database
    historical_data = HistoricalTimetableData.objects.all()
    
    if not historical_data.exists():
        return {
            'success': False,
            'error': 'No historical data available for training',
            'models_trained': 0,
        }
    
    # Convert to list of dictionaries
    assignments = []
    for record in historical_data:
        assignments.append({
            'instructor_id': record.instructor.id,
            'instructor_name': record.instructor.name,
            'day': record.day,
            'time_slot': record.time_slot,
            'course_id': record.course.id,
        })
    
    model_dir = get_model_dir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_version = f"v{timestamp}"
    
    results = {
        'success': True,
        'model_version': model_version,
        'model_type': model_type,
        'models_trained': 0,
        'per_faculty': per_faculty,
        'faculty_models': {},
        'global_metrics': None,
    }
    
    if per_faculty:
        # Train individual model for each instructor with sufficient data
        instructor_data = {}
        for assignment in assignments:
            inst_id = assignment['instructor_id']
            if inst_id not in instructor_data:
                instructor_data[inst_id] = []
            instructor_data[inst_id].append(assignment)
        
        for instructor_id, inst_assignments in instructor_data.items():
            if len(inst_assignments) < min_samples_per_instructor:
                continue
            
            try:
                # Prepare training data
                X, y, feature_columns = prepare_training_data(
                    inst_assignments,
                    min_samples_per_instructor=min_samples_per_instructor
                )
                
                if X.empty:
                    continue
                
                # Train model
                predictor = PreferencePredictor(model_type=model_type)
                metrics = predictor.train(X, y, feature_columns)
                
                # Save model
                model_filename = f"faculty_{instructor_id}_{model_version}.joblib"
                model_path = model_dir / model_filename
                predictor.save(str(model_path))
                
                # Store results
                results['faculty_models'][instructor_id] = {
                    'model_path': str(model_path),
                    'metrics': metrics,
                    'samples': len(inst_assignments),
                }
                results['models_trained'] += 1
                
                # Update FacultyPreference records in database
                update_faculty_preferences(
                    instructor_id, predictor, model_version, inst_assignments
                )
                
            except Exception as e:
                results['faculty_models'][instructor_id] = {
                    'error': str(e),
                }
    
    # Always train a global model as fallback
    try:
        X, y, feature_columns = prepare_training_data(assignments)
        
        if not X.empty:
            global_predictor = PreferencePredictor(model_type=model_type)
            global_metrics = global_predictor.train(X, y, feature_columns)
            
            # Save global model
            global_model_path = model_dir / f"global_{model_version}.joblib"
            global_predictor.save(str(global_model_path))
            
            results['global_metrics'] = global_metrics
            results['global_model_path'] = str(global_model_path)
            
            # Create MLModelMetadata record
            MLModelMetadata.objects.create(
                model_version=model_version,
                model_path=str(global_model_path),
                model_type=model_type,
                training_samples=len(X),
                accuracy=global_metrics.get('accuracy'),
                feature_columns=feature_columns,
                is_active=True,
            )
            
            # Deactivate old models
            MLModelMetadata.objects.exclude(
                model_version=model_version
            ).update(is_active=False)
    
    except Exception as e:
        results['global_error'] = str(e)
    
    return results


def update_faculty_preferences(
    instructor_id: int,
    predictor: PreferencePredictor,
    model_version: str,
    assignments: List[Dict]
):
    """
    Update FacultyPreference records in database after training.
    
    Args:
        instructor_id: ID of the instructor
        predictor: Trained predictor
        model_version: Model version string
        assignments: List of instructor's assignments
    """
    instructor = Instructor.objects.get(id=instructor_id)
    
    # Get unique day-time combinations from assignments
    day_time_combinations = set()
    for assignment in assignments:
        day_time_combinations.add((assignment['day'], assignment['time_slot']))
    
    # Predict preferences for each day-time combination
    for day, time_slot in day_time_combinations:
        features = extract_features(
            instructor_id=instructor_id,
            day=day,
            time_slot=time_slot,
            historical_data=pd.DataFrame(assignments)
        )
        
        # Create feature array
        feature_values = [
            features['day_encoded'],
            features['start_hour'],
            features['is_morning'],
            features['is_mid'],
            features['is_afternoon'],
            features['freq_instructor_day'],
            features['freq_instructor_time'],
            features['freq_instructor_day_time'],
        ]
        
        score, confidence = predictor.predict(np.array(feature_values).reshape(1, -1))
        
        # Update or create FacultyPreference record
        FacultyPreference.objects.update_or_create(
            instructor=instructor,
            preferred_day=day,
            preferred_time=time_slot,
            defaults={
                'preference_score': score,
                'confidence': confidence,
                'frequency_count': int(features['freq_instructor_total'] * features['freq_instructor_day_time']),
                'model_version': model_version,
            }
        )


def predict_preference(
    instructor_id: Union[int, str],
    day: str,
    time_slot: str,
    use_global_fallback: bool = True
) -> Dict[str, any]:
    """
    Predict preference score for a faculty-day-time combination.
    
    Args:
        instructor_id: ID or name of the instructor
        day: Day of the week (e.g., 'Monday')
        time_slot: Time slot string (e.g., '10:00 - 11:00')
        use_global_fallback: Whether to use global model if per-faculty model not available
        
    Returns:
        Dictionary with prediction results
    """
    # Try to get instructor by ID or name
    try:
        if isinstance(instructor_id, int):
            instructor = Instructor.objects.get(id=instructor_id)
        else:
            instructor = Instructor.objects.get(name=instructor_id)
        instructor_id = instructor.id
    except Instructor.DoesNotExist:
        return {
            'success': False,
            'error': f'Instructor not found: {instructor_id}',
            'preference_score': 0.5,
            'confidence': 0.0,
        }
    
    # Check for cached preference in database
    try:
        cached_pref = FacultyPreference.objects.get(
            instructor=instructor,
            preferred_day=day,
            preferred_time=time_slot
        )
        return {
            'success': True,
            'preference_score': cached_pref.preference_score,
            'confidence': cached_pref.confidence,
            'model_version': cached_pref.model_version,
            'source': 'database_cache',
            'frequency_count': cached_pref.frequency_count,
        }
    except FacultyPreference.DoesNotExist:
        pass
    
    # Try to load per-faculty model
    model_dir = get_model_dir()
    per_faculty_model = None
    
    # Look for most recent model for this instructor
    model_files = list(model_dir.glob(f'faculty_{instructor_id}_*.joblib'))
    if model_files:
        # Sort by modification time (most recent first)
        model_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        per_faculty_model = model_files[0]
    
    predictor = None
    
    if per_faculty_model:
        try:
            predictor = PreferencePredictor()
            predictor.load(str(per_faculty_model))
        except Exception:
            predictor = None
    
    # Fall back to global model if needed
    if predictor is None and use_global_fallback:
        try:
            # Get active global model
            active_model = MLModelMetadata.objects.filter(is_active=True).first()
            if active_model:
                predictor = PreferencePredictor()
                predictor.load(active_model.model_path)
        except Exception:
            predictor = None
    
    # If no model available, use rule-based fallback
    if predictor is None:
        # Rule-based scoring based on historical frequency
        historical_count = HistoricalTimetableData.objects.filter(
            instructor=instructor,
            day=day,
            time_slot=time_slot
        ).count()
        
        total_assignments = HistoricalTimetableData.objects.filter(
            instructor=instructor
        ).count()
        
        if total_assignments > 0:
            score = min(1.0, historical_count / (total_assignments * 0.3))
        else:
            score = 0.5
        
        return {
            'success': True,
            'preference_score': score,
            'confidence': 0.3,  # Low confidence for rule-based
            'source': 'rule_based_fallback',
            'frequency_count': historical_count,
        }
    
    # Get historical data for feature extraction
    historical_data = HistoricalTimetableData.objects.filter(
        instructor=instructor
    )
    
    assignments = []
    for record in historical_data:
        assignments.append({
            'instructor_id': record.instructor.id,
            'day': record.day,
            'time_slot': record.time_slot,
        })
    
    # Extract features
    features = extract_features(
        instructor_id=instructor_id,
        day=day,
        time_slot=time_slot,
        historical_data=pd.DataFrame(assignments) if assignments else None
    )
    
    # Create feature array
    if predictor.feature_columns:
        feature_values = [features[col] for col in predictor.feature_columns]
    else:
        feature_values = [
            features['day_encoded'],
            features['start_hour'],
            features['is_morning'],
            features['is_mid'],
            features['is_afternoon'],
            features['freq_instructor_day'],
            features['freq_instructor_time'],
            features['freq_instructor_day_time'],
        ]
    
    # Make prediction
    score, confidence = predictor.predict(np.array(feature_values).reshape(1, -1))
    
    return {
        'success': True,
        'preference_score': score,
        'confidence': confidence,
        'source': 'ml_model',
        'model_type': predictor.model_type,
    }


def get_active_model() -> Optional[MLModelMetadata]:
    """Get the currently active global model metadata."""
    return MLModelMetadata.objects.filter(is_active=True).first()


def get_all_faculty_preferences(instructor_id: Optional[int] = None) -> List[Dict]:
    """
    Get all faculty preferences, optionally filtered by instructor.
    
    Args:
        instructor_id: Optional instructor ID to filter by
        
    Returns:
        List of preference dictionaries
    """
    queryset = FacultyPreference.objects.all()
    if instructor_id:
        queryset = queryset.filter(instructor_id=instructor_id)
    
    preferences = []
    for pref in queryset.select_related('instructor'):
        preferences.append({
            'instructor_id': pref.instructor.id,
            'instructor_name': pref.instructor.name,
            'preferred_day': pref.preferred_day,
            'preferred_time': pref.preferred_time,
            'preference_score': pref.preference_score,
            'confidence': pref.confidence,
            'frequency_count': pref.frequency_count,
            'model_version': pref.model_version,
        })
    
    return preferences


def bulk_predict_preferences(
    instructor_id: int,
    day_time_slots: List[Tuple[str, str]]
) -> List[Dict]:
    """
    Predict preferences for multiple day-time combinations for a faculty.
    
    Args:
        instructor_id: ID of the instructor
        day_time_slots: List of (day, time_slot) tuples
        
    Returns:
        List of prediction dictionaries
    """
    results = []
    for day, time_slot in day_time_slots:
        prediction = predict_preference(instructor_id, day, time_slot)
        prediction['day'] = day
        prediction['time_slot'] = time_slot
        results.append(prediction)
    
    return results

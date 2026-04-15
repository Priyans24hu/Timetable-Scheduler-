"""
Feature Engineering Module for Faculty Preference Learning

This module handles:
- Day encoding (Mon-Fri -> 0-4)
- Time slot encoding and categorization
- Feature extraction from historical data
- Data preprocessing for ML model training
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


# Day encoding mapping
DAY_ENCODING = {
    'Monday': 0,
    'Tuesday': 1,
    'Wednesday': 2,
    'Thursday': 3,
    'Friday': 4,
    'Saturday': 5,
    'Sunday': 6,
}

# Reverse mapping for decoding
DAY_DECODING = {v: k for k, v in DAY_ENCODING.items()}

# Time slot categorization
TIME_PERIODS = {
    'morning': ['8:45 - 9:45', '9:30 - 10:30', '10:00 - 11:00', '10:30 - 11:30'],
    'mid': ['11:00 - 12:00', '11:30 - 12:30', '12:30 - 1:30', '1:00 - 2:00'],
    'afternoon': ['1:00 - 2:00', '2:15 - 3:15', '2:30 - 3:30', '3:30 - 4:30', '4:30 - 5:30'],
}


def encode_day(day: str) -> int:
    """
    Encode day of week to numerical value.
    
    Args:
        day: Day name (e.g., 'Monday', 'Tuesday')
        
    Returns:
        Encoded day (0-5)
    """
    return DAY_ENCODING.get(day, 0)


def decode_day(day_code: int) -> str:
    """
    Decode numerical day to day name.
    
    Args:
        day_code: Encoded day (0-5)
        
    Returns:
        Day name
    """
    return DAY_DECODING.get(day_code, 'Monday')


def get_time_period(time_slot: str) -> str:
    """
    Categorize time slot into morning, mid, or afternoon.
    
    Args:
        time_slot: Time slot string (e.g., '10:00 - 11:00')
        
    Returns:
        Period category ('morning', 'mid', 'afternoon')
    """
    for period, slots in TIME_PERIODS.items():
        if time_slot in slots:
            return period
    return 'mid'  # Default to mid-day if not found


def encode_time_slot(time_slot: str) -> Dict[str, any]:
    """
    Extract features from time slot.
    
    Args:
        time_slot: Time slot string (e.g., '10:00 - 11:00')
        
    Returns:
        Dictionary with time slot features
    """
    period = get_time_period(time_slot)
    
    # Extract start hour
    try:
        start_time = time_slot.split(' - ')[0]
        hour = int(start_time.split(':')[0])
        minute = int(start_time.split(':')[1])
        
        # Convert to decimal hour
        decimal_time = hour + minute / 60.0
    except (ValueError, IndexError):
        decimal_time = 12.0  # Default to noon
    
    return {
        'period': period,
        'is_morning': 1 if period == 'morning' else 0,
        'is_mid': 1 if period == 'mid' else 0,
        'is_afternoon': 1 if period == 'afternoon' else 0,
        'start_hour': decimal_time,
    }


def calculate_frequency_features(
    instructor_id: int,
    day: str,
    time_slot: str,
    historical_data: pd.DataFrame
) -> Dict[str, float]:
    """
    Calculate frequency-based features for an instructor-day-time combination.
    
    Args:
        instructor_id: ID of the instructor
        day: Day of the week
        time_slot: Time slot string
        historical_data: DataFrame with historical assignments
        
    Returns:
        Dictionary with frequency features
    """
    if historical_data.empty:
        return {
            'freq_instructor_day': 0.0,
            'freq_instructor_time': 0.0,
            'freq_instructor_day_time': 0.0,
            'freq_instructor_total': 0.0,
        }
    
    # Filter data for this instructor
    instructor_data = historical_data[
        historical_data['instructor_id'] == instructor_id
    ]
    
    if instructor_data.empty:
        return {
            'freq_instructor_day': 0.0,
            'freq_instructor_time': 0.0,
            'freq_instructor_day_time': 0.0,
            'freq_instructor_total': 0.0,
        }
    
    # Total assignments for this instructor
    total_assignments = len(instructor_data)
    
    # Count assignments for this day
    day_count = len(instructor_data[instructor_data['day'] == day])
    
    # Count assignments for this time slot
    time_count = len(instructor_data[instructor_data['time_slot'] == time_slot])
    
    # Count assignments for this specific day-time combination
    day_time_count = len(instructor_data[
        (instructor_data['day'] == day) & 
        (instructor_data['time_slot'] == time_slot)
    ])
    
    # Normalize by total assignments
    return {
        'freq_instructor_day': day_count / total_assignments if total_assignments > 0 else 0.0,
        'freq_instructor_time': time_count / total_assignments if total_assignments > 0 else 0.0,
        'freq_instructor_day_time': day_time_count / total_assignments if total_assignments > 0 else 0.0,
        'freq_instructor_total': total_assignments,
    }


def extract_features(
    instructor_id: int,
    day: str,
    time_slot: str,
    historical_data: Optional[pd.DataFrame] = None
) -> Dict[str, any]:
    """
    Extract all features for a given instructor-day-time combination.
    
    Args:
        instructor_id: ID of the instructor
        day: Day of the week
        time_slot: Time slot string
        historical_data: Optional DataFrame with historical data for frequency calculation
        
    Returns:
        Dictionary with all features
    """
    # Basic encoding
    day_encoded = encode_day(day)
    time_features = encode_time_slot(time_slot)
    
    features = {
        'instructor_id': instructor_id,
        'day_encoded': day_encoded,
        'day_name': day,
        'time_slot': time_slot,
        'start_hour': time_features['start_hour'],
        'is_morning': time_features['is_morning'],
        'is_mid': time_features['is_mid'],
        'is_afternoon': time_features['is_afternoon'],
    }
    
    # Add frequency features if historical data is available
    if historical_data is not None and not historical_data.empty:
        freq_features = calculate_frequency_features(
            instructor_id, day, time_slot, historical_data
        )
        features.update(freq_features)
    else:
        features.update({
            'freq_instructor_day': 0.0,
            'freq_instructor_time': 0.0,
            'freq_instructor_day_time': 0.0,
            'freq_instructor_total': 0.0,
        })
    
    return features


def prepare_training_data(
    historical_assignments: List[Dict],
    min_samples_per_instructor: int = 3
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Prepare training data from historical assignments.
    
    Args:
        historical_assignments: List of dictionaries with assignment data
        min_samples_per_instructor: Minimum samples required per instructor
        
    Returns:
        Tuple of (X DataFrame, y Series) for model training
    """
    if not historical_assignments:
        return pd.DataFrame(), pd.Series()
    
    # Convert to DataFrame
    df = pd.DataFrame(historical_assignments)
    
    # Create a DataFrame for frequency calculation
    historical_df = df.copy()
    
    # Extract features for each assignment
    feature_rows = []
    for _, row in df.iterrows():
        features = extract_features(
            instructor_id=row['instructor_id'],
            day=row['day'],
            time_slot=row['time_slot'],
            historical_data=historical_df
        )
        feature_rows.append(features)
    
    # Create feature DataFrame
    feature_df = pd.DataFrame(feature_rows)
    
    # Define feature columns for training
    feature_columns = [
        'day_encoded',
        'start_hour',
        'is_morning',
        'is_mid',
        'is_afternoon',
        'freq_instructor_day',
        'freq_instructor_time',
        'freq_instructor_day_time',
    ]
    
    X = feature_df[feature_columns]
    
    # Create labels based on frequency
    # Higher frequency = higher preference (label = 1 if above median)
    median_freq = feature_df['freq_instructor_day_time'].median()
    y = (feature_df['freq_instructor_day_time'] > median_freq).astype(int)
    
    return X, y, feature_columns


def get_preference_label(
    instructor_id: int,
    day: str,
    time_slot: str,
    historical_data: pd.DataFrame
) -> int:
    """
    Generate preference label for training data.
    Label = 1 if instructor frequently teaches at this day/time, 0 otherwise.
    
    Args:
        instructor_id: ID of the instructor
        day: Day of the week
        time_slot: Time slot string
        historical_data: DataFrame with historical assignments
        
    Returns:
        Binary label (0 or 1)
    """
    if historical_data.empty:
        return 0
    
    # Calculate frequency for this instructor-day-time
    freq_features = calculate_frequency_features(
        instructor_id, day, time_slot, historical_data
    )
    
    # Label as 1 if frequency is above a threshold (e.g., 20%)
    threshold = 0.2
    return 1 if freq_features['freq_instructor_day_time'] >= threshold else 0


def create_global_features(
    day: str,
    time_slot: str
) -> np.ndarray:
    """
    Create feature vector for global model prediction (without instructor-specific features).
    
    Args:
        day: Day of the week
        time_slot: Time slot string
        
    Returns:
        NumPy array of features
    """
    day_encoded = encode_day(day)
    time_features = encode_time_slot(time_slot)
    
    features = [
        day_encoded,
        time_features['start_hour'],
        time_features['is_morning'],
        time_features['is_mid'],
        time_features['is_afternoon'],
        0.0,  # freq_instructor_day (not applicable for global)
        0.0,  # freq_instructor_time (not applicable for global)
        0.0,  # freq_instructor_day_time (not applicable for global)
    ]
    
    return np.array(features).reshape(1, -1)

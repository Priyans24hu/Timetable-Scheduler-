"""
Preference Integration Module for Genetic Algorithm

This module provides:
- Preference score calculation for schedule classes
- Integration with GA fitness function
- Weight management for preference optimization
- Caching of preference scores for performance
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from functools import lru_cache

# Django imports
from django.core.cache import cache

# Local imports
from ..models import Instructor, FacultyPreference, MeetingTime
from .preference_model import predict_preference


# Default preference weight (can be adjusted)
DEFAULT_PREFERENCE_WEIGHT = 0.15
PREFERENCE_WEIGHT_KEY = 'preference_weight'

# Cache timeout in seconds (1 hour)
CACHE_TIMEOUT = 3600


def get_preference_weight() -> float:
    """
    Get the current preference weight for fitness calculation.
    
    Returns:
        Preference weight (0.0 to 1.0)
    """
    # Try to get from cache first
    weight = cache.get(PREFERENCE_WEIGHT_KEY)
    if weight is not None:
        return float(weight)
    return DEFAULT_PREFERENCE_WEIGHT


def set_preference_weight(weight: float):
    """
    Set the preference weight for fitness calculation.
    
    Args:
        weight: New weight value (0.0 to 1.0)
    """
    weight = max(0.0, min(1.0, weight))  # Clamp between 0 and 1
    cache.set(PREFERENCE_WEIGHT_KEY, weight, timeout=None)


def calculate_preference_score(
    instructor_id: int,
    meeting_time,
    use_cache: bool = True
) -> Tuple[float, float]:
    """
    Calculate preference score for a faculty-time combination.
    
    Args:
        instructor_id: ID of the instructor
        meeting_time: MeetingTime object (has day and time attributes)
        use_cache: Whether to use caching for performance
        
    Returns:
        Tuple of (preference_score, confidence)
    """
    if meeting_time is None:
        return 0.5, 0.0  # Neutral score with no confidence
    
    day = meeting_time.day
    time_slot = meeting_time.time
    
    # Create cache key
    if use_cache:
        cache_key = f"pref_score:{instructor_id}:{day}:{time_slot}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result['score'], cached_result['confidence']
    
    # Get prediction
    prediction = predict_preference(instructor_id, day, time_slot)
    
    score = prediction.get('preference_score', 0.5)
    confidence = prediction.get('confidence', 0.0)
    
    # Cache the result
    if use_cache:
        cache.set(cache_key, {'score': score, 'confidence': confidence}, timeout=CACHE_TIMEOUT)
    
    return score, confidence


def calculate_schedule_preference_score(
    classes: List,
    aggregation_method: str = 'mean'
) -> Dict[str, float]:
    """
    Calculate aggregate preference score for an entire schedule.
    
    Args:
        classes: List of Class objects in the schedule
        aggregation_method: How to aggregate scores ('mean', 'min', 'weighted')
        
    Returns:
        Dictionary with aggregate scores
    """
    if not classes:
        return {
            'average_score': 0.5,
            'min_score': 0.5,
            'weighted_score': 0.5,
            'total_classes': 0,
        }
    
    scores = []
    confidences = []
    
    for class_obj in classes:
        if class_obj.instructor and class_obj.meeting_time:
            score, confidence = calculate_preference_score(
                class_obj.instructor.id,
                class_obj.meeting_time
            )
            scores.append(score)
            confidences.append(confidence)
    
    if not scores:
        return {
            'average_score': 0.5,
            'min_score': 0.5,
            'weighted_score': 0.5,
            'total_classes': 0,
        }
    
    scores_array = np.array(scores)
    confidences_array = np.array(confidences)
    
    # Calculate different aggregation methods
    average_score = np.mean(scores_array)
    min_score = np.min(scores_array)
    
    # Weighted by confidence (higher confidence = more weight)
    if np.sum(confidences_array) > 0:
        weighted_score = np.average(scores_array, weights=confidences_array)
    else:
        weighted_score = average_score
    
    # Percentage of high-preference assignments (score > 0.7)
    high_preference_ratio = np.mean(scores_array > 0.7)
    
    return {
        'average_score': float(average_score),
        'min_score': float(min_score),
        'weighted_score': float(weighted_score),
        'high_preference_ratio': float(high_preference_ratio),
        'total_classes': len(scores),
    }


def integrate_preference_with_fitness(
    base_fitness: float,
    preference_score: float,
    num_conflicts: int,
    weight: Optional[float] = None
) -> float:
    """
    Integrate preference score with GA fitness value.
    
    Formula: Fitness = Base Score - Conflict Penalty + Preference Score * Weight
    
    Args:
        base_fitness: Base fitness from conflict resolution
        preference_score: Preference score (0.0 to 1.0)
        num_conflicts: Number of conflicts in schedule
        weight: Preference weight (uses default if not provided)
        
    Returns:
        Integrated fitness score
    """
    if weight is None:
        weight = get_preference_weight()
    
    # Base fitness from conflict resolution (1 / (conflicts + 1))
    # This is already calculated in the original fitness function
    
    # Preference bonus: add preference_score * weight
    # Scale preference contribution based on conflict penalty
    conflict_penalty = num_conflicts * 0.1  # Each conflict reduces fitness
    
    # Calculate final fitness
    # Fitness = Base - Penalty + Preference_Bonus
    # Preference bonus is scaled so it doesn't override hard constraints
    preference_bonus = preference_score * weight * (1.0 / (num_conflicts + 1))
    
    final_fitness = base_fitness + preference_bonus
    
    return final_fitness


def get_instructor_preference_summary(instructor_id: int) -> Dict:
    """
    Get preference summary for an instructor.
    
    Args:
        instructor_id: ID of the instructor
        
    Returns:
        Dictionary with preference summary
    """
    try:
        instructor = Instructor.objects.get(id=instructor_id)
    except Instructor.DoesNotExist:
        return {'error': 'Instructor not found'}
    
    # Get all preferences for this instructor
    preferences = FacultyPreference.objects.filter(
        instructor=instructor
    ).order_by('-preference_score')
    
    if not preferences.exists():
        return {
            'instructor_id': instructor_id,
            'instructor_name': instructor.name,
            'has_preferences': False,
            'message': 'No preference data available for this instructor',
        }
    
    # Group by day
    day_preferences = defaultdict(list)
    for pref in preferences:
        day_preferences[pref.preferred_day].append({
            'time_slot': pref.preferred_time,
            'score': pref.preference_score,
            'confidence': pref.confidence,
        })
    
    # Get top preferences
    top_preferences = []
    for pref in preferences[:5]:  # Top 5
        top_preferences.append({
            'day': pref.preferred_day,
            'time_slot': pref.preferred_time,
            'score': pref.preference_score,
            'confidence': pref.confidence,
        })
    
    # Get least preferred slots
    least_preferences = []
    for pref in preferences.order_by('preference_score')[:5]:  # Bottom 5
        least_preferences.append({
            'day': pref.preferred_day,
            'time_slot': pref.preferred_time,
            'score': pref.preference_score,
            'confidence': pref.confidence,
        })
    
    # Calculate statistics
    scores = [p.preference_score for p in preferences]
    avg_score = np.mean(scores)
    
    return {
        'instructor_id': instructor_id,
        'instructor_name': instructor.name,
        'has_preferences': True,
        'total_preferences': len(preferences),
        'average_score': float(avg_score),
        'top_preferences': top_preferences,
        'least_preferred': least_preferences,
        'preferences_by_day': dict(day_preferences),
    }


def invalidate_preference_cache():
    """
    Invalidate all cached preference scores.
    Call this after training a new model or updating preferences.
    """
    # Note: This is a simple implementation. In production, you might use
    # a more sophisticated cache invalidation strategy.
    cache.delete_pattern("pref_score:*")


def get_preference_statistics() -> Dict:
    """
    Get system-wide preference statistics.
    
    Returns:
        Dictionary with preference statistics
    """
    from ..models import FacultyPreference, Instructor
    
    total_instructors = Instructor.objects.count()
    instructors_with_preferences = FacultyPreference.objects.values(
        'instructor'
    ).distinct().count()
    
    total_preferences = FacultyPreference.objects.count()
    
    if total_preferences > 0:
        avg_score = FacultyPreference.objects.all().aggregate(
            avg_score=models.Avg('preference_score')
        )['avg_score'] or 0.0
        
        high_prefs = FacultyPreference.objects.filter(
            preference_score__gte=0.7
        ).count()
        
        low_prefs = FacultyPreference.objects.filter(
            preference_score__lte=0.3
        ).count()
    else:
        avg_score = 0.0
        high_prefs = 0
        low_prefs = 0
    
    return {
        'total_instructors': total_instructors,
        'instructors_with_preferences': instructors_with_preferences,
        'coverage_percent': (instructors_with_preferences / total_instructors * 100) 
                          if total_instructors > 0 else 0.0,
        'total_preferences': total_preferences,
        'average_preference_score': float(avg_score),
        'high_preferences': high_prefs,
        'low_preferences': low_prefs,
        'preference_weight': get_preference_weight(),
    }


# Import models at the end to avoid circular imports
from .. import models

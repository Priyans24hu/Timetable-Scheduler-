from django.contrib import admin
from .models import *

# ==================== EXISTING MODELS ====================
admin.site.register(Room)
admin.site.register(Instructor)
admin.site.register(MeetingTime)
admin.site.register(Course)
admin.site.register(Department)
admin.site.register(Section)


# ==================== TIMETABLE EXPORT MODELS ====================
@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = (
        'section', 'course', 'instructor', 'room', 'meeting_time', 
        'day', 'time_slot', 'status_indicator', 'is_locked', 'has_conflict',
        'preference_score', 'entry_type', 'is_active'
    )
    list_filter = (
        'is_active', 'has_conflict', 'is_locked', 'entry_type',
        'generation_batch', 'meeting_time__day', 'instructor'
    )
    search_fields = (
        'section__section_id', 'course__course_name', 
        'instructor__name', 'room__r_number'
    )
    ordering = ('meeting_time__day', 'meeting_time__time')
    
    fieldsets = (
        ('Class Information', {
            'fields': ('section', 'course', 'instructor', 'room', 'meeting_time')
        }),
        ('Status & Metadata', {
            'fields': ('is_active', 'entry_type', 'is_locked', 'has_conflict', 'generation_batch')
        }),
        ('AI & Analytics', {
            'fields': ('preference_score', 'conflict_details'),
            'classes': ('collapse',)
        }),
        ('Modification History', {
            'fields': ('modified_by', 'last_modified', 'generated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('last_modified', 'generated_at', 'day', 'time_slot', 'status_indicator')
    
    actions = ['lock_entries', 'unlock_entries', 'mark_as_resolved']
    
    def day(self, obj):
        return obj.day
    day.short_description = 'Day'
    
    def time_slot(self, obj):
        return obj.time_slot
    time_slot.short_description = 'Time Slot'
    
    def status_indicator(self, obj):
        return obj.status_indicator
    status_indicator.short_description = 'Status'
    
    def lock_entries(self, request, queryset):
        queryset.update(is_locked=True)
    lock_entries.short_description = "Lock selected entries (preserve during regeneration)"
    
    def unlock_entries(self, request, queryset):
        queryset.update(is_locked=False)
    unlock_entries.short_description = "Unlock selected entries"
    
    def mark_as_resolved(self, request, queryset):
        queryset.update(has_conflict=False, conflict_details={})
    mark_as_resolved.short_description = "Mark selected entries as resolved"


@admin.register(ConflictLog)
class ConflictLogAdmin(admin.ModelAdmin):
    list_display = ('entry', 'conflict_type', 'is_resolved', 'detected_at', 'resolution_method')
    list_filter = ('conflict_type', 'is_resolved', 'detected_at', 'resolution_method')
    search_fields = ('entry__section__section_id', 'entry__course__course_name', 'message')
    ordering = ('-detected_at',)
    
    fieldsets = (
        ('Conflict Details', {
            'fields': ('entry', 'conflict_type', 'message', 'conflicting_entry')
        }),
        ('Resolution', {
            'fields': ('is_resolved', 'resolved_at', 'resolution_method')
        }),
    )
    readonly_fields = ('detected_at', 'resolved_at')
    
    actions = ['mark_resolved']
    
    def mark_resolved(self, request, queryset):
        for conflict in queryset.filter(is_resolved=False):
            conflict.mark_resolved('manual_admin')
    mark_resolved.short_description = "Mark selected conflicts as resolved"


@admin.register(GenerationLog)
class GenerationLogAdmin(admin.ModelAdmin):
    list_display = ('batch_id', 'generated_at', 'fitness_score', 'total_entries', 'conflicts', 'is_active')
    list_filter = ('is_active', 'generated_at')
    search_fields = ('batch_id',)
    ordering = ('-generated_at',)


# ==================== AI-BASED FACULTY PREFERENCE LEARNING MODELS ====================
@admin.register(HistoricalTimetableData)
class HistoricalTimetableDataAdmin(admin.ModelAdmin):
    list_display = ('instructor', 'day', 'time_slot', 'course', 'section', 'created_at')
    list_filter = ('day', 'source_generation_batch', 'created_at')
    search_fields = ('instructor__name', 'course__course_name', 'section__section_id')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'


@admin.register(FacultyPreference)
class FacultyPreferenceAdmin(admin.ModelAdmin):
    list_display = ('instructor', 'preferred_day', 'preferred_time', 'preference_score', 'confidence', 'frequency_count')
    list_filter = ('preferred_day', 'model_version')
    search_fields = ('instructor__name', 'preferred_day', 'preferred_time')
    ordering = ('-preference_score',)
    
    fieldsets = (
        ('Instructor & Time', {
            'fields': ('instructor', 'preferred_day', 'preferred_time')
        }),
        ('ML Prediction', {
            'fields': ('preference_score', 'confidence', 'frequency_count', 'model_version')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MLModelMetadata)
class MLModelMetadataAdmin(admin.ModelAdmin):
    list_display = ('model_version', 'model_type', 'training_date', 'accuracy', 'training_samples', 'is_active')
    list_filter = ('model_type', 'is_active', 'training_date')
    search_fields = ('model_version', 'model_path')
    ordering = ('-training_date',)
    
    fieldsets = (
        ('Model Information', {
            'fields': ('model_version', 'model_type', 'model_path', 'is_active')
        }),
        ('Training Details', {
            'fields': ('training_date', 'training_samples', 'accuracy', 'feature_columns')
        }),
    )
    readonly_fields = ('training_date',)

from django.urls import path
from .views import *

urlpatterns = [
    path('', home, name='home'),
    path('timetableGeneration/', timetable, name='timetable'),

    path('instructorAdd/', instructorAdd, name='instructorAdd'),
    path('instructorEdit/', instructorEdit, name='instructorEdit'),
    path('instructorDelete/<int:pk>/', instructorDelete, name='deleteinstructor'),

    path('roomAdd/', roomAdd, name='roomAdd'),
    path('roomEdit/', roomEdit, name='roomEdit'),
    path('roomDelete/<int:pk>/', roomDelete, name='deleteroom'),

    path('meetingTimeAdd/', meetingTimeAdd, name='meetingTimeAdd'),
    path('meetingTimeEdit/', meetingTimeEdit, name='meetingTimeEdit'),
    path('meetingTimeDelete/<str:pk>/', meetingTimeDelete, name='deletemeetingtime'),

    path('courseAdd/', courseAdd, name='courseAdd'),
    path('courseEdit/', courseEdit, name='courseEdit'),
    path('courseDelete/<str:pk>/', courseDelete, name='deletecourse'),

    path('departmentAdd/', departmentAdd, name='departmentAdd'),
    path('departmentEdit/', departmentEdit, name='departmentEdit'),
    path('departmentDelete/<int:pk>/', departmentDelete, name='deletedepartment'),

    path('sectionAdd/', sectionAdd, name='sectionAdd'),
    path('sectionEdit/', sectionEdit, name='sectionEdit'),
    path('sectionDelete/<str:pk>/', sectionDelete, name='deletesection'),

    path('api/genNum/', apiGenNum, name='apiGenNum'),
    path('api/terminateGens/', apiterminateGens, name='apiterminateGens'),
    
    # PDF Export and Generation History URLs
    path('timetable/pdf/', timetable_pdf, name='timetable_pdf'),
    path('timetable/pdf/<str:batch_id>/', timetable_pdf, name='timetable_pdf_batch'),
    path('timetable/stored/', view_stored_timetable, name='view_stored_timetable'),
    path('timetable/stored/<str:batch_id>/', view_stored_timetable, name='view_stored_timetable_batch'),
    path('timetable/history/', generation_history, name='generation_history'),
    path('timetable/activate/<str:batch_id>/', activate_generation_view, name='activate_generation'),
    path('timetable/delete/<str:batch_id>/', delete_generation_view, name='delete_generation'),
    
    # AI-BASED FACULTY PREFERENCE LEARNING API ENDPOINTS
    path('api/predict-preference/', api_predict_preference, name='api_predict_preference'),
    path('api/train-model/', api_train_model, name='api_train_model'),
    path('api/faculty-preferences/', api_faculty_preferences, name='api_faculty_preferences'),
    path('api/faculty-preferences/<int:instructor_id>/', api_faculty_preferences, name='api_faculty_preferences_detail'),
    path('api/preference-statistics/', api_preference_statistics, name='api_preference_statistics'),
    path('api/set-preference-weight/', api_set_preference_weight, name='api_set_preference_weight'),
    
    # INTELLIGENT EDITING SYSTEM API ENDPOINTS
    path('api/check-conflict/', api_check_conflict, name='api_check_conflict'),
    path('api/suggest', api_suggest, name='api_suggest'),
    path('api/quick-fix/<int:entry_id>/', api_quick_fix, name='api_quick_fix'),
    path('api/update-entry/<int:entry_id>/', api_update_entry, name='api_update_entry'),
    path('api/auto-fix', api_auto_fix, name='api_auto_fix'),
    path('api/toggle-lock/<int:entry_id>', api_toggle_lock, name='api_toggle_lock'),
    path('api/validate-all/', api_validate_all, name='api_validate_all'),
    path('api/conflict-summary', api_get_conflict_summary, name='api_conflict_summary'),
    
    # CONFLICT LOG PAGE - Task 8
    path('conflict-log/', conflict_log_view, name='conflict_log'),
    
    # PREFERENCE HEATMAP - Task 9
    path('preference-heatmap/', preference_heatmap_view, name='preference_heatmap'),
    path('api/preference-heatmap/', api_preference_heatmap, name='api_preference_heatmap'),
]

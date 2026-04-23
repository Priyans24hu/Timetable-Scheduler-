# Timetable Scheduler - Complete Project Documentation

## 1. PROJECT OVERVIEW

The **Timetable Scheduler** is an intelligent, AI-enhanced web application designed to automate and optimize university timetable generation. It utilizes **Genetic Algorithms** for schedule optimization while incorporating modern UI/UX features for efficient timetable management.

### Key Objectives:
- Automate timetable generation using evolutionary algorithms
- Minimize scheduling conflicts through constraint satisfaction
- Provide an intuitive interface for manual adjustments
- Enable data-driven decisions through analytics and visualizations
- Support faculty preference learning through AI/ML integration

---

## 2. TECHNOLOGY STACK

### Backend Architecture
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | Django 4.x | Web framework for rapid development |
| **Language** | Python 3.9+ | Core programming language |
| **Database** | SQLite (default) / PostgreSQL | Data persistence |
| **Algorithm** | Genetic Algorithm | Schedule optimization engine |
| **ML/AI** | scikit-learn, pandas, numpy | Preference learning & prediction |
| **API** | Django REST (JSON) | Frontend-backend communication |

### Frontend Architecture
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Templating** | Django Templates | Server-side rendering |
| **Styling** | CSS3 + Custom CSS | Responsive design |
| **Interactivity** | Vanilla JavaScript | Dynamic UI behavior |
| **Icons** | Emoji + Font Awesome | Visual indicators |
| **Charts** | CSS-based Heatmaps | Data visualization |

### External Libraries
```
Django==4.x
scikit-learn>=1.0
pandas>=1.3
numpy>=1.21
joblib>=1.0
```

---

## 3. SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                      │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐  │
│  │  Dashboard   │ │  Timetable   │ │   Conflict Log      │  │
│  │   (Task 6)   │ │   (Tasks     │ │    (Task 8)         │  │
│  │              │ │    1-5,7,10) │ │                     │  │
│  └──────────────┘ └──────────────┘ └─────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐                        │
│  │   Heatmap    │ │   Entities   │ │                       │
│  │   (Task 9)   │ │  Management  │ │                       │
│  └──────────────┘ └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                       │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              Django Views & Controllers                │   │
│  │  • Timetable Generation View                          │   │
│  │  • Entity CRUD Views (Rooms, Instructors, etc.)       │   │
│  │  • Intelligent Editing APIs (Tasks 1-10)              │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                           │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐  │
│  │   Genetic    │ │  Constraint  │ │  Suggestion Engine  │  │
│  │  Algorithm   │ │    Engine    │ │    (Task 4)         │  │
│  │              │ │              │ │                     │  │
│  └──────────────┘ └──────────────┘ └─────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐  │
│  │  Preference  │ │ Preference   │ │  Auto-Fix Engine    │  │
│  │    Model     │ │ Integration  │ │    (Task 3)         │  │
│  │   (ML/AI)    │ │              │ │                     │  │
│  └──────────────┘ └──────────────┘ └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       DATA LAYER                             │
│  ┌───────────────────────────────────────────────────────┐   │
│  │                    Django Models                       │   │
│  │  • Room, Instructor, MeetingTime, Course              │   │
│  │  • Department, Section, TimetableEntry              │   │
│  │  • GenerationLog, ConflictLog, HistoricalData        │   │
│  │  • FacultyPreference, MLModelMetadata                │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. DATABASE MODELS (Detailed)

### Core Models

#### 1. Room Model
```python
class Room(models.Model):
    r_number = models.CharField(max_length=10)      # Room number (e.g., "101")
    seating_capacity = models.IntegerField()         # Maximum capacity
    has_projector = models.BooleanField(default=False)
    has_computers = models.BooleanField(default=False)  # For labs
    room_type = models.CharField(max_length=20, choices=[
        ('classroom', 'Classroom'),
        ('lab', 'Computer Lab'),
        ('hall', 'Lecture Hall'),
        ('seminar', 'Seminar Room')
    ])
```
**Purpose**: Stores classroom and laboratory information with capacity and equipment details.

#### 2. Instructor Model
```python
class Instructor(models.Model):
    uid = models.CharField(max_length=10)           # Unique instructor ID
    name = models.CharField(max_length=100)          # Instructor name
    email = models.EmailField()
    department = models.ForeignKey('Department')
    preferred_days = models.JSONField(default=list)  # ['Mon', 'Wed', 'Fri']
    unavailable_slots = models.JSONField(default=list)  # Time slots
    max_consecutive_hours = models.IntegerField(default=4)
```
**Purpose**: Faculty information with preference and availability constraints.

#### 3. Course Model
```python
class Course(models.Model):
    course_number = models.CharField(max_length=10)  # Course code
    course_name = models.CharField(max_length=100)  # Full name
    department = models.ForeignKey('Department')
    max_numb_students = models.IntegerField()        # Enrollment limit
    credit_hours = models.IntegerField(default=3)
    course_type = models.CharField(choices=[
        ('lecture', 'Lecture'),
        ('lab', 'Laboratory'),
        ('seminar', 'Seminar')
    ])
    requires_lab = models.BooleanField(default=False)
```
**Purpose**: Course catalog with capacity and type information.

#### 4. MeetingTime Model
```python
class MeetingTime(models.Model):
    pid = models.CharField(max_length=10)           # Period ID
    time = models.CharField(max_length=50)          # Time range (e.g., "09:00-10:30")
    day = models.CharField(max_length=15, choices=[
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday')
    ])
    duration_minutes = models.IntegerField(default=90)
```
**Purpose**: Time slot definitions for scheduling.

#### 5. Department Model
```python
class Department(models.Model):
    dept_name = models.CharField(max_length=100)
    building = models.CharField(max_length=50)
    head_instructor = models.ForeignKey('Instructor', null=True)
```
**Purpose**: Department organization and management.

#### 6. Section Model
```python
class Section(models.Model):
    section_id = models.CharField(max_length=10)    # Section code
    department = models.ForeignKey('Department')
    num_class_in_week = models.IntegerField()       # Classes per week
    course = models.ForeignKey('Course')
    instructor = models.ForeignKey('Instructor')
    meeting_time = models.ForeignKey('MeetingTime')
    room = models.ForeignKey('Room')
    semester = models.CharField(max_length=20)
    year = models.IntegerField()
```
**Purpose**: Links courses, instructors, times, and rooms - the core scheduling unit.

---

### AI/ML & Logging Models

#### 7. TimetableEntry Model (Enhanced)
```python
class TimetableEntry(models.Model):
    # Core Fields
    entry_id = models.AutoField(primary_key=True)
    section = models.ForeignKey('Section')
    course = models.ForeignKey('Course')
    instructor = models.ForeignKey('Instructor')
    room = models.ForeignKey('Room')
    meeting_time = models.ForeignKey('MeetingTime')
    
    # UI Enhancement Fields (Tasks 1-10)
    is_locked = models.BooleanField(default=False)       # Task 2
    has_conflict = models.BooleanField(default=False)     # Task 1
    entry_type = models.CharField(max_length=20, choices=[
        ('manual', 'Manual Entry'),                        # Task 7
        ('auto', 'Auto Generated'),
        ('hybrid', 'Hybrid')
    ], default='auto')
    
    # AI/ML Fields
    preference_score = models.FloatField(null=True, blank=True)
    confidence_score = models.FloatField(default=0.0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    generated_by = models.ForeignKey(User, null=True)
```
**Purpose**: Individual timetable slots with conflict tracking and preference scoring.

#### 8. GenerationLog Model
```python
class GenerationLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User)
    parameters = models.JSONField()                    # GA parameters used
    population_size = models.IntegerField()
    mutation_rate = models.FloatField()
    crossover_rate = models.FloatField()
    best_fitness = models.FloatField()
    number_of_conflicts = models.IntegerField()
    execution_time_seconds = models.FloatField()
    success = models.BooleanField()
```
**Purpose**: Audit trail for timetable generation attempts.

#### 9. ConflictLog Model (Task 8)
```python
class ConflictLog(models.Model):
    entry = models.ForeignKey('TimetableEntry')
    conflict_type = models.CharField(max_length=20, choices=[
        ('room_double_booked', 'Room Double Booked'),
        ('instructor_double_booked', 'Instructor Double Booked'),
        ('room_capacity', 'Room Capacity Exceeded'),
        ('instructor_preference', 'Instructor Preference Violation'),
        ('prerequisite', 'Prerequisite Not Met'),
        ('time_preference', 'Time Slot Preference Violation')
    ])
    severity = models.CharField(max_length=10, choices=[
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low')
    ])
    description = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored')
    ], default='pending')
    resolution_action = models.TextField(blank=True)
```
**Purpose**: Comprehensive conflict tracking and resolution history.

#### 10. HistoricalTimetableData Model (ML Training)
```python
class HistoricalTimetableData(models.Model):
    # Features for ML training
    section = models.ForeignKey('Section')
    instructor = models.ForeignKey('Instructor')
    course = models.ForeignKey('Course')
    room = models.ForeignKey('Room')
    meeting_time = models.ForeignKey('MeetingTime')
    day_of_week = models.IntegerField()  # 0-6
    time_slot_index = models.IntegerField()
    
    # Labels
    was_successful = models.BooleanField()
    preference_score = models.FloatField()
    conflict_occurred = models.BooleanField()
    instructor_satisfaction = models.FloatField()
    
    # Metadata
    semester = models.CharField(max_length=20)
    year = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
```
**Purpose**: Training data for ML preference prediction.

#### 11. FacultyPreference Model
```python
class FacultyPreference(models.Model):
    instructor = models.ForeignKey('Instructor')
    day_of_week = models.IntegerField(choices=[(i, day) for i, day in enumerate([
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'
    ])])
    time_slot = models.CharField(max_length=20)
    preference_score = models.FloatField()  # 0.0 to 1.0
    weight = models.FloatField(default=1.0)
    source = models.CharField(max_length=20, choices=[
        ('explicit', 'Explicitly Stated'),
        ('inferred', 'ML Inferred'),
        ('historical', 'Historical Data')
    ])
    updated_at = models.DateTimeField(auto_now=True)
```
**Purpose**: Faculty preference storage with ML inference support.

#### 12. MLModelMetadata Model
```python
class MLModelMetadata(models.Model):
    model_name = models.CharField(max_length=100)
    model_type = models.CharField(max_length=50)  # 'RandomForest', 'SVM', etc.
    version = models.CharField(max_length=20)
    accuracy = models.FloatField()
    precision = models.FloatField()
    recall = models.FloatField()
    f1_score = models.FloatField()
    training_data_count = models.IntegerField()
    last_trained_at = models.DateTimeField(auto_now=True)
    model_file_path = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
```
**Purpose**: ML model versioning and performance tracking.

---

## 5. FEATURES (All 10 UI Tasks + Core Features)

### Core Features

#### 1. Genetic Algorithm Timetable Generation
- **Population Size**: Configurable (default: 100)
- **Selection**: Tournament selection
- **Crossover**: Single-point crossover
- **Mutation**: Adaptive mutation rate
- **Elitism**: Top 10% preserved
- **Termination**: Max generations or fitness threshold

#### 2. Constraint Satisfaction
| Hard Constraints | Soft Constraints |
|-----------------|------------------|
| No room double-booking | Instructor time preferences |
| No instructor double-booking | Course distribution balance |
| Room capacity <= enrollment | Minimize back-to-back classes |
| Required equipment available | Preferred time slots |
| No prerequisite conflicts | Even weekly distribution |

---

### UI Enhancement Tasks (1-10)

#### Task 1: Conflict Visual Indicators
```
Features:
• Red border highlighting on conflicting entries
• ⚠️ Warning icon on conflict cells
• Hover tooltip showing conflict details
• Real-time conflict detection
• CSS classes: .conflict, .entry-status.conflict
```

#### Task 2: Lock/Unlock Toggle Buttons
```
Features:
• 🔒 Lock button on each entry
• 🔓 Unlock button for locked entries
• Locked entries excluded from auto-fix
• Visual lock icon indicator
• API endpoint: /api/toggle-lock/<id>/
```

#### Task 3: Conflict Alert Panel
```
Features:
• Top banner showing conflict count
• Severity-based color coding
• Quick "Auto-Fix" button
• Dismissible alerts
• Links to conflict log page
• Real-time updates
```

#### Task 4: Suggestion Sidebar
```
Features:
• Slide-out panel from right
• AI-generated alternative suggestions
• Preference-based slot rankings
• One-click apply suggestion
• Confidence scores displayed
• API endpoint: /api/suggest
```

#### Task 5: Enhanced Entry Detail Modal
```
Features:
• Popup modal on entry click
• Full entry details display
• Section, Course, Instructor info
• Room and Time details
• Conflict status and suggestions
• Quick actions (Edit, Delete, Resolve)
```

#### Task 6: Dashboard Widgets
```
Features (on Home Page):
• 📊 Total Classes widget
• ⚠️ Conflicts Detected widget
• 📅 Today's Schedule widget
• 🎯 Quick Actions widget
• 📈 Last Generated widget
• Live data from API endpoints
• Color-coded status indicators
```

#### Task 7: Filter & Search Bar
```
Features:
• 🔍 Search by course/faculty name
• 📅 Filter by day (dropdown)
• 🏷️ Filter by entry type (Manual/Auto/Hybrid)
• ⚡ Filter by status (Conflict/Locked/OK)
• Real-time filtering
• Clear filters button
• Results count display
```

#### Task 8: Conflict Log Page
```
URL: /conflict-log/

Features:
• Complete conflict history table
• Filter by status (Pending/Resolved)
• Filter by type (Hard/Soft constraint)
• Filter by severity (High/Medium/Low)
• Date range filtering
• Stats cards (Total/Resolved/Pending)
• Action buttons per conflict
• View and Resolve actions
• Auto-fix all button
```

#### Task 9: Preference Heatmap View
```
URL: /preference-heatmap/

Features:
• Visual heatmap grid (Days × Time Slots)
• Color-coded preference scores:
  - Green (0.8-1.0): Excellent
  - Light Green (0.6-0.8): Good
  - Orange (0.4-0.6): Neutral
  - Red (0.0-0.4): Poor
• Instructor selector chips
• Average preference score display
• Best time slot identification
• Hover tooltips with details
• 🤖 Train AI Model button
```

#### Task 10: Batch Action Toolbar
```
Features:
• ☑️ Checkboxes on each timetable entry
• Floating toolbar when entries selected
• "X selected" counter display
• ☑️ Select All button
• 🔒 Batch Lock button
• 🔓 Batch Unlock button
• ✅ Batch Resolve button
• 🗑️ Batch Delete button
• 📤 Batch Export (CSV) button
• ❌ Clear Selection button
• Confirmation dialogs for destructive actions

API Endpoints:
• POST /api/batch-lock/
• POST /api/batch-delete/
• POST /api/batch-resolve/
• GET /api/export-entries/?ids=1,2,3
```

---

## 6. API ENDPOINTS REFERENCE

### Intelligent Editing APIs
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/conflict-summary` | GET | Get conflict statistics |
| `/api/validate-all/` | POST | Validate entire timetable |
| `/api/auto-fix` | POST | Auto-resolve conflicts |
| `/api/suggest` | GET | Get AI suggestions |
| `/api/quick-fix/<id>/` | POST | Fix specific entry |
| `/api/toggle-lock/<id>/` | POST | Lock/unlock entry |

### Batch Action APIs (Task 10)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/batch-lock/` | POST | Lock multiple entries |
| `/api/batch-delete/` | POST | Delete multiple entries |
| `/api/batch-resolve/` | POST | Resolve multiple conflicts |
| `/api/export-entries/` | GET | Export as CSV |

### Preference Heatmap APIs (Task 9)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/preference-heatmap/` | GET | Get heatmap data |
| `/api/train-model/` | POST | Train ML model |

---

## 7. GENETIC ALGORITHM DETAILS

### Algorithm Parameters
```python
POPULATION_SIZE = 100
MAX_GENERATIONS = 1000
MUTATION_RATE = 0.01
CROSSOVER_RATE = 0.9
ELITISM_COUNT = 10
```

### Fitness Function
```
Fitness = 1 / (1 + NumberOfConflicts + SoftConstraintPenalties)

Where:
- Hard Constraint Violation: +100 penalty
- Soft Constraint Violation: +10 penalty
- Preference Score Bonus: -0.5 (if favorable)
```

### Selection Method
**Tournament Selection**: Randomly select 5 individuals, pick the best.

### Crossover Method
**Single-Point Crossover**: Split schedule at random point, swap segments.

### Mutation Method
**Swap Mutation**: Randomly swap two class assignments.

---

## 8. ML/AI PREFERENCE LEARNING

### Model Architecture
```
Input Features:
├── Instructor ID (encoded)
├── Day of Week (0-4)
├── Time Slot Index
├── Course Type
├── Historical Satisfaction Score
└── Previous Semester Success

Output:
└── Preference Score (0.0 - 1.0)
```

### Training Pipeline
1. Collect historical timetable data
2. Engineer features from past schedules
3. Train RandomForest Regressor
4. Evaluate with cross-validation
5. Deploy model for predictions
6. Continuously retrain with new data

### Prediction Usage
- Generate preference heatmap
- Rank alternative time slots
- Optimize schedule for faculty satisfaction

---

## 9. INSTALLATION & SETUP

### Prerequisites
```bash
Python 3.9+
 pip
virtualenv (recommended)
```

### Installation Steps
```bash
# 1. Clone repository
git clone https://github.com/Priyans24hu/Timetable-Scheduler-.git
cd Timetable-Scheduler

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run migrations
python manage.py migrate

# 6. Create superuser (admin)
python manage.py createsuperuser

# 7. Run development server
python manage.py runserver

# 8. Access application
# Open browser: http://127.0.0.1:8000/
```

### Default Credentials
```
Admin User:
  Username: admin
  Password: admin123

Test User:
  Username: testuser
  Password: testpass
```

---

## 10. PROJECT STRUCTURE

```
TimetableScheduler/
├── SchedulerApp/                    # Main Django App
│   ├── models.py                    # All 12+ models
│   ├── views.py                     # Views + GA implementation
│   ├── urls.py                      # URL routing
│   ├── admin.py                     # Admin configurations
│   ├── forms.py                     # Django forms
│   ├── services/                    # Service layer
│   │   ├── __init__.py
│   │   ├── constraint_engine.py     # Hard/soft constraint validation
│   │   ├── suggestion_engine.py     # AI suggestion generation
│   │   ├── preference_model.py      # ML model training
│   │   └── preference_integration.py
│   └── tests.py                     # Unit tests
├── templates/                       # HTML Templates
│   ├── base.html                    # Base layout
│   ├── index.html                   # Dashboard (Task 6)
│   ├── timetable_stored.html        # Main timetable (Tasks 1-5,7,10)
│   ├── conflict_log.html            # Conflict log (Task 8)
│   ├── preference_heatmap.html      # Heatmap (Task 9)
│   └── ...                          # Entity management templates
├── static/                          # Static files
│   ├── css/
│   └── js/
├── requirements.txt                 # Python dependencies
├── README.md                        # Basic readme
└── manage.py                        # Django management
```

---

## 11. FUTURE ENHANCEMENTS

### Planned Features
1. **Drag-and-Drop Rescheduling**: Visual timetable editing
2. **Email Notifications**: Alert faculty of schedule changes
3. **Calendar Export**: iCal/Outlook integration
4. **Mobile App**: React Native companion app
5. **Advanced Analytics**: Power BI / Tableau integration
6. **Multi-Campus Support**: Distributed scheduling
7. **Real-time Collaboration**: WebSocket-based live editing

### Research Directions
1. **Reinforcement Learning**: RL-based schedule optimization
2. **Natural Language**: NLP for constraint input
3. **Computer Vision**: OCR for importing paper schedules
4. **Blockchain**: Immutable schedule audit trail

---

## 12. VIVA QUESTIONS & ANSWERS

### Q1: What algorithm is used and why?
**A**: Genetic Algorithm - it's effective for NP-hard scheduling problems, provides multiple good solutions, and handles complex constraints well.

### Q2: How does the conflict detection work?
**A**: Real-time validation checks hard constraints (room/instructor double-booking, capacity) whenever a change is made.

### Q3: What ML technique is used?
**A**: Random Forest regression for preference prediction based on historical data.

### Q4: How are faculty preferences learned?
**A**: Through explicit input, historical schedule success analysis, and inference from patterns.

### Q5: What makes this different from existing systems?
**A**: AI-driven suggestions, preference learning, comprehensive conflict management, and modern UI with batch operations.

---

## 13. CONTRIBUTORS & ACKNOWLEDGMENTS

**Developer**: [Your Name]
**Institution**: [Your College/University]
**Project Duration**: [Time Period]
**Guided By**: [Professor/Supervisor Name]

---

## License

This project is for educational purposes.

---

**Last Updated**: April 2026
**Version**: 2.0 (All 10 UI Tasks Complete)

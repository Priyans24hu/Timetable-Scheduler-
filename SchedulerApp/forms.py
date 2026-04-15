from django.forms import ModelForm
from .models import *
from django import forms
from django.contrib.auth.forms import AuthenticationForm


class UserLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(UserLoginForm, self).__init__(*args, **kwargs)

    username = forms.CharField(widget=forms.TextInput(
        attrs={
            'class': 'form-control',
            'type': 'text',
            'placeholder': 'UserName',
            'id': 'id_username'
        }))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={
            'class': 'form-control',
            'type': 'password',
            'placeholder': 'Password',
            'id': 'id_password',
        }))


class RoomForm(ModelForm):
    class Meta:
        model = Room
        labels = {
            'r_number': 'Room Number',
            'seating_capacity': 'Seating Capacity',
            'room_type': 'Room Type',
            'equipment_available': 'Equipment Available'
        }
        fields = ['r_number', 'seating_capacity', 'room_type', 'equipment_available']


class InstructorForm(ModelForm):
    class Meta:
        model = Instructor
        labels = {
            'uid': 'Faculty ID',
            'name': 'Faculty Name',
            'specialization': 'Specialization',
            'max_courses_per_semester': 'Max Courses/Semester'
        }
        fields = ['uid', 'name', 'specialization', 'max_courses_per_semester']


class MeetingTimeForm(ModelForm):
    class Meta:
        model = MeetingTime
        fields = ['pid', 'time', 'day']
        widgets = {
            'pid': forms.TextInput(),
            'time': forms.Select(),
            'day': forms.Select(),
        }


class CourseForm(ModelForm):
    class Meta:
        model = Course
        labels = {
            'course_name': 'Course Name',
            'course_type': 'Course Type',
            'equipment_required': 'Equipment Required'
        }
        fields = [
            'course_number', 'course_name', 'course_type', 'equipment_required', 'instructors'
        ]


class DepartmentForm(ModelForm):
    class Meta:
        model = Department
        labels = {'dept_name': 'Department name'}
        fields = ['dept_name', 'courses']


class SectionForm(ModelForm):
    class Meta:
        model = Section
        labels = {
            'num_class_in_week': 'Total classes in a week',
            'lectures_per_semester': 'Lectures per semester',
            'strength': 'Section Strength (No. of Students)'
        }
        fields = ['section_id', 'department', 'num_class_in_week', 'lectures_per_semester', 'strength']

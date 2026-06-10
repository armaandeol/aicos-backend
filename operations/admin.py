from django.contrib import admin
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'status', 'class_level', 'section', 'school')
    list_filter = ('school', 'date', 'status', 'class_level', 'section')
    search_fields = ('student__user__first_name', 'student__user__email')
    date_hierarchy = 'date'

# --- NEW ADMIN FOR EXAMINATIONS ---

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'start_date', 'end_date', 'is_published', 'school')
    list_filter = ('school', 'academic_year', 'is_published')
    search_fields = ('name', 'academic_year__name')
    date_hierarchy = 'start_date'

@admin.register(StudentGrade)
class StudentGradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'subject', 'marks_obtained', 'max_marks', 'school')
    list_filter = ('school', 'exam', 'subject')
    search_fields = ('student__user__first_name', 'student__user__email', 'subject__name')

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'section', 'due_date', 'school')
    list_filter = ('school', 'subject', 'section')
    search_fields = ('title', 'subject__name')

@admin.register(StudentSubmission)
class StudentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'grade', 'submitted_at', 'school')
    list_filter = ('school', 'status', 'assignment')
    search_fields = ('student__user__first_name', 'assignment__title')
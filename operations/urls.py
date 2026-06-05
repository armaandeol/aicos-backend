from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AttendanceViewSet, ExamViewSet, StudentGradeViewSet, AssignmentViewSet, StudentSubmissionViewSet

router = DefaultRouter()
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'grades', StudentGradeViewSet, basename='grade')
router.register(r'assignments', AssignmentViewSet, basename='assignment')
router.register(r'submissions', StudentSubmissionViewSet, basename='submission')

urlpatterns = [
    path('', include(router.urls)),
]
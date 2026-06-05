from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from tenants.views import TenantAwareModelViewSet
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from .serializers import (
    AttendanceSerializer, BulkAttendanceSerializer,
    ExamSerializer, StudentGradeSerializer, BulkGradeSubmitSerializer, AssignmentSerializer, StudentSubmissionSerializer
)

class AttendanceViewSet(TenantAwareModelViewSet):
    queryset = Attendance.objects.select_related('student__user', 'academic_year', 'class_level', 'section').all()
    serializer_class = AttendanceSerializer
    # ... (Keep your existing get_queryset and bulk_record methods here) ...

    def get_queryset(self):
        qs = super().get_queryset()
        date = self.request.query_params.get('date', None)
        student_id = self.request.query_params.get('student', None)
        section_id = self.request.query_params.get('section', None)
        if date: qs = qs.filter(date=date)
        if student_id: qs = qs.filter(student_id=student_id)
        if section_id: qs = qs.filter(section_id=section_id)
        return qs

    @extend_schema(request=BulkAttendanceSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='bulk-record')
    def bulk_record(self, request):
        serializer = BulkAttendanceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = request.user.school

        attendance_objects = [
            Attendance(
                school=school, academic_year_id=data['academic_year_id'],
                class_level_id=data['class_level_id'], section_id=data['section_id'],
                date=data['date'], student_id=r['student_id'],
                status=r['status'], remarks=r.get('remarks', '')
            ) for r in data['records']
        ]

        with transaction.atomic():
            Attendance.objects.bulk_create(
                attendance_objects, update_conflicts=True,
                unique_fields=['school', 'student', 'date'], update_fields=['status', 'remarks']
            )
        return Response({"detail": f"Processed attendance for {len(attendance_objects)} students."}, status=status.HTTP_200_OK)

# --- NEW VIEWS FOR EXAMS & GRADES ---

class ExamViewSet(TenantAwareModelViewSet):
    queryset = Exam.objects.select_related('academic_year').all()
    serializer_class = ExamSerializer

class StudentGradeViewSet(TenantAwareModelViewSet):
    queryset = StudentGrade.objects.select_related('student__user', 'exam', 'subject').all()
    serializer_class = StudentGradeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        exam_id = self.request.query_params.get('exam', None)
        student_id = self.request.query_params.get('student', None)
        subject_id = self.request.query_params.get('subject', None)
        
        if exam_id: qs = qs.filter(exam_id=exam_id)
        if student_id: qs = qs.filter(student_id=student_id)
        if subject_id: qs = qs.filter(subject_id=subject_id)
        return qs

    @extend_schema(request=BulkGradeSubmitSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='bulk-submit')
    def bulk_submit(self, request):
        """
        POST /api/v1/operations/grades/bulk-submit/
        Highly optimized "Upsert" endpoint for submitting an entire column of grades.
        Safeguarded by TeacherAssignment validation.
        """
        serializer = BulkGradeSubmitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        school = request.user.school

        # Generate the list of Grade objects in memory (Vectorized preparation)
        grade_objects = []
        for record in data['records']:
            grade_objects.append(
                StudentGrade(
                    school=school,
                    exam_id=data['exam_id'],
                    subject_id=data['subject_id'],
                    student_id=record['student_id'],
                    marks_obtained=record['marks_obtained'],
                    max_marks=record.get('max_marks', 100.00),
                    remarks=record.get('remarks', '')
                )
            )

        # SQL Upsert Execution
        with transaction.atomic():
            StudentGrade.objects.bulk_create(
                grade_objects,
                update_conflicts=True,
                unique_fields=['school', 'exam', 'student', 'subject'], # Conflict Target
                update_fields=['marks_obtained', 'max_marks', 'remarks'] # Update payload if exists
            )

        return Response(
            {"detail": f"Successfully processed grades for {len(grade_objects)} students."},
            status=status.HTTP_200_OK
        )
    
class AssignmentViewSet(TenantAwareModelViewSet):
    queryset = Assignment.objects.select_related('subject', 'section', 'teacher').all()
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Filter for student's section if student is authenticated
        if hasattr(self.request.user, 'student_profile'):
            student_section = self.request.user.student_profile.enrollments.first().section
            return qs.filter(section=student_section)
        return qs

class StudentSubmissionViewSet(TenantAwareModelViewSet):
    queryset = StudentSubmission.objects.all()
    serializer_class = StudentSubmissionSerializer
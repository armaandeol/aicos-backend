from django.db import transaction
from rest_framework import viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta

from tenants.views import TenantAwareModelViewSet
from profiles.models import StudentProfile, ParentProfile, TeacherProfile
from academics.models import StudentEnrollment, TeacherAssignment
from accounts.permissions import IsStudent, IsTeacher, IsParent, IsTeacherOrStaff, IsParentOfStudent
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from .serializers import (
    AttendanceSerializer, BulkAttendanceSerializer,
    ExamSerializer, StudentGradeSerializer, BulkGradeSubmitSerializer,
    AssignmentSerializer, StudentSubmissionSerializer,
    StudentSubmissionCreateSerializer, AssignmentWithStatusSerializer,
)


# --- SHARED OWNERSHIP HELPERS ---

def get_caller_student_id(user):
    """
    If the logged-in user IS a student themselves, return their own
    StudentProfile id. Otherwise return None.
    """
    profile = StudentProfile.objects.filter(user=user).first()
    return profile.id if profile else None


def parent_can_access_student(user, student_id, require_academics=True):
    """
    True only if `user` has a ParentProfile that is mapped to `student_id`
    via ParentStudentMapping, and (if require_academics) that mapping has
    can_view_academics=True.
    """
    parent_profile = ParentProfile.objects.filter(user=user).first()
    if not parent_profile:
        return False

    from profiles.models import ParentStudentMapping
    qs = ParentStudentMapping.objects.filter(parent=parent_profile, student_id=student_id)
    if require_academics:
        qs = qs.filter(can_view_academics=True)
    return qs.exists()


def resolve_effective_student_id(request):
    """
    Figures out which student's data this request is allowed to see,
    given who is actually logged in.
    """
    user = request.user
    requested_student_id = request.query_params.get('student')

    own_student_id = get_caller_student_id(user)
    if own_student_id:
        return str(own_student_id)

    parent_profile = ParentProfile.objects.filter(user=user).first()
    if parent_profile:
        if not requested_student_id:
            raise ValidationError({"student": "This parameter is required for parent accounts."})
        if not parent_can_access_student(user, requested_student_id):
            raise PermissionDenied("You are not authorized to view this student's data.")
        return requested_student_id

    return requested_student_id


# ============================================
# ATTENDANCE VIEWSET
# ============================================

class AttendanceViewSet(TenantAwareModelViewSet):
    """
    Attendance ViewSet with proper RBAC:
    - Students: Can only view their own attendance via /me/ endpoints
    - Teachers: Can view and manage attendance for their sections
    - Parents: Can view their children's attendance via /me/ with student param
    - Admins: Full access
    """
    queryset = Attendance.objects.select_related('student__user', 'academic_year', 'class_level', 'section').all()
    serializer_class = AttendanceSerializer

    def get_permissions(self):
        """Dynamic permission checks based on action"""
        if self.action in ['my_attendance', 'my_attendance_summary', 'my_today_attendance', 'my_section_attendance']:
            return [IsAuthenticated()]
        elif self.action in ['bulk_record', 'create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        else:
            return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                student = StudentProfile.objects.get(user=user)
                return qs.filter(student=student)
            except StudentProfile.DoesNotExist:
                pass
        
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

    # --- STUDENT/PARENT ATTENDANCE METHODS ---

    @action(detail=False, methods=['get'], url_path='me')
    def my_attendance(self, request):
        """
        GET /api/v1/operations/attendance/me/
        
        For Students: Returns their own attendance records
        For Parents: Returns their child's attendance records (requires ?student=ID)
        For Teachers: Returns attendance for their sections
        """
        user = request.user
        student_id = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
            student_id = student.id
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student_id = requested_student_id
            except ParentProfile.DoesNotExist:
                pass

        if student_id:
            queryset = Attendance.objects.filter(
                student_id=student_id,
                school=request.user.school
            ).order_by('-date')
        else:
            section_id = request.query_params.get('section')
            queryset = Attendance.objects.filter(school=request.user.school)
            if section_id:
                queryset = queryset.filter(section_id=section_id)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if month and year:
            queryset = queryset.filter(date__month=month, date__year=year)
        elif month:
            queryset = queryset.filter(date__month=month)
        elif year:
            queryset = queryset.filter(date__year=year)

        if not any([start_date, end_date, month, year, request.query_params.get('section')]):
            queryset = queryset[:30]

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "count": queryset.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=['get'], url_path='me/summary')
    def my_attendance_summary(self, request):
        """
        GET /api/v1/operations/attendance/me/summary/
        
        For Students: Returns their own attendance summary
        For Parents: Returns their child's attendance summary (requires ?student=ID)
        """
        user = request.user
        student_id = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
            student_id = student.id
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student_id = requested_student_id
            except ParentProfile.DoesNotExist:
                pass

        if student_id:
            queryset = Attendance.objects.filter(
                student_id=student_id,
                school=request.user.school
            )
        else:
            queryset = Attendance.objects.filter(school=request.user.school)

        academic_year_id = request.query_params.get('academic_year_id')
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        if month:
            queryset = queryset.filter(date__month=month)
        if year:
            queryset = queryset.filter(date__year=year)

        total_records = queryset.count()
        if total_records == 0:
            return Response({
                "total_days": 0,
                "present": 0,
                "absent": 0,
                "late": 0,
                "half_day": 0,
                "attendance_percentage": 0,
                "status": "No records found"
            })

        present = queryset.filter(status='Present').count()
        absent = queryset.filter(status='Absent').count()
        late = queryset.filter(status='Late').count()
        half_day = queryset.filter(status='Half-Day').count()

        present_days = present + late
        attendance_percentage = round((present_days / total_records) * 100, 2)

        if attendance_percentage >= 90:
            status_msg = "Excellent"
        elif attendance_percentage >= 75:
            status_msg = "Good"
        elif attendance_percentage >= 60:
            status_msg = "Needs Improvement"
        else:
            status_msg = "Poor - Please contact school"

        return Response({
            "total_days": total_records,
            "present": present,
            "absent": absent,
            "late": late,
            "half_day": half_day,
            "attendance_percentage": attendance_percentage,
            "status": status_msg
        })

    # --- TEACHER ATTENDANCE METHODS ---

    @action(detail=False, methods=['get'], url_path='me/today')
    def my_today_attendance(self, request):
        """
        GET /api/v1/operations/attendance/me/today/
        Returns today's attendance for all sections the teacher teaches
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        today = timezone.now().date()
        
        assignments = TeacherAssignment.objects.filter(
            teacher=teacher,
            school=request.user.school
        ).select_related('section', 'class_level', 'subject', 'academic_year')

        sections_data = []
        for assignment in assignments:
            enrollments = StudentEnrollment.objects.filter(
                school=request.user.school,
                section=assignment.section,
                academic_year=assignment.academic_year
            ).select_related('student__user')

            student_ids = [e.student.id for e in enrollments]
            attendance_records = Attendance.objects.filter(
                school=request.user.school,
                section=assignment.section,
                date=today,
                student_id__in=student_ids
            ).select_related('student__user')

            attendance_data = []
            for enrollment in enrollments:
                record = attendance_records.filter(student=enrollment.student).first()
                attendance_data.append({
                    "student_id": str(enrollment.student.id),
                    "student_name": f"{enrollment.student.user.first_name} {enrollment.student.user.last_name}",
                    "roll_number": enrollment.roll_number,
                    "status": record.status if record else "Not Marked",
                    "remarks": record.remarks if record else ""
                })

            sections_data.append({
                "section_id": str(assignment.section.id),
                "section_name": assignment.section.name,
                "class_level": assignment.class_level.name,
                "subject": assignment.subject.name,
                "total_students": len(attendance_data),
                "marked": attendance_records.count(),
                "pending": len(attendance_data) - attendance_records.count(),
                "attendance": attendance_data
            })

        return Response({
            "date": today.isoformat(),
            "sections": sections_data
        })

    @action(detail=False, methods=['get'], url_path='me/section/(?P<section_id>[^/.]+)')
    def my_section_attendance(self, request, section_id):
        """
        GET /api/v1/operations/attendance/me/section/{section_id}/
        Returns attendance for a specific section
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        assignment = TeacherAssignment.objects.filter(
            teacher=teacher,
            section_id=section_id,
            school=request.user.school
        ).first()

        if not assignment:
            return Response(
                {"detail": "You are not assigned to this section."},
                status=status.HTTP_403_FORBIDDEN
            )

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        attendance_qs = Attendance.objects.filter(
            school=request.user.school,
            section_id=section_id
        ).select_related('student__user')

        if start_date:
            attendance_qs = attendance_qs.filter(date__gte=start_date)
        if end_date:
            attendance_qs = attendance_qs.filter(date__lte=end_date)
        if month and year:
            attendance_qs = attendance_qs.filter(date__month=month, date__year=year)

        dates_data = {}
        for record in attendance_qs:
            date_str = record.date.isoformat()
            if date_str not in dates_data:
                dates_data[date_str] = {
                    "date": date_str,
                    "total": 0,
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "half_day": 0,
                    "records": []
                }
            dates_data[date_str]["total"] += 1
            status_key = record.status.lower().replace('-', '_')
            if status_key in dates_data[date_str]:
                dates_data[date_str][status_key] += 1
            dates_data[date_str]["records"].append({
                "student_id": str(record.student.id),
                "student_name": record.student.user.first_name,
                "status": record.status,
                "remarks": record.remarks
            })

        return Response({
            "section": {
                "id": str(assignment.section.id),
                "name": assignment.section.name,
                "class_level": assignment.class_level.name,
                "subject": assignment.subject.name
            },
            "attendance": list(dates_data.values())
        })


# ============================================
# EXAM VIEWSET
# ============================================

class ExamViewSet(TenantAwareModelViewSet):
    """
    Exam ViewSet with proper RBAC:
    - Students: Can view their own exams via /me/ endpoints
    - Parents: Can view their children's exams via /me/ with student param
    - Teachers: Can view and manage exams
    - Admins: Full access
    """
    queryset = Exam.objects.select_related('academic_year').all()
    serializer_class = ExamSerializer

    def get_permissions(self):
        if self.action in ['my_exams', 'my_upcoming_exams']:
            return [IsAuthenticated()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        else:
            return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                student = StudentProfile.objects.get(user=user)
                enrollment = StudentEnrollment.objects.filter(
                    student=student,
                    school=user.school
                ).order_by('-academic_year__start_date').first()
                if enrollment:
                    return qs.filter(academic_year=enrollment.academic_year)
                return qs.none()
            except StudentProfile.DoesNotExist:
                pass
        return qs

    @action(detail=False, methods=['get'], url_path='me')
    def my_exams(self, request):
        """
        GET /api/v1/operations/exams/me/
        
        For Students: Returns their own exams
        For Parents: Returns their child's exams (requires ?student=ID)
        """
        user = request.user
        student = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student = StudentProfile.objects.get(id=requested_student_id, school=request.user.school)
            except (ParentProfile.DoesNotExist, StudentProfile.DoesNotExist):
                return Response(
                    {"detail": "Student profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if not student:
            return Response({
                "count": 0,
                "results": []
            })

        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        if not enrollment:
            return Response({
                "count": 0,
                "results": []
            })

        exams = Exam.objects.filter(
            school=request.user.school,
            academic_year=enrollment.academic_year
        ).order_by('start_date')

        serializer = self.get_serializer(exams, many=True)
        return Response({
            "count": exams.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=['get'], url_path='me/upcoming')
    def my_upcoming_exams(self, request):
        """
        GET /api/v1/operations/exams/me/upcoming/
        
        For Students: Returns their upcoming exams
        For Parents: Returns their child's upcoming exams (requires ?student=ID)
        """
        user = request.user
        student = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student = StudentProfile.objects.get(id=requested_student_id, school=request.user.school)
            except (ParentProfile.DoesNotExist, StudentProfile.DoesNotExist):
                return Response(
                    {"detail": "Student profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if not student:
            return Response({
                "count": 0,
                "results": []
            })

        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        if not enrollment:
            return Response({
                "count": 0,
                "results": []
            })

        today = timezone.now().date()
        exams = Exam.objects.filter(
            school=request.user.school,
            academic_year=enrollment.academic_year,
            start_date__gte=today
        ).order_by('start_date')

        serializer = self.get_serializer(exams, many=True)
        return Response({
            "count": exams.count(),
            "results": serializer.data
        })


# ============================================
# STUDENT GRADE VIEWSET
# ============================================

class StudentGradeViewSet(TenantAwareModelViewSet):
    """
    StudentGrade ViewSet with proper RBAC:
    - Students: Can view their own grades via /me/ endpoints
    - Parents: Can view their children's grades via /me/ with student param
    - Teachers: Can view and manage grades for their sections
    - Admins: Full access
    """
    queryset = StudentGrade.objects.select_related('student__user', 'exam', 'subject').all()
    serializer_class = StudentGradeSerializer

    def get_permissions(self):
        if self.action in ['my_grades', 'my_report_card', 'my_section_gradebook']:
            return [IsAuthenticated()]
        elif self.action in ['bulk_submit', 'create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        else:
            return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                student = StudentProfile.objects.get(user=user)
                return qs.filter(student=student)
            except StudentProfile.DoesNotExist:
                pass
        
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
        serializer = BulkGradeSubmitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        school = request.user.school

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

        with transaction.atomic():
            StudentGrade.objects.bulk_create(
                grade_objects,
                update_conflicts=True,
                unique_fields=['school', 'exam', 'student', 'subject'],
                update_fields=['marks_obtained', 'max_marks', 'remarks']
            )

        return Response(
            {"detail": f"Successfully processed grades for {len(grade_objects)} students."},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='me')
    def my_grades(self, request):
        """
        GET /api/v1/operations/grades/me/
        
        For Students: Returns their own grades
        For Parents: Returns their child's grades (requires ?student=ID)
        """
        user = request.user
        student_id = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
            student_id = student.id
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student_id = requested_student_id
            except ParentProfile.DoesNotExist:
                return Response(
                    {"detail": "Student or Parent profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if not student_id:
            return Response(
                {"detail": "Student ID not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        queryset = StudentGrade.objects.filter(
            student_id=student_id,
            school=request.user.school
        ).select_related('exam', 'subject', 'exam__academic_year')

        exam_id = request.query_params.get('exam_id')
        academic_year_id = request.query_params.get('academic_year_id')

        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if academic_year_id:
            queryset = queryset.filter(exam__academic_year_id=academic_year_id)

        queryset = queryset.order_by('-exam__start_date', 'subject__name')

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "count": queryset.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=['get'], url_path='me/report-card')
    def my_report_card(self, request):
        """
        GET /api/v1/operations/grades/me/report-card/
        
        For Students: Returns their own report card
        For Parents: Returns their child's report card (requires ?student=ID)
        """
        user = request.user
        student = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student = StudentProfile.objects.get(id=requested_student_id, school=request.user.school)
            except (ParentProfile.DoesNotExist, StudentProfile.DoesNotExist):
                return Response(
                    {"detail": "Student or Parent profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if not student:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        queryset = StudentGrade.objects.filter(
            student=student,
            school=request.user.school
        ).select_related('exam', 'subject', 'exam__academic_year')

        academic_year_id = request.query_params.get('academic_year_id')
        if academic_year_id:
            queryset = queryset.filter(exam__academic_year_id=academic_year_id)

        exams_data = {}
        for grade in queryset:
            exam_name = grade.exam.name
            if exam_name not in exams_data:
                exams_data[exam_name] = {
                    "exam_id": str(grade.exam.id),
                    "exam_name": exam_name,
                    "exam_date": grade.exam.start_date,
                    "is_published": grade.exam.is_published,
                    "subjects": []
                }
            
            exams_data[exam_name]["subjects"].append({
                "subject_id": str(grade.subject.id),
                "subject_name": grade.subject.name,
                "marks_obtained": float(grade.marks_obtained),
                "max_marks": float(grade.max_marks),
                "percentage": round((grade.marks_obtained / grade.max_marks) * 100, 2) if grade.max_marks > 0 else 0,
                "remarks": grade.remarks
            })

        all_grades = queryset.all()
        total_marks = sum(g.marks_obtained for g in all_grades)
        total_max = sum(g.max_marks for g in all_grades)
        overall_percentage = round((total_marks / total_max) * 100, 2) if total_max > 0 else 0

        return Response({
            "student_name": f"{student.user.first_name} {student.user.last_name}",
            "enrollment_number": student.enrollment_number,
            "overall_percentage": overall_percentage,
            "total_subjects": all_grades.count(),
            "exams": list(exams_data.values())
        })

    # --- TEACHER GRADEBOOK METHODS ---

    @action(detail=False, methods=['get'], url_path='me/section/(?P<section_id>[^/.]+)/exam/(?P<exam_id>[^/.]+)')
    def my_section_gradebook(self, request, section_id, exam_id):
        """
        GET /api/v1/operations/grades/me/section/{section_id}/exam/{exam_id}/
        Returns gradebook for a specific section and exam
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        assignment = TeacherAssignment.objects.filter(
            teacher=teacher,
            section_id=section_id,
            school=request.user.school
        ).first()

        if not assignment:
            return Response(
                {"detail": "You are not assigned to this section."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            exam = Exam.objects.get(id=exam_id, school=request.user.school)
        except Exam.DoesNotExist:
            return Response(
                {"detail": "Exam not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollments = StudentEnrollment.objects.filter(
            school=request.user.school,
            section_id=section_id,
            academic_year=exam.academic_year
        ).select_related('student__user')

        student_ids = [e.student.id for e in enrollments]
        grades = StudentGrade.objects.filter(
            school=request.user.school,
            exam_id=exam_id,
            student_id__in=student_ids,
            subject=assignment.subject
        ).select_related('student__user')

        gradebook = []
        for enrollment in enrollments:
            student = enrollment.student
            grade = grades.filter(student=student).first()
            gradebook.append({
                "student_id": str(student.id),
                "student_name": f"{student.user.first_name} {student.user.last_name}",
                "roll_number": enrollment.roll_number,
                "marks_obtained": float(grade.marks_obtained) if grade else None,
                "max_marks": float(grade.max_marks) if grade else 100.00,
                "percentage": float(grade.marks_obtained / grade.max_marks * 100) if grade and grade.max_marks > 0 else None,
                "remarks": grade.remarks if grade else None,
                "graded": bool(grade)
            })

        graded = [g for g in gradebook if g['graded']]
        total_marks = sum(g['marks_obtained'] for g in graded if g['marks_obtained'])
        total_max = sum(g['max_marks'] for g in graded if g['max_marks'])
        avg_percentage = round((total_marks / total_max) * 100, 2) if total_max > 0 else 0

        return Response({
            "exam": {
                "id": str(exam.id),
                "name": exam.name,
                "date": exam.start_date
            },
            "subject": {
                "id": str(assignment.subject.id),
                "name": assignment.subject.name
            },
            "section": {
                "id": str(assignment.section.id),
                "name": assignment.section.name,
                "class_level": assignment.class_level.name
            },
            "summary": {
                "total_students": len(gradebook),
                "graded_students": len(graded),
                "average_percentage": avg_percentage,
                "highest": max((g['percentage'] for g in graded if g['percentage']), default=0),
                "lowest": min((g['percentage'] for g in graded if g['percentage']), default=0)
            },
            "gradebook": gradebook
        })


# ============================================
# ASSIGNMENT VIEWSET
# ============================================

class AssignmentViewSet(TenantAwareModelViewSet):
    """
    Assignment ViewSet with proper RBAC:
    - Students: Can view their own assignments via /me/ endpoints
    - Parents: Can view their children's assignments via /for-student/ with student param
    - Teachers: Can create, update, delete assignments
    - Admins: Full access
    """
    queryset = Assignment.objects.select_related('subject', 'section', 'teacher').all()
    serializer_class = AssignmentSerializer

    def get_permissions(self):
        if self.action in ['my_assignments', 'my_upcoming_assignments']:
            return [IsAuthenticated(), IsStudent()]
        elif self.action == 'for_student':
            return [IsAuthenticated()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        else:
            return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()

        own_student_id = get_caller_student_id(self.request.user)
        if own_student_id:
            enrollment = StudentEnrollment.objects.filter(student_id=own_student_id).order_by(
                '-academic_year__start_date'
            ).first()
            if enrollment:
                return qs.filter(section_id=enrollment.section_id)
            return qs.none()

        section_id = self.request.query_params.get('section', None)
        subject_id = self.request.query_params.get('subject', None)
        teacher_id = self.request.query_params.get('teacher', None)

        if section_id:
            qs = qs.filter(section_id=section_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        teacher_profile = TeacherProfile.objects.filter(user=user).first()
        if not (user.is_superuser or user.is_staff or teacher_profile):
            raise PermissionDenied("Only teachers or staff can create assignments.")
        super().perform_create(serializer)

    @extend_schema(responses={200: AssignmentWithStatusSerializer(many=True)})
    @action(detail=False, methods=['get'], url_path='for-student')
    def for_student(self, request):
        effective_student_id = resolve_effective_student_id(request)
        if not effective_student_id:
            raise ValidationError({"student": "This parameter is required."})

        enrollment = StudentEnrollment.objects.filter(student_id=effective_student_id).order_by(
            '-academic_year__start_date'
        ).first()
        if not enrollment:
            return Response({"count": 0, "results": []}, status=status.HTTP_200_OK)

        assignments = Assignment.objects.filter(
            school=request.user.school, section_id=enrollment.section_id
        ).select_related('subject', 'section', 'teacher').order_by('-due_date')

        serializer = AssignmentWithStatusSerializer(
            assignments, many=True, context={'student_id': effective_student_id}
        )
        return Response({"count": assignments.count(), "results": serializer.data}, status=status.HTTP_200_OK)

    # --- STUDENT ASSIGNMENT METHODS ---

    @action(detail=False, methods=['get'], url_path='me')
    def my_assignments(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        if not enrollment:
            return Response({
                "count": 0,
                "results": []
            })

        assignments = Assignment.objects.filter(
            school=request.user.school,
            section_id=enrollment.section_id
        ).select_related('subject', 'section', 'teacher').order_by('-due_date')

        serializer = AssignmentWithStatusSerializer(
            assignments, 
            many=True, 
            context={'student_id': str(student.id)}
        )
        
        return Response({
            "count": assignments.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=['get'], url_path='me/upcoming')
    def my_upcoming_assignments(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        if not enrollment:
            return Response({
                "count": 0,
                "results": []
            })

        now = timezone.now()
        assignments = Assignment.objects.filter(
            school=request.user.school,
            section_id=enrollment.section_id,
            due_date__gte=now
        ).select_related('subject', 'section', 'teacher').order_by('due_date')

        serializer = AssignmentWithStatusSerializer(
            assignments, 
            many=True, 
            context={'student_id': str(student.id)}
        )
        
        return Response({
            "count": assignments.count(),
            "results": serializer.data
        })

    # --- TEACHER ASSIGNMENT METHODS ---

    @action(detail=False, methods=['get'], url_path='me/teacher')
    def my_teacher_assignments(self, request):
        """
        GET /api/v1/operations/assignments/me/teacher/
        Returns assignments created by the current teacher
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        assignments = Assignment.objects.filter(
            teacher=teacher,
            school=request.user.school
        ).select_related('subject', 'section').order_by('-created_at')

        section_id = request.query_params.get('section_id')
        if section_id:
            assignments = assignments.filter(section_id=section_id)

        subject_id = request.query_params.get('subject_id')
        if subject_id:
            assignments = assignments.filter(subject_id=subject_id)

        status_filter = request.query_params.get('status')
        now = timezone.now()
        if status_filter == 'upcoming':
            assignments = assignments.filter(due_date__gte=now)
        elif status_filter == 'past':
            assignments = assignments.filter(due_date__lt=now)

        data = []
        for assignment in assignments:
            submission_count = StudentSubmission.objects.filter(
                assignment=assignment
            ).count()
            
            graded_count = StudentSubmission.objects.filter(
                assignment=assignment,
                grade__isnull=False
            ).count()

            data.append({
                "id": str(assignment.id),
                "title": assignment.title,
                "description": assignment.description,
                "subject": {
                    "id": str(assignment.subject.id),
                    "name": assignment.subject.name
                },
                "section": {
                    "id": str(assignment.section.id),
                    "name": assignment.section.name
                },
                "due_date": assignment.due_date,
                "created_at": assignment.created_at,
                "submission_count": submission_count,
                "graded_count": graded_count,
                "pending_grading": submission_count - graded_count
            })

        return Response({
            "count": len(data),
            "results": data
        })


# ============================================
# STUDENT SUBMISSION VIEWSET
# ============================================

class StudentSubmissionViewSet(TenantAwareModelViewSet):
    """
    StudentSubmission ViewSet with proper RBAC:
    - Students: Can submit assignments and view their own submissions
    - Parents: Can view their children's submissions via /me/ with student param
    - Teachers: Can view and grade submissions
    - Admins: Full access
    """
    queryset = StudentSubmission.objects.select_related('assignment', 'student__user').all()
    serializer_class = StudentSubmissionSerializer

    def get_permissions(self):
        if self.action == 'submit':
            return [IsAuthenticated(), IsStudent()]
        elif self.action in ['my_submissions', 'my_pending_submissions', 'my_assignment_submissions']:
            return [IsAuthenticated()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacher()]
        else:
            return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()

        own_student_id = get_caller_student_id(self.request.user)
        if own_student_id:
            return qs.filter(student_id=own_student_id)

        student_id = self.request.query_params.get('student', None)
        assignment_id = self.request.query_params.get('assignment', None)

        parent_profile = ParentProfile.objects.filter(user=self.request.user).first()
        if parent_profile:
            if not student_id:
                return qs.none()
            if not parent_can_access_student(self.request.user, student_id):
                return qs.none()

        if student_id:
            qs = qs.filter(student_id=student_id)
        if assignment_id:
            qs = qs.filter(assignment_id=assignment_id)

        return qs

    @action(detail=False, methods=['post'], url_path='submit')
    def submit(self, request):
        own_student_id = get_caller_student_id(request.user)
        if not own_student_id:
            raise PermissionDenied("Only students can submit assignments.")

        assignment_id = request.data.get('assignment')
        if not assignment_id:
            raise ValidationError({"assignment": "This field is required."})

        assignment = Assignment.objects.filter(id=assignment_id, school=request.user.school).first()
        if not assignment:
            raise ValidationError({"assignment": "Invalid assignment."})

        existing = StudentSubmission.objects.filter(
            assignment=assignment, student_id=own_student_id
        ).first()

        serializer = StudentSubmissionCreateSerializer(
            instance=existing, data=request.data, partial=bool(existing)
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            school=request.user.school,
            student_id=own_student_id,
            assignment=assignment,
            status='Submitted',
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED if not existing else status.HTTP_200_OK)

    def perform_update(self, serializer):
        user = self.request.user
        is_teacher_or_staff = user.is_superuser or user.is_staff or TeacherProfile.objects.filter(user=user).exists()

        if not is_teacher_or_staff:
            for field in ('grade', 'status'):
                serializer.validated_data.pop(field, None)

        super().perform_update(serializer)

    # --- STUDENT/PARENT SUBMISSION METHODS ---

    @action(detail=False, methods=['get'], url_path='me')
    def my_submissions(self, request):
        user = request.user
        student_id = None
        
        try:
            student = StudentProfile.objects.get(user=user, school=user.school)
            student_id = student.id
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                requested_student_id = request.query_params.get('student')
                if not requested_student_id:
                    return Response(
                        {"detail": "student parameter is required for parent accounts."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(
                    parent=parent, 
                    student_id=requested_student_id,
                    can_view_academics=True
                ).exists():
                    return Response(
                        {"detail": "You are not authorized to view this student's data."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                student_id = requested_student_id
            except ParentProfile.DoesNotExist:
                return Response(
                    {"detail": "Student or Parent profile not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        if not student_id:
            return Response(
                {"detail": "Student ID not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        submissions = StudentSubmission.objects.filter(
            student_id=student_id,
            school=request.user.school
        ).select_related('assignment', 'assignment__subject', 'assignment__section')\
         .order_by('-submitted_at')

        serializer = self.get_serializer(submissions, many=True)
        return Response({
            "count": submissions.count(),
            "results": serializer.data
        })

    # --- TEACHER SUBMISSION METHODS ---

    @action(detail=False, methods=['get'], url_path='me/pending')
    def my_pending_submissions(self, request):
        """
        GET /api/v1/operations/submissions/me/pending/
        Returns submissions pending grading for the teacher
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        assignments = Assignment.objects.filter(
            teacher=teacher,
            school=request.user.school
        )

        pending_submissions = StudentSubmission.objects.filter(
            school=request.user.school,
            assignment__in=assignments,
            grade__isnull=True,
            status='Submitted'
        ).select_related('assignment', 'student__user', 'assignment__subject', 'assignment__section')

        assignment_id = request.query_params.get('assignment_id')
        if assignment_id:
            pending_submissions = pending_submissions.filter(assignment_id=assignment_id)

        data = []
        for submission in pending_submissions:
            data.append({
                "id": str(submission.id),
                "student": {
                    "id": str(submission.student.id),
                    "name": f"{submission.student.user.first_name} {submission.student.user.last_name}",
                    "enrollment_number": submission.student.enrollment_number
                },
                "assignment": {
                    "id": str(submission.assignment.id),
                    "title": submission.assignment.title,
                    "subject": submission.assignment.subject.name,
                    "section": submission.assignment.section.name,
                    "due_date": submission.assignment.due_date
                },
                "submitted_at": submission.submitted_at,
                "file": submission.file.url if submission.file else None
            })

        return Response({
            "count": len(data),
            "results": data
        })

    @action(detail=False, methods=['get'], url_path='me/assignment/(?P<assignment_id>[^/.]+)')
    def my_assignment_submissions(self, request, assignment_id):
        """
        GET /api/v1/operations/submissions/me/assignment/{assignment_id}/
        Returns all submissions for a specific assignment
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        assignment = Assignment.objects.filter(
            id=assignment_id,
            teacher=teacher,
            school=request.user.school
        ).first()

        if not assignment:
            return Response(
                {"detail": "Assignment not found or you don't have permission."},
                status=status.HTTP_403_FORBIDDEN
            )

        submissions = StudentSubmission.objects.filter(
            assignment=assignment,
            school=request.user.school
        ).select_related('student__user').order_by('-submitted_at')

        data = []
        for submission in submissions:
            data.append({
                "id": str(submission.id),
                "student": {
                    "id": str(submission.student.id),
                    "name": f"{submission.student.user.first_name} {submission.student.user.last_name}",
                    "enrollment_number": submission.student.enrollment_number
                },
                "file": submission.file.url if submission.file else None,
                "submitted_at": submission.submitted_at,
                "grade": float(submission.grade) if submission.grade is not None else None,
                "status": submission.status,
                "remarks": getattr(submission, 'remarks', '')
            })

        total = len(data)
        graded = len([s for s in data if s['grade'] is not None])
        pending = total - graded

        return Response({
            "assignment": {
                "id": str(assignment.id),
                "title": assignment.title,
                "description": assignment.description,
                "subject": assignment.subject.name,
                "section": assignment.section.name,
                "due_date": assignment.due_date
            },
            "summary": {
                "total_submissions": total,
                "graded": graded,
                "pending": pending
            },
            "submissions": data
        })
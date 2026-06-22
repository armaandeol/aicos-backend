from rest_framework import viewsets, views, response, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from tenants.views import TenantAwareModelViewSet
from accounts.permissions import IsStudent, IsTeacher, IsParent, IsParentOfStudent, IsStudentOrReadOnly
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from .serializers import (
    StudentProfileSerializer, TeacherProfileSerializer,
    ParentProfileSerializer, ParentStudentMappingSerializer
)
from academics.models import StudentEnrollment
from operations.models import Attendance, StudentGrade, Assignment
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta


class StudentProfileViewSet(TenantAwareModelViewSet):
    serializer_class = StudentProfileSerializer
    
    # ✅ Both SearchFilter (name/email/ID) AND DjangoFilterBackend (status/class)
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'enrollment_number', 'phone_number']
    filterset_fields = {
        'is_archived': ['exact'],  # ?is_archived=true / false
        'school': ['exact'],       # already scoped by tenant but kept for safety
    }
    
    # ✅ RBAC: Only students can access
    permission_classes = [IsAuthenticated, IsStudentOrReadOnly]

    def get_queryset(self):
        # Start with tenant-scoped queryset with related data prefetched
        qs = super().get_queryset().select_related('user').prefetch_related(
            'parent_mappings__parent__user'
        )
        
        # Handle class_level filter manually (via enrollment)
        class_level = self.request.query_params.get('class_level', None)
        if class_level:
            qs = qs.filter(
                enrollments__class_level_id=class_level,
                enrollments__school=self.request.user.school
            ).distinct()
        
        # If user is superuser or staff, return all
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return qs
        
        # If user is student, return only their profile
        try:
            student = StudentProfile.objects.get(user=user)
            return qs.filter(id=student.id)
        except StudentProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET /api/v1/profiles/students/me/ - Get current student's profile
        PUT /api/v1/profiles/students/me/ - Update current student's profile
        PATCH /api/v1/profiles/students/me/ - Partial update current student's profile
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(student)
            return Response(serializer.data)
        
        # PUT or PATCH
        serializer = self.get_serializer(student, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='me/parents')
    def my_parents(self, request):
        """
        GET /api/v1/profiles/students/me/parents/
        Returns all parents/guardians linked to the current student.
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        mappings = ParentStudentMapping.objects.filter(
            student=student,
            school=request.user.school
        ).select_related('parent__user')

        data = []
        for mapping in mappings:
            data.append({
                "id": mapping.id,
                "parent_id": mapping.parent.id,
                "name": f"{mapping.parent.user.first_name} {mapping.parent.user.last_name}",
                "email": mapping.parent.user.email,
                "phone": mapping.parent.phone_number,
                "relationship": mapping.relationship,
                "is_primary_contact": mapping.is_primary_contact,
                "can_view_academics": mapping.can_view_academics,
                "can_pay_fees": mapping.can_pay_fees
            })

        return Response({"parents": data})


class TeacherProfileViewSet(TenantAwareModelViewSet):
    queryset = TeacherProfile.objects.select_related('user').all()
    serializer_class = TeacherProfileSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_id']
    
    # ✅ RBAC: Only teachers can access
    permission_classes = [IsAuthenticated, IsTeacher]

    def get_queryset(self):
        """Override to ensure teachers only see their own profile"""
        user = self.request.user
        qs = super().get_queryset()
        
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            teacher = TeacherProfile.objects.get(user=user)
            return qs.filter(id=teacher.id)
        except TeacherProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET /api/v1/profiles/teachers/me/ - Get current teacher's profile
        PUT /api/v1/profiles/teachers/me/ - Update current teacher's profile
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(teacher)
            return Response(serializer.data)
        
        serializer = self.get_serializer(teacher, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class ParentProfileViewSet(TenantAwareModelViewSet):
    queryset = ParentProfile.objects.select_related('user').all()
    serializer_class = ParentProfileSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'phone_number']
    
    # ✅ RBAC: Only parents can access
    permission_classes = [IsAuthenticated, IsParent]

    def get_queryset(self):
        """Override to ensure parents only see their own profile"""
        user = self.request.user
        qs = super().get_queryset()
        
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            parent = ParentProfile.objects.get(user=user)
            return qs.filter(id=parent.id)
        except ParentProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET /api/v1/profiles/parents/me/ - Get current parent's profile
        PUT /api/v1/profiles/parents/me/ - Update current parent's profile
        """
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(parent)
            return Response(serializer.data)
        
        serializer = self.get_serializer(parent, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='me/children')
    def my_children(self, request):
        """
        GET /api/v1/profiles/parents/me/children/
        Returns all students linked to the current parent.
        """
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        mappings = ParentStudentMapping.objects.filter(
            parent=parent,
            school=request.user.school
        ).select_related('student__user', 'student')

        data = []
        for mapping in mappings:
            student = mapping.student
            enrollment = StudentEnrollment.objects.filter(
                student=student,
                school=request.user.school
            ).order_by('-academic_year__start_date').first()
            
            data.append({
                "id": mapping.id,
                "student_id": student.id,
                "name": f"{student.user.first_name} {student.user.last_name}",
                "email": student.user.email,
                "enrollment_number": student.enrollment_number,
                "relationship": mapping.relationship,
                "current_class": {
                    "class": enrollment.class_level.name if enrollment else None,
                    "section": enrollment.section.name if enrollment else None,
                    "academic_year": enrollment.academic_year.name if enrollment else None
                } if enrollment else None
            })

        return Response({"children": data})


class ParentStudentMappingViewSet(TenantAwareModelViewSet):
    queryset = ParentStudentMapping.objects.all()
    serializer_class = ParentStudentMappingSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'parent__user__first_name',
        'parent__user__last_name',
        'student__user__first_name',
        'student__user__last_name',
        'relationship'
    ]
    
    # ✅ RBAC: Only parents or admin can access
    permission_classes = [IsAuthenticated, IsParent]

    def get_queryset(self):
        """Override to ensure parents only see their own mappings"""
        user = self.request.user
        qs = super().get_queryset()
        
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            parent = ParentProfile.objects.get(user=user)
            return qs.filter(parent=parent)
        except ParentProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['post'], url_path='request')
    def request_mapping(self, request):
        """
        POST /api/v1/profiles/parent-student-mappings/request/
        Allows a parent to request linking to a student.
        """
        student_id = request.data.get('student_id')
        relationship = request.data.get('relationship', 'Guardian')
        
        if not student_id:
            return Response(
                {"detail": "student_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
            student = StudentProfile.objects.get(id=student_id, school=request.user.school)
        except (ParentProfile.DoesNotExist, StudentProfile.DoesNotExist):
            return Response(
                {"detail": "Invalid parent or student profile."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if mapping already exists
        if ParentStudentMapping.objects.filter(parent=parent, student=student).exists():
            return Response(
                {"detail": "Mapping already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        mapping = ParentStudentMapping.objects.create(
            school=request.user.school,
            parent=parent,
            student=student,
            relationship=relationship,
            is_primary_contact=False,
            can_view_academics=False,
            can_pay_fees=False
        )

        serializer = self.get_serializer(mapping)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# --- TASK 2.4: Context Switching API ---

class UserContextView(views.APIView):
    """
    GET /api/v1/profiles/me/
    Returns the user's base identity, their RBAC roles, and any 
    linked profiles (Teacher, Parent, Student) for frontend context switching.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        student_profile = StudentProfile.objects.filter(user=user).first()
        teacher_profile = TeacherProfile.objects.filter(user=user).first()
        parent_profile = ParentProfile.objects.filter(user=user).first()

        roles = []
        if hasattr(user, 'user_roles'):
            roles = list(user.user_roles.filter(school=user.school).values_list('role__name', flat=True))

        payload = {
            "identity": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "school_id": user.school_id,
            },
            "roles": roles,
            "is_superuser": user.is_superuser,
            "profiles": {
                "student": {
                    "exists": bool(student_profile),
                    "id": student_profile.id if student_profile else None,
                },
                "teacher": {
                    "exists": bool(teacher_profile),
                    "id": teacher_profile.id if teacher_profile else None,
                },
                "parent": {
                    "exists": bool(parent_profile),
                    "id": parent_profile.id if parent_profile else None,
                }
            }
        }
        
        return response.Response(payload)
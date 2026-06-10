import uuid
from django.db import models
from django.conf import settings
from tenants.models import TenantAwareModel

class BaseProfile(TenantAwareModel):
    """
    Abstract base class containing common fields for all human entities.
    Inherits from TenantAwareModel to ensure tenant isolation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # One user can have one profile of a specific type per school.
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    
    # We'll wire up S3 for this in Phase 7
    profile_picture = models.ImageField(upload_to='profiles/pictures/', blank=True, null=True)

    class Meta:
        abstract = True


class StudentProfile(BaseProfile):
    """Profile specifically for Students."""
    enrollment_number = models.CharField(max_length=50)
    blood_group = models.CharField(max_length=10, blank=True, null=True)
    
    # Soft delete field as requested in API specs for Alumni preservation
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']
        # Ensures two different schools can use the same enrollment number, 
        # but within a single school, it must be unique.
        constraints = [
            models.UniqueConstraint(fields=['school', 'enrollment_number'], name='unique_school_enrollment')
        ]

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.enrollment_number}"


class TeacherProfile(BaseProfile):
    """Profile specifically for Teachers/Educators."""
    employee_id = models.CharField(max_length=50)
    qualification = models.CharField(max_length=255, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(fields=['school', 'employee_id'], name='unique_school_employee_id')
        ]

    def __str__(self):
        return f"Prof. {self.user.last_name} ({self.employee_id})"


class ParentProfile(BaseProfile):
    """Profile specifically for Parents/Guardians."""
    occupation = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} (Parent)"

class ParentStudentMapping(TenantAwareModel):
    """
    Maps a parent to a student. This handles complex family structures 
    (e.g., siblings, divorced parents, step-parents) securely.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(ParentProfile, on_delete=models.CASCADE, related_name='student_mappings')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='parent_mappings')
    relationship = models.CharField(max_length=50) # e.g., 'Father', 'Mother', 'Guardian'
    
    # Granular permissions for edge cases (e.g., divorced parents)
    is_primary_contact = models.BooleanField(default=True)
    can_view_academics = models.BooleanField(default=True)
    can_pay_fees = models.BooleanField(default=True)

    class Meta:
        ordering = ['-id']
        # A parent shouldn't be mapped to the exact same student twice
        constraints = [
            models.UniqueConstraint(fields=['parent', 'student'], name='unique_parent_student_mapping')
        ]

    def __str__(self):
        return f"{self.parent.user.first_name} -> {self.student.user.first_name} ({self.relationship})"
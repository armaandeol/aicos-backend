from rest_framework import serializers
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from profiles.models import StudentProfile, TeacherProfile
from academics.models import TeacherAssignment

# --- EXISTING ATTENDANCE SERIALIZERS ---
class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_enrollment_no = serializers.CharField(source='student.enrollment_number', read_only=True)

    class Meta:
        model = Attendance
        fields = '__all__'
        read_only_fields = ('school', 'id')

class AttendanceRecordItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=Attendance.StatusChoices.choices)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)

class BulkAttendanceSerializer(serializers.Serializer):
    date = serializers.DateField()
    academic_year_id = serializers.UUIDField()
    class_level_id = serializers.UUIDField()
    section_id = serializers.UUIDField()
    records = AttendanceRecordItemSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        request = self.context.get('request')
        school = request.user.school
        
        student_ids = [record['student_id'] for record in attrs['records']]
        valid_students_count = StudentProfile.objects.filter(id__in=student_ids, school=school).count()
        
        if valid_students_count != len(student_ids):
            raise serializers.ValidationError("One or more students do not exist or belong to another school.")
        return attrs

# --- NEW EXAM & GRADING SERIALIZERS FOR TASK 4.3 ---

class ExamSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = Exam
        fields = '__all__'
        read_only_fields = ('school', 'id')

class StudentGradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = StudentGrade
        fields = '__all__'
        read_only_fields = ('school', 'id')

# --- BULK GRADING LOGIC ---

class GradeRecordItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    marks_obtained = serializers.DecimalField(max_digits=5, decimal_places=2)
    max_marks = serializers.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)

class BulkGradeSubmitSerializer(serializers.Serializer):
    """
    Validates the payload for submitting an entire column of grades.
    Enforces strict Teacher-Subject-Section RBAC logic.
    """
    exam_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    section_id = serializers.UUIDField() # Needed to verify if the teacher teaches this section
    records = GradeRecordItemSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user
        school = user.school
        
        exam = Exam.objects.filter(id=attrs['exam_id'], school=school).first()
        if not exam:
            raise serializers.ValidationError({"exam_id": "Invalid Exam or does not belong to your school."})

        # --- THE CRITICAL AUTHORIZATION LOGIC ---
        # Allow superusers or school admins to bypass this check
        if not (user.is_superuser or user.is_staff):
            teacher_profile = TeacherProfile.objects.filter(user=user).first()
            if not teacher_profile:
                raise serializers.ValidationError("You must be a registered teacher to submit grades.")

            # Validate the teacher is specifically assigned to this Subject and Section for this Academic Year
            is_assigned = TeacherAssignment.objects.filter(
                school=school,
                teacher=teacher_profile,
                subject_id=attrs['subject_id'],
                section_id=attrs['section_id'],
                academic_year=exam.academic_year
            ).exists()

            if not is_assigned:
                raise serializers.ValidationError(
                    "Security Exception: You are not assigned to teach this subject to this section. Grading access denied."
                )

        # Anti-Hijacking: Ensure all students in the payload belong to the school
        student_ids = [record['student_id'] for record in attrs['records']]
        valid_students_count = StudentProfile.objects.filter(id__in=student_ids, school=school).count()
        if valid_students_count != len(student_ids):
            raise serializers.ValidationError("One or more students do not exist or belong to another school.")
            
        return attrs
    


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = '__all__'
        read_only_fields = ('school', 'id', 'created_at')

class StudentSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentSubmission
        fields = '__all__'
        read_only_fields = ('school', 'id', 'submitted_at')
from rest_framework import serializers
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping

class StudentProfileSerializer(serializers.ModelSerializer):
    # Fetching user details so the frontend doesn't just get a UUID
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    address = serializers.CharField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    blood_group = serializers.CharField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

class TeacherProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = TeacherProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

class ParentProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = ParentProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

class ParentStudentMappingSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.user.first_name', read_only=True)
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)

    class Meta:
        model = ParentStudentMapping
        fields = '__all__'
        read_only_fields = ('school', 'id')
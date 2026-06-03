# school_admin/serializers/dashboard_serializers.py
from rest_framework import serializers
from school_admin.models import Notification, ActivityLog

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('school', 'id', 'created_at')

class ActivityLogSerializer(serializers.ModelSerializer):
    # Fetch the user's name instead of just their UUID
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = '__all__'
        read_only_fields = ('school', 'id', 'timestamp')

    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return "System"
from django.utils import timezone
from django.db.models import Count, Avg
from django.db.models.functions import TruncMonth
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, permissions
# Cross-app imports targeting the core models safely
from profiles.models import StudentProfile, TeacherProfile
from academics.models import ClassLevel, Section # Assuming ClassRoom lives in academics
from operations.models import Attendance
from school_admin.models import Notification

class DashboardStatsAPIView(APIView):
    """
    Retrieves high-level dashboard metrics for the School Administrator panel.
    Calculates total students, teachers, active classes, and overall attendance rate.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Safely capture the logged-in administrator's school context
        school = getattr(request.user, 'school', None)
        if not school:
            return Response(
                {"error": "User account is not associated with any active school/tenant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Optimized counts evaluated directly in the database engine
            total_students = StudentProfile.objects.filter(school=school).count()
            total_teachers = TeacherProfile.objects.filter(school=school).count()
            total_classes = ClassLevel.objects.filter(school=school).count()

            # --- NEW ATTENDANCE LOGIC ---
            # 1. Get all attendance records for this school
            all_attendance = Attendance.objects.filter(school=school)
            total_attendance_records = all_attendance.count()
            
            # 2. Get records where the student was Present or Late (meaning they showed up)
            present_records = all_attendance.filter(status__in=['Present', 'Late']).count()
            
            # 3. Calculate the percentage mathematically to avoid division by zero
            if total_attendance_records > 0:
                attendance_rate = (present_records / total_attendance_records) * 100
            else:
                attendance_rate = 100.00  # Default to 100% if no attendance data exists yet
            # ----------------------------

            payload = {
                "total_students": total_students,
                "total_teachers": total_teachers,
                "total_classes": total_classes,
                "attendance_rate": round(float(attendance_rate), 2),
                "academic_year": "2025-2026" 
            }
            
            return Response(payload, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": "Failed to calculate dashboard statistics.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class EnrollmentTrendAPIView(APIView):
    """
    Returns monthly student signup trends for the last 6 months 
    to populate the frontend bar charts.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = getattr(request.user, 'school', None)
        if not school:
            return Response({"error": "School context missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            six_months_ago = timezone.now() - timezone.timedelta(days=180)
            
            # FIXED: Querying 'user__date_joined' instead of 'created_at'
            trends = (
                StudentProfile.objects.filter(school=school, user__date_joined__gte=six_months_ago)
                .annotate(month=TruncMonth('user__date_joined'))
                .values('month')
                .annotate(count=Count('id'))
                .order_by('month')
            )

            # Format the output into clean JSON labels/values
            chart_data = [
                {
                    "month": item['month'].strftime('%B %Y') if item['month'] else "Unknown",
                    "enrollments": item['count']
                }
                for item in trends
            ]

            return Response({"trends": chart_data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": "Failed to compile enrollment trend analytics.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class NotificationListAPIView(APIView):
    """
    Fetches unresolved system alerts, notifications, and cross-profile requests.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = getattr(request.user, 'school', None)
        if not school:
            return Response({"error": "School context missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Fetch active alerts sorted by latest timestamp
            notifications = Notification.objects.filter(
                school=school,
                is_read=False
            ).order_by('-created_at')[:20]  # Limit to top 20 recent alerts

            serialized_notifications = [
                {
                    "id": item.id,
                    "title": item.title,
                    "message": item.message,
                    "type": item.notification_type,  # e.g., 'alert', 'info', 'request'
                    "created_at": item.created_at.isoformat()
                }
                for item in notifications
            ]

            return Response({"notifications": serialized_notifications}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": "Failed to pull operational notifications.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
from rest_framework.generics import ListAPIView
from school_admin.models import ActivityLog
from school_admin.serializers.dashboard_serializers import ActivityLogSerializer

class ActivityLogListAPIView(ListAPIView):
    """
    GET /api/v1/school-admin/logs/
    Returns the most recent activity logs for the dashboard feed.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ActivityLogSerializer

    def get_queryset(self):
        # Fetch the 10 most recent activities for the admin's school
        return ActivityLog.objects.filter(school=self.request.user.school).order_by('-timestamp')[:10]
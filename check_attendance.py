import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()
from operations.models import Attendance
for a in Attendance.objects.all():
    print(a.date, a.student_id, a.status)

import uuid
from django.db import models
from django.conf import settings
from tenants.models import TenantAwareModel

class Conversation(TenantAwareModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tutor_conversations')
    student_profile = models.ForeignKey('profiles.StudentProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='tutor_conversations')
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100, blank=True, null=True)
    class_level = models.CharField(max_length=50, blank=True, null=True)
    system_context = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    message_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.email}: {self.title[:50]}"

class Message(TenantAwareModel):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'AI Assistant'), ('system', 'System')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_used = models.IntegerField(default=0)
    model_used = models.CharField(max_length=50, default='deepseek-chat', blank=True)
    is_responded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."

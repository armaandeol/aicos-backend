from rest_framework import serializers
from .models import Conversation, Message

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'tokens_used', 'model_used', 'created_at']
        read_only_fields = ['id', 'created_at']

class ConversationListSerializer(serializers.ModelSerializer):
    last_message_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['id', 'title', 'subject', 'class_level', 'message_count', 'is_active', 'created_at', 'updated_at', 'last_message_preview']
    
    def get_last_message_preview(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return last_msg.content[:100]
        return "No messages yet"

class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Conversation
        fields = ['id', 'title', 'subject', 'class_level', 'system_context', 'messages', 'message_count', 'is_active', 'created_at', 'updated_at']

class CreateConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['id', 'title', 'subject', 'class_level', 'system_context', 'message_count', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'message_count', 'is_active', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['user'] = request.user
        validated_data['school'] = request.user.school
        
        # Auto-assign student profile if exists
        if hasattr(request.user, 'student_profile'):
            validated_data['student_profile'] = request.user.student_profile
        
        # Generate default system context if not provided
        if not validated_data.get('system_context'):
            topic = validated_data.get('title', 'general')
            subject = validated_data.get('subject', '')
            validated_data['system_context'] = f"You are an AI tutor helping with {topic}. Subject: {subject}. Be patient and explain concepts clearly step by step."
        
        return super().create(validated_data)

class SendMessageSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()
    message = serializers.CharField(max_length=5000, min_length=1)
    
    def validate_conversation_id(self, value):
        try:
            conversation = Conversation.objects.get(id=value)
            return value
        except Conversation.DoesNotExist:
            raise serializers.ValidationError("Conversation not found")

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from tenants.views import TenantAwareModelViewSet
from .models import Conversation, Message
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    CreateConversationSerializer, SendMessageSerializer, MessageSerializer
)
from .services.deepseek_client import deepseek_client

class ConversationViewSet(TenantAwareModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Conversation.objects.filter(
            user=self.request.user,
            school=self.request.user.school
        )
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateConversationSerializer
        elif self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationListSerializer
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school, user=self.request.user)
    
    @action(detail=False, methods=['post'], url_path='chat')
    def chat(self, request):
        serializer = SendMessageSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        conversation_id = serializer.validated_data['conversation_id']
        user_message = serializer.validated_data['message']
        conversation = Conversation.objects.get(id=conversation_id)
        
        try:
            with transaction.atomic():
                # 1. Save user message
                user_msg = Message.objects.create(
                    school=request.user.school,
                    conversation=conversation,
                    role='user',
                    content=user_message
                )
                
                # 2. Get conversation context for AI
                context = []
                
                # Add system context if exists
                if conversation.system_context:
                    context.append({
                        "role": "system",
                        "content": conversation.system_context
                    })
                
                # Add last 10 messages for context (to save tokens)
                recent_messages = conversation.messages.order_by('-created_at')[:10]
                for msg in reversed(recent_messages):
                    context.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                
                # 3. Get AI response from DeepSeek
                ai_response = deepseek_client.get_tutor_response(
                    conversation_context=context,
                    user_message=user_message,
                    temperature=0.7
                )
                
                # 4. Save AI response
                assistant_msg = Message.objects.create(
                    school=request.user.school,
                    conversation=conversation,
                    role='assistant',
                    content=ai_response['content'],
                    tokens_used=ai_response['tokens_used'],
                    model_used=ai_response['model']
                )
                
                # 5. Update user message as responded
                user_msg.is_responded = True
                user_msg.save(update_fields=['is_responded'])
                
                # 6. Update conversation message count
                conversation.message_count = conversation.messages.count()
                conversation.save(update_fields=['message_count'])
                
                # 7. Return the AI response
                return Response(MessageSerializer(assistant_msg).data, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {"error": f"Failed to get AI response: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

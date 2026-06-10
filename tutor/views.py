from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
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
        # Return only active (not soft-deleted) conversations for list views
        return Conversation.objects.filter(
            user=self.request.user,
            school=self.request.user.school,
            is_active=True,  # Only show active conversations
            is_deleted=False  # Exclude soft-deleted
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
    
    @action(detail=True, methods=['post'], url_path='soft-delete')
    def soft_delete(self, request, pk=None):
        """
        Soft delete a conversation (hide from user but keep in database)
        """
        conversation = self.get_object()
        
        # Mark as soft deleted
        conversation.is_active = False
        conversation.is_deleted = True
        conversation.deleted_at = timezone.now()
        conversation.save(update_fields=['is_active', 'is_deleted', 'deleted_at'])
        
        return Response({
            "detail": "Conversation moved to trash successfully",
            "conversation_id": str(conversation.id),
            "deleted_at": conversation.deleted_at
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        """
        Restore a soft-deleted conversation
        """
        # Allow access to soft-deleted conversations for restore operation
        conversation = Conversation.objects.get(
            id=pk,
            user=request.user,
            school=request.user.school,
            is_deleted=True  # Only allow restoring deleted conversations
        )
        
        # Restore the conversation
        conversation.is_active = True
        conversation.is_deleted = False
        conversation.deleted_at = None
        conversation.save(update_fields=['is_active', 'is_deleted', 'deleted_at'])
        
        return Response({
            "detail": "Conversation restored successfully",
            "conversation_id": str(conversation.id)
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='trash')
    def trash_list(self, request):
        """
        List all soft-deleted conversations (trash bin)
        """
        deleted_conversations = Conversation.objects.filter(
            user=request.user,
            school=request.user.school,
            is_deleted=True
        )
        serializer = ConversationListSerializer(deleted_conversations, many=True)
        return Response({
            "count": deleted_conversations.count(),
            "results": serializer.data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['delete'], url_path='permanent-delete')
    def permanent_delete(self, request, pk=None):
        """
        Permanently delete a conversation from database (hard delete)
        Use with caution - this cannot be undone
        """
        conversation = Conversation.objects.get(
            id=pk,
            user=request.user,
            school=request.user.school
        )
        
        # Store info for response
        conversation_title = conversation.title
        
        # Permanently delete from database
        conversation.delete()
        
        return Response({
            "detail": f"Conversation '{conversation_title}' permanently deleted",
            "conversation_id": str(pk)
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['delete'], url_path='empty-trash')
    def empty_trash(self, request):
        """
        Permanently delete all soft-deleted conversations for the user
        """
        deleted_conversations = Conversation.objects.filter(
            user=request.user,
            school=request.user.school,
            is_deleted=True
        )
        
        count = deleted_conversations.count()
        deleted_conversations.delete()
        
        return Response({
            "detail": f"Permanently deleted {count} conversations from trash",
            "deleted_count": count
        }, status=status.HTTP_200_OK)
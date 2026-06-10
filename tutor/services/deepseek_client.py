import os
import requests
from django.conf import settings

class DeepSeekClient:
    """
    Client for DeepSeek API (OpenAI-compatible)
    """
    
    def __init__(self):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        self.base_url = "https://api.deepseek.com/v1"
        
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment variables")
    
    def chat_completion(self, messages, temperature=0.7, max_tokens=2000):
        """
        Send chat completion request to DeepSeek API
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"DeepSeek API error: {str(e)}")
    
    def get_tutor_response(self, conversation_context, user_message, temperature=0.7):
        """
        Get AI tutor response for a user message
        """
        # Prepare messages with context
        messages = conversation_context.copy()
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        # Get response from API
        response = self.chat_completion(messages, temperature=temperature)
        
        # Extract the assistant's reply
        assistant_message = response['choices'][0]['message']['content']
        tokens_used = response.get('usage', {}).get('total_tokens', 0)
        
        return {
            "content": assistant_message,
            "tokens_used": tokens_used,
            "model": "deepseek-chat",
            "raw_response": response
        }

# Create singleton instance
deepseek_client = DeepSeekClient()

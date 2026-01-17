from groq import Groq
import config

class Summarizer:
    def __init__(self):
        self.client = Groq(api_key=config.GROQ_API_KEY)
    
    def summarize_messages(self, messages):
        """Generate bullet-point summary with message count"""
        if not messages:
            return "No messages found in the specified timeframe."
        
        # Format messages for LLM
        conversation = "\n".join([
            f"[{msg['timestamp']}] {msg.get('username') or msg.get('first_name', 'Unknown')}: {msg['message_text']}"
            for msg in messages
        ])
        
        prompt = f"""You are a conversation summarizer for a Telegram group. Analyze the following {len(messages)} messages and provide:

1. A concise bullet-point summary of the main topics discussed
2. Key decisions or action items (if any)
3. Important announcements or highlights

Keep it brief and informative. Use bullet points.

CONVERSATION:
{conversation}

SUMMARY:"""
        
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-70b-versatile",  # Fast, multi-language support
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800
            )
            
            summary = response.choices[0].message.content
            return f"📊 **Summary of {len(messages)} messages:**\n\n{summary}"
        
        except Exception as e:
            return f"❌ Error generating summary: {str(e)}"
    
    def summarize_user_messages(self, username, messages):
        """Summarize specific user's contributions"""
        if not messages:
            return f"No messages found from {username} in the specified timeframe."
        
        user_texts = [msg['message_text'] for msg in messages]
        conversation = "\n".join(user_texts)
        
        prompt = f"""Summarize the key contributions and topics discussed by user '{username}' based on their {len(messages)} messages:

{conversation}

Provide a brief bullet-point summary of their main points."""
        
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            summary = response.choices[0].message.content
            return f"👤 **Summary for @{username} ({len(messages)} messages):**\n\n{summary}"
        
        except Exception as e:
            return f"❌ Error generating user summary: {str(e)}"

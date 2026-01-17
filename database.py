from supabase import create_client, Client
from datetime import datetime, timedelta
import config

class Database:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    
    def init_tables(self):
        """Initialize database tables - Run this once manually in Supabase SQL Editor"""
        # SQL Schema (run in Supabase dashboard):
        """
        -- Messages table
        CREATE TABLE messages (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT,
            first_name TEXT,
            message_text TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX idx_messages_group_timestamp ON messages(group_id, timestamp DESC);
        CREATE INDEX idx_messages_user ON messages(user_id, group_id);
        
        -- Group settings table
        CREATE TABLE group_settings (
            group_id BIGINT PRIMARY KEY,
            lookback_minutes INT DEFAULT 60,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        -- Summaries table (for tracking and auto-deletion)
        CREATE TABLE summaries (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL,
            summary_text TEXT NOT NULL,
            message_count INT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX idx_summaries_created ON summaries(created_at);
        """
        pass
    
    def store_message(self, group_id, message_id, user_id, username, first_name, message_text, timestamp):
        """Store a new message in the database"""
        try:
            self.client.table("messages").insert({
                "group_id": group_id,
                "message_id": message_id,
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "message_text": message_text,
                "timestamp": timestamp.isoformat()
            }).execute()
        except Exception as e:
            print(f"Error storing message: {e}")
    
    def get_messages(self, group_id, lookback_minutes, max_messages=500):
        """Fetch messages for summary"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        
        try:
            response = self.client.table("messages")\
                .select("*")\
                .eq("group_id", group_id)\
                .gte("timestamp", cutoff_time.isoformat())\
                .order("timestamp", desc=False)\
                .limit(max_messages)\
                .execute()
            
            return response.data
        except Exception as e:
            print(f"Error fetching messages: {e}")
            return []
    
    def get_user_messages(self, group_id, username, lookback_minutes):
        """Fetch messages from specific user"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        
        try:
            response = self.client.table("messages")\
                .select("*")\
                .eq("group_id", group_id)\
                .eq("username", username.replace("@", ""))\
                .gte("timestamp", cutoff_time.isoformat())\
                .order("timestamp", desc=False)\
                .execute()
            
            return response.data
        except Exception as e:
            print(f"Error fetching user messages: {e}")
            return []
    
    def get_active_users(self, group_id, lookback_minutes):
        """Get most active users with message counts"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        
        try:
            response = self.client.table("messages")\
                .select("username, first_name")\
                .eq("group_id", group_id)\
                .gte("timestamp", cutoff_time.isoformat())\
                .execute()
            
            # Count messages per user
            user_counts = {}
            for msg in response.data:
                username = msg.get("username") or msg.get("first_name", "Unknown")
                user_counts[username] = user_counts.get(username, 0) + 1
            
            # Sort by message count
            return sorted(user_counts.items(), key=lambda x: x[1], reverse=True)
        except Exception as e:
            print(f"Error getting active users: {e}")
            return []
    
    def set_group_lookback(self, group_id, lookback_minutes):
        """Update group's lookback window setting"""
        try:
            self.client.table("group_settings")\
                .upsert({"group_id": group_id, "lookback_minutes": lookback_minutes})\
                .execute()
        except Exception as e:
            print(f"Error updating settings: {e}")
    
    def get_group_lookback(self, group_id):
        """Get group's lookback window"""
        try:
            response = self.client.table("group_settings")\
                .select("lookback_minutes")\
                .eq("group_id", group_id)\
                .execute()
            
            if response.data:
                return response.data[0]["lookback_minutes"]
            return config.DEFAULT_LOOKBACK_MINUTES
        except Exception as e:
            print(f"Error fetching settings: {e}")
            return config.DEFAULT_LOOKBACK_MINUTES
    
    def store_summary(self, group_id, summary_text, message_count):
        """Store summary for tracking"""
        try:
            self.client.table("summaries").insert({
                "group_id": group_id,
                "summary_text": summary_text,
                "message_count": message_count
            }).execute()
        except Exception as e:
            print(f"Error storing summary: {e}")
    
    def cleanup_old_data(self):
        """Delete messages older than 7 days and summaries older than 14 days"""
        msg_cutoff = datetime.utcnow() - timedelta(days=config.MESSAGE_RETENTION_DAYS)
        summary_cutoff = datetime.utcnow() - timedelta(days=config.SUMMARY_DELETION_DAYS)
        
        try:
            # Delete old messages
            self.client.table("messages")\
                .delete()\
                .lt("timestamp", msg_cutoff.isoformat())\
                .execute()
            
            # Delete old summaries
            self.client.table("summaries")\
                .delete()\
                .lt("created_at", summary_cutoff.isoformat())\
                .execute()
            
            print(f"Cleanup completed at {datetime.utcnow()}")
        except Exception as e:
            print(f"Error during cleanup: {e}")

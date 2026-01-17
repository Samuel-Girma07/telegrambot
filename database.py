"""
Database operations using Supabase
Handles all data persistence for the bot
"""

from supabase import create_client
from datetime import datetime, timedelta, timezone
import config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        """Initialize Supabase client"""
        # NO type hint for client to avoid version issues
        try:
            self.client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
            logger.info("✅ Supabase client initialized successfully")
        except Exception as e:
            logger.critical(f"Failed to initialize Supabase client: {e}")
            raise

    def store_message(self, group_id, message_id, user_id, username, first_name, message_text, timestamp):
        """Store a message in the database"""
        try:
            data = {
                "group_id": group_id,
                "message_id": message_id,
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "message_text": message_text,
                "timestamp": timestamp.isoformat()
            }
            
            result = self.client.table("messages").insert(data).execute()
            logger.debug(f"Message stored: group={group_id}, user=@{username}")
            return result
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            return None
    
    def get_recent_messages(self, group_id, minutes):
        """Get recent messages from a group within specified time window"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            result = self.client.table("messages")\
                .select("*")\
                .eq("group_id", group_id)\
                .gte("timestamp", cutoff_time.isoformat())\
                .order("timestamp", desc=False)\
                .execute()
            
            messages = result.data if result.data else []
            logger.info(f"Retrieved {len(messages)} messages for group {group_id}")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []
    
    def get_user_messages(self, group_id, username, minutes):
        """Get messages from a specific user within time window"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            result = self.client.table("messages")\
                .select("*")\
                .eq("group_id", group_id)\
                .eq("username", username)\
                .gte("timestamp", cutoff_time.isoformat())\
                .order("timestamp", desc=False)\
                .execute()
            
            messages = result.data if result.data else []
            logger.info(f"Retrieved {len(messages)} messages from @{username}")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting user messages: {e}")
            return []
    
    def get_user_stats(self, group_id, minutes, limit=10):
        """Get user activity statistics for a group"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            result = self.client.table("messages")\
                .select("username, first_name")\
                .eq("group_id", group_id)\
                .gte("timestamp", cutoff_time.isoformat())\
                .execute()
            
            if not result.data:
                return []
            
            # Count messages per user
            user_counts = {}
            for msg in result.data:
                username = msg.get("username", "unknown")
                first_name = msg.get("first_name", "Unknown")
                key = (username, first_name)
                user_counts[key] = user_counts.get(key, 0) + 1
            
            # Sort by message count (descending) and limit
            sorted_stats = sorted(
                user_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:limit]
            
            # Format as list of tuples
            stats = [(username, first_name, count) 
                    for (username, first_name), count in sorted_stats]
            
            logger.info(f"User stats calculated for group {group_id}: {len(stats)} users")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return []
    
    def get_group_setting(self, group_id):
        """Get the lookback time setting for a group"""
        try:
            result = self.client.table("group_settings")\
                .select("lookback_minutes")\
                .eq("group_id", group_id)\
                .execute()
            
            if result.data and len(result.data) > 0:
                minutes = result.data[0]["lookback_minutes"]
                logger.debug(f"Group {group_id} setting: {minutes} minutes")
                return minutes
            else:
                # Return default if not set
                logger.debug(f"Group {group_id} using default setting")
                return config.DEFAULT_LOOKBACK_MINUTES
                
        except Exception as e:
            logger.error(f"Error getting group setting: {e}")
            return config.DEFAULT_LOOKBACK_MINUTES
    
    def update_group_setting(self, group_id, lookback_minutes):
        """Update the lookback time setting for a group"""
        try:
            # Check if setting exists
            existing = self.client.table("group_settings")\
                .select("*")\
                .eq("group_id", group_id)\
                .execute()
            
            data = {
                "group_id": group_id,
                "lookback_minutes": lookback_minutes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if existing.data and len(existing.data) > 0:
                # Update existing setting
                result = self.client.table("group_settings")\
                    .update(data)\
                    .eq("group_id", group_id)\
                    .execute()
                logger.info(f"Updated setting for group {group_id}: {lookback_minutes} min")
            else:
                # Insert new setting
                data["created_at"] = datetime.now(timezone.utc).isoformat()
                result = self.client.table("group_settings")\
                    .insert(data)\
                    .execute()
                logger.info(f"Created setting for group {group_id}: {lookback_minutes} min")
            
            return result
            
        except Exception as e:
            logger.error(f"Error updating group setting: {e}")
            return None
    
    def cleanup_old_data(self, days=7):
        """Delete messages older than specified days"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            result = self.client.table("messages")\
                .delete()\
                .lt("timestamp", cutoff_date.isoformat())\
                .execute()
            
            logger.info(f"Cleanup completed: Deleted messages older than {days} days")
            return result
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return None

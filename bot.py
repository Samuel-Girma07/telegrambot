"""
Telegram Conversation Summarizer Bot
With health check endpoint for Render deployment

Features:
- Summarize group conversations using AI
- Track user activity and message statistics
- Configurable time windows for summaries
- Health check endpoint for Render.com
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters, 
    ContextTypes
)
from datetime import datetime, timedelta, timezone, time
import logging
import threading
import os

# ============================================
# HEALTH CHECK SERVER FOR RENDER
# ============================================
from flask import Flask

health_app = Flask(__name__)

@health_app.route('/')
def home():
    """Root endpoint - confirms bot is running"""
    return "Telegram Bot is running! ✅", 200

@health_app.route('/health')
def health():
    """Health check endpoint for Render"""
    return "OK", 200

def run_health_server():
    """
    Run Flask server on port specified by Render
    Render sets PORT env var to 10000
    """
    try:
        port = int(os.environ.get('PORT', 8080))
        # Use 0.0.0.0 to bind to all interfaces (required for Render)
        health_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================
# GLOBAL VARIABLES
# ============================================
db = None
summarizer = None

# ============================================
# COMMAND HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Show welcome message"""
    welcome_message = """
👋 **Welcome to Conversation Summarizer Bot!**

I help you catch up on group conversations without reading hundreds of messages.

**Commands:**
• `/catchup` - Get a summary of recent messages
• `/setting` - Configure lookback time window (Admin only)
• `/who` - See most active users
• `/person @username` - Summary of specific user's messages

⚠️ **Note:** I can only track messages from the moment I joined this group forward.

Add me to your groups and let's get started! 🚀
    """
    try:
        await update.message.reply_text(welcome_message, parse_mode="Markdown")
        logger.info(f"Start command executed by user {update.message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        # Only try to reply if we can
        try:
            await update.message.reply_text("An error occurred. Please try again.")
        except:
            pass

async def catchup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /catchup command - Generate conversation summary"""
    global db, summarizer
    
    try:
        # Only works in groups
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        group_id = update.message.chat_id
        lookback_minutes = db.get_group_setting(group_id)
        
        # Fetch recent messages
        messages = db.get_recent_messages(group_id, lookback_minutes)
        
        if not messages:
            await update.message.reply_text(
                f"📭 No messages found in the last {lookback_minutes} minutes."
            )
            return
        
        await update.message.reply_text("⏳ Generating summary...")
        
        # Generate AI summary
        summary_text = summarizer.summarize(messages)
        
        await update.message.reply_text(
            f"📊 **Summary of last {lookback_minutes} minutes:**\n\n{summary_text}",
            parse_mode="Markdown"
        )
        
        logger.info(f"Catchup generated for group {group_id} ({len(messages)} messages)")
        
    except Exception as e:
        logger.error(f"Error in catchup: {e}")
        await update.message.reply_text("❌ An error occurred generating the summary.")

async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setting command - Configure time window (admin only)"""
    global db
    
    try:
        # Only works in groups
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        # Check if user is admin
        user = update.message.from_user
        chat = update.message.chat
        member = await context.bot.get_chat_member(chat.id, user.id)
        
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("⚠️ Only admins can change settings!")
            return
        
        # Import config to access TIME_WINDOWS
        import config
        
        # Build inline keyboard with time options
        keyboard = []
        for label, minutes in config.TIME_WINDOWS.items():
            keyboard.append([InlineKeyboardButton(label, callback_data=f"set_{minutes}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        current_setting = db.get_group_setting(chat.id)
        
        await update.message.reply_text(
            f"⚙️ **Current setting:** {current_setting} minutes\n\n"
            f"Choose a new time window:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in setting command: {e}")
        await update.message.reply_text("❌ An error occurred.")

async def setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setting selection from inline keyboard"""
    global db
    
    query = update.callback_query
    await query.answer()
    
    try:
        # Extract minutes from callback data
        minutes = int(query.data.replace("set_", ""))
        group_id = query.message.chat_id
        
        # Update database
        db.update_group_setting(group_id, minutes)
        
        await query.edit_message_text(
            f"✅ **Setting updated!**\n\n"
            f"New lookback time: **{minutes} minutes**"
        )
        
        logger.info(f"Setting updated for group {group_id}: {minutes} minutes")
        
    except Exception as e:
        logger.error(f"Error in setting callback: {e}")
        await query.edit_message_text("❌ An error occurred updating the setting.")

async def who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /who command - Show most active users"""
    global db
    
    try:
        # Only works in groups
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        group_id = update.message.chat_id
        lookback_minutes = db.get_group_setting(group_id)
        
        # Get user statistics
        stats = db.get_user_stats(group_id, lookback_minutes)
        
        if not stats:
            await update.message.reply_text(
                f"📭 No messages found in the last {lookback_minutes} minutes."
            )
            return
        
        # Format response
        response = f"👥 **Most active users (last {lookback_minutes} min):**\n\n"
        
        for rank, (username, first_name, count) in enumerate(stats, 1):
            display_name = f"@{username}" if username else first_name
            response += f"{rank}. {display_name}: **{count}** messages\n"
        
        await update.message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in who command: {e}")
        await update.message.reply_text("❌ An error occurred.")

async def person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /person command - Get summary for specific user"""
    global db, summarizer
    
    try:
        # Only works in groups
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        # Check if username provided
        if not context.args:
            await update.message.reply_text("⚠️ Usage: `/person @username`", parse_mode="Markdown")
            return
        
        target_username = context.args[0].lstrip("@")
        group_id = update.message.chat_id
        lookback_minutes = db.get_group_setting(group_id)
        
        # Get messages from specific user
        messages = db.get_user_messages(group_id, target_username, lookback_minutes)
        
        if not messages:
            await update.message.reply_text(
                f"📭 No messages from @{target_username} in the last {lookback_minutes} minutes."
            )
            return
        
        # Generate summary
        summary_text = summarizer.summarize(messages)
        
        await update.message.reply_text(
            f"📊 **Summary of @{target_username}'s messages:**\n\n{summary_text}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in person command: {e}")
        await update.message.reply_text("❌ An error occurred.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store all group messages in database"""
    global db
    
    try:
        if update.message and update.message.chat.type in ["group", "supergroup"]:
            message = update.message
            
            # Only store text messages
            if not message.text:
                return
            
            # Store in database
            db.store_message(
                group_id=message.chat_id,
                message_id=message.message_id,
                user_id=message.from_user.id,
                username=message.from_user.username or "unknown",
                first_name=message.from_user.first_name or "Unknown",
                message_text=message.text,
                timestamp=message.date
            )
            
            logger.debug(f"Stored message from group {message.chat_id}")
    
    except Exception as e:
        logger.error(f"Error storing message: {e}")

async def daily_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Run daily cleanup of old data (scheduled job)"""
    global db
    
    try:
        logger.info("Starting daily cleanup...")
        db.cleanup_old_data()
        logger.info("Daily cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during daily cleanup: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error {context.error}")

# ============================================
# MAIN APPLICATION
# ============================================

def main():
    """
    Main application entry point
    Starts health server, initializes database, and runs bot
    """
    global db, summarizer
    
    try:
        # STEP 1: START HEALTH SERVER FIRST (critical for Render)
        logger.info("Starting health check server...")
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        logger.info("✅ Health server started successfully")
        
        # STEP 2: INITIALIZE DATABASE AND SUMMARIZER
        logger.info("Initializing database and summarizer...")
        import config
        from database import Database
        from summarizer import Summarizer
        
        db = Database()
        summarizer = Summarizer()
        logger.info("✅ Database and summarizer initialized successfully")
        
        # STEP 3: CREATE TELEGRAM BOT APPLICATION
        logger.info("Creating Telegram bot application...")
        app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Register command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("catchup", catchup))
        app.add_handler(CommandHandler("setting", setting))
        app.add_handler(CommandHandler("who", who))
        app.add_handler(CommandHandler("person", person))
        
        # Register callback handler for settings menu
        app.add_handler(CallbackQueryHandler(setting_callback, pattern="^set_"))
        
        # Register message handler (store all text messages)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        
        # Register error handler
        app.add_error_handler(error_handler)
        
        # Schedule daily cleanup job at 3 AM UTC
        app.job_queue.run_daily(
            daily_cleanup, 
            time=time(hour=3, minute=0, tzinfo=timezone.utc)
        )
        
        logger.info("🤖 Telegram bot started successfully!")
        logger.info("Running in polling mode...")
        print("\n" + "="*60)
        print("✅ Bot is running successfully!")
        print("="*60)
        print("Press Ctrl+C to stop.\n")
        
        # Start polling (long polling mode for updates)
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.error(f"❌ Fatal error starting bot: {e}")
        # In case of fatal error, keep main thread alive for a bit so logs can flush
        import time as t
        t.sleep(5)
        raise

if __name__ == "__main__":
    main()

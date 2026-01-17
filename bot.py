"""
Telegram Conversation Summarizer Bot
With health check endpoint for Koyeb
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta, timezone
import config
from database import Database
from summarizer import Summarizer
import logging
import threading
import os

# ============================================
# HEALTH CHECK SERVER FOR KOYEB
# ============================================
from flask import Flask

health_app = Flask(__name__)

@health_app.route('/')
def home():
    return "Telegram Bot is running!", 200

@health_app.route('/health')
def health():
    return "OK", 200

def run_health_server():
    """Run Flask server on port 8080 for Koyeb health checks"""
    port = int(os.environ.get('PORT', 8080))
    health_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ============================================
# Setup logging
# ============================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database and summarizer
db = Database()
summarizer = Summarizer()

# ============================================
# COMMAND HANDLERS (keep all your existing code)
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
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
        await update.message.reply_text("An error occurred. Please try again.")

# [KEEP ALL YOUR OTHER COMMAND HANDLERS - catchup, setting, who, person, etc.]
# [Don't duplicate, just keep the existing code]

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store all group messages"""
    try:
        if update.message and update.message.chat.type in ["group", "supergroup"]:
            message = update.message
            
            if not message.text:
                return
            
            db.store_message(
                group_id=message.chat_id,
                message_id=message.message_id,
                user_id=message.from_user.id,
                username=message.from_user.username or "unknown",
                first_name=message.from_user.first_name or "Unknown",
                message_text=message.text,
                timestamp=message.date
            )
            
            logger.info(f"Stored message from group {message.chat_id}")
    
    except Exception as e:
        logger.error(f"Error storing message: {e}")

# [KEEP ALL OTHER HANDLERS - catchup, setting, etc. - I won't repeat them here]

async def daily_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Run daily cleanup of old data"""
    try:
        logger.info("Starting daily cleanup...")
        db.cleanup_old_data()
        logger.info("Daily cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during daily cleanup: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

# ============================================
# MAIN APPLICATION
# ============================================

def main():
    """Start the bot and health server"""
    try:
        # START HEALTH SERVER IN BACKGROUND THREAD
        logger.info("Starting health check server on port 8080...")
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        logger.info("✅ Health server started")
        
        # Create Telegram bot application
        app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Add command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("catchup", catchup))
        app.add_handler(CommandHandler("setting", setting))
        app.add_handler(CommandHandler("who", who))
        app.add_handler(CommandHandler("person", person))
        
        # Add callback handler for settings menu
        app.add_handler(CallbackQueryHandler(setting_callback, pattern="^set_"))
        
        # Add message handler (store all group messages)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        
        # Add error handler
        app.add_error_handler(error_handler)
        
        # Add daily cleanup job (runs at 3 AM UTC)
        app.job_queue.run_daily(
            daily_cleanup, 
            time=datetime.time(hour=3, minute=0, tzinfo=timezone.utc)
        )
        
        logger.info("🤖 Telegram bot started successfully! Running in polling mode...")
        print("✅ Bot is running... Press Ctrl+C to stop.")
        
        # Start polling
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.error(f"Fatal error starting bot: {e}")
        raise

if __name__ == "__main__":
    main()

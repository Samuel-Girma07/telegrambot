"""
Telegram Conversation Summarizer Bot
Optimized for Render.com free tier deployment
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta, timezone
import config
from database import Database
from summarizer import Summarizer
import logging

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database and summarizer
db = Database()
summarizer = Summarizer()

# ============================================
# COMMAND HANDLERS
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


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store all group messages"""
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
            
            logger.info(f"Stored message from group {message.chat_id}")
    
    except Exception as e:
        logger.error(f"Error storing message: {e}")


async def catchup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate conversation summary"""
    try:
        # Check if command is in group
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        group_id = update.message.chat_id
        lookback_minutes = db.get_group_lookback(group_id)
        
        # Send processing message
        processing_msg = await update.message.reply_text("🔄 Generating summary... This may take a few seconds.")
        
        # Fetch messages
        messages = db.get_messages(group_id, lookback_minutes, config.MAX_MESSAGES_PER_SUMMARY)
        
        if not messages:
            await processing_msg.edit_text(
                f"📭 No messages found in the last {lookback_minutes} minutes.\n"
                f"Use /setting to adjust the time window."
            )
            return
        
        # Generate summary
        summary = summarizer.summarize_messages(messages)
        
        # Store summary for tracking
        db.store_summary(group_id, summary, len(messages))
        
        # Send summary
        await processing_msg.edit_text(summary, parse_mode="Markdown")
        logger.info(f"Summary generated for group {group_id}: {len(messages)} messages")
    
    except Exception as e:
        logger.error(f"Error in catchup command: {e}")
        await update.message.reply_text(
            "❌ An error occurred while generating the summary. Please try again later."
        )


async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu (admin only)"""
    try:
        # Check if command is in group
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        # Check if user is admin
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            
            if member.status not in ["creator", "administrator"]:
                await update.message.reply_text("⚠️ Only group admins can change settings.")
                logger.info(f"Non-admin user {user_id} tried to access settings")
                return
        
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("❌ Error checking permissions. Please try again.")
            return
        
        # Create inline keyboard with time options
        keyboard = []
        for label, minutes in config.TIME_WINDOWS.items():
            keyboard.append([InlineKeyboardButton(label, callback_data=f"set_{minutes}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        current_setting = db.get_group_lookback(chat_id)
        await update.message.reply_text(
            f"⚙️ **Current lookback window:** {current_setting} minutes\n\n"
            f"Select a new time window:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        logger.info(f"Settings menu shown to admin {user_id} in group {chat_id}")
    
    except Exception as e:
        logger.error(f"Error in setting command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")


async def setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setting selection from inline keyboard"""
    try:
        query = update.callback_query
        await query.answer()
        
        # Extract minutes from callback data
        minutes = int(query.data.split("_")[1])
        group_id = query.message.chat_id
        
        # Update database
        db.set_group_lookback(group_id, minutes)
        
        # Confirm update
        await query.edit_message_text(
            f"✅ Lookback window updated to **{minutes} minutes**!\n\n"
            f"Use /catchup to test the new setting.",
            parse_mode="Markdown"
        )
        logger.info(f"Lookback window updated to {minutes} minutes for group {group_id}")
    
    except Exception as e:
        logger.error(f"Error in setting callback: {e}")
        try:
            await query.edit_message_text("❌ Error updating settings. Please try again.")
        except:
            pass


async def who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show most active users"""
    try:
        # Check if command is in group
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        group_id = update.message.chat_id
        lookback_minutes = db.get_group_lookback(group_id)
        
        # Fetch active users
        active_users = db.get_active_users(group_id, lookback_minutes)
        
        if not active_users:
            await update.message.reply_text(
                f"📭 No activity in the last {lookback_minutes} minutes."
            )
            return
        
        # Format response
        response = f"👥 **Most Active Users (Last {lookback_minutes} minutes):**\n\n"
        for i, (username, count) in enumerate(active_users[:10], 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▪️"
            response += f"{emoji} {i}. @{username}: {count} messages\n"
        
        await update.message.reply_text(response, parse_mode="Markdown")
        logger.info(f"Active users list generated for group {group_id}")
    
    except Exception as e:
        logger.error(f"Error in who command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")


async def person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarize specific user's messages"""
    try:
        # Check if command is in group
        if update.message.chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("⚠️ This command only works in groups!")
            return
        
        # Check if username is provided
        if not context.args:
            await update.message.reply_text(
                "Usage: `/person @username`\n\nExample: `/person @john`",
                parse_mode="Markdown"
            )
            return
        
        username = context.args[0].replace("@", "")
        group_id = update.message.chat_id
        lookback_minutes = db.get_group_lookback(group_id)
        
        # Send processing message
        processing_msg = await update.message.reply_text("🔄 Fetching user messages...")
        
        # Fetch user-specific messages
        messages = db.get_user_messages(group_id, username, lookback_minutes)
        
        if not messages:
            await processing_msg.edit_text(
                f"📭 No messages found from @{username} in the last {lookback_minutes} minutes."
            )
            return
        
        # Generate summary
        summary = summarizer.summarize_user_messages(username, messages)
        
        # Send summary
        await processing_msg.edit_text(summary, parse_mode="Markdown")
        logger.info(f"User summary generated for @{username} in group {group_id}")
    
    except Exception as e:
        logger.error(f"Error in person command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")


# ============================================
# SCHEDULED JOBS
# ============================================

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
    """Start the bot"""
    try:
        # Create application
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
        
        logger.info("Bot started successfully! Running in polling mode...")
        print("✅ Bot is running... Press Ctrl+C to stop.")
        
        # Start polling
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.error(f"Fatal error starting bot: {e}")
        raise


if __name__ == "__main__":
    main()

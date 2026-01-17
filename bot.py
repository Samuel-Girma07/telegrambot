from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta
import pytz
import config
from database import Database
from summarizer import Summarizer

db = Database()
summarizer = Summarizer()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = """
👋 **Welcome to Conversation Summarizer Bot!**

I help you catch up on group conversations without reading hundreds of messages.

**Commands:**
• `/catchup` - Get a summary of recent messages
• `/setting` - Configure lookback time window
• `/who` - See most active users
• `/person @username` - Summary of specific user's messages

⚠️ **Note:** I can only track messages from the moment I joined this group forward.

Add me to your groups and let's get started! 🚀
    """
    await update.message.reply_text(welcome_message, parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store all group messages"""
    if update.message.chat.type in ["group", "supergroup"]:
        message = update.message
        
        db.store_message(
            group_id=message.chat_id,
            message_id=message.message_id,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text=message.text or "[Non-text message]",
            timestamp=message.date
        )

async def catchup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate conversation summary"""
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command only works in groups!")
        return
    
    group_id = update.message.chat_id
    lookback_minutes = db.get_group_lookback(group_id)
    
    await update.message.reply_text("🔄 Generating summary... This may take a few seconds.")
    
    # Fetch messages
    messages = db.get_messages(group_id, lookback_minutes, config.MAX_MESSAGES_PER_SUMMARY)
    
    if not messages:
        await update.message.reply_text(
            f"No messages found in the last {lookback_minutes} minutes. "
            f"Use /setting to adjust the time window."
        )
        return
    
    # Generate summary
    summary = summarizer.summarize_messages(messages)
    
    # Store summary
    db.store_summary(group_id, summary, len(messages))
    
    await update.message.reply_text(summary, parse_mode="Markdown")

async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu (admin only)"""
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command only works in groups!")
        return
    
    # Check if user is admin
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    member = await context.bot.get_chat_member(chat_id, user_id)
    
    if member.status not in ["creator", "administrator"]:
        await update.message.reply_text("⚠️ Only group admins can change settings.")
        return
    
    # Create inline keyboard
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

async def setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setting selection"""
    query = update.callback_query
    await query.answer()
    
    minutes = int(query.data.split("_")[1])
    group_id = query.message.chat_id
    
    db.set_group_lookback(group_id, minutes)
    
    await query.edit_message_text(
        f"✅ Lookback window updated to **{minutes} minutes**!",
        parse_mode="Markdown"
    )

async def who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show most active users"""
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command only works in groups!")
        return
    
    group_id = update.message.chat_id
    lookback_minutes = db.get_group_lookback(group_id)
    
    active_users = db.get_active_users(group_id, lookback_minutes)
    
    if not active_users:
        await update.message.reply_text("No activity in the specified timeframe.")
        return
    
    response = f"👥 **Most Active Users (Last {lookback_minutes} minutes):**\n\n"
    for i, (username, count) in enumerate(active_users[:10], 1):
        response += f"{i}. @{username}: {count} messages\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarize specific user's messages"""
    if update.message.chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command only works in groups!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/person @username`", parse_mode="Markdown")
        return
    
    username = context.args[0].replace("@", "")
    group_id = update.message.chat_id
    lookback_minutes = db.get_group_lookback(group_id)
    
    await update.message.reply_text("🔄 Fetching user messages...")
    
    messages = db.get_user_messages(group_id, username, lookback_minutes)
    summary = summarizer.summarize_user_messages(username, messages)
    
    await update.message.reply_text(summary, parse_mode="Markdown")

async def daily_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Run daily cleanup of old data"""
    print("Running daily cleanup...")
    db.cleanup_old_data()

async def shutdown_warning(context: ContextTypes.DEFAULT_TYPE):
    """Send warning before bot goes down (for PythonAnywhere)"""
    # This would be triggered manually or via cron
    message = "⚠️ Bot maintenance scheduled in 10 minutes. Service will resume shortly."
    # Send to all active groups (you'd need to track these)
    pass

def main():
    """Start the bot"""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catchup", catchup))
    app.add_handler(CommandHandler("setting", setting))
    app.add_handler(CommandHandler("who", who))
    app.add_handler(CommandHandler("person", person))
    
    # Callback handler for settings
    app.add_handler(CallbackQueryHandler(setting_callback, pattern="^set_"))
    
    # Message handler (store all group messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Daily cleanup job (runs at 3 AM UTC)
    app.job_queue.run_daily(daily_cleanup, time=datetime.time(hour=3, minute=0))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

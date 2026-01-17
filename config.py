import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Groq Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Bot Settings
MESSAGE_RETENTION_DAYS = 7
SUMMARY_DELETION_DAYS = 14
MAX_MESSAGES_PER_SUMMARY = 500
DEFAULT_LOOKBACK_MINUTES = 60

# Time windows for /setting command (in minutes)
TIME_WINDOWS = {
    "10 minutes": 10,
    "30 minutes": 30,
    "1 hour": 60,
    "6 hours": 360,
    "12 hours": 720,
    "24 hours": 1440,
    "3 days": 4320,
    "1 week": 10080,
    "1 month": 43200
}

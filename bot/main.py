import asyncio
from telethon import TelegramClient
from bot.config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, logger
from bot.database import init_db
from bot.scheduler import scheduler, load_recovery_jobs
import bot.scheduler as scheduler_module

# Import Handlers
from bot.handlers.start import start_handler, help_handler
from bot.handlers.chat_management import detect_handler, deletechat_handler
from bot.handlers.schedule import schedule_handler
from bot.handlers.repeat import repeat_handler
from bot.handlers.list import list_handler
from bot.handlers.bulk import bulk_handler
from bot.handlers.admin_manager import admin_manager_handler
from bot.handlers.cancel import cancel_one_handler, stopall_handler
from bot.handlers.user_management import adduser_handler, backup_handler

bot = TelegramClient('session_bot', API_ID, API_HASH)

async def main():
    logger.info("Starting Bot...")
    await bot.start(bot_token=BOT_TOKEN)
    
    # Initialize DB & Scheduler
    await init_db(OWNER_ID)
    scheduler_module.bot_client = bot
    scheduler.start()
    
    # Auto-recovery
    await load_recovery_jobs()
    logger.info("System Ready & Scheduled Jobs Recovered.")

    # Register Handlers
    bot.add_event_handler(start_handler)
    bot.add_event_handler(help_handler)
    bot.add_event_handler(bulk_handler)
    bot.add_event_handler(detect_handler)
    bot.add_event_handler(deletechat_handler)
    bot.add_event_handler(schedule_handler)
    bot.add_event_handler(repeat_handler)
    bot.add_event_handler(list_handler)
    bot.add_event_handler(cancel_one_handler)
    bot.add_event_handler(stopall_handler)
    bot.add_event_handler(adduser_handler)
    bot.add_event_handler(backup_handler)

    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
from bot.config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from bot.database import init_db, run_state
from telethon import TelegramClient
import bot.scheduler as scheduler_module

bot = TelegramClient('session_bot', API_ID, API_HASH)

async def test_run():
    await bot.start(bot_token=BOT_TOKEN)
    await init_db(OWNER_ID)
    scheduler_module.bot_client = bot
    
    # Get the active run
    active_run = await run_state.find_one({"status": "active"})
    if active_run:
        print(f"Executing run {active_run['run_id']}")
        await scheduler_module.execute_run_batch(active_run['run_id'])
        print("Success")
    else:
        print("No active run found")

if __name__ == "__main__":
    asyncio.run(test_run())

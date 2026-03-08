import asyncio
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon.errors import FloodWaitError
from bot.database import automations
from bot.config import logger

scheduler = AsyncIOScheduler(timezone=datetime.timezone.utc)
bot_client = None  # Injected on startup

async def delete_message_job(chat_id: int, message_id: int):
    try:
        await bot_client.delete_messages(chat_id, message_id)
    except Exception as e:
        logger.error(f"Failed to auto-delete {message_id} in {chat_id}: {e}")

async def execute_automation(automation_id: int):
    auto = await automations.find_one({"automation_id": automation_id})
    if not auto or auto["status"] != "active":
        return

    try:
        if auto["content_type"] == "text":
            msg = await bot_client.send_message(auto["chat_id"], auto["content"])
        else:
            msg = await bot_client.send_file(
                auto["chat_id"], 
                auto["content"], # file_id
                caption=auto.get("caption", "")
            )
        
        if auto.get("auto_delete"):
            run_date = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=auto["delete_after_minutes"])
            scheduler.add_job(
                delete_message_job, 'date', run_date=run_date,
                args=[auto["chat_id"], msg.id]
            )
            
    except FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s. Pausing execution.")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error executing automation {automation_id}: {e}")

async def load_recovery_jobs():
    cursor = automations.find({"status": "active"})
    async for auto in cursor:
        schedule_job(auto)

def schedule_job(auto_data: dict):
    job_id = f"auto_{auto_data['automation_id']}"
    if scheduler.get_job(job_id):
        return

    if auto_data["type"] == "schedule":
        if auto_data.get("repeat_interval"):
            scheduler.add_job(
                execute_automation, 'interval', minutes=auto_data["repeat_interval"],
                start_date=auto_data["schedule_time"], id=job_id, args=[auto_data["automation_id"]]
            )
        else:
            if auto_data["schedule_time"] > datetime.datetime.now():
                scheduler.add_job(
                    execute_automation, 'date', run_date=auto_data["schedule_time"],
                    id=job_id, args=[auto_data["automation_id"]]
                )
    elif auto_data["type"] == "repeat":
        scheduler.add_job(
            execute_automation, 'interval', minutes=auto_data["repeat_interval"],
            id=job_id, args=[auto_data["automation_id"]]
        )

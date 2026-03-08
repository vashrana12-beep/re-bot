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
            # Ensure this is also safely timezone-aware
            run_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=auto["delete_after_minutes"])
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

    # ---- CRITICAL TIMEZONE FIX ----
    # 1. Safely extract the schedule time
    sched_time = auto_data.get("schedule_time")
    
    # 2. If it exists but has no timezone (naive), force it to be UTC
    if sched_time is not None:
        if sched_time.tzinfo is None:
            sched_time = sched_time.replace(tzinfo=datetime.timezone.utc)
            
    # 3. Create a strict, timezone-aware "now" for comparison
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # -------------------------------

    if auto_data["type"] == "schedule":
        if auto_data.get("repeat_interval"):
            scheduler.add_job(
                execute_automation, 'interval', minutes=auto_data["repeat_interval"],
                start_date=sched_time, id=job_id, args=[auto_data["automation_id"]]
            )
        else:
            # Compare aware to aware
            if sched_time > now_utc:
                scheduler.add_job(
                    execute_automation, 'date', run_date=sched_time,
                    id=job_id, args=[auto_data["automation_id"]]
                )
    elif auto_data["type"] == "repeat":
        scheduler.add_job(
            execute_automation, 'interval', minutes=auto_data["repeat_interval"],
            id=job_id, args=[auto_data["automation_id"]]
        )

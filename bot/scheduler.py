import asyncio
import datetime
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon.errors import FloodWaitError
from bot.database import automations
from bot.config import logger

SCHEDULER_TIMEZONE = datetime.timezone.utc
RECOVERY_GRACE_SECONDS = 24 * 60 * 60

scheduler = AsyncIOScheduler(
    timezone=SCHEDULER_TIMEZONE,
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        # APScheduler defaults this to 1 second, which makes jobs easy to miss.
        "misfire_grace_time": RECOVERY_GRACE_SECONDS,
    },
)
bot_client = None  # Injected on startup


def _normalize_schedule_time(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=SCHEDULER_TIMEZONE)

    return value.astimezone(SCHEDULER_TIMEZONE)


async def _mark_automation_status(automation_id: int, status: str):
    await automations.update_one(
        {"automation_id": automation_id},
        {"$set": {"status": status}},
    )


def _scheduler_listener(event):
    if event.code == EVENT_JOB_MISSED:
        logger.warning(f"Job {event.job_id} missed its run window.")
    elif event.exception:
        logger.error(f"Job {event.job_id} crashed: {event.exception}")


scheduler.add_listener(_scheduler_listener, EVENT_JOB_MISSED | EVENT_JOB_ERROR)


async def delete_message_job(chat_id: int, message_id: int):
    try:
        await bot_client.delete_messages(chat_id, message_id)
    except Exception as e:
        logger.error(f"Failed to auto-delete {message_id} in {chat_id}: {e}")


async def execute_automation(automation_id: int):
    auto = await automations.find_one({"automation_id": automation_id})
    if not auto or auto["status"] != "active":
        return

    if bot_client is None:
        logger.error(f"Bot client not ready for automation {automation_id}.")
        return

    try:
        if auto["content_type"] == "text":
            msg = await bot_client.send_message(auto["chat_id"], auto["content"])
        else:
            msg = await bot_client.send_file(
                auto["chat_id"],
                auto["content"],
                caption=auto.get("caption", "")
            )

        if auto.get("pin_message"):
            try:
                await bot_client.pin_message(auto["chat_id"], msg.id)
            except Exception as e:
                logger.error(f"Failed to pin message in {auto['chat_id']}: {e}")

        if auto.get("auto_delete"):
            run_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                minutes=auto["delete_after_minutes"]
            )
            scheduler.add_job(
                delete_message_job,
                "date",
                run_date=run_date,
                args=[auto["chat_id"], msg.id],
            )

        if auto["type"] == "schedule" and not auto.get("repeat_interval"):
            await automations.update_one(
                {"automation_id": automation_id},
                {"$set": {"status": "completed"}}
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

    sched_time = _normalize_schedule_time(auto_data.get("schedule_time"))
    repeat_interval = auto_data.get("repeat_interval") or 0
    now_utc = datetime.datetime.now(SCHEDULER_TIMEZONE)

    if repeat_interval < 0:
        logger.error(f"Skipping automation {auto_data['automation_id']}: interval cannot be negative.")
        return

    if auto_data["type"] == "schedule":
        if repeat_interval:
            if sched_time is None:
                logger.error(
                    f"Skipping automation {auto_data['automation_id']}: scheduled repeats need a start time."
                )
                return

            scheduler.add_job(
                execute_automation,
                "interval",
                minutes=repeat_interval,
                start_date=sched_time,
                id=job_id,
                args=[auto_data["automation_id"]],
            )
        else:
            if sched_time is None:
                logger.error(
                    f"Skipping automation {auto_data['automation_id']}: one-off schedules need a run date."
                )
                return

            if now_utc - sched_time > datetime.timedelta(seconds=RECOVERY_GRACE_SECONDS):
                logger.warning(
                    f"Skipping stale automation {auto_data['automation_id']}: scheduled time {sched_time} is too old."
                )
                asyncio.create_task(_mark_automation_status(auto_data["automation_id"], "missed"))
                return

            scheduler.add_job(
                execute_automation,
                "date",
                run_date=sched_time,
                id=job_id,
                args=[auto_data["automation_id"]],
            )
    elif auto_data["type"] == "repeat":
        if repeat_interval <= 0:
            logger.error(
                f"Skipping automation {auto_data['automation_id']}: repeat interval must be greater than zero."
            )
            return

        scheduler.add_job(
            execute_automation,
            "interval",
            minutes=repeat_interval,
            id=job_id,
            args=[auto_data["automation_id"]],
        )

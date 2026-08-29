import asyncio
import datetime
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelInvalidError
)
from bot.database import automations, chats, run_state, sources
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
            content_val = auto["content"]
            if isinstance(content_val, int) or (isinstance(content_val, str) and content_val.isdigit()):
                original_msg = await bot_client.get_messages(auto["created_by"], ids=int(content_val))
                if original_msg and original_msg.media:
                    media_to_send = original_msg.media
                else:
                    logger.error(f"Could not find original media message {content_val} in chat {auto['created_by']}")
                    return
            else:
                media_to_send = content_val

            msg = await bot_client.send_file(
                auto["chat_id"],
                media_to_send,
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
    except (ChannelPrivateError, ChatWriteForbiddenError, UserBannedInChannelError, ChannelInvalidError) as e:
        logger.warning(f"Chat inaccessible for automation {automation_id}, removing chat {auto['chat_id']}: {e}")
        await chats.delete_one({"chat_id": auto["chat_id"]})
        await automations.update_many(
            {"chat_id": auto["chat_id"]},
            {"$set": {"status": "error_deleted"}}
        )
    except ValueError as e:
        if "entity" in str(e).lower() or "peer" in str(e).lower():
            logger.warning(f"Entity not found for automation {automation_id}, removing chat {auto['chat_id']}: {e}")
            await chats.delete_one({"chat_id": auto["chat_id"]})
            await automations.update_many(
                {"chat_id": auto["chat_id"]},
                {"$set": {"status": "error_deleted"}}
            )
        else:
            logger.error(f"Error executing automation {automation_id}: {e}")
    except Exception as e:
        logger.error(f"Error executing automation {automation_id}: {e}")


async def load_recovery_jobs():
    cursor = automations.find({"status": "active"})
    async for auto in cursor:
        schedule_job(auto)

    run_cursor = run_state.find({"status": "active"})
    async for r in run_cursor:
        src = await sources.find_one({"source_id": r["source_id"]})
        if src:
            schedule_run_batch(r, src)


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

async def execute_run_batch(run_id: int):
    run_data = await run_state.find_one({"run_id": run_id, "status": "active"})
    if not run_data:
        return
        
    source = await sources.find_one({"source_id": run_data["source_id"]})
    if not source:
        logger.error(f"Source for run {run_id} not found.")
        return

    batch_size = source.get("batch_size", 5)
    posts_limit = source.get("posts_limit", 5)
    start_id = run_data["current_msg_id"]
    target_idx = run_data["current_target_index"]
    target_chats = run_data.get("target_chats", [])

    if target_idx >= len(target_chats):
        logger.info(f"Run {run_id} completed all target chats.")
        await run_state.update_one({"_id": run_data["_id"]}, {"$set": {"status": "completed"}})
        return

    current_targets = target_chats[target_idx : target_idx + batch_size]
    
    messages_to_forward = []
    try:
        source_entity = await bot_client.get_entity(source["source_id"])
        # Fetching a larger chunk of IDs (e.g. up to 20 extra) to account for deleted messages
        ids_to_fetch = list(range(start_id, start_id + posts_limit + 20))
        msgs = await bot_client.get_messages(source_entity, ids=ids_to_fetch)
        valid_msgs = [m for m in msgs if m and not getattr(m, 'action', False)]
        # Take only the number of posts requested
        messages_to_forward = valid_msgs[:posts_limit]
    except Exception as e:
        logger.error(f"Error fetching messages from source {source['source_id']}: {e}")
        await run_state.update_one({"_id": run_data["_id"]}, {"$set": {"status": "paused"}})
        return
    
    if not messages_to_forward:
        logger.info(f"No more messages found in source {source['source_id']} starting from {start_id}. Pausing run.")
        await run_state.update_one({"_id": run_data["_id"]}, {"$set": {"status": "paused"}})
        return
    
    for i, chat_id in enumerate(current_targets):
        msg = messages_to_forward[i % len(messages_to_forward)]
        try:
            sent_msg = None
            if msg.media:
                sent_msg = await bot_client.send_file(chat_id, msg.media, caption=msg.text)
            else:
                sent_msg = await bot_client.send_message(chat_id, msg.text)
            
            if source.get("auto_delete") and source.get("delete_after_minutes"):
                run_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=source["delete_after_minutes"])
                scheduler.add_job(
                    delete_message_job,
                    "date",
                    run_date=run_date,
                    args=[chat_id, sent_msg.id],
                )
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s while running batch {run_id}.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error sending message to {chat_id} in run {run_id}: {e}")
            
    next_start_id = messages_to_forward[-1].id + 1
    next_target_idx = target_idx + batch_size
    
    await run_state.update_one(
        {"_id": run_data["_id"]},
        {"$set": {
            "current_target_index": next_target_idx,
            "current_msg_id": next_start_id
        }}
    )

def schedule_run_batch(run_data: dict, source_data: dict):
    job_id = f"run_batch_{run_data['run_id']}"
    if scheduler.get_job(job_id):
        return
        
    interval = source_data.get("interval_minutes", 5)
    
    scheduler.add_job(
        execute_run_batch,
        "interval",
        minutes=interval,
        id=job_id,
        args=[run_data["run_id"]]
    )

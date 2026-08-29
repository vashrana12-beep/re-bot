import asyncio
import datetime
from telethon import events
from bot.database import sources, run_state, chats, get_next_sequence
from bot.scheduler import schedule_run_batch
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r"^/run start$", func=lambda e: e.is_private))
@requires_role("admin")
async def run_start_handler(event):
    async with event.client.conversation(event.chat_id, timeout=120) as conv:
        try:
            # Check if there's already an active run
            active_run = await run_state.find_one({"status": {"$in": ["active", "paused"]}})
            if active_run:
                return await conv.send_message(f"A run is already {active_run['status']}. Please stop it first using `/run stop`.")

            all_sources = []
            async for src in sources.find():
                all_sources.append(src)
            
            if not all_sources:
                return await conv.send_message("No sources configured. Use `/add_source` first.")
            
            source = all_sources[0]
            if len(all_sources) > 1:
                msg = "Select a source to start running:\n"
                for i, src in enumerate(all_sources):
                    msg += f"{i+1}. {src.get('source_title', src['source_id'])}\n"
                await conv.send_message(msg)
                
                idx_str = (await conv.get_response()).text.strip()
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(all_sources):
                        source = all_sources[idx]
                    else:
                        return await conv.send_message("Invalid selection.")
                except ValueError:
                    return await conv.send_message("Invalid selection.")
            
            all_chats = []
            async for chat in chats.find():
                chat_id = chat["chat_id"]
                if chat.get("type") == "channel":
                    all_chats.append(chat_id)
                elif chat.get("type") == "channel/group":
                    try:
                        entity = await event.client.get_entity(chat_id)
                        if getattr(entity, 'broadcast', False):
                            all_chats.append(chat_id)
                    except Exception:
                        pass
            
            if not all_chats:
                return await conv.send_message("No target chats registered in the bot.")
            
            run_id = await get_next_sequence("run_id")
            new_run = {
                "run_id": run_id,
                "source_id": source["source_id"],
                "target_chats": all_chats,
                "current_target_index": 0,
                "current_msg_id": source.get("start_id", 1),
                "status": "active",
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            
            await run_state.insert_one(new_run)
            
            schedule_run_batch(new_run, source)
            
            await conv.send_message(f"Run started for source '{source.get('source_title', source['source_id'])}'!\nBatch size: {source['batch_size']}, Interval: {source['interval_minutes']}m.\nTargeting {len(all_chats)} channels.")
            
        except asyncio.TimeoutError:
            await conv.send_message("Conversation timed out.")
        except Exception as e:
            await conv.send_message(f"Error starting run: {str(e)}")


@events.register(events.NewMessage(pattern=r"^/run stop$", func=lambda e: e.is_private))
@requires_role("admin")
async def run_stop_handler(event):
    active_run = await run_state.find_one({"status": {"$in": ["active", "paused"]}})
    if not active_run:
        return await event.respond("No active or paused runs to stop.")
    
    await run_state.update_one({"_id": active_run["_id"]}, {"$set": {"status": "completed"}})
    
    from bot.scheduler import scheduler
    job_id = f"run_batch_{active_run['run_id']}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        
    await event.respond("Run stopped.")


@events.register(events.NewMessage(pattern=r"^/run pause$", func=lambda e: e.is_private))
@requires_role("admin")
async def run_pause_handler(event):
    active_run = await run_state.find_one({"status": "active"})
    if not active_run:
        return await event.respond("No active runs to pause.")
    
    await run_state.update_one({"_id": active_run["_id"]}, {"$set": {"status": "paused"}})
    
    from bot.scheduler import scheduler
    job_id = f"run_batch_{active_run['run_id']}"
    if scheduler.get_job(job_id):
        scheduler.pause_job(job_id)
        
    await event.respond("Run paused.")


@events.register(events.NewMessage(pattern=r"^/run resume$", func=lambda e: e.is_private))
@requires_role("admin")
async def run_resume_handler(event):
    paused_run = await run_state.find_one({"status": "paused"})
    if not paused_run:
        return await event.respond("No paused runs to resume.")
    
    await run_state.update_one({"_id": paused_run["_id"]}, {"$set": {"status": "active"}})
    
    from bot.scheduler import scheduler
    job_id = f"run_batch_{paused_run['run_id']}"
    if scheduler.get_job(job_id):
        scheduler.resume_job(job_id)
    else:
        # If the bot restarted, the job might not exist in scheduler
        source = await sources.find_one({"source_id": paused_run["source_id"]})
        if source:
            schedule_run_batch(paused_run, source)
        
    await event.respond("Run resumed.")

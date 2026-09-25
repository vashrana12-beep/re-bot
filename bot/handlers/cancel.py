from telethon import events
from bot.database import automations, run_state, sources
from bot.scheduler import scheduler, schedule_job, schedule_run_batch
from bot.access_control import requires_role

# 1. PAUSE ALL (Owner) - Pauses all active automations (can be resumed)
@events.register(events.NewMessage(pattern=r'(?i)^/(?:pause_?all|pause\s+all)$'))
@requires_role("owner")
async def pause_all_handler(event):
    res = await automations.update_many({"status": "active"}, {"$set": {"status": "paused"}})
    for job in scheduler.get_jobs():
        if job.id.startswith("auto_"):
            job.pause()
    await run_state.update_many({"status": "active"}, {"$set": {"status": "paused"}})
    for job in scheduler.get_jobs():
        if job.id.startswith("run_batch_"):
            job.pause()
    await event.respond(
        f"⏸️ **All System Automations PAUSED.**\n\n"
        f"• `{res.modified_count}` active automation(s) paused.\n"
        f"• Use `/resume all` to resume them."
    )

# 2. RESUME ALL (Owner) - Resumes all paused automations back to active
@events.register(events.NewMessage(pattern=r'(?i)^/(?:resume_?all|resume\s+all)$'))
@requires_role("owner")
async def resume_all_handler(event):
    paused_cursor = automations.find({"status": "paused"})
    resumed_count = 0
    async for auto in paused_cursor:
        resumed_count += 1
        await automations.update_one({"_id": auto["_id"]}, {"$set": {"status": "active"}})
        job_id = f"auto_{auto['automation_id']}"
        job = scheduler.get_job(job_id)
        if job:
            job.resume()
        else:
            auto["status"] = "active"
            schedule_job(auto)

    run_cursor = run_state.find({"status": "paused"})
    async for r in run_cursor:
        await run_state.update_one({"_id": r["_id"]}, {"$set": {"status": "active"}})
        job_id = f"run_batch_{r['run_id']}"
        job = scheduler.get_job(job_id)
        if job:
            job.resume()
        else:
            src = await sources.find_one({"source_id": r["source_id"]})
            if src:
                schedule_run_batch(r, src)

    if resumed_count == 0:
        await event.respond("ℹ️ No paused automations found to resume.")
    else:
        await event.respond(f"▶️ **All System Automations RESUMED.**\n\n• `{resumed_count}` automation(s) resumed and running.")

# 3. STOP ALL (Owner) - Permanently stops and cancels all automations
@events.register(events.NewMessage(pattern=r'(?i)^/(?:stop_?all|stop\s+all)$'))
@requires_role("owner")
async def stop_all_handler(event):
    res = await automations.update_many(
        {"status": {"$in": ["active", "paused"]}},
        {"$set": {"status": "cancelled"}}
    )
    for job in list(scheduler.get_jobs()):
        if job.id.startswith("auto_"):
            scheduler.remove_job(job.id)
        elif job.id.startswith("run_batch_"):
            scheduler.remove_job(job.id)

    await run_state.update_many(
        {"status": {"$in": ["active", "paused"]}},
        {"$set": {"status": "completed"}}
    )
    await event.respond(
        f"🛑 **All System Automations STOPPED & CANCELLED.**\n\n"
        f"• `{res.modified_count}` automation(s) cancelled.\n"
        f"• All repeating and scheduled jobs have been removed."
    )

# 4. SINGLE PAUSE (/pause <id> or /pause)
@events.register(events.NewMessage(pattern=r'(?i)^/pause(?:\s+(\d+))?$'))
@requires_role("admin")
async def pause_handler(event):
    match = event.pattern_match.group(1)
    if not match:
        return await event.respond(
            "ℹ️ **Usage for Pause:**\n"
            "• `/pause <id>` - Pause a specific automation ID\n"
            "• `/pause all` - Pause all system automations"
        )
    auto_id = int(match)
    auto = await automations.find_one({"automation_id": auto_id})
    if not auto:
        return await event.respond(f"❌ Automation ID `{auto_id}` not found.")
    if auto.get("status") == "paused":
        return await event.respond(f"⚠️ Automation ID `{auto_id}` is already paused.")
    if auto.get("status") == "cancelled":
        return await event.respond(f"❌ Automation ID `{auto_id}` is cancelled and cannot be paused.")

    await automations.update_one({"automation_id": auto_id}, {"$set": {"status": "paused"}})
    job_id = f"auto_{auto_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.pause()
    await event.respond(f"⏸️ **Paused Automation ID:** `{auto_id}`\nUse `/resume {auto_id}` to resume.")

# 5. SINGLE RESUME (/resume <id> or /resume)
@events.register(events.NewMessage(pattern=r'(?i)^/resume(?:\s+(\d+))?$'))
@requires_role("admin")
async def resume_handler(event):
    match = event.pattern_match.group(1)
    if not match:
        return await event.respond(
            "ℹ️ **Usage for Resume:**\n"
            "• `/resume <id>` - Resume a specific automation ID\n"
            "• `/resume all` - Resume all paused automations"
        )
    auto_id = int(match)
    auto = await automations.find_one({"automation_id": auto_id})
    if not auto:
        return await event.respond(f"❌ Automation ID `{auto_id}` not found.")
    if auto.get("status") == "active":
        return await event.respond(f"⚠️ Automation ID `{auto_id}` is already active.")
    if auto.get("status") == "cancelled":
        return await event.respond(f"❌ Automation ID `{auto_id}` is cancelled and cannot be resumed.")

    await automations.update_one({"automation_id": auto_id}, {"$set": {"status": "active"}})
    job_id = f"auto_{auto_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.resume()
    else:
        auto["status"] = "active"
        schedule_job(auto)
    await event.respond(f"▶️ **Resumed Automation ID:** `{auto_id}`")

# 6. SINGLE CANCEL/STOP (/cancel <id> or /stop <id> or /cancel or /stop)
@events.register(events.NewMessage(pattern=r'(?i)^/(?:cancel|stop)(?:\s+(\d+))?$'))
@requires_role("admin")
async def cancel_handler(event):
    match = event.pattern_match.group(1)
    if not match:
        return await event.respond(
            "ℹ️ **Usage for Stop / Cancel:**\n"
            "• `/stop <id>` or `/cancel <id>` - Cancel a specific automation ID\n"
            "• `/stop all` - Stop and cancel all system automations"
        )
    auto_id = int(match)
    res = await automations.update_one({"automation_id": auto_id}, {"$set": {"status": "cancelled"}})
    if res.matched_count == 0:
        return await event.respond(f"❌ Automation ID `{auto_id}` not found.")
    job_id = f"auto_{auto_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    await event.respond(f"🛑 **Cancelled Automation ID:** `{auto_id}`")

# Backwards compatibility aliases
cancel_one_handler = cancel_handler
stopall_handler = stop_all_handler
from telethon import events
from bot.database import automations
from bot.scheduler import scheduler
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/cancel (\d+)$'))
@requires_role("admin")
async def cancel_one_handler(event):
    auto_id = int(event.pattern_match.group(1))
    await automations.update_one({"automation_id": auto_id}, {"$set": {"status": "cancelled"}})
    job_id = f"auto_{auto_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    await event.respond(f"✅ Cancelled ID: {auto_id}")

@events.register(events.NewMessage(pattern=r'^/stopall$|^/pause_?all$|^/pause\s+all$'))
@requires_role("owner")
async def stopall_handler(event):
    await automations.update_many({"status": "active"}, {"$set": {"status": "paused"}})
    for job in scheduler.get_jobs():
        if job.id.startswith("auto_"):
            job.pause()
    await event.respond("🛑 All system automations PAUSED.")

@events.register(events.NewMessage(pattern=r'^/resume_?all$|^/resume\s+all$'))
@requires_role("owner")
async def resumeall_handler(event):
    await automations.update_many({"status": "paused"}, {"$set": {"status": "active"}})
    for job in scheduler.get_jobs():
        if job.id.startswith("auto_"):
            job.resume()
    await event.respond("▶️ All system automations RESUMED.")
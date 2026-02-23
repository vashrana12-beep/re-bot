import datetime
from telethon import events
from bot.database import chats, automations
from bot.scheduler import scheduler
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/detect$'))
@requires_role("admin")
async def detect_handler(event):
    if event.is_private:
        return await event.respond("Use this in a group or channel.")
    
    chat_id = event.chat_id
    existing = await chats.find_one({"chat_id": chat_id})
    if existing:
        return await event.respond("Chat is already registered.")
    
    await chats.insert_one({
        "chat_id": chat_id,
        "title": event.chat.title,
        "type": "group" if event.is_group else "channel",
        "added_by": event.sender_id,
        "allowed_users": [event.sender_id],
        "added_at": datetime.datetime.now(datetime.UTC)
    })
    await event.respond(f"✅ Registered chat: {event.chat.title} ({chat_id})")

@events.register(events.NewMessage(pattern=r'^/deletechat(?: \d+)?$'))
@requires_role("owner")
async def deletechat_handler(event):
    parts = event.text.split()
    if len(parts) != 2:
        return await event.respond("Usage: /deletechat <chat_id>")
    
    chat_id = int(parts[1])
    await chats.delete_one({"chat_id": chat_id})
    
    # Cancel related automations
    cursor = automations.find({"chat_id": chat_id, "status": "active"})
    async for auto in cursor:
        job_id = f"auto_{auto['automation_id']}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            
    await automations.update_many({"chat_id": chat_id}, {"$set": {"status": "cancelled"}})
    await event.respond(f"🗑 Chat {chat_id} and all its automations removed.")
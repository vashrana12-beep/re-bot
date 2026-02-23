import datetime, json, os
from telethon import events
from bot.database import users, chats, automations
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/adduser (\d+) (owner|admin|viewer)$'))
@requires_role("owner")
async def adduser_handler(event):
    user_id = int(event.pattern_match.group(1))
    role = event.pattern_match.group(2)
    
    await users.update_one(
        {"user_id": user_id},
        {"$set": {"role": role, "added_by": event.sender_id, "added_at": datetime.datetime.now(datetime.UTC)}},
        upsert=True
    )
    await event.respond(f"✅ User {user_id} added as {role.upper()}.")

@events.register(events.NewMessage(pattern=r'^/backup$'))
@requires_role("owner")
async def backup_handler(event):
    backup_data = {
        "users": await users.find({}, {"_id": 0}).to_list(None),
        "chats": await chats.find({}, {"_id": 0}).to_list(None)
    }
    with open("backup.json", "w") as f:
        json.dump(backup_data, f, default=str)
    
    await event.client.send_file(event.chat_id, "backup.json", caption="📦 System Backup")
    os.remove("backup.json")
from telethon import events
from bot.database import automations
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/(listall|listschedules|listrepeats)$'))
@requires_role("viewer")
async def list_handler(event):
    cmd = event.pattern_match.group(1)
    query = {} if cmd == "listall" else {"type": "schedule" if cmd == "listschedules" else "repeat"}
    
    cursor = automations.find(query)
    text = f"**{cmd.upper()}**\n\n"
    count = 0
    async for auto in cursor:
        count += 1
        text += f"ID: `{auto['automation_id']}` | Type: {auto['type']} | Status: {auto['status']}\n"
        text += f"Chat: {auto['chat_id']} | Interval: {auto['repeat_interval']}m\n---\n"
        
    if count == 0:
        text = "No automations found."
    await event.respond(text)
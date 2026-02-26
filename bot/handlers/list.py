from telethon import events
from bot.database import automations
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/(listall|listschedules|listrepeats)$'))
@requires_role("viewer")
async def list_handler(event):
    cmd = event.pattern_match.group(1)
    
    # 1. Filter out cancelled tasks - only show ACTIVE
    query = {"status": "active"} 
    if cmd == "listschedules":
        query["type"] = "schedule"
    elif cmd == "listrepeats":
        query["type"] = "repeat"
    
    cursor = automations.find(query)
    text = f"**{cmd.upper()} (Active)**\n\n"
    count = 0
    
    async for auto in cursor:
        count += 1
        
        # 2. Format the content to show links/text or media names
        c_type = auto.get('content_type', 'text')
        raw_content = auto.get('content', '')
        
        if c_type == 'text':
            # Remove newlines to keep it neat, and limit to 60 characters
            preview = raw_content.replace("\n", " ")
            preview = preview[:60] + "..." if len(preview) > 60 else preview
            content_display = f"🔗 Link/Text: {preview}"
        else:
            # Just show the media type (e.g., Video, Photo, Gif)
            content_display = f"📁 Media: {c_type.capitalize()}"

        text += f"**ID:** `{auto['automation_id']}` | **Type:** {auto['type'].capitalize()}\n"
        text += f"**Chat:** `{auto['chat_id']}` | **Interval:** {auto['repeat_interval']}m\n"
        text += f"{content_display}\n---\n"
        
    if count == 0:
        text = "No active automations found."
        
    # 3. Safety Check: If the list is too long, send in multiple messages
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await event.respond(text[i:i+4000])
    else:
        await event.respond(text)

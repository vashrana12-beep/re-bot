from telethon import events
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/start$', func=lambda e: e.is_private))
@requires_role("viewer")
async def start_handler(event):
    await event.respond(
        "I am Automation Manager Bot.\n\n"
        "Add me to your group or channel as admin.\n"
        "Use /detect inside that chat to register it."
    )
from telethon import events
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/start$', func=lambda e: e.is_private))
@requires_role("viewer")
async def start_handler(event):
    await event.respond(
        "👋 **I am your Automation Manager Bot.**\n\n"
        "Add me to your group or channel as admin.\n"
        "Use `/detect` inside groups, or `/detect <chat_id>` here to register them.\n\n"
        "Send /help to see all my commands!"
    )

@events.register(events.NewMessage(pattern=r'^/help$', func=lambda e: e.is_private))
@requires_role("viewer")
async def help_handler(event):
    help_text = (
        "🤖 **AUTOMATION BOT COMMANDS**\n\n"
        "**Admin Commands:**\n"
        "🔹 `/detect` - Register current group\n"
        "🔹 `/detect <chat_id>` - Register a chat manually\n"
        "🔹 `/add_source` - Add a source channel for run\n"
        "🔹 `/remove_source` - Remove a source channel\n"
        "🔹 `/list_source` - List configured sources\n"
        "🔹 `/run start|stop|pause|resume` - Manage forwarding run\n"
        "🔹 `/schedule` - Schedule a post for a single chat\n"
        "🔹 `/repeat` - Create a quick repeating post for a single chat\n"
        "🚀 `/bulkschedule` - Schedule a post across multiple chats at once\n"
        "🚀 `/bulkrepeat` - Set a repeating post across multiple chats at once\n"
        "🔹 `/cancel <id>` - Cancel a specific automation\n"
        "🔹 `/delete <link> <end_id>` - Delete specific messages or ranges\n"
        "🔹 `/pause <id>` - Pause an automation\n"
        "🔹 `/resume <id>` - Resume an automation\n\n"
        "**Viewer Commands:**\n"
        "🔹 `/listall` - View all active automations\n"
        "🔹 `/listschedules` - View active schedules\n"
        "🔹 `/listrepeats` - View active repeats\n\n"
        "**Owner Commands:**\n"
        "👑 `/adduser <id> <role>` - Add a user (admin/viewer)\n"
        "👑 `/removeuser <id>` - Remove a user\n"
        "👑 `/deletechat <chat_id>` - Remove chat & automations\n"
        "👑 `/pause all` - Pause all active automations (can be resumed)\n"
        "👑 `/resume all` - Resume all paused automations\n"
        "👑 `/stop all` (or `/stopall`) - Permanently stop & cancel all automations\n"
        "👑 `/backup` - Export DB backup\n"
        "👑 `/admin <id>` - Promote user to admin in selected chats\n"
        "👑 `/deadmin <id>` - Remove user's admin rights\n"
    )
    await event.respond(help_text)

import datetime
import asyncio
from telethon import events
from bot.database import automations, get_next_sequence, chats
from bot.scheduler import schedule_job
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/repeat$', func=lambda e: e.is_private))
@requires_role("admin")
async def repeat_handler(event):
    async with event.client.conversation(event.chat_id, timeout=60) as conv:
        try:
            await conv.send_message("Send the Target Chat ID:")
            chat_id = int((await conv.get_response()).text)
            
            if not await chats.find_one({"chat_id": chat_id}):
                return await conv.send_message("❌ Chat not registered.")

            await conv.send_message("Send the content (Text or Media):")
            msg = await conv.get_response()
            
            content_type, content, caption = "text", msg.text, ""
            if msg.media:
                content = msg.file.id
                caption = msg.text
                content_type = "document"
                
            await conv.send_message("Interval in minutes:")
            interval = int((await conv.get_response()).text)

            await conv.send_message("Auto Delete? (ON/OFF):")
            ad_msg = (await conv.get_response()).text.lower()
            auto_delete, delete_after = False, 0
            if ad_msg == "on":
                auto_delete = True
                await conv.send_message("Delete after minutes:")
                delete_after = int((await conv.get_response()).text)

            auto_id = await get_next_sequence("automation_id")
            auto_data = {
                "automation_id": auto_id, "chat_id": chat_id, "created_by": event.sender_id,
                "type": "repeat", "content_type": content_type, "content": content, "caption": caption,
                "schedule_time": None, "repeat_interval": interval, "auto_delete": auto_delete,
                "delete_after_minutes": delete_after, "status": "active",
                "created_at": datetime.datetime.now(datetime.UTC)
            }
            await automations.insert_one(auto_data)
            schedule_job(auto_data)
            
            await conv.send_message(f"✅ Repeat Created!\nAutomation ID: `{auto_id}`")
        except asyncio.TimeoutError:
            await conv.send_message("⏳ Conversation timed out.")
        except Exception as e:
            await conv.send_message(f"❌ Error: {str(e)}")

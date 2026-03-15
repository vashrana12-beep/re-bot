import asyncio
import datetime
from telethon import events
from bot.database import automations, get_next_sequence, chats
from bot.scheduler import schedule_job
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/(schedule|repeat)$', func=lambda e: e.is_private))
@requires_role("admin")
async def schedule_handler(event):
    cmd_type = event.pattern_match.group(1) # 'schedule' or 'repeat'
    
    async with event.client.conversation(event.chat_id, timeout=120) as conv:
        try:
            # 1. Target Chat
            await conv.send_message("Send the Target Chat ID:")
            chat_id_msg = await conv.get_response()
            chat_id = int(chat_id_msg.text)
            
            if not await chats.find_one({"chat_id": chat_id}):
                return await conv.send_message("❌ Chat not registered. Use /detect first.")

            # 2. Content
            await conv.send_message("Send the content (Text, Link, or Media):")
            content_msg = await conv.get_response()
            
            content_type, content, caption = "text", content_msg.text, ""
            if content_msg.media and hasattr(content_msg, 'file') and content_msg.file:
                content = content_msg.file.id
                caption = content_msg.text or ""
                if content_msg.photo: content_type = "photo"
                elif content_msg.video: content_type = "video"
                elif content_msg.gif: content_type = "gif"
                else: content_type = "document"
                
            # 3. Time / Interval Setup
            schedule_time = None
            interval = 0
            
            if cmd_type == "schedule":
                await conv.send_message("Send datetime in UTC (YYYY-MM-DD HH:MM):")
                time_msg = await conv.get_response()
                schedule_time = datetime.datetime.strptime(time_msg.text, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
                
                await conv.send_message("Repeat? (ON/OFF):")
                repeat_msg = (await conv.get_response()).text.lower()
                if repeat_msg == "on":
                    await conv.send_message("Interval in minutes:")
                    interval = int((await conv.get_response()).text)
            else:
                # Logic just for /repeat
                await conv.send_message("Interval in minutes:")
                interval = int((await conv.get_response()).text)

            # 4. Auto Delete
            await conv.send_message("Auto Delete? (ON/OFF):")
            ad_msg = (await conv.get_response()).text.lower()
            auto_delete, delete_after = False, 0
            if ad_msg == "on":
                auto_delete = True
                await conv.send_message("Delete after minutes:")
                delete_after = int((await conv.get_response()).text)

            # 5. NEW: Pin Feature
            await conv.send_message("Pin this message? (ON/OFF):")
            pin_msg = (await conv.get_response()).text.lower()
            pin_message = True if pin_msg == "on" else False

            # 6. Save to DB
            auto_id = await get_next_sequence("automation_id")
            auto_data = {
                "automation_id": auto_id, 
                "chat_id": chat_id, 
                "created_by": event.sender_id,
                "type": cmd_type, 
                "content_type": content_type, 
                "content": content, 
                "caption": caption,
                "schedule_time": schedule_time, 
                "repeat_interval": interval, 
                "auto_delete": auto_delete,
                "delete_after_minutes": delete_after, 
                "pin_message": pin_message, 
                "status": "active",
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            await automations.insert_one(auto_data)
            schedule_job(auto_data)
            
            await conv.send_message(f"✅ {cmd_type.capitalize()} Created!\nAutomation ID: `{auto_id}`")
            
        except asyncio.TimeoutError:
            await conv.send_message("⏳ Conversation timed out.")
        except ValueError:
            await conv.send_message(f"❌ Invalid Input. Check your dates and numbers.")
        except Exception as e:
            await conv.send_message(f"❌ Error: {str(e)}")

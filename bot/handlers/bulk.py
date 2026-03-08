import datetime
import asyncio
from telethon import events, Button
from bot.database import automations, get_next_sequence, chats
from bot.scheduler import schedule_job
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/(bulkschedule|bulkrepeat)$', func=lambda e: e.is_private))
@requires_role("admin")
async def bulk_handler(event):
    cmd_type = event.pattern_match.group(1) # 'bulkschedule' or 'bulkrepeat'
    
    # 1. Fetch all registered chats from the database
    all_chats = {}
    async for c in chats.find():
        all_chats[c["chat_id"]] = c["title"]
        
    if not all_chats:
        return await event.respond("❌ No chats registered. Use /detect first.")

    async with event.client.conversation(event.chat_id, timeout=120) as conv:
        try:
            # 2. Interactive Toggle Keyboard
            selected_chats = set()
            
            def build_kb():
                buttons = []
                for cid, title in all_chats.items():
                    # Truncate long titles to keep keyboard neat
                    display_title = title[:20] + "..." if len(title) > 20 else title
                    icon = "🟢" if cid in selected_chats else "🔴"
                    buttons.append([Button.inline(f"{icon} {display_title}", data=f"tgl_{cid}")])
                buttons.append([Button.inline("✅ Confirm Selection", data="confirm_bulk")])
                return buttons
            
            msg = await conv.send_message(
                f"**Bulk {cmd_type.replace('bulk', '').capitalize()} Setup**\nSelect target chats:", 
                buttons=build_kb()
            )
            
            # 3. Wait for button clicks until confirmed
            while True:
                response = await conv.wait_event(events.CallbackQuery(sender_id=event.sender_id))
                data = response.data.decode('utf-8')
                
                if data == "confirm_bulk":
                    if not selected_chats:
                        await response.answer("Select at least one chat!", alert=True)
                        continue
                    await response.edit(f"✅ Selected {len(selected_chats)} chats.", buttons=None)
                    break
                elif data.startswith("tgl_"):
                    cid = int(data.split("_")[1])
                    if cid in selected_chats:
                        selected_chats.remove(cid)
                    else:
                        selected_chats.add(cid)
                    await response.edit(buttons=build_kb())

            # 4. Collect Content
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

            # 5. Collect Schedule Time (Only for bulkschedule)
            schedule_time = None
            if cmd_type == "bulkschedule":
                await conv.send_message("Send datetime in UTC (YYYY-MM-DD HH:MM):")
                time_msg = await conv.get_response()
                schedule_time = datetime.datetime.strptime(time_msg.text, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.UTC)
                
                await conv.send_message("Repeat? (ON/OFF):")
                repeat_msg = (await conv.get_response()).text.lower()
                interval = 0
                if repeat_msg == "on":
                    await conv.send_message("Interval in minutes:")
                    interval = int((await conv.get_response()).text)
            else:
                # bulkrepeat logic
                await conv.send_message("Interval in minutes:")
                interval = int((await conv.get_response()).text)

            # 6. Auto Delete
            await conv.send_message("Auto Delete? (ON/OFF):")
            ad_msg = (await conv.get_response()).text.lower()
            auto_delete, delete_after = False, 0
            if ad_msg == "on":
                auto_delete = True
                await conv.send_message("Delete after minutes:")
                delete_after = int((await conv.get_response()).text)

            # 7. Apply to all selected chats
            status_msg = await conv.send_message(f"⏳ Generating automations for {len(selected_chats)} chats...")
            created_ids = []
            
            for chat_id in selected_chats:
                auto_id = await get_next_sequence("automation_id")
                auto_data = {
                    "automation_id": auto_id,
                    "chat_id": chat_id,
                    "created_by": event.sender_id,
                    "type": cmd_type.replace("bulk", ""),
                    "content_type": content_type,
                    "content": content,
                    "caption": caption,
                    "schedule_time": schedule_time,
                    "repeat_interval": interval,
                    "auto_delete": auto_delete,
                    "delete_after_minutes": delete_after,
                    "status": "active",
                    "created_at": datetime.datetime.now(datetime.UTC)
                }
                await automations.insert_one(auto_data)
                schedule_job(auto_data)
                created_ids.append(str(auto_id))
            
            id_list = ", ".join(created_ids)
            await status_msg.edit(f"✅ **Bulk Setup Complete!**\nApplied to {len(selected_chats)} chats.\nAutomation IDs: `{id_list}`")
            
        except asyncio.TimeoutError:
            await conv.send_message("⏳ Conversation timed out.")
        except ValueError as ve:
            await conv.send_message(f"❌ Invalid Input: Please check your dates or numbers.")
        except Exception as e:
            await conv.send_message(f"❌ System Error: {str(e)}")

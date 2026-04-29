import asyncio
import datetime
from telethon import events
from bot.database import automations, get_next_sequence, chats
from bot.scheduler import schedule_job
from bot.access_control import requires_role


def _parse_positive_int(raw_value: str, label: str) -> int:
    value = int(raw_value.strip())
    if value <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return value


@events.register(events.NewMessage(pattern=r"^/repeat$", func=lambda e: e.is_private))
@requires_role("admin")
async def repeat_handler(event):
    async with event.client.conversation(event.chat_id, timeout=60) as conv:
        try:
            all_chats_list = []
            async for chat in chats.find():
                all_chats_list.append((chat["chat_id"], chat["title"]))

            if not all_chats_list:
                return await event.respond("No chats registered. Use /detect first.")

            page = 0
            def build_kb():
                from bot.utils.keyboard import build_chat_keyboard
                return build_chat_keyboard(all_chats_list, set(), page, is_multi=False)

            await conv.send_message("Select Target Chat:", buttons=build_kb())
            chat_id = None

            while True:
                response = await conv.wait_event(
                    events.CallbackQuery(func=lambda e: e.sender_id == event.sender_id)
                )
                data = response.data.decode("utf-8")

                if data == "ignore":
                    await response.answer()
                    continue

                if data.startswith("page_"):
                    page = int(data.split("_")[1])
                    await response.edit(buttons=build_kb())

                elif data.startswith("sel_"):
                    chat_id = int(data.split("_", 1)[1])
                    await response.edit(f"Selected Chat ID: `{chat_id}`", buttons=None)
                    break

            await conv.send_message("Send the content (Text, Link, or Media):")
            msg = await conv.get_response()

            content_type, content, caption = "text", msg.text, ""
            if msg.media and hasattr(msg, "file") and msg.file:
                content = msg.file.id
                caption = msg.text or ""
                if msg.photo:
                    content_type = "photo"
                elif msg.video:
                    content_type = "video"
                elif msg.gif:
                    content_type = "gif"
                else:
                    content_type = "document"

            await conv.send_message("Interval in minutes:")
            interval = _parse_positive_int((await conv.get_response()).text, "Interval")

            await conv.send_message("Auto Delete? (ON/OFF):")
            ad_msg = (await conv.get_response()).text.strip().lower()
            auto_delete, delete_after = False, 0
            if ad_msg == "on":
                auto_delete = True
                await conv.send_message("Delete after minutes:")
                delete_after = _parse_positive_int((await conv.get_response()).text, "Delete-after time")

            auto_id = await get_next_sequence("automation_id")
            auto_data = {
                "automation_id": auto_id,
                "chat_id": chat_id,
                "created_by": event.sender_id,
                "type": "repeat",
                "content_type": content_type,
                "content": content,
                "caption": caption,
                "schedule_time": None,
                "repeat_interval": interval,
                "auto_delete": auto_delete,
                "delete_after_minutes": delete_after,
                "status": "active",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
            await automations.insert_one(auto_data)
            schedule_job(auto_data)

            await conv.send_message(f"Repeat Created!\nAutomation ID: `{auto_id}`")
        except asyncio.TimeoutError:
            await conv.send_message("Conversation timed out.")
        except ValueError as e:
            error_message = str(e) or "Invalid input. Check your numbers."
            await conv.send_message(error_message)
        except Exception as e:
            await conv.send_message(f"Error: {str(e)}")

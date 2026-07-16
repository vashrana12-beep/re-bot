import asyncio
import datetime
from zoneinfo import ZoneInfo
from telethon import events
from bot.database import automations, get_next_sequence, chats
from bot.scheduler import schedule_job
from bot.access_control import requires_role

LOCAL_TZ = ZoneInfo("Asia/Kolkata")


def _parse_positive_int(raw_value: str, label: str) -> int:
    value = int(raw_value.strip())
    if value <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return value


@events.register(events.NewMessage(pattern=r"^/schedule$", func=lambda e: e.is_private))
@requires_role("admin")
async def schedule_handler(event):
    async with event.client.conversation(event.chat_id, timeout=120) as conv:
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
            content_msg = await conv.get_response()

            content_type, content, caption = "text", content_msg.text, ""
            if content_msg.media and hasattr(content_msg, "file") and content_msg.file:
                content = content_msg.id
                caption = content_msg.text or ""
                if content_msg.photo:
                    content_type = "photo"
                elif content_msg.video:
                    content_type = "video"
                elif content_msg.gif:
                    content_type = "gif"
                else:
                    content_type = "document"

            schedule_time = None
            interval = 0

            await conv.send_message("Send datetime in YOUR LOCAL TIME (YYYY-MM-DD HH:MM):")
            time_msg = await conv.get_response()

            local_dt = datetime.datetime.strptime(time_msg.text.strip(), "%Y-%m-%d %H:%M")
            aware_local_dt = local_dt.replace(tzinfo=LOCAL_TZ)
            schedule_time = aware_local_dt.astimezone(datetime.timezone.utc)

            if schedule_time <= datetime.datetime.now(datetime.timezone.utc):
                return await conv.send_message(
                    "Time Error!\n"
                    "The time you entered has already passed.\n"
                    "Please enter a valid future time."
                )

            await conv.send_message("Repeat? (Yes/No):")
            repeat_msg = (await conv.get_response()).text.strip().lower()
            if repeat_msg == "yes":
                await conv.send_message("Interval in minutes:")
                interval = _parse_positive_int((await conv.get_response()).text, "Interval")

            await conv.send_message("Deleted? (Yes/No):")
            ad_msg = (await conv.get_response()).text.strip().lower()
            auto_delete, delete_after = False, 0
            if ad_msg == "yes":
                auto_delete = True
                await conv.send_message("Delete after minutes:")
                delete_after = _parse_positive_int((await conv.get_response()).text, "Delete-after time")

            await conv.send_message("Pin? (Yes/No):")
            pin_msg = (await conv.get_response()).text.strip().lower()
            pin_message = pin_msg == "yes"

            auto_id = await get_next_sequence("automation_id")
            auto_data = {
                "automation_id": auto_id,
                "chat_id": chat_id,
                "created_by": event.sender_id,
                "type": "schedule",
                "content_type": content_type,
                "content": content,
                "caption": caption,
                "schedule_time": schedule_time,
                "repeat_interval": interval,
                "auto_delete": auto_delete,
                "delete_after_minutes": delete_after,
                "pin_message": pin_message,
                "status": "active",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
            await automations.insert_one(auto_data)
            schedule_job(auto_data)

            await conv.send_message(f"Schedule Created!\nAutomation ID: `{auto_id}`")

        except asyncio.TimeoutError:
            await conv.send_message("Conversation timed out.")
        except ValueError as e:
            error_message = str(e) or "Invalid input. Check your dates and numbers."
            await conv.send_message(error_message)
        except Exception as e:
            await conv.send_message(f"Error: {str(e)}")

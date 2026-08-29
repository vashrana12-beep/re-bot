import asyncio
from telethon import events
from bot.database import sources
from bot.access_control import requires_role

def _parse_positive_int(raw_value: str, label: str) -> int:
    value = int(raw_value.strip())
    if value <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return value

@events.register(events.NewMessage(pattern=r"^/add_source(?:\s*(.*))?$", func=lambda e: e.is_private))
@requires_role("admin")
async def add_source_handler(event):
    async with event.client.conversation(event.chat_id, timeout=120) as conv:
        try:
            source_input = event.pattern_match.group(1)
            if source_input and source_input.strip():
                source_text = source_input.strip()
            else:
                await conv.send_message("Enter the Source Channel ID or Username:")
                source_text = (await conv.get_response()).text.strip()
            
            try:
                try:
                    entity_id = int(source_text)
                except ValueError:
                    entity_id = source_text
                source_entity = await event.client.get_entity(entity_id)
                source_id = source_entity.id
                source_title = getattr(source_entity, 'title', str(source_id))
            except Exception as e:
                return await conv.send_message(f"Could not find that channel. Ensure the bot is a member or it's public. Error: {e}")

            await conv.send_message("Auto-delete forwarded posts? (Yes/No):")
            ad_msg = (await conv.get_response()).text.strip().lower()
            auto_delete, delete_after = False, 0
            if ad_msg == "yes":
                auto_delete = True
                await conv.send_message("Delete after how many minutes?:")
                delete_after = _parse_positive_int((await conv.get_response()).text, "Delete-after time")

            await conv.send_message("How many target channels should receive posts at a time (batch size)?:")
            batch_size = _parse_positive_int((await conv.get_response()).text, "Batch size")

            await conv.send_message("Time interval between batches (minutes)?:")
            interval = _parse_positive_int((await conv.get_response()).text, "Interval")

            await conv.send_message("How many posts to fetch from source per batch?:")
            posts_limit = _parse_positive_int((await conv.get_response()).text, "Posts limit")

            await conv.send_message("Starting message ID? (Enter a number, default is 1):")
            start_id_str = (await conv.get_response()).text.strip()
            if not start_id_str:
                start_id = 1
            else:
                start_id = _parse_positive_int(start_id_str, "Start ID")

            source_data = {
                "source_id": source_id,
                "source_title": source_title,
                "auto_delete": auto_delete,
                "delete_after_minutes": delete_after,
                "batch_size": batch_size,
                "interval_minutes": interval,
                "posts_limit": posts_limit,
                "start_id": start_id,
                "added_by": event.sender_id
            }

            await sources.update_one(
                {"source_id": source_id},
                {"$set": source_data},
                upsert=True
            )
            await conv.send_message(f"Source channel '{source_title}' added/updated successfully!")

        except asyncio.TimeoutError:
            await conv.send_message("Conversation timed out.")
        except ValueError as e:
            await conv.send_message(str(e))
        except Exception as e:
            await conv.send_message(f"Error: {str(e)}")


@events.register(events.NewMessage(pattern=r"^/remove_source(?:\s*(.*))?$", func=lambda e: e.is_private))
@requires_role("admin")
async def remove_source_handler(event):
    async with event.client.conversation(event.chat_id, timeout=120) as conv:
        try:
            target_id = event.pattern_match.group(1)
            if target_id and target_id.strip():
                target_id = target_id.strip()
                try:
                    target_id_val = int(target_id)
                except ValueError:
                    target_id_val = target_id
                
                res = await sources.delete_one({"source_id": target_id_val})
                if res.deleted_count > 0:
                    return await conv.send_message(f"Removed source '{target_id}'.")
                else:
                    return await conv.send_message(f"Source '{target_id}' not found.")
            all_sources = []
            async for src in sources.find():
                all_sources.append(src)
            if not all_sources:
                return await conv.send_message("No sources found.")
            
            msg = "Select a source to remove by typing its number:\n"
            for i, src in enumerate(all_sources):
                msg += f"{i+1}. {src.get('source_title', src['source_id'])}\n"
            await conv.send_message(msg)
            idx_str = (await conv.get_response()).text.strip()
            try:
                idx = int(idx_str) - 1
                if 0 <= idx < len(all_sources):
                    src_to_delete = all_sources[idx]
                    await sources.delete_one({"_id": src_to_delete["_id"]})
                    await conv.send_message(f"Removed source '{src_to_delete.get('source_title', src_to_delete['source_id'])}'.")
                else:
                    await conv.send_message("Invalid number.")
            except ValueError:
                await conv.send_message("Please enter a valid number.")
        except asyncio.TimeoutError:
            await conv.send_message("Conversation timed out.")
        except Exception as e:
            await conv.send_message(f"Error: {str(e)}")


@events.register(events.NewMessage(pattern=r"^/(list_source|lists_source)$", func=lambda e: e.is_private))
@requires_role("admin")
async def list_source_handler(event):
    try:
        all_sources = []
        async for src in sources.find():
            all_sources.append(src)
        if not all_sources:
            return await event.respond("No sources found.")
        
        msg = "**Configured Sources:**\n\n"
        for src in all_sources:
            msg += f"**{src.get('source_title', src['source_id'])}**\n"
            msg += f"Batch Size: {src['batch_size']}, Interval: {src['interval_minutes']}m\n"
            msg += f"Posts per batch: {src['posts_limit']}, Start ID: {src['start_id']}\n"
            msg += f"Auto-Delete: {'Yes ('+str(src['delete_after_minutes'])+'m)' if src.get('auto_delete') else 'No'}\n\n"
        
        await event.respond(msg)
    except Exception as e:
        await event.respond(f"Error: {str(e)}")

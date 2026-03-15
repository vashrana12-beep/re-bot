import asyncio
from telethon import events
from bot.access_control import requires_role

@events.register(events.NewMessage(pattern=r'^/delete(?:\s+|$)', func=lambda e: e.is_private))
@requires_role("admin")
async def delete_msg_handler(event):
    args = event.message.text.split()
    
    if len(args) < 2:
        return await event.respond(
            "❌ **Invalid Format.**\n\n"
            "**Single Message:**\n`/delete <telegram_link>`\n\n"
            "**Range of Messages:**\n`/delete <telegram_link> <end_id>`"
        )
        
    link = args[1]
    
    # 1. Parse the Telegram Link
    try:
        parts = link.split('/')
        if 't.me' not in parts:
            return await event.respond("❌ Invalid Telegram link. It must contain 't.me'.")
            
        if 'c' in parts:
            # Private link format: https://t.me/c/1234567890/5
            c_index = parts.index('c')
            chat_id = int(f"-100{parts[c_index + 1]}")
            start_id = int(parts[c_index + 2])
        else:
            # Public link format: https://t.me/username/5
            tme_index = parts.index('t.me')
            chat_id = parts[tme_index + 1]
            try:
                chat_id = int(chat_id) # In case it's an ID without the 'c'
            except ValueError:
                pass # It's a string username (e.g., @mychannel)
            start_id = int(parts[tme_index + 2])
            
    except Exception as e:
        return await event.respond(f"❌ Could not parse the link. Ensure it is a valid message link.\n**Error:** `{e}`")

    # 2. Determine the Range based on what the user typed
    try:
        if len(args) == 2:
            end_id = start_id # Only link provided -> Single delete
        elif len(args) == 3:
            end_id = int(args[2]) # Link + End ID provided -> Range
        elif len(args) >= 4:
            end_id = int(args[3]) # Link + Start ID + End ID provided -> Range
        else:
            end_id = start_id
            
        # Swap if they accidentally put the bigger number first
        if start_id > end_id:
            start_id, end_id = end_id, start_id
            
    except ValueError:
        return await event.respond("❌ The message IDs must be numbers.")

    status_msg = await event.respond(f"⏳ Deleting messages from `{start_id}` to `{end_id}`...")

    # 3. Execute the Deletion in chunks of 100 (Telegram's limit)
    message_ids = list(range(start_id, end_id + 1))
    deleted_count = 0
    
    try:
        chunk_size = 100
        for i in range(0, len(message_ids), chunk_size):
            chunk = message_ids[i:i + chunk_size]
            await event.client.delete_messages(chat_id, chunk)
            deleted_count += len(chunk)
            await asyncio.sleep(1.5) # Prevent flood waits from Telegram's API
            
        await status_msg.edit(f"✅ **Success!** Automatically deleted `{deleted_count}` messages.")
    except Exception as e:
        await status_msg.edit(f"❌ **An error occurred.**\nThe bot might not have delete permissions in that chat.\n**Details:** `{e}`")

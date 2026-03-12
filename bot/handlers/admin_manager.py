import asyncio
from telethon import events
from bot.database import chats
from bot.access_control import requires_role

# Helper to apply full permissions safely based on Chat Type
async def set_admin_rights(client, chat_id, user_id, make_admin=True):
    try:
        if not make_admin:
            # Revokes admin privileges completely
            await client.edit_admin(chat_id, user_id, is_admin=False)
            return True, None

        # Fetch the chat to see if it's a Channel or a Group
        chat_entity = await client.get_entity(chat_id)
        
        # In Telethon, 'broadcast' is True for Channels, False for Groups/Supergroups
        is_channel = getattr(chat_entity, 'broadcast', False)

        if is_channel:
            # --- CHANNEL SPECIFIC RIGHTS ---
            await client.edit_admin(
                chat_id, user_id,
                change_info=True, 
                post_messages=True,   # Channel only
                edit_messages=True,   # Channel only
                delete_messages=True, 
                invite_users=True,
                add_admins=True, 
                manage_call=True
            )
        else:
            # --- GROUP/SUPERGROUP SPECIFIC RIGHTS ---
            await client.edit_admin(
                chat_id, user_id,
                change_info=True, 
                delete_messages=True, 
                ban_users=True,       # Group only
                invite_users=True,
                pin_messages=True,    # Group only
                add_admins=True, 
                manage_call=True,
                anonymous=False       # Set to True if you want hidden admins in groups!
            )
            
        return True, None
    except Exception as e:
        return False, str(e)

@events.register(events.NewMessage(pattern=r'^/(admin|deadmin)(?: (.*))?$', func=lambda e: e.is_private))
@requires_role("owner")
async def admin_manager_handler(event):
    action = event.pattern_match.group(1) # 'admin' or 'deadmin'
    args = event.pattern_match.group(2)
    is_promoting = (action == "admin")

    # 1. Extract Target User ID
    target_user_id = None
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg.forward:
            target_user_id = reply_msg.forward.sender_id
        else:
            target_user_id = reply_msg.sender_id
    elif args:
        try:
            target_user_id = int(args.strip())
        except ValueError:
            target_user_id = args.strip() # Allow @usernames

    if not target_user_id:
        return await event.respond("❌ Please provide a User ID, username, or reply to a forwarded message.")

    # Prevent editing yourself
    if target_user_id == event.sender_id:
        return await event.respond("⚠️ You cannot change your own admin status via the bot.")

    # 2. Start Conversation for Target Chat
    async with event.client.conversation(event.chat_id, timeout=60) as conv:
        try:
            action_word = "make them an admin" if is_promoting else "remove their admin rights"
            await conv.send_message(
                f"📥 Target user `{target_user_id}` selected.\n\n"
                f"**Send the specific Chat ID where you want to {action_word}.**\n"
                f"*(Or reply with `all` to run the global broadcast to all registered chats).*"
            )
            
            response = await conv.get_response()
            target_chat_input = response.text.strip().lower()

            status_msg = await conv.send_message("⏳ Processing request...")

            # 3. Handle 'ALL' Broadcast
            if target_chat_input == "all":
                success_count = 0
                fail_count = 0
                
                # Pull all chats from your existing MongoDB database
                async for chat_doc in chats.find():
                    success, error = await set_admin_rights(event.client, chat_doc["chat_id"], target_user_id, is_promoting)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                    await asyncio.sleep(1) # Prevent FloodWaits during global broadcast
                
                word = "Promoted" if is_promoting else "Demoted"
                await status_msg.edit(f"🌍 **Global Broadcast Complete!**\n✅ {word} in {success_count} chats.\n❌ Failed in {fail_count} chats.")

            # 4. Handle Specific Chat ID
            else:
                try:
                    specific_chat_id = int(target_chat_input)
                except ValueError:
                    return await status_msg.edit("❌ Failed! That does not look like a valid numerical Chat ID.")

                success, error = await set_admin_rights(event.client, specific_chat_id, target_user_id, is_promoting)
                
                if success:
                    word = "an admin" if is_promoting else "removed as admin"
                    await status_msg.edit(f"✅ Success! `{target_user_id}` is now {word} in `{specific_chat_id}`.")
                else:
                    await status_msg.edit(f"❌ Failed! The bot might lack 'Add New Admins' rights.\n**Error:** `{error}`")

        except asyncio.TimeoutError:
            await conv.send_message("⏳ Conversation timed out.")
        except Exception as e:
            await conv.send_message(f"❌ System Error: {str(e)}")

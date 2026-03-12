import asyncio
from telethon import events
from bot.database import chats
from bot.access_control import requires_role

# --- Helper function using strict Telethon privileges logic with Smart Fallback ---
async def apply_admin_rights(client, chat_id, user_id, action="admin"):
    try:
        if action == "admin":
            entity = await client.get_entity(chat_id)
            is_channel = getattr(entity, 'broadcast', False)

            if is_channel:
                # Safe permissions specifically for Channels
                await client.edit_admin(
                    chat_id, user_id,
                    change_info=True, post_messages=True, edit_messages=True,
                    delete_messages=True, invite_users=True,
                    add_admins=True, manage_call=True
                )
            else:
                # --- SMART FALLBACK FOR GROUPS ---
                try:
                    # Attempt 1: Try to make them an Anonymous Admin
                    await client.edit_admin(
                        chat_id, user_id,
                        change_info=True, delete_messages=True, ban_users=True, 
                        invite_users=True, pin_messages=True, add_admins=True, 
                        manage_call=True, anonymous=True 
                    )
                except Exception:
                    # Attempt 2: If the bot lacks anonymity power, fallback to Normal Admin
                    await client.edit_admin(
                        chat_id, user_id,
                        change_info=True, delete_messages=True, ban_users=True, 
                        invite_users=True, pin_messages=True, add_admins=True, 
                        manage_call=True, anonymous=False 
                    )
        else:
            # Demote / Remove admin
            await client.edit_admin(chat_id, user_id, is_admin=False)
        return True, None
    except Exception as e:
        return False, str(e)

@events.register(events.NewMessage(pattern=r'^/(admin|deadmin)(?: (.*))?$', func=lambda e: e.is_private))
@requires_role("owner")
async def admin_manager_handler(event):
    action = event.pattern_match.group(1) # 'admin' or 'deadmin'
    args = event.pattern_match.group(2)

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
            target_user_id = args.strip() 

    if not target_user_id:
        return await event.respond("❌ Please provide a User ID, username, or reply to a forwarded message.")

    if target_user_id == event.sender_id:
        return await event.respond("⚠️ You cannot change your own admin status via the bot.")

    # 2. Start Clean Conversation Flow
    async with event.client.conversation(event.chat_id, timeout=60) as conv:
        try:
            action_word = "make them an admin" if action == "admin" else "remove their admin rights"
            await conv.send_message(
                f"📥 Target user `{target_user_id}` selected.\n\n"
                f"**Please send the specific Channel/Group ID where you want to {action_word}.**\n"
                f"*(Or reply with `all` to run the global broadcast to all saved chats).*"
            )
            
            response = await conv.get_response()
            target_input = response.text.strip().lower()
            status_msg = await conv.send_message("⏳ Processing request...")

            # 3. Handle 'ALL' Global Broadcast (Merged Logic)
            if target_input == "all":
                successful_actions = 0
                processed_chats = set() # Keeps track so we don't do the same chat twice
                
                # Step A: Aggressively search all active dialogs (From your script)
                try:
                    async for dialog in event.client.iter_dialogs():
                        if dialog.is_channel or dialog.is_group:
                            success, _ = await apply_admin_rights(event.client, dialog.id, target_user_id, action)
                            if success:
                                successful_actions += 1
                            processed_chats.add(dialog.id)
                except Exception:
                    pass # Ignore errors and move to fallback

                # Step B: Fallback to MongoDB registered chats (In case iter_dialogs misses any)
                async for chat_doc in chats.find():
                    cid = chat_doc["chat_id"]
                    if cid not in processed_chats:
                        success, _ = await apply_admin_rights(event.client, cid, target_user_id, action)
                        if success:
                            successful_actions += 1

                word = "applied admin to" if action == "admin" else "removed admin from"
                await status_msg.edit(f"🌍 **Automatically {word} {successful_actions} channels/groups!**")

            # 4. Handle Specific Chat ID (From your script)
            else:
                try:
                    specific_chat_id = int(target_input)
                except ValueError:
                    return await status_msg.edit("❌ Failed! That does not look like a valid numerical Chat ID.")

                success, error_msg = await apply_admin_rights(event.client, specific_chat_id, target_user_id, action)
                
                if success:
                    if action == "admin":
                        await status_msg.edit(f"✅ Success! `{target_user_id}` is now an admin in `{specific_chat_id}`.")
                    else:
                        await status_msg.edit(f"✅ Success! Removed admin rights from `{target_user_id}` in `{specific_chat_id}`.")
                else:
                    await status_msg.edit(f"❌ Failed! The bot is likely not an admin in that channel, or it lacks the 'Add New Admins' right.\n**Error details:** `{error_msg}`")

        except asyncio.TimeoutError:
            await conv.send_message("⏳ Conversation timed out.")
        except Exception as e:
            await conv.send_message(f"❌ System Error: {str(e)}")

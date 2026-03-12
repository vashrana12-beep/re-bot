import asyncio
from telethon import events
from telethon.tl.functions.channels import EditAdminRequest
from telethon.tl.functions.messages import EditChatAdminRequest
from telethon.tl.types import ChatAdminRights, Channel, Chat
from bot.database import chats
from bot.access_control import requires_role

# Helper to apply full permissions safely using Raw API (Matches Pyrogram exactly)
async def set_admin_rights(client, chat_id, user_id, make_admin=True):
    try:
        # Fetch entities correctly
        chat_entity = await client.get_entity(chat_id)
        user_entity = await client.get_input_entity(user_id)

        if not make_admin:
            # --- REVOKE ADMIN ---
            if isinstance(chat_entity, Channel):
                empty_rights = ChatAdminRights(
                    change_info=False, post_messages=False, edit_messages=False,
                    delete_messages=False, ban_users=False, invite_users=False,
                    pin_messages=False, add_admins=False, anonymous=False,
                    manage_call=False, other=False
                )
                await client(EditAdminRequest(channel=chat_entity, user_id=user_entity, admin_rights=empty_rights, rank=""))
            else:
                await client(EditChatAdminRequest(chat_id=chat_entity.id, user_id=user_entity, is_admin=False))
            return True, None

        if isinstance(chat_entity, Channel):
            if chat_entity.broadcast:
                # --- CHANNEL LOGIC ---
                rights = ChatAdminRights(
                    other=True,          # can_manage_chat (The Pyrogram secret!)
                    change_info=True, 
                    post_messages=True, 
                    edit_messages=True,
                    delete_messages=True, 
                    invite_users=True,
                    add_admins=True, 
                    manage_call=True
                )
            else:
                # --- MEGAGROUP LOGIC ---
                rights = ChatAdminRights(
                    other=True,          # can_manage_chat (CRITICAL for anonymous to work)
                    change_info=True, 
                    delete_messages=True, 
                    ban_users=True,       
                    invite_users=True,
                    pin_messages=True, 
                    add_admins=True, 
                    manage_call=True,
                    anonymous=True       # Hidden Admins will now work perfectly!
                )
            await client(EditAdminRequest(channel=chat_entity, user_id=user_entity, admin_rights=rights, rank=""))
            
        elif isinstance(chat_entity, Chat):
            # --- BASIC GROUP LOGIC ---
            await client(EditChatAdminRequest(chat_id=chat_entity.id, user_id=user_entity, is_admin=True))

        return True, None
    except Exception as e:
        return False, str(e)

@events.register(events.NewMessage(pattern=r'^/(admin|deadmin)(?: (.*))?$', func=lambda e: e.is_private))
@requires_role("owner")
async def admin_manager_handler(event):
    action = event.pattern_match.group(1)
    args = event.pattern_match.group(2)
    is_promoting = (action == "admin")

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

            if target_chat_input == "all":
                success_count = 0
                fail_count = 0
                async for chat_doc in chats.find():
                    success, error = await set_admin_rights(event.client, chat_doc["chat_id"], target_user_id, is_promoting)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                    await asyncio.sleep(1)
                
                word = "Promoted" if is_promoting else "Demoted"
                await status_msg.edit(f"🌍 **Global Broadcast Complete!**\n✅ {word} in {success_count} chats.\n❌ Failed in {fail_count} chats.")
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

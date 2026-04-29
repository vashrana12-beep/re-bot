from telethon import Button

def build_chat_keyboard(all_chats_list, selected_chats, page, is_multi=False):
    """
    Builds a paginated keyboard for chat selection.
    all_chats_list: list of tuples [(chat_id, title), ...]
    selected_chats: set of selected chat_ids (used if is_multi=True)
    page: current page index (0-based)
    is_multi: if True, toggles selection and includes a Confirm button.
              if False, single selection.
    """
    items_per_page = 50
    total_pages = max(1, (len(all_chats_list) + items_per_page - 1) // items_per_page)
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_chats = all_chats_list[start_idx:end_idx]

    buttons = []
    
    for chat_id, title in current_chats:
        display_title = title[:20] + "..." if len(title) > 20 else title
        if is_multi:
            icon = "🟢" if chat_id in selected_chats else "🔴"
            buttons.append([Button.inline(f"{icon} {display_title}", data=f"tgl_{chat_id}")])
        else:
            buttons.append([Button.inline(display_title, data=f"sel_{chat_id}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(Button.inline("⬅️ Prev", data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(Button.inline("Next ➡️", data=f"page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
        buttons.append([Button.inline(f"📄 Page {page+1}/{total_pages}", data="ignore")])

    if is_multi:
        buttons.append([
            Button.inline("✅ Select All", data="select_all"),
            Button.inline("❌ Deselect All", data="deselect_all")
        ])
        buttons.append([Button.inline("✅ Confirm Selection", data="confirm_bulk")])
        
    return buttons

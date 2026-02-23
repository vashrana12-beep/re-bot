from telethon import events
from bot.database import users
from bot.config import OWNER_ID

ROLES = {"owner": 3, "admin": 2, "viewer": 1}

def requires_role(min_role: str):
    def decorator(handler):
        async def wrapper(event):
            user_id = event.sender_id
            if user_id == OWNER_ID:
                return await handler(event)
            
            user = await users.find_one({"user_id": user_id})
            if not user:
                raise events.StopPropagation
            
            if ROLES.get(user.get("role", "viewer"), 0) < ROLES.get(min_role, 0):
                raise events.StopPropagation
                
            return await handler(event)
        return wrapper
    return decorator
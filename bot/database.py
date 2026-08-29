import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client.automation_bot

users = db.users
chats = db.chats
automations = db.automations
counters = db.counters
sources = db.sources
run_state = db.run_state

async def get_next_sequence(name: str) -> int:
    doc = await counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    return doc["seq"]

async def init_db(owner_id: int):
    # Ensure owner exists
    owner = await users.find_one({"user_id": owner_id})
    if not owner:
        await users.insert_one({
            "user_id": owner_id,
            "role": "owner",
            "added_by": owner_id,
            "added_at": datetime.datetime.now(datetime.UTC)
        })
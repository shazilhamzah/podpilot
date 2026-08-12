import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv(override=True)

MONGO_URI = os.getenv("MONGO_DB_URI")

if MONGO_URI:
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db_name = os.getenv("MONGO_DB_NAME", "podpilot")
    db = client[db_name]
else:
    client = None
    db = None
    print("[WARNING] MONGO_DB_URI is not set. Database features will not work.")

from pymongo import MongoClient
import os
from dotenv import load_dotenv
load_dotenv('backend/.env')
client = MongoClient(os.getenv("MONGO_DB_URI"), tlsCAFile=__import__('certifi').where())
db = client.podpilot
doc = db.snapshots.find_one({"name": "History Test"})
if doc:
    print(doc.get("analysis_results", {}).keys())

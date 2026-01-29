# seed_db.py
import asyncio
import random
from datetime import datetime, timedelta, timezone
# Import your actual database connection helper here
from core.database import get_database, connect_to_mongo, get_token_usage_collection 

async def seed_token_data():
    print("Connecting to MongoDB...")
    await connect_to_mongo() # Ensure connection is established
    
    usage_coll = get_token_usage_collection()
    plans = ["Basic", "Premium", "Enterprise"]
    emails = ["user1@test.com", "user2@test.com", "admin@test.com"]
    
    seed_data = []
    for i in range(50): # Let's do 50 for a better looking graph
        random_days = random.randint(0, 6)
        ts = datetime.now(timezone.utc) - timedelta(days=random_days)
        
        seed_data.append({
            "user_email": random.choice(emails),
            "tokens_used": random.randint(50, 500),
            "plan_type": random.choice(plans),
            "timestamp": ts
        })
    
    await usage_coll.insert_many(seed_data)
    print("Done! Successfully seeded 50 logs.")

if __name__ == "__main__":
    asyncio.run(seed_token_data())
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings
from pymongo.server_api import ServerApi
import redis.asyncio as redis
client = None
database = None

async def connect_to_mongo():
    global client, database
    try:
        client = AsyncIOMotorClient(settings.DB_URL, server_api=ServerApi('1'))
        database = client[settings.DB_NAME]
        await client.admin.command('ping')
        print("✅ Successfully connected to MongoDB!")
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        raise e

async def close_mongo_connection():
    global client
    if client:
        client.close()

def get_database():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database



class CacheManager:
    def __init__(self):
        self.redis_client = None
        self.max_memory_bytes = 100 * 1024 * 1024  # 100MB default limit

    async def connect(self):
        self.redis_client = await redis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        # Flush the cache on startup for a clean live environment
        await self.redis_client.flushdb()
        print("✅ Redis cache cleared and connected.")

    async def disconnect(self):
        if self.redis_client:
            await self.redis_client.close()

    async def check_and_clear_if_overflowed(self):
        """
        Checks Redis memory usage and automatically clears cache if it exceeds the limit.
        This prevents Redis from running out of memory and crashing.
        """
        if not self.redis_client:
            return
        
        try:
            # Get Redis INFO stats
            info = await self.redis_client.info("memory")
            used_memory = info.get("used_memory", 0)
            
            # If memory usage exceeds threshold, clear the cache
            if used_memory > self.max_memory_bytes:
                print(f"⚠️  Redis memory overflow detected ({used_memory / (1024*1024):.2f}MB). Clearing cache...")
                await self.redis_client.flushdb()
                print(f"✅ Redis cache cleared successfully.")
                return True
            return False
        except Exception as e:
            print(f"❌ Error checking Redis memory: {e}")
            return False

    async def set_with_overflow_check(self, key: str, value: str, ex: int = None):
        """
        Sets a key in Redis with automatic overflow protection.
        If cache is full, it clears the cache before setting the new key.
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized")
        
        try:
            # Check for overflow before setting
            await self.check_and_clear_if_overflowed()
            
            # Set the key
            if ex:
                await self.redis_client.setex(key, ex, value)
            else:
                await self.redis_client.set(key, value)
            return True
        except Exception as e:
            print(f"❌ Error setting Redis key '{key}': {e}")
            return False

    async def get(self, key: str):
        """Retrieve value from Redis with error handling."""
        if not self.redis_client:
            raise RuntimeError("Redis client not initialized")
        
        try:
            return await self.redis_client.get(key)
        except Exception as e:
            print(f"❌ Error getting Redis key '{key}': {e}")
            return None

cache_manager = CacheManager()




# Existing Collections
def get_users_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.users

def get_chats_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.chats

def get_documents_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.documents

def get_knowledge_base_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.knowledge_base

# New Collections for Admin Dashboard (from your screenshot)
def get_token_usage_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.token_usage

def get_subscriptions_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.subscriptions

def get_plans_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.plans

def get_messages_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.messages

def get_settings_collection():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.settings

def get_embedding_vector():
    if database is None:
        raise RuntimeError("Database not initialized. Ensure connect_to_mongo() has been called.")
    return database.embedding_vector
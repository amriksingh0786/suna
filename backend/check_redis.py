import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services import redis

async def check_redis():
    await redis.initialize_async()
    
    # Check for active runs
    active_keys = await redis.keys('active_run:*')
    print(f'Active run keys: {active_keys}')
    
    # Check for response lists
    response_keys = await redis.keys('agent_run:*:responses')
    print(f'Response list keys: {response_keys}')
    
    # Check for any agent run keys
    agent_keys = await redis.keys('agent_run:*')
    print(f'All agent run keys: {agent_keys}')
    
    await redis.close()

if __name__ == "__main__":
    asyncio.run(check_redis()) 
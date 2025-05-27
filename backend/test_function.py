import asyncio
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

async def test_function():
    client = create_client(url, key)
    try:
        # Test if the function exists
        result = client.rpc('ensure_x_api_user_account', {'x_api_user_id': '8ffdb326-b14a-42b4-959e-96e684d26645'}).execute()
        print('Function result:', result)
    except Exception as e:
        print('Function error:', e)

if __name__ == "__main__":
    asyncio.run(test_function()) 
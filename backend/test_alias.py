#!/usr/bin/env python3
"""Test the alias functionality."""

import asyncio
from services.llm import make_llm_api_call

async def test_alias():
    print('🧪 Testing haiku alias...')
    response = await make_llm_api_call(
        model_name='haiku',
        messages=[{'role': 'user', 'content': 'Say "Alias working!"'}],
        max_tokens=50
    )
    print('✅ SUCCESS:', response.choices[0].message.content)
    print('Model used:', response.model)

if __name__ == "__main__":
    asyncio.run(test_alias()) 
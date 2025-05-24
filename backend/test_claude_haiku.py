#!/usr/bin/env python3
"""Quick test for Claude 3.5 Haiku to verify prompt caching fix."""

import asyncio
from services.llm import make_llm_api_call

async def test_claude_35_haiku():
    """Test Claude 3.5 Haiku with the prompt caching fix."""
    messages = [{'role': 'user', 'content': 'Give me a brief response about the weather today.'}]
    
    try:
        print("🧪 Testing Claude 3.5 Haiku...")
        response = await make_llm_api_call(
            model_name='bedrock/anthropic.claude-3-5-haiku-20241022-v1:0',
            messages=messages,
            max_tokens=100,
            temperature=0.7
        )
        
        print('✅ Claude 3.5 Haiku SUCCESS!')
        print('Response:', response.choices[0].message.content)
        print('Model used:', response.model)
        
        if hasattr(response, 'usage') and response.usage:
            print('Token usage:', response.usage)
            
    except Exception as e:
        print('❌ Failed:', str(e))

if __name__ == "__main__":
    asyncio.run(test_claude_35_haiku()) 
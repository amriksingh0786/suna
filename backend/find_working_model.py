#!/usr/bin/env python3
"""Find working Bedrock models that you have access to."""

import asyncio
from services.llm import make_llm_api_call

# Test models in order of preference
test_models = [
    # Claude models (different versions)
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",  # Older Haiku, might have access
    "bedrock/anthropic.claude-instant-v1",  # Very basic Claude
    "bedrock/anthropic.claude-v2:1",  # Claude 2.1
    "bedrock/anthropic.claude-v2",  # Claude 2
    
    # Try without APAC inference profiles (direct models)
    "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",  # Direct Claude 3 Sonnet
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",  # Direct Claude 3 Haiku
    
    # Amazon models
    "bedrock/amazon.titan-text-express-v1",  # Amazon Titan
    "bedrock/amazon.titan-text-lite-v1",  # Amazon Titan Lite
]

async def test_model_access(model_name: str) -> bool:
    """Test if we have access to a specific model."""
    messages = [{"role": "user", "content": "Hi, respond with just 'OK' please."}]
    
    try:
        print(f"🧪 Testing {model_name}...")
        response = await make_llm_api_call(
            model_name=model_name,
            messages=messages,
            max_tokens=10,
            temperature=0,
            enable_fallback=False  # Test direct access
        )
        
        if hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content
            print(f"✅ SUCCESS: {model_name}")
            print(f"   Response: {content}")
            print(f"   Model used: {response.model}")
            return True
            
    except Exception as e:
        error_msg = str(e)
        if "no agreement" in error_msg.lower() or "access" in error_msg.lower():
            print(f"❌ NO ACCESS: {model_name}")
        elif "throttling" in error_msg.lower():
            print(f"⚠️  THROTTLED: {model_name} (but you have access)")
            return True  # You have access, just throttled
        else:
            print(f"❌ ERROR: {model_name} - {error_msg[:100]}...")
    
    return False

async def find_working_models():
    """Find all working models and recommend the best one."""
    print("🔍 Finding working Bedrock models for your account...")
    print("=" * 60)
    
    working_models = []
    
    for model in test_models:
        if await test_model_access(model):
            working_models.append(model)
        print("-" * 40)
    
    print("\n📋 Summary:")
    print("=" * 30)
    
    if working_models:
        print(f"✅ Found {len(working_models)} working model(s):")
        for i, model in enumerate(working_models, 1):
            print(f"  {i}. {model}")
        
        print(f"\n💡 RECOMMENDED: Use this model immediately:")
        print(f"   model_name = \"{working_models[0]}\"")
        
        print(f"\n📝 Quick test command:")
        print(f"   poetry run python -c \"")
        print(f"import asyncio")
        print(f"from services.llm import make_llm_api_call")
        print(f"async def test(): ")
        print(f"    response = await make_llm_api_call('{working_models[0]}', [{'role':'user','content':'Hello!'}])")
        print(f"    print(response.choices[0].message.content)")
        print(f"asyncio.run(test())\"")
        
    else:
        print("❌ No working models found. You need to request access to models in AWS Bedrock console.")
        print("\n🚀 Quick fix: Request access to these models (usually instant approval):")
        print("   1. Claude 3 Haiku")
        print("   2. Amazon Titan Text Express")
        print("   3. Claude Instant")

if __name__ == "__main__":
    asyncio.run(find_working_models()) 
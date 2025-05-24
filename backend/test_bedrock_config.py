#!/usr/bin/env python3
"""
Test script to verify AWS Bedrock configuration and model routing.
"""

import asyncio
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from utils.bedrock_models import (
    get_bedrock_model_config, 
    get_model_id_for_bedrock, 
    is_bedrock_model,
    list_available_bedrock_models,
    validate_bedrock_credentials,
    get_required_iam_permissions,
    check_model_availability
)
from utils.logger import logger
from services.llm import test_bedrock

async def test_bedrock_configuration():
    """Test the Bedrock configuration and model routing."""
    
    print("🔍 Testing AWS Bedrock Configuration")
    print("=" * 50)
    
    # Test 1: Credential validation
    print("\n1. Testing AWS Credentials:")
    if validate_bedrock_credentials():
        print("✅ AWS Bedrock credentials are configured")
    else:
        print("❌ AWS Bedrock credentials are missing")
        print("   Please set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION_NAME")
        return False
    
    # Test 2: Model configuration
    print("\n2. Testing Model Configuration:")
    test_models = [
        "bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0",
        "bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
        "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0"
    ]
    
    for model in test_models:
        config = get_bedrock_model_config(model)
        model_id = get_model_id_for_bedrock(model)
        if config and model_id:
            print(f"✅ {model}")
            print(f"   Model ID: {model_id}")
            print(f"   Description: {config['description']}")
        else:
            print(f"❌ {model} - No configuration found")
    
    # Test 3: Model aliases
    print("\n3. Testing Model Aliases:")
    aliases = ["claude-3.7", "claude-sonnet-4", "claude-3.5", "claude-haiku"]
    for alias in aliases:
        if is_bedrock_model(alias) or alias in ["claude-3.7", "claude-sonnet-4"]:
            model_id = get_model_id_for_bedrock(alias)
            if model_id:
                print(f"✅ {alias} -> {model_id}")
            else:
                print(f"❌ {alias} - No model ID found")
    
    # Test 4: List available models
    print("\n4. Available Bedrock Models:")
    models = list_available_bedrock_models()
    for model, description in models.items():
        print(f"   • {model}: {description}")
    
    # Test 5: API call test (optional - requires valid credentials and model access)
    print("\n5. Testing API Call (requires valid AWS credentials and model access):")
    try:
        success = await test_bedrock()
        if success:
            print("✅ Bedrock API call successful")
        else:
            print("❌ Bedrock API call failed")
    except Exception as e:
        error_str = str(e)
        print(f"❌ Bedrock API test failed: {error_str}")
        
        if "not authorized" in error_str:
            print("\n🔧 IAM Permission Issue Detected!")
            print("This appears to be an authorization problem. Here's how to fix it:")
            
            # Get IAM permission information
            iam_info = get_required_iam_permissions()
            print(f"\n📋 Required IAM Policy ({iam_info['policy_name']}):")
            import json
            print(json.dumps(iam_info['policy_document'], indent=2))
            
            print("\n📝 Setup Instructions:")
            for i, instruction in enumerate(iam_info['instructions'], 1):
                print(f"   {i}. {instruction}")
                
            print(f"\n🌍 Region Availability Check:")
            import os
            current_region = os.getenv('AWS_REGION_NAME', 'us-west-2')
            availability = check_model_availability(current_region)
            print(f"   Current region: {current_region}")
            for model, available in availability.items():
                status = "✅" if available else "❌"
                print(f"   {status} {model}")
            
            if not all(availability.values()):
                print(f"\n⚠️  Some models may not be available in {current_region}")
                print("   Consider switching to us-east-1 or us-west-2 for full model access")
    
    print("\n" + "=" * 50)
    print("✅ Bedrock configuration test completed!")
    return True

if __name__ == "__main__":
    asyncio.run(test_bedrock_configuration()) 
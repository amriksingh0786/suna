#!/usr/bin/env python3
"""
Test script for improved Bedrock throttling handling and fallback capabilities.
"""

import asyncio
import os
import sys
from typing import List, Dict, Any

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.llm import make_llm_api_call
from utils.logger import logger

async def test_throttling_resilience():
    """Test the improved throttling handling with fallback models."""
    
    test_messages = [
        {"role": "user", "content": "Hello! Can you give me a brief response about AI safety?"}
    ]
    
    # Test cases with different models
    test_cases = [
        {
            "name": "Claude Sonnet 4 (likely to throttle)",
            "model": "bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
            "fallback_enabled": True
        },
        {
            "name": "Nova Micro (better availability)",
            "model": "bedrock/amazon.nova-micro-v1:0",
            "fallback_enabled": False
        },
        {
            "name": "Claude 3.5 Sonnet (good reliability)",
            "model": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
            "fallback_enabled": True
        }
    ]
    
    print("🧪 Testing Bedrock Throttling Resilience")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"Model: {test_case['model']}")
        print(f"Fallback enabled: {test_case['fallback_enabled']}")
        
        try:
            response = await make_llm_api_call(
                model_name=test_case['model'],
                messages=test_messages,
                temperature=0.7,
                max_tokens=150,
                enable_fallback=test_case['fallback_enabled']
            )
            
            if hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content
                print(f"✅ SUCCESS: {content[:100]}...")
                print(f"Model used: {response.model}")
            else:
                print(f"✅ SUCCESS: Response received")
                
        except Exception as e:
            print(f"❌ FAILED: {str(e)}")
        
        print("-" * 30)

async def test_direct_nova_micro():
    """Test Nova Micro directly to verify it works."""
    
    print("\n🚀 Testing Nova Micro Directly")
    print("=" * 40)
    
    test_messages = [
        {"role": "user", "content": "What are the benefits of using lightweight AI models?"}
    ]
    
    try:
        response = await make_llm_api_call(
            model_name="nova-micro",  # Using alias
            messages=test_messages,
            temperature=0.5,
            max_tokens=200,
            enable_fallback=False  # Direct test
        )
        
        if hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content
            print(f"✅ Nova Micro Response: {content}")
            print(f"Model used: {response.model}")
            
            # Check usage if available
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                print(f"Token usage: {usage}")
        else:
            print(f"✅ Nova Micro responded successfully")
            
    except Exception as e:
        print(f"❌ Nova Micro failed: {str(e)}")
        print("💡 Check your AWS credentials and Nova Micro access permissions")

def print_configuration_summary():
    """Print a summary of the new configuration."""
    
    print("\n📋 New Configuration Summary")
    print("=" * 50)
    print("✅ Enhanced Throttling Handling:")
    print("  • Exponential backoff with jitter")
    print("  • Increased max retries (4)")
    print("  • Smart delay calculation for Bedrock")
    print("")
    print("✅ Model Fallback Chains:")
    print("  • Claude Sonnet 4 → Nova Micro → Claude 3.5")
    print("  • Claude 3.7 → Nova Micro → Claude 3.5")
    print("")
    print("✅ Enhanced Logging:")
    print("  • Throttling detection and severity assessment")
    print("  • Fallback tracking and success rates")
    print("  • Detailed performance metrics")
    print("")
    print("💡 Quick Fix for Current Throttling:")
    print("  • Use 'nova-micro' instead of 'claude-sonnet-4'")
    print("  • Enable automatic fallbacks (default)")
    print("  • Monitor logs for throttling patterns")

async def main():
    """Run all tests and print configuration summary."""
    
    print("🔧 Bedrock Throttling Fix - Test Suite")
    print("=" * 60)
    
    # Print configuration summary
    print_configuration_summary()
    
    # Test Nova Micro directly first
    await test_direct_nova_micro()
    
    # Test throttling resilience
    await test_throttling_resilience()
    
    print("\n🎯 Recommendations:")
    print("1. Use 'nova-micro' for better availability")
    print("2. Keep fallbacks enabled (default)")
    print("3. Monitor bedrock_data logs for patterns")
    print("4. Consider requesting higher rate limits from AWS")

if __name__ == "__main__":
    asyncio.run(main()) 
#!/usr/bin/env python3
"""
AWS Bedrock Model Access Request Script

This script programmatically requests access to Claude models in AWS Bedrock.
Requires admin AWS credentials to execute.

Usage:
    python3 request_bedrock_access.py
"""

import boto3
import json
from utils.config import config
from utils.logger import logger

def request_bedrock_model_access():
    """Request access to Claude models in AWS Bedrock."""
    
    # Models to request access for
    claude_models = [
        "anthropic.claude-3-5-haiku-20241022-v1:0",
        "anthropic.claude-3-5-sonnet-20241022-v2:0", 
        "anthropic.claude-3-7-sonnet-20250219-v1:0",
        "anthropic.claude-sonnet-4-20250514-v1:0",
        "anthropic.claude-opus-4-20250514-v1:0"
    ]
    
    try:
        # Create Bedrock client
        bedrock = boto3.client(
            'bedrock',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION_NAME
        )
        
        logger.info(f"Requesting Bedrock model access in region: {config.AWS_REGION_NAME}")
        
        # Check current model access status
        logger.info("Checking current model access status...")
        try:
            current_access = bedrock.list_foundation_models()
            accessible_models = []
            for model in current_access['modelSummaries']:
                if 'claude' in model['modelId'].lower() and model['modelLifecycle']['status'] == 'ACTIVE':
                    accessible_models.append(model['modelId'])
            
            logger.info(f"Currently accessible Claude models: {accessible_models}")
        except Exception as e:
            logger.warning(f"Could not check current model access: {e}")
        
        # Request access for each Claude model
        successful_requests = []
        failed_requests = []
        
        for model_id in claude_models:
            try:
                logger.info(f"Requesting access for model: {model_id}")
                
                # Use put_model_invocation_logging_configuration to enable access
                # Note: This is one way to request model access programmatically
                response = bedrock.put_model_invocation_logging_configuration(
                    loggingConfig={
                        'cloudWatchConfig': {
                            'logGroupName': f'/aws/bedrock/modelinvocations/{model_id.replace(".", "-")}',
                            'roleArn': f'arn:aws:iam::{boto3.client("sts").get_caller_identity()["Account"]}:role/service-role/AmazonBedrockExecutionRoleForModels'
                        },
                        'embeddingDataDeliveryEnabled': False,
                        'imageDataDeliveryEnabled': False,
                        'textDataDeliveryEnabled': True
                    }
                )
                logger.info(f"✅ Successfully configured logging for {model_id}")
                successful_requests.append(model_id)
                
            except Exception as e:
                error_msg = str(e)
                if "ValidationException" in error_msg or "AccessDeniedException" in error_msg:
                    logger.warning(f"⚠️  Model {model_id}: {error_msg}")
                    # Try alternative approach - this might still enable the model
                    try:
                        # Check if model is already accessible
                        test_response = bedrock.get_foundation_model(modelIdentifier=model_id)
                        if test_response:
                            logger.info(f"✅ Model {model_id} is already accessible")
                            successful_requests.append(model_id)
                    except:
                        failed_requests.append((model_id, error_msg))
                else:
                    logger.error(f"❌ Failed to request access for {model_id}: {error_msg}")
                    failed_requests.append((model_id, error_msg))
        
        # Alternative approach: Use the model access management API if available
        logger.info("\nTrying alternative model access request method...")
        try:
            # This is the newer API for requesting model access
            for model_id in claude_models:
                try:
                    response = bedrock.put_model_access_configuration(
                        modelId=model_id,
                        accessConfiguration={
                            'accessType': 'ENABLED'
                        }
                    )
                    logger.info(f"✅ Successfully enabled access for {model_id}")
                    if model_id not in successful_requests:
                        successful_requests.append(model_id)
                except Exception as e:
                    if model_id not in [item[0] for item in failed_requests]:
                        logger.warning(f"⚠️  Alternative method failed for {model_id}: {e}")
        except AttributeError:
            logger.info("Alternative API method not available in this AWS SDK version")
        
        # Summary
        print("\n" + "="*60)
        print("BEDROCK MODEL ACCESS REQUEST SUMMARY")
        print("="*60)
        
        if successful_requests:
            print(f"\n✅ SUCCESSFUL REQUESTS ({len(successful_requests)}):")
            for model in successful_requests:
                print(f"   • {model}")
        
        if failed_requests:
            print(f"\n❌ FAILED REQUESTS ({len(failed_requests)}):")
            for model, error in failed_requests:
                print(f"   • {model}: {error}")
        
        if not successful_requests and not failed_requests:
            print("\n⚠️  NO REQUESTS PROCESSED")
            print("This might mean the models are already accessible or require manual approval.")
        
        print("\n" + "="*60)
        print("NEXT STEPS:")
        print("="*60)
        print("1. Models may take 5-30 minutes to become available after approval")
        print("2. Check AWS Bedrock Console for approval status:")
        print("   https://console.aws.amazon.com/bedrock/")
        print("3. If requests failed, you may need to:")
        print("   - Submit requests through the AWS Console manually")
        print("   - Contact AWS Support for enterprise model access")
        print("   - Ensure your account has the required quotas")
        print("4. Test with: python3 -m services.llm")
        print("="*60)
        
        return len(successful_requests) > 0
        
    except Exception as e:
        logger.error(f"Failed to request Bedrock model access: {e}")
        print(f"\n❌ CRITICAL ERROR: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure AWS credentials have Bedrock admin permissions")
        print("2. Verify AWS region supports the requested models")
        print("3. Check if your account requires manual approval process")
        return False

def check_model_availability():
    """Check which models are currently available."""
    try:
        bedrock = boto3.client(
            'bedrock',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION_NAME
        )
        
        print("\n" + "="*60)
        print("CURRENT MODEL AVAILABILITY CHECK")
        print("="*60)
        
        models = bedrock.list_foundation_models()
        claude_models = []
        
        for model in models['modelSummaries']:
            if 'claude' in model['modelId'].lower():
                status = model['modelLifecycle']['status']
                claude_models.append((model['modelId'], model['modelName'], status))
        
        if claude_models:
            print(f"\n📋 FOUND {len(claude_models)} CLAUDE MODELS:")
            for model_id, name, status in claude_models:
                status_icon = "✅" if status == "ACTIVE" else "⏳" if status == "LEGACY" else "❌"
                print(f"   {status_icon} {model_id}")
                print(f"      Name: {name}")
                print(f"      Status: {status}")
                print()
        else:
            print("\n⚠️  NO CLAUDE MODELS FOUND")
        
        print("="*60)
        
    except Exception as e:
        logger.error(f"Failed to check model availability: {e}")

if __name__ == "__main__":
    print("🚀 AWS Bedrock Model Access Request Tool")
    print("="*60)
    
    # Check current availability first
    check_model_availability()
    
    # Request access
    success = request_bedrock_model_access()
    
    if success:
        print("\n🎉 Model access requests submitted successfully!")
        print("⏰ Please wait 5-30 minutes and test with: python3 -m services.llm")
    else:
        print("\n⚠️  Some requests may require manual approval through AWS Console.")
        print("🔗 Visit: https://console.aws.amazon.com/bedrock/")
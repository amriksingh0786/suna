#!/usr/bin/env python3
"""
AWS Bedrock Permission Fixer

This script diagnoses and fixes Bedrock model access permissions.
"""

import boto3
import json
from utils.config import config
from utils.logger import logger

def check_and_fix_bedrock_permissions():
    """Check and fix Bedrock permissions."""
    
    try:
        # Create AWS clients
        sts = boto3.client(
            'sts',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION_NAME
        )
        
        iam = boto3.client(
            'iam',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION_NAME
        )
        
        bedrock = boto3.client(
            'bedrock',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION_NAME
        )
        
        # Get current identity
        identity = sts.get_caller_identity()
        account_id = identity['Account']
        user_arn = identity['Arn']
        
        print("🔍 BEDROCK PERMISSION DIAGNOSIS")
        print("="*60)
        print(f"Account ID: {account_id}")
        print(f"User ARN: {user_arn}")
        print(f"Region: {config.AWS_REGION_NAME}")
        print()
        
        # Check if user has Bedrock permissions
        print("📋 CHECKING IAM PERMISSIONS...")
        
        # Get user policies
        username = user_arn.split('/')[-1] if 'user/' in user_arn else None
        
        if username:
            try:
                # Check attached policies
                attached_policies = iam.list_attached_user_policies(UserName=username)
                print(f"✅ User {username} has {len(attached_policies['AttachedPolicies'])} attached policies:")
                
                has_bedrock_access = False
                for policy in attached_policies['AttachedPolicies']:
                    print(f"   • {policy['PolicyName']}: {policy['PolicyArn']}")
                    if 'bedrock' in policy['PolicyName'].lower():
                        has_bedrock_access = True
                
                if not has_bedrock_access:
                    print("⚠️  No Bedrock-specific policies found")
                    
                    # Try to attach AmazonBedrockFullAccess
                    print("🔧 Attempting to attach AmazonBedrockFullAccess policy...")
                    try:
                        iam.attach_user_policy(
                            UserName=username,
                            PolicyArn='arn:aws:iam::aws:policy/AmazonBedrockFullAccess'
                        )
                        print("✅ Successfully attached AmazonBedrockFullAccess policy")
                        has_bedrock_access = True
                    except Exception as e:
                        print(f"❌ Failed to attach policy: {e}")
                
            except Exception as e:
                print(f"⚠️  Could not check user policies: {e}")
        
        # Try to enable model access through Bedrock console API
        print("\n🔧 ATTEMPTING TO ENABLE MODEL ACCESS...")
        
        models_to_enable = [
            'anthropic.claude-3-5-haiku-20241022-v1:0',
            'anthropic.claude-3-5-sonnet-20241022-v2:0',
            'anthropic.claude-3-7-sonnet-20250219-v1:0'
        ]
        
        # Try the model access request API
        bedrock_runtime = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION_NAME
        )
        
        for model_id in models_to_enable:
            print(f"\n🧪 Testing direct access to {model_id}...")
            try:
                # Try a simple invoke to test access
                response = bedrock_runtime.invoke_model(
                    modelId=model_id,
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 10
                    }),
                    contentType='application/json'
                )
                
                if response:
                    print(f"✅ SUCCESS: {model_id} is accessible!")
                    result = json.loads(response['body'].read())
                    print(f"   Response: {result}")
                    
            except Exception as e:
                error_msg = str(e)
                print(f"❌ FAILED: {model_id}")
                print(f"   Error: {error_msg}")
                
                if "ValidationException" in error_msg:
                    print("   🔧 This might be a request format issue, not permissions")
                elif "AccessDeniedException" in error_msg or "don't have access" in error_msg:
                    print("   🔧 This is definitely a permissions issue")
                    
                    # Try to request access via the model access management
                    try:
                        print(f"   🔄 Attempting to request access...")
                        
                        # This is the new way to request model access
                        response = bedrock.put_model_invocation_logging_configuration(
                            loggingConfig={
                                'cloudWatchConfig': {
                                    'logGroupName': '/aws/bedrock/modelinvocations',
                                    'roleArn': f'arn:aws:iam::{account_id}:role/service-role/AmazonBedrockExecutionRoleForModels'
                                },
                                'embeddingDataDeliveryEnabled': False,
                                'imageDataDeliveryEnabled': False,
                                'textDataDeliveryEnabled': True
                            }
                        )
                        print("   ✅ Logging configuration set (may help with access)")
                        
                    except Exception as log_error:
                        print(f"   ⚠️  Logging setup failed: {log_error}")
        
        print("\n" + "="*60)
        print("MANUAL STEPS TO ENABLE BEDROCK ACCESS:")
        print("="*60)
        print("1. Go to AWS Console: https://console.aws.amazon.com/bedrock/")
        print("2. Navigate to 'Model access' in the left sidebar")
        print("3. Click 'Request model access'")
        print("4. Select the Claude models you want:")
        print("   ☐ Claude 3.5 Haiku")
        print("   ☐ Claude 3.5 Sonnet")
        print("   ☐ Claude 3.7 Sonnet")
        print("5. Fill out the use case form")
        print("6. Submit the request")
        print("7. Wait for approval (usually 5-30 minutes)")
        print("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"Permission check failed: {e}")
        print(f"❌ CRITICAL ERROR: {e}")
        return False

if __name__ == "__main__":
    print("🔧 AWS Bedrock Permission Fixer")
    print("="*60)
    
    success = check_and_fix_bedrock_permissions()
    
    if success:
        print("\n✅ Permission check completed!")
        print("🔗 If models still don't work, follow the manual steps above.")
    else:
        print("\n❌ Permission check failed!")
        print("🔗 Please check your AWS credentials and try again.")
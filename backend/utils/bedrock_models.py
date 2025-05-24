"""
AWS Bedrock Model Configurations

This module provides centralized configuration for AWS Bedrock models,
including model ARNs, inference profiles, and region mappings.
"""

from typing import Dict, Optional, Any
from utils.logger import logger

# Bedrock model configurations with their corresponding ARNs
BEDROCK_MODEL_CONFIGS = {
    # Claude 3.7 Sonnet (Inference Profile - works across accounts)
    "bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0": {
        "model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "model_id_apac": "apac.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "model_id_eu": "eu.anthropic.claude-3-7-sonnet-20250219-v1:0",
        "region": "us-west-2",
        "supports_inference_profile": True,
        "description": "Claude 3.7 Sonnet with inference profile for optimized performance"
    },
    
    # Claude Sonnet 4 (Inference Profile - works across accounts)
    "bedrock/anthropic.claude-sonnet-4-20250514-v1:0": {
        "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "model_id_apac": "apac.anthropic.claude-sonnet-4-20250514-v1:0",
        "model_id_eu": "eu.anthropic.claude-sonnet-4-20250514-v1:0",
        "region": "us-west-2", 
        "supports_inference_profile": True,
        "description": "Claude Sonnet 4 with inference profile for optimized performance"
    },
    
    # Claude 3.5 Sonnet (Inference Profile)
    "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0": {
        "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_id_apac": "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_id_eu": "eu.anthropic.claude-3-5-sonnet-20240620-v1:0",  # Different version for EU
        "region": "us-west-2",
        "supports_inference_profile": True,
        "description": "Claude 3.5 Sonnet with inference profile for optimized performance"
    },
    
    # Claude 3.5 Haiku (Inference Profile)
    "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0": {
        "model_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "model_id_apac": "apac.anthropic.claude-3-haiku-20240307-v1:0",  # Different version for APAC
        "model_id_eu": "eu.anthropic.claude-3-haiku-20240307-v1:0",
        "region": "us-west-2",
        "supports_inference_profile": True,
        "description": "Claude 3.5 Haiku with inference profile for fast responses"
    },
    
    # Claude 3 Haiku (Direct Model - Working)
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0": {
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "region": "ap-south-1",
        "supports_inference_profile": False,
        "description": "Claude 3 Haiku - Fast, economical, and reliable model for most tasks"
    },
    
    # Amazon Nova Micro (APAC Inference Profile)
    "bedrock/amazon.nova-micro-v1:0": {
        "model_id_apac": "apac.amazon.nova-micro-v1:0",
        "region": "ap-south-1",
        "arn": "arn:aws:bedrock:ap-south-1:269678200989:inference-profile/apac.amazon.nova-micro-v1:0",
        "supports_inference_profile": True,
        "supported_regions": [
            "ap-southeast-2",  # Asia Pacific (Sydney)
            "ap-northeast-1",  # Asia Pacific (Tokyo)
            "ap-south-1",      # Asia Pacific (Mumbai)
            "ap-northeast-2",  # Asia Pacific (Seoul)
            "ap-southeast-1",  # Asia Pacific (Singapore)
            "ap-northeast-3"   # Asia Pacific (Osaka)
        ],
        "description": "Amazon Nova Micro - Routes requests to Nova Micro across APAC regions (Sydney, Tokyo, Mumbai, Seoul, Singapore, Osaka)"
    },
    
    # Add more models as needed
}

# Model aliases for easier access
BEDROCK_MODEL_ALIASES = {
    "claude-3.7": "bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0",
    "claude-sonnet-4": "bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
    "claude-3.5": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-haiku": "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
    "claude-3-haiku": "bedrock/anthropic.claude-3-haiku-20240307-v1:0",  # Working model
    "haiku": "bedrock/anthropic.claude-3-haiku-20240307-v1:0",  # Quick alias
    "nova-micro": "bedrock/amazon.nova-micro-v1:0",
    "nova-micro-apac": "bedrock/amazon.nova-micro-v1:0",
}

def get_bedrock_model_config(model_name: str) -> Optional[Dict]:
    """
    Get the Bedrock configuration for a given model name.
    
    Args:
        model_name: The model name (e.g., "bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0")
        
    Returns:
        Dict with model configuration or None if not found
    """
    # Check if it's an alias first
    if model_name in BEDROCK_MODEL_ALIASES:
        model_name = BEDROCK_MODEL_ALIASES[model_name]
    
    config = BEDROCK_MODEL_CONFIGS.get(model_name)
    if config:
        logger.debug(f"Found Bedrock config for {model_name}: {config}")
    else:
        logger.warning(f"No Bedrock config found for model: {model_name}")
    
    return config

def get_model_id_for_bedrock(model_name: str) -> Optional[str]:
    """
    Get the appropriate model_id for a Bedrock model based on the current AWS region.
    
    Args:
        model_name: The model name
        
    Returns:
        The model_id to use for the API call, or None if not a Bedrock model
    """
    import os
    
    # Check if it's an alias first
    if model_name in BEDROCK_MODEL_ALIASES:
        model_name = BEDROCK_MODEL_ALIASES[model_name]
    
    if not model_name.startswith("bedrock/"):
        return None
        
    config = get_bedrock_model_config(model_name)
    if not config:
        return None
    
    # Get current AWS region
    aws_region = os.getenv('AWS_REGION_NAME', 'us-west-2')
    
    # Determine which inference profile to use based on region
    if aws_region.startswith('ap-'):
        # Asia Pacific regions
        model_id = config.get("model_id_apac", config.get("model_id"))
        logger.debug(f"Using APAC inference profile for region {aws_region}: {model_id}")
    elif aws_region.startswith('eu-'):
        # European regions
        model_id = config.get("model_id_eu", config.get("model_id"))
        logger.debug(f"Using EU inference profile for region {aws_region}: {model_id}")
    else:
        # US and other regions (default)
        model_id = config.get("model_id")
        logger.debug(f"Using US inference profile for region {aws_region}: {model_id}")
    
    return model_id

def is_bedrock_model(model_name: str) -> bool:
    """Check if a model name refers to a Bedrock model."""
    return model_name.startswith("bedrock/")

def list_available_bedrock_models() -> Dict[str, str]:
    """List all available Bedrock models with their descriptions."""
    return {
        model: config["description"] 
        for model, config in BEDROCK_MODEL_CONFIGS.items()
    }

def validate_bedrock_credentials() -> bool:
    """
    Validate that AWS Bedrock credentials are properly configured.
    
    Returns:
        True if credentials are available, False otherwise
    """
    import os
    
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = os.getenv('AWS_REGION_NAME')
    
    if aws_access_key and aws_secret_key and aws_region:
        logger.info(f"AWS Bedrock credentials validated for region: {aws_region}")
        return True
    else:
        logger.error("Missing AWS Bedrock credentials. Please ensure AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION_NAME are set.")
        return False

def get_required_iam_permissions() -> Dict[str, Any]:
    """
    Get the required IAM permissions for Bedrock access.
    
    Returns:
        Dict with IAM policy information
    """
    return {
        "policy_name": "BedrockInvokePolicy",
        "policy_document": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "BedrockInvokeModels",
                    "Effect": "Allow", 
                    "Action": [
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"
                    ],
                    "Resource": [
                        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                        "arn:aws:bedrock:*::foundation-model/amazon.nova-*",
                        "arn:aws:bedrock:*:*:inference-profile/*"
                    ]
                }
            ]
        },
        "instructions": [
            "1. Go to AWS IAM Console",
            "2. Create a new policy or attach to existing user/role", 
            "3. Use the policy document above",
            "4. Ensure your AWS region has Claude models enabled",
            "5. Request model access in AWS Bedrock console if needed"
        ]
    }

def check_model_availability(region: str = "us-west-2") -> Dict[str, bool]:
    """
    Check which models are likely available in the specified region.
    
    Args:
        region: AWS region to check
        
    Returns:
        Dict mapping model names to availability status
    """
    # Regions where Claude models are available based on AWS documentation
    us_regions = ["us-east-1", "us-west-2", "us-east-2"]
    eu_regions = ["eu-west-1", "eu-central-1", "eu-west-3", "eu-north-1"]
    apac_regions = [
        "ap-northeast-1", "ap-northeast-2", "ap-northeast-3", 
        "ap-south-1", "ap-south-2", "ap-southeast-1", "ap-southeast-2"
    ]
    
    # Determine region group
    is_us_region = region in us_regions
    is_eu_region = region in eu_regions  
    is_apac_region = region in apac_regions
    
    availability = {}
    for model_name, config in BEDROCK_MODEL_CONFIGS.items():
        # Check if the model has inference profiles for this region
        if is_apac_region:
            available = "model_id_apac" in config
        elif is_eu_region:
            available = "model_id_eu" in config
        elif is_us_region:
            available = "model_id" in config
        else:
            # Unknown region, assume unavailable
            available = False
            
        availability[model_name] = available
            
    return availability 
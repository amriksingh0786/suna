#!/usr/bin/env python3
"""
Daytona Sandbox Health Check

This script checks the health and connectivity of the Daytona sandbox service.
It tests API connectivity, sandbox creation capabilities, and response times.
"""

import time
import sys
from utils.logger import logger
from utils.config import config
from daytona_sdk import Daytona, DaytonaConfig


def check_daytona_health():
    """Check Daytona service health and connectivity."""
    
    logger.info("Starting Daytona sandbox health check...")
    
    # Check configuration
    if not config.DAYTONA_API_KEY:
        logger.error("DAYTONA_API_KEY not configured")
        return False
    
    if not config.DAYTONA_SERVER_URL:
        logger.error("DAYTONA_SERVER_URL not configured")
        return False
    
    if not config.DAYTONA_TARGET:
        logger.error("DAYTONA_TARGET not configured")
        return False
    
    logger.info(f"Configuration check passed:")
    logger.info(f"  Server URL: {config.DAYTONA_SERVER_URL}")
    logger.info(f"  Target: {config.DAYTONA_TARGET}")
    logger.info(f"  API Key: {'*' * 20}...")
    
    try:
        # Initialize Daytona client
        daytona_config = DaytonaConfig(
            api_key=config.DAYTONA_API_KEY,
            server_url=config.DAYTONA_SERVER_URL,
            target=config.DAYTONA_TARGET
        )
        
        daytona = Daytona(daytona_config)
        logger.info("Daytona client initialized successfully")
        
        # Test basic API connectivity
        start_time = time.time()
        try:
            # Try to list workspaces (this should be a quick operation)
            workspaces = daytona.list()
            api_response_time = time.time() - start_time
            
            logger.info(f"API connectivity test passed (response time: {api_response_time:.2f}s)")
            logger.info(f"Found {len(workspaces)} existing workspaces")
            
            # Check if response time is reasonable
            if api_response_time > 10:
                logger.warning(f"API response time is high ({api_response_time:.2f}s) - this may indicate network issues")
            
            return True
            
        except Exception as api_error:
            api_response_time = time.time() - start_time
            logger.error(f"API connectivity test failed after {api_response_time:.2f}s: {str(api_error)}")
            
            # Check if this looks like a timeout
            if api_response_time > 30 or "timeout" in str(api_error).lower():
                logger.error("This appears to be a timeout issue - check network connectivity to Daytona server")
            
            return False
            
    except Exception as e:
        logger.error(f"Failed to initialize Daytona client: {str(e)}")
        return False


def check_sandbox_creation_capability():
    """Test sandbox creation capability without actually creating one."""
    
    logger.info("Testing sandbox creation capability...")
    
    try:
        # This is just a configuration test - we're not actually creating a sandbox
        from sandbox.sandbox import Configuration
        
        logger.info(f"Sandbox configuration:")
        logger.info(f"  Image: {Configuration.SANDBOX_IMAGE_NAME}")
        logger.info(f"  Creation timeout: {config.SANDBOX_CREATION_TIMEOUT}s")
        logger.info(f"  Max retries: {config.SANDBOX_MAX_RETRIES}")
        
        return True
        
    except Exception as e:
        logger.error(f"Sandbox configuration test failed: {str(e)}")
        return False


if __name__ == "__main__":
    logger.info("="*50)
    logger.info("Daytona Sandbox Health Check")
    logger.info("="*50)
    
    all_checks_passed = True
    
    # Run health checks
    checks = [
        ("Daytona API Health", check_daytona_health),
        ("Sandbox Configuration", check_sandbox_creation_capability),
    ]
    
    for check_name, check_function in checks:
        logger.info(f"\nRunning {check_name}...")
        try:
            result = check_function()
            if result:
                logger.info(f"✅ {check_name}: PASSED")
            else:
                logger.error(f"❌ {check_name}: FAILED")
                all_checks_passed = False
        except Exception as e:
            logger.error(f"❌ {check_name}: ERROR - {str(e)}")
            all_checks_passed = False
    
    # Summary
    logger.info("\n" + "="*50)
    if all_checks_passed:
        logger.info("🎉 All health checks passed!")
        logger.info("Daytona sandbox service appears to be healthy")
    else:
        logger.error("⚠️  Some health checks failed")
        logger.error("Check the logs above for specific issues")
    
    logger.info("="*50)
    
    sys.exit(0 if all_checks_passed else 1) 
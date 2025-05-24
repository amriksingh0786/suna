"""
LLM API interface for making calls to various language models.

This module provides a unified interface for making API calls to different LLM providers
(OpenAI, Anthropic, Groq, etc.) using LiteLLM. It includes support for:
- Streaming responses
- Tool calls and function calling
- Retry logic with exponential backoff
- Model-specific configurations
- Comprehensive error handling and logging
"""

from typing import Union, Dict, Any, Optional, AsyncGenerator, List
import os
import json
import asyncio
import time
import uuid
from openai import OpenAIError
import litellm
from utils.logger import logger
from utils.config import config
from utils.bedrock_models import get_model_id_for_bedrock, is_bedrock_model, validate_bedrock_credentials, BEDROCK_MODEL_ALIASES
from utils.bedrock_logger import log_bedrock_call

# litellm.set_verbose=True
litellm.modify_params=True

# Constants
MAX_RETRIES = 4  # Increased for throttling scenarios
RATE_LIMIT_DELAY = 30
RETRY_DELAY = 0.1
BEDROCK_THROTTLE_BASE_DELAY = 1  # Start with 1 second for Bedrock throttling
BEDROCK_MAX_THROTTLE_DELAY = 60  # Cap at 60 seconds

# Model fallback chains for Bedrock
BEDROCK_MODEL_FALLBACKS = {
    "bedrock/anthropic.claude-sonnet-4-20250514-v1:0": [
        "bedrock/anthropic.claude-3-haiku-20240307-v1:0",  # Working alternative
        "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
    ],
    "bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0": [
        "bedrock/anthropic.claude-3-haiku-20240307-v1:0",  # Working alternative
        "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
    ]
}

class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass

class LLMRetryError(LLMError):
    """Exception raised when retries are exhausted."""
    pass

def setup_api_keys() -> None:
    """Set up API keys from environment variables."""
    providers = ['OPENAI', 'ANTHROPIC', 'GROQ', 'OPENROUTER']
    for provider in providers:
        key = getattr(config, f'{provider}_API_KEY')
        if key:
            logger.debug(f"API key set for provider: {provider}")
        else:
            logger.warning(f"No API key found for provider: {provider}")

    # Set up OpenRouter API base if not already set
    if config.OPENROUTER_API_KEY and config.OPENROUTER_API_BASE:
        os.environ['OPENROUTER_API_BASE'] = config.OPENROUTER_API_BASE
        logger.debug(f"Set OPENROUTER_API_BASE to {config.OPENROUTER_API_BASE}")

    # Set up AWS Bedrock credentials
    aws_access_key = config.AWS_ACCESS_KEY_ID
    aws_secret_key = config.AWS_SECRET_ACCESS_KEY
    aws_region = config.AWS_REGION_NAME

    if aws_access_key and aws_secret_key and aws_region:
        logger.debug(f"AWS credentials set for Bedrock in region: {aws_region}")
        # Configure LiteLLM to use AWS credentials
        os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
        os.environ['AWS_REGION_NAME'] = aws_region
    else:
        logger.warning(f"Missing AWS credentials for Bedrock integration - access_key: {bool(aws_access_key)}, secret_key: {bool(aws_secret_key)}, region: {aws_region}")

async def handle_error(error: Exception, attempt: int, max_attempts: int, model_name: str = "") -> None:
    """Handle API errors with appropriate delays and logging."""
    import random
    
    # Determine if this is a Bedrock throttling error
    is_bedrock = model_name.startswith("bedrock/")
    is_throttling = (
        isinstance(error, litellm.exceptions.RateLimitError) or
        "ThrottlingException" in str(error) or
        "throttling" in str(error).lower()
    )
    
    if is_bedrock and is_throttling:
        # Exponential backoff with jitter for Bedrock throttling
        base_delay = BEDROCK_THROTTLE_BASE_DELAY * (2 ** attempt)
        # Add jitter (±25% random variation)
        jitter = random.uniform(0.75, 1.25)
        delay = min(base_delay * jitter, BEDROCK_MAX_THROTTLE_DELAY)
        
        logger.warning(f"Bedrock throttling detected on attempt {attempt + 1}/{max_attempts} for {model_name}")
        logger.info(f"Using exponential backoff: waiting {delay:.2f} seconds before retry")
    elif isinstance(error, litellm.exceptions.RateLimitError):
        delay = RATE_LIMIT_DELAY
        logger.warning(f"Rate limit on attempt {attempt + 1}/{max_attempts}: {str(error)}")
    else:
        delay = RETRY_DELAY
        logger.warning(f"Error on attempt {attempt + 1}/{max_attempts}: {str(error)}")
    
    logger.debug(f"Waiting {delay:.2f} seconds before retry...")
    await asyncio.sleep(delay)

def prepare_params(
    messages: List[Dict[str, Any]],
    model_name: str,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    response_format: Optional[Any] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = False,
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = 'low'
) -> Dict[str, Any]:
    """Prepare parameters for the API call."""
    params = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "response_format": response_format,
        "top_p": top_p,
        "stream": stream,
    }

    if api_key:
        params["api_key"] = api_key
    if api_base:
        params["api_base"] = api_base
    if model_id:
        params["model_id"] = model_id

    # Handle token limits
    if max_tokens is not None:
        # For Claude 3.7 in Bedrock, do not set max_tokens or max_tokens_to_sample
        # as it causes errors with inference profiles
        if model_name.startswith("bedrock/") and "claude-3-7" in model_name:
            logger.debug(f"Skipping max_tokens for Claude 3.7 model: {model_name}")
            # Do not add any max_tokens parameter for Claude 3.7
        else:
            param_name = "max_completion_tokens" if 'o1' in model_name else "max_tokens"
            params[param_name] = max_tokens

    # Add tools if provided
    if tools:
        params.update({
            "tools": tools,
            "tool_choice": tool_choice
        })
        logger.debug(f"Added {len(tools)} tools to API parameters")

    # # Add Claude-specific headers
    if "claude" in model_name.lower() or "anthropic" in model_name.lower():
        params["extra_headers"] = {
            # "anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"
            "anthropic-beta": "output-128k-2025-02-19"
        }
        logger.debug("Added Claude-specific headers")

    # Add OpenRouter-specific parameters
    if model_name.startswith("openrouter/"):
        logger.debug(f"Preparing OpenRouter parameters for model: {model_name}")

        # Add optional site URL and app name from config
        site_url = config.OR_SITE_URL
        app_name = config.OR_APP_NAME
        if site_url or app_name:
            extra_headers = params.get("extra_headers", {})
            if site_url:
                extra_headers["HTTP-Referer"] = site_url
            if app_name:
                extra_headers["X-Title"] = app_name
            params["extra_headers"] = extra_headers
            logger.debug(f"Added OpenRouter site URL and app name to headers")

    # Add Bedrock-specific parameters
    if is_bedrock_model(model_name):
        logger.debug(f"Preparing AWS Bedrock parameters for model: {model_name}")

        # Auto-set model_id using the utility function if not provided
        if not model_id:
            auto_model_id = get_model_id_for_bedrock(model_name)
            if auto_model_id:
                params["model_id"] = auto_model_id
                logger.debug(f"Auto-set model_id for {model_name}: {auto_model_id}")
            else:
                logger.warning(f"No model_id configuration found for Bedrock model: {model_name}")
        
        # Validate credentials
        if not validate_bedrock_credentials():
            logger.error("AWS Bedrock credentials not properly configured")
            raise LLMError("AWS Bedrock credentials not configured")

    # Apply Anthropic prompt caching (minimal implementation)
    # Check model name *after* potential modifications (like adding bedrock/ prefix)
    effective_model_name = params.get("model", model_name) # Use model from params if set, else original
    if "claude" in effective_model_name.lower() or "anthropic" in effective_model_name.lower():
        # Skip prompt caching for Bedrock models as it's not supported with inference profiles
        if not is_bedrock_model(model_name):
            messages = params["messages"] # Direct reference, modification affects params

            # Ensure messages is a list
            if not isinstance(messages, list):
                return params # Return early if messages format is unexpected

            # 1. Process the first message if it's a system prompt with string content
            if messages and messages[0].get("role") == "system":
                content = messages[0].get("content")
                if isinstance(content, str):
                    # Wrap the string content in the required list structure
                    messages[0]["content"] = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                elif isinstance(content, list):
                     # If content is already a list, check if the first text block needs cache_control
                     for item in content:
                         if isinstance(item, dict) and item.get("type") == "text":
                             if "cache_control" not in item:
                                 item["cache_control"] = {"type": "ephemeral"}
                                 break # Apply to the first text block only for system prompt

            # 2. Find and process relevant user and assistant messages
            last_user_idx = -1
            second_last_user_idx = -1
            last_assistant_idx = -1

            for i in range(len(messages) - 1, -1, -1):
                role = messages[i].get("role")
                if role == "user":
                    if last_user_idx == -1:
                        last_user_idx = i
                    elif second_last_user_idx == -1:
                        second_last_user_idx = i
                elif role == "assistant":
                    if last_assistant_idx == -1:
                        last_assistant_idx = i

                # Stop searching if we've found all needed messages
                if last_user_idx != -1 and second_last_user_idx != -1 and last_assistant_idx != -1:
                     break

            # Helper function to apply cache control
            def apply_cache_control(message_idx: int, message_role: str):
                if message_idx == -1:
                    return

                message = messages[message_idx]
                content = message.get("content")

                if isinstance(content, str):
                    message["content"] = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            if "cache_control" not in item:
                               item["cache_control"] = {"type": "ephemeral"}

            # Apply cache control to the identified messages
            apply_cache_control(last_user_idx, "last user")
            apply_cache_control(second_last_user_idx, "second last user")
            apply_cache_control(last_assistant_idx, "last assistant")
        else:
            logger.debug("Skipping prompt caching for Bedrock model (not supported with inference profiles)")

    # Add reasoning_effort for Anthropic models if enabled
    use_thinking = enable_thinking if enable_thinking is not None else False
    is_anthropic = "anthropic" in effective_model_name.lower() or "claude" in effective_model_name.lower()

    if is_anthropic and use_thinking:
        effort_level = reasoning_effort if reasoning_effort else 'low'
        params["reasoning_effort"] = effort_level
        params["temperature"] = 1.0 # Required by Anthropic when reasoning_effort is used
        logger.info(f"Anthropic thinking enabled with reasoning_effort='{effort_level}'")

    return params

async def try_model_fallbacks(
    original_model: str,
    messages: List[Dict[str, Any]],
    **kwargs
) -> Union[Dict[str, Any], None]:
    """
    Try fallback models when the original model is throttled.
    
    Returns:
        API response from fallback model or None if all fallbacks fail
    """
    fallbacks = BEDROCK_MODEL_FALLBACKS.get(original_model, [])
    
    if not fallbacks:
        logger.debug(f"No fallback models configured for {original_model}")
        return None
    
    logger.info(f"Trying {len(fallbacks)} fallback models for {original_model}")
    
    for i, fallback_model in enumerate(fallbacks):
        try:
            logger.info(f"Attempting fallback {i+1}/{len(fallbacks)}: {fallback_model}")
            
            # Update the model name in kwargs
            fallback_kwargs = kwargs.copy()
            fallback_kwargs['model_name'] = fallback_model
            
            # Try with fewer retries for fallbacks to fail fast
            response = await make_llm_api_call_internal(
                messages=messages,
                max_retries=2,  # Fewer retries for fallbacks
                **fallback_kwargs
            )
            
            logger.info(f"✅ Fallback successful with {fallback_model}")
            return response
            
        except Exception as e:
            logger.warning(f"Fallback {fallback_model} also failed: {str(e)}")
            continue
    
    logger.error(f"All fallback models failed for {original_model}")
    return None

async def make_llm_api_call_internal(
    messages: List[Dict[str, Any]],
    model_name: str,
    response_format: Optional[Any] = None,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = False,
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = 'low',
    max_retries: int = MAX_RETRIES
) -> Union[Dict[str, Any], AsyncGenerator]:
    """
    Make an API call to a language model using LiteLLM.

    Args:
        messages: List of message dictionaries for the conversation
        model_name: Name of the model to use (e.g., "gpt-4", "claude-3", "openrouter/openai/gpt-4", "bedrock/anthropic.claude-3-sonnet-20240229-v1:0")
        response_format: Desired format for the response
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens in the response
        tools: List of tool definitions for function calling
        tool_choice: How to select tools ("auto" or "none")
        api_key: Override default API key
        api_base: Override default API base URL
        stream: Whether to stream the response
        top_p: Top-p sampling parameter
        model_id: Optional ARN for Bedrock inference profiles
        enable_thinking: Whether to enable thinking
        reasoning_effort: Level of reasoning effort
        max_retries: Maximum number of retries for the API call

    Returns:
        Union[Dict[str, Any], AsyncGenerator]: API response or stream

    Raises:
        LLMRetryError: If API call fails after retries
        LLMError: For other API-related errors
    """
    # Generate unique request ID for tracking
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    # debug <timestamp>.json messages
    logger.info(f"Making LLM API call to model: {model_name} (Thinking: {enable_thinking}, Effort: {reasoning_effort})")
    logger.info(f"📡 API Call: Using model {model_name}")
    
    params = prepare_params(
        messages=messages,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        tools=tools,
        tool_choice=tool_choice,
        api_key=api_key,
        api_base=api_base,
        stream=stream,
        top_p=top_p,
        model_id=model_id,
        enable_thinking=enable_thinking,
        reasoning_effort=reasoning_effort
    )
    
    # Enhanced logging for Bedrock calls
    is_bedrock = is_bedrock_model(model_name)
    if is_bedrock:
        # Log the request details
        request_data = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model_id": params.get("model_id"),
            "reasoning_effort": reasoning_effort,
            "enable_thinking": enable_thinking
        }
        log_bedrock_call(
            model_id=params.get("model_id", model_name),
            request_data=request_data,
            request_id=request_id
        )
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"Attempt {attempt + 1}/{max_retries}")
            # logger.debug(f"API request parameters: {json.dumps(params, indent=2)}")

            response = await litellm.acompletion(**params)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            logger.debug(f"Successfully received API response from {model_name}")
            logger.debug(f"Response: {response}")
            
            # Enhanced logging for Bedrock responses
            if is_bedrock:
                response_data = {
                    "content": response.choices[0].message.content if response.choices else "",
                    "model": response.model,
                    "usage": response.usage.__dict__ if hasattr(response, 'usage') and response.usage else {}
                }
                log_bedrock_call(
                    model_id=params.get("model_id", model_name),
                    request_data={},  # Already logged above
                    response_data=response_data,
                    duration_ms=duration_ms,
                    request_id=request_id
                )
            
            return response

        except (litellm.exceptions.RateLimitError, OpenAIError, json.JSONDecodeError) as e:
            last_error = e
            
            # Enhanced logging for Bedrock errors
            if is_bedrock:
                duration_ms = (time.time() - start_time) * 1000
                log_bedrock_call(
                    model_id=params.get("model_id", model_name),
                    request_data={},  # Already logged above
                    error=e,
                    duration_ms=duration_ms,
                    request_id=request_id
                )
            
            await handle_error(e, attempt, max_retries, model_name)

        except Exception as e:
            # Enhanced logging for Bedrock errors
            if is_bedrock:
                duration_ms = (time.time() - start_time) * 1000
                log_bedrock_call(
                    model_id=params.get("model_id", model_name),
                    request_data={},  # Already logged above
                    error=e,
                    duration_ms=duration_ms,
                    request_id=request_id
                )
            
            logger.error(f"Unexpected error during API call: {str(e)}", exc_info=True)
            raise LLMError(f"API call failed: {str(e)}")

    error_msg = f"Failed to make API call after {max_retries} attempts"
    if last_error:
        error_msg += f". Last error: {str(last_error)}"
    logger.error(error_msg, exc_info=True)
    raise LLMRetryError(error_msg)

async def make_llm_api_call(
    messages: List[Dict[str, Any]],
    model_name: str,
    response_format: Optional[Any] = None,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = False,
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = 'low',
    enable_fallback: bool = True
) -> Union[Dict[str, Any], AsyncGenerator]:
    """
    Make an LLM API call with automatic fallback for throttled Bedrock models.
    
    This is the main entry point that includes intelligent fallback logic.
    When a Bedrock model is throttled, it will automatically try fallback models.
    
    Args:
        messages: List of chat messages
        model_name: The LLM model to use (supports aliases like 'haiku', 'claude-3-haiku')
        response_format: Optional response format specification
        temperature: Sampling temperature (0.0 to 1.0)
        max_tokens: Maximum tokens to generate
        tools: List of tool/function definitions
        tool_choice: Tool choice strategy ("auto", "none", or specific tool)
        api_key: Optional API key override
        api_base: Optional API base URL override
        stream: Whether to stream the response
        top_p: Top-p sampling parameter
        model_id: Optional model ID for Bedrock
        enable_thinking: Whether to enable thinking
        reasoning_effort: Level of reasoning effort
        enable_fallback: Whether to try fallback models on throttling (default: True)

    Returns:
        Union[Dict[str, Any], AsyncGenerator]: API response or stream

    Raises:
        LLMRetryError: If primary and all fallback models fail
        LLMError: For other API-related errors
    """
    # Resolve model aliases first
    original_model_name = model_name
    if model_name in BEDROCK_MODEL_ALIASES:
        resolved_model = BEDROCK_MODEL_ALIASES[model_name]
        logger.debug(f"Resolved alias '{model_name}' to '{resolved_model}'")
        model_name = resolved_model
    
    original_model = model_name
    is_bedrock = model_name.startswith("bedrock/")
    
    try:
        # Try the primary model first
        response = await make_llm_api_call_internal(
            messages=messages,
            model_name=model_name,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            api_key=api_key,
            api_base=api_base,
            stream=stream,
            top_p=top_p,
            model_id=model_id,
            enable_thinking=enable_thinking,
            reasoning_effort=reasoning_effort
        )
        return response
        
    except (LLMRetryError, Exception) as e:
        # Check if this is a throttling error and we should try fallbacks
        is_throttling = (
            isinstance(e, litellm.exceptions.RateLimitError) or
            "ThrottlingException" in str(e) or
            "throttling" in str(e).lower()
        )
        
        if is_bedrock and is_throttling and enable_fallback:
            logger.warning(f"Primary model {original_model} throttled, trying fallbacks...")
            
            # Try fallback models
            fallback_response = await try_model_fallbacks(
                original_model=original_model,
                messages=messages,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                api_key=api_key,
                api_base=api_base,
                stream=stream,
                top_p=top_p,
                model_id=model_id,
                enable_thinking=enable_thinking,
                reasoning_effort=reasoning_effort
            )
            
            if fallback_response:
                return fallback_response
        
        # If fallbacks failed or no fallbacks available, re-raise the original error
        raise e

# Initialize API keys on module import
setup_api_keys()

# Test code for OpenRouter integration
async def test_openrouter():
    """Test the OpenRouter integration with a simple query."""
    test_messages = [
        {"role": "user", "content": "Hello, can you give me a quick test response?"}
    ]

    try:
        # Test with standard OpenRouter model
        print("\n--- Testing standard OpenRouter model ---")
        response = await make_llm_api_call(
            model_name="openrouter/openai/gpt-4o-mini",
            messages=test_messages,
            temperature=0.7,
            max_tokens=100
        )
        print(f"Response: {response.choices[0].message.content}")

        # Test with deepseek model
        print("\n--- Testing deepseek model ---")
        response = await make_llm_api_call(
            model_name="openrouter/deepseek/deepseek-r1-distill-llama-70b",
            messages=test_messages,
            temperature=0.7,
            max_tokens=100
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Model used: {response.model}")

        # Test with Mistral model
        print("\n--- Testing Mistral model ---")
        response = await make_llm_api_call(
            model_name="openrouter/mistralai/mixtral-8x7b-instruct",
            messages=test_messages,
            temperature=0.7,
            max_tokens=100
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Model used: {response.model}")

        return True
    except Exception as e:
        print(f"Error testing OpenRouter: {str(e)}")
        return False

async def test_bedrock():
    """Test the AWS Bedrock integration with a simple query."""
    test_messages = [
        {"role": "user", "content": "Hello, can you give me a quick test response?"}
    ]

    try:
        # Test with Claude 3.7 Sonnet via Bedrock
        response = await make_llm_api_call(
            model_name="bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0",
            messages=test_messages,
            temperature=0.7,
            # Claude 3.7 has issues with max_tokens, so omit it
            # max_tokens=100
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Model used: {response.model}")

        return True
    except Exception as e:
        print(f"Error testing Bedrock: {str(e)}")
        return False

if __name__ == "__main__":
    import asyncio

    test_success = asyncio.run(test_bedrock())

    if test_success:
        print("\n✅ integration test completed successfully!")
    else:
        print("\n❌ Bedrock integration test failed!")

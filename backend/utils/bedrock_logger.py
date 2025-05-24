"""
Specialized logging for AWS Bedrock API calls.

This module provides enhanced logging specifically for Bedrock interactions,
including request/response tracking, error handling, and performance metrics.
"""

import json
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone

from utils.logger import logger


def log_bedrock_call(
    model_id: str,
    request_data: Optional[Dict[str, Any]] = None,
    response_data: Optional[Dict[str, Any]] = None,
    error: Optional[Exception] = None,
    duration_ms: Optional[float] = None,
    request_id: Optional[str] = None,
    is_fallback: bool = False,
    original_model: Optional[str] = None
) -> None:
    """
    Log AWS Bedrock API calls with detailed information.
    
    Args:
        model_id: The Bedrock model ID being used
        request_data: Request payload data (optional)
        response_data: Response payload data (optional)
        error: Exception if the call failed (optional)
        duration_ms: Duration of the call in milliseconds (optional)
        request_id: Unique request identifier for correlation (optional)
        is_fallback: Whether this is a fallback model call (optional)
        original_model: Original model if this is a fallback (optional)
    """
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    
    # Base log data
    log_entry = {
        'timestamp': timestamp,
        'service': 'bedrock',
        'model_id': model_id,
        'request_id': request_id,
        'is_fallback': is_fallback
    }
    
    # Add fallback information
    if is_fallback and original_model:
        log_entry['original_model'] = original_model
        log_entry['fallback_reason'] = 'throttling'
    
    # Add timing information if available
    if duration_ms is not None:
        log_entry['duration_ms'] = round(duration_ms, 2)
        log_entry['duration_category'] = _categorize_duration(duration_ms)
    
    # Handle different types of log entries
    if error:
        # Enhanced error logging for throttling detection
        error_type = type(error).__name__
        error_message = str(error)
        is_throttling = (
            "ThrottlingException" in error_message or
            "throttling" in error_message.lower() or
            "RateLimitError" in error_type
        )
        
        log_entry.update({
            'status': 'error',
            'error_type': error_type,
            'error_message': error_message,
            'is_throttling': is_throttling
        })
        
        if is_throttling:
            log_entry['throttling_severity'] = _assess_throttling_severity(error_message)
            
        error_prefix = "🔄 Fallback model failed" if is_fallback else "❌ Bedrock API call failed"
        logger.error(f"{error_prefix} for model {model_id}", extra={'bedrock_data': log_entry})
        
    elif response_data:
        # Response logging
        log_entry.update({
            'status': 'success',
            'response_summary': _summarize_response(response_data)
        })
        
        # Add usage information if available
        if 'usage' in response_data and response_data['usage']:
            log_entry['token_usage'] = response_data['usage']
            
        success_prefix = "✅ Fallback successful" if is_fallback else "✅ Bedrock API call completed"
        logger.info(f"{success_prefix} for model {model_id}", extra={'bedrock_data': log_entry})
        
    elif request_data:
        # Request logging
        log_entry.update({
            'status': 'request',
            'request_summary': _summarize_request(request_data)
        })
        
        request_prefix = "🔄 Trying fallback model" if is_fallback else "📡 Bedrock API call initiated"
        logger.info(f"{request_prefix} for model {model_id}", extra={'bedrock_data': log_entry})
        
    else:
        # Generic logging
        logger.info(f"Bedrock API interaction for model {model_id}", extra={'bedrock_data': log_entry})


def _summarize_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a summary of request data for logging.
    
    Args:
        request_data: The full request data
        
    Returns:
        Dict with summarized request information
    """
    summary = {}
    
    if 'messages' in request_data:
        messages = request_data['messages']
        summary['message_count'] = len(messages) if isinstance(messages, list) else 1
        
        # Get total character count across all messages
        total_chars = 0
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict) and 'content' in msg:
                    content = msg['content']
                    if isinstance(content, str):
                        total_chars += len(content)
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                total_chars += len(item.get('text', ''))
        
        summary['total_input_chars'] = total_chars
    
    # Add other relevant request parameters
    for key in ['temperature', 'max_tokens', 'reasoning_effort', 'enable_thinking']:
        if key in request_data and request_data[key] is not None:
            summary[key] = request_data[key]
    
    return summary


def _summarize_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a summary of response data for logging.
    
    Args:
        response_data: The full response data
        
    Returns:
        Dict with summarized response information
    """
    summary = {}
    
    if 'content' in response_data:
        content = response_data['content']
        if isinstance(content, str):
            summary['response_chars'] = len(content)
            summary['response_preview'] = content[:100] + '...' if len(content) > 100 else content
    
    if 'model' in response_data:
        summary['response_model'] = response_data['model']
    
    return summary


def _categorize_duration(duration_ms: float) -> str:
    """
    Categorize API call duration for analysis.
    
    Args:
        duration_ms: Duration in milliseconds
        
    Returns:
        String category for the duration
    """
    if duration_ms < 1000:  # Less than 1 second
        return 'fast'
    elif duration_ms < 5000:  # 1-5 seconds
        return 'normal'
    elif duration_ms < 15000:  # 5-15 seconds
        return 'slow'
    else:  # More than 15 seconds
        return 'very_slow'


def _assess_throttling_severity(error_message: str) -> str:
    """
    Assess the severity of throttling based on error message.
    
    Args:
        error_message: The error message from the API
        
    Returns:
        String indicating throttling severity
    """
    error_lower = error_message.lower()
    
    if 'rate exceeded' in error_lower or 'quota exceeded' in error_lower:
        return 'severe'
    elif 'throttling' in error_lower:
        return 'moderate'
    elif 'rate limit' in error_lower:
        return 'mild'
    else:
        return 'unknown'


def get_throttling_statistics(
    time_window_hours: int = 24
) -> Dict[str, Any]:
    """
    Get throttling statistics from recent logs.
    
    Args:
        time_window_hours: Hours to look back for statistics
        
    Returns:
        Dict with throttling statistics
    """
    # This is a placeholder for future implementation
    # In a real system, you'd query your log storage/database
    return {
        'time_window_hours': time_window_hours,
        'total_calls': 0,
        'throttled_calls': 0,
        'throttling_rate': 0.0,
        'most_throttled_models': [],
        'fallback_success_rate': 0.0,
        'recommendation': 'Monitor throttling patterns and consider using Nova Micro for better availability'
    } 
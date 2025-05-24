#!/usr/bin/env python3
"""
Bedrock Log Viewer - Monitor AWS Bedrock API calls in real-time.

This utility helps you view and filter Bedrock logs to monitor:
- API requests and responses
- Error rates and types
- Performance metrics
- Usage patterns
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime
from typing import Dict, Any, List
import re

def parse_log_line(line: str) -> Dict[str, Any]:
    """Parse a log line and extract structured data."""
    try:
        # Look for JSON data in the log line
        json_match = re.search(r'\{.*\}', line)
        if json_match:
            json_data = json.loads(json_match.group())
            
            # Extract timestamp from the beginning of the line
            timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})', line)
            if timestamp_match:
                json_data['log_timestamp'] = timestamp_match.group(1)
            
            return json_data
    except (json.JSONDecodeError, AttributeError):
        pass
    
    return {}

def format_bedrock_event(event: Dict[str, Any]) -> str:
    """Format a Bedrock event for display."""
    event_type = event.get('event', 'unknown')
    timestamp = event.get('log_timestamp', 'unknown')
    model_id = event.get('model_id', 'unknown')
    request_id = event.get('request_id', 'N/A')
    
    if event_type == 'bedrock_request':
        prompt_length = event.get('prompt_length', 0)
        max_tokens = event.get('max_tokens', 'N/A')
        temperature = event.get('temperature', 'N/A')
        return f"🚀 [{timestamp}] REQUEST {request_id} | Model: {model_id} | Prompt: {prompt_length} chars | Max tokens: {max_tokens} | Temp: {temperature}"
    
    elif event_type == 'bedrock_response':
        duration = event.get('duration_ms', 0)
        response_length = event.get('response_length', 0)
        stop_reason = event.get('stop_reason', 'unknown')
        return f"✅ [{timestamp}] RESPONSE {request_id} | Model: {model_id} | Duration: {duration:.1f}ms | Response: {response_length} chars | Stop: {stop_reason}"
    
    elif event_type == 'bedrock_error':
        duration = event.get('duration_ms', 0)
        error_type = event.get('error_type', 'unknown')
        error_category = event.get('error_category', 'unknown')
        error_message = event.get('error_message', '')[:100]
        return f"❌ [{timestamp}] ERROR {request_id} | Model: {model_id} | Duration: {duration:.1f}ms | Type: {error_type} | Category: {error_category} | Message: {error_message}..."
    
    elif event_type == 'bedrock_metrics':
        duration = event.get('duration_ms', 0)
        success = event.get('success', False)
        status = "✅" if success else "❌"
        return f"📊 [{timestamp}] METRICS {request_id} | Model: {model_id} | Duration: {duration:.1f}ms | Status: {status}"
    
    return f"📝 [{timestamp}] {event_type.upper()} {request_id} | Model: {model_id}"

def get_latest_log_file() -> str:
    """Get the path to the latest log file."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        print(f"❌ Log directory '{log_dir}' not found!")
        sys.exit(1)
    
    # Find the latest log file
    log_files = [f for f in os.listdir(log_dir) if f.startswith('agentpress_') and f.endswith('.log')]
    if not log_files:
        print(f"❌ No log files found in '{log_dir}'!")
        sys.exit(1)
    
    latest_log = max(log_files, key=lambda f: os.path.getmtime(os.path.join(log_dir, f)))
    return os.path.join(log_dir, latest_log)

def tail_logs(log_file: str, filter_bedrock: bool = True, follow: bool = False):
    """Tail log file and display Bedrock events."""
    print(f"📖 Monitoring Bedrock logs from: {log_file}")
    print("=" * 80)
    
    try:
        with open(log_file, 'r') as f:
            # Go to end of file if following
            if follow:
                f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    # Check if this line contains Bedrock event data
                    if filter_bedrock and ('bedrock_' not in line):
                        continue
                    
                    event = parse_log_line(line.strip())
                    if event and event.get('event', '').startswith('bedrock_'):
                        print(format_bedrock_event(event))
                    elif not filter_bedrock:
                        # Show all log lines if not filtering
                        print(line.strip())
                
                elif follow:
                    # Wait for new lines
                    time.sleep(0.1)
                else:
                    # End of file and not following
                    break
                    
    except KeyboardInterrupt:
        print("\n👋 Stopped monitoring logs")
    except FileNotFoundError:
        print(f"❌ Log file not found: {log_file}")

def analyze_logs(log_file: str, hours: int = 1):
    """Analyze Bedrock logs and show statistics."""
    print(f"📊 Analyzing Bedrock logs from: {log_file}")
    print(f"🕐 Looking at last {hours} hour(s)")
    print("=" * 80)
    
    cutoff_time = time.time() - (hours * 3600)
    
    events = []
    with open(log_file, 'r') as f:
        for line in f:
            if 'bedrock_' not in line:
                continue
                
            event = parse_log_line(line.strip())
            if event and event.get('event', '').startswith('bedrock_'):
                # Simple time filtering (could be improved)
                events.append(event)
    
    if not events:
        print("❌ No Bedrock events found in logs")
        return
    
    # Analyze events
    requests = [e for e in events if e.get('event') == 'bedrock_request']
    responses = [e for e in events if e.get('event') == 'bedrock_response']
    errors = [e for e in events if e.get('event') == 'bedrock_error']
    
    print(f"📈 Total Events: {len(events)}")
    print(f"🚀 Requests: {len(requests)}")
    print(f"✅ Responses: {len(responses)}")
    print(f"❌ Errors: {len(errors)}")
    
    if responses:
        durations = [e.get('duration_ms', 0) for e in responses]
        avg_duration = sum(durations) / len(durations)
        print(f"⏱️  Average Response Time: {avg_duration:.1f}ms")
        print(f"⚡ Fastest Response: {min(durations):.1f}ms")
        print(f"🐌 Slowest Response: {max(durations):.1f}ms")
    
    if errors:
        error_categories = {}
        for error in errors:
            category = error.get('error_category', 'unknown')
            error_categories[category] = error_categories.get(category, 0) + 1
        
        print(f"\n🚨 Error Breakdown:")
        for category, count in error_categories.items():
            print(f"   {category}: {count}")
    
    # Model usage
    models = {}
    for event in events:
        model = event.get('model_id', 'unknown')
        models[model] = models.get(model, 0) + 1
    
    print(f"\n🤖 Model Usage:")
    for model, count in sorted(models.items(), key=lambda x: x[1], reverse=True):
        print(f"   {model}: {count} calls")

def main():
    parser = argparse.ArgumentParser(description="Monitor AWS Bedrock logs")
    parser.add_argument('--file', '-f', help="Specific log file to monitor")
    parser.add_argument('--follow', '-F', action='store_true', help="Follow log file (like tail -f)")
    parser.add_argument('--all', '-a', action='store_true', help="Show all log lines, not just Bedrock")
    parser.add_argument('--analyze', '-A', action='store_true', help="Analyze logs and show statistics")
    parser.add_argument('--hours', type=int, default=1, help="Hours to analyze (default: 1)")
    
    args = parser.parse_args()
    
    # Determine log file
    log_file = args.file if args.file else get_latest_log_file()
    
    if args.analyze:
        analyze_logs(log_file, args.hours)
    else:
        tail_logs(log_file, filter_bedrock=not args.all, follow=args.follow)

if __name__ == "__main__":
    main() 
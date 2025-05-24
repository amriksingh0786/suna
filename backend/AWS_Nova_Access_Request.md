# AWS Bedrock Nova Model Access Request

## Steps to Request Access to Amazon Nova Models

### 1. Navigate to AWS Bedrock Console

- Go to [AWS Bedrock Console](https://console.aws.amazon.com/bedrock)
- Ensure you're in the `ap-south-1` region (Mumbai)

### 2. Request Model Access

1. In the left sidebar, click on **"Model access"**
2. Look for **Amazon Nova models** in the list
3. Find specifically:
   - **Amazon Nova Micro** (`amazon.nova-micro-v1:0`)
   - **Amazon Nova Lite** (optional, for better performance)
   - **Amazon Nova Pro** (optional, for advanced tasks)

### 3. Enable Models

1. Click the **checkbox** next to each Nova model you want to access
2. Click **"Request model access"** or **"Manage model access"**
3. If prompted, provide business justification:
   ```
   Business Justification:
   - Developing AI agent platform requiring reliable, cost-effective language models
   - Need Nova Micro as fallback model for high-availability scenarios
   - Currently experiencing throttling with Claude models during peak usage
   - Nova Micro will serve as backup to ensure continuous service availability
   ```

### 4. Wait for Approval

- **Nova Micro**: Usually approved instantly or within a few minutes
- **Nova Lite/Pro**: May take up to 24 hours
- You'll receive an email confirmation when access is granted

### 5. Verify Access

After approval, test access using our script:

```bash
poetry run python test_throttling_fix.py
```

## Alternative Models Available Now

If you need immediate access while waiting for Nova approval, these models should work:

### Claude 3.5 Haiku (Fast & Economical)

```python
response = await make_llm_api_call(
    model_name="bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
    messages=messages
)
```

### Claude 3 Haiku (More Economical)

```python
response = await make_llm_api_call(
    model_name="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    messages=messages
)
```

## Current Throttling Solution Status

✅ **Working Now:**

- Enhanced throttling handling with exponential backoff
- Automatic model fallbacks when throttling occurs
- Improved logging for monitoring throttling patterns
- Claude Sonnet 4 working successfully (no throttling in test)

🔧 **Next Steps:**

1. Request Nova Micro access (5 minutes)
2. Update fallback chains once Nova is available
3. Monitor logs for throttling patterns
4. Consider requesting higher rate limits for frequently used models

## Immediate Fix for Your Throttling Issue

Since Claude Sonnet 4 worked in our test, try using Claude 3.5 Haiku as your primary model:

```python
# Instead of the throttled model, use:
model_name = "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0"
```

This model has:

- ✅ Better availability than Sonnet 4
- ✅ Much faster response times
- ✅ Lower cost per token
- ✅ Good quality for most tasks
- ✅ Less likely to be throttled

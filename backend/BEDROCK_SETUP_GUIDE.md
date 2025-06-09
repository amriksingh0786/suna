# AWS Bedrock Model Access Setup Guide

## Current Status ❌
Your backend is configured for **Bedrock-only** operation but model access needs to be approved manually.

## Issue Diagnosis ✅
- ✅ AWS IAM permissions are correct
- ✅ AWS credentials are working  
- ✅ Models exist and are listed as "ACTIVE"
- ❌ **Model invocation access is not granted yet**

## Manual Fix Required 🔧

### Step 1: Request Model Access in AWS Console

1. **Go to AWS Bedrock Console:**
   - Navigate to: https://console.aws.amazon.com/bedrock/
   - **Important**: Make sure you're in the `us-west-2` region

2. **Navigate to Model Access:**
   - In the left sidebar, click **"Model access"**
   - Click **"Request model access"** or **"Manage model access"**

3. **Select Claude Models to Enable:**
   - ☐ **Claude 3.5 Haiku** (`anthropic.claude-3-5-haiku-20241022-v1:0`)
   - ☐ **Claude 3.5 Sonnet v2** (`anthropic.claude-3-5-sonnet-20241022-v2:0`)
   - ☐ **Claude 3.7 Sonnet** (`anthropic.claude-3-7-sonnet-20250219-v1:0`)
   - ☐ **Claude Sonnet 4** (`anthropic.claude-sonnet-4-20250514-v1:0`) *(optional)*

4. **Fill Out Use Case Form:**
   - **Use Case**: "AI Development Platform for Code Generation and Analysis"
   - **Description**: "Building an AI-powered development assistant that helps with code generation, debugging, and technical documentation"
   - **Company**: Your company name
   - **Expected Usage**: "Medium volume - development and testing"

5. **Submit Request:**
   - Review and submit the model access request
   - **Approval time**: Usually 5-30 minutes (can be up to 24 hours)

### Step 2: Test After Approval

Once AWS approves your request, test with:

```bash
python3 -m services.llm
```

Expected output:
```
✅ Bedrock working!
Response: Hello! This is a test response.
```

### Step 3: Switch Models if Needed

If Haiku gets approved first, you can use it immediately:

```bash
# In .env file:
MODEL_TO_USE = bedrock/anthropic.claude-3-5-haiku-20241022-v1:0
```

If you prefer Sonnet models:
```bash
# In .env file:
MODEL_TO_USE = bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
```

## Why Manual Approval is Required

AWS Bedrock requires explicit approval for Claude models because:
- **Enterprise Models**: Claude models have usage restrictions
- **Cost Management**: Prevents accidental high-cost usage
- **Compliance**: Ensures proper use case documentation
- **Account Verification**: Confirms legitimate business use

## Alternative: Use OpenAI Temporarily

If you need immediate functionality while waiting for Bedrock approval:

```bash
# In .env file:
MODEL_TO_USE = openai/gpt-4o
```

```python
# In utils/constants.py, temporarily change aliases:
"sonnet-3.5": "openai/gpt-4o",
"haiku-3.5": "openai/gpt-4o-mini",
```

## Expected Timeline

- **Immediate**: IAM permissions (✅ already done)
- **5-30 minutes**: Basic Claude model approval
- **1-24 hours**: Enterprise Claude model approval
- **1-3 days**: High-volume usage approval

## Troubleshooting

### If approval takes too long:
1. Check AWS Support Center for ticket status
2. Contact AWS Support via console
3. Verify your AWS account is in good standing
4. Ensure billing information is complete

### If models still fail after approval:
1. Wait 5-10 minutes for permissions to propagate
2. Restart your application
3. Check the AWS Bedrock Console for model status
4. Verify the correct region (`us-west-2`)

## Your Backend Configuration Summary

✅ **Ready for Bedrock:**
- Model aliases configured for Bedrock
- Inference profile ARNs correctly mapped
- Error handling in place
- Cost-optimized model selection

⏳ **Waiting for:**
- AWS Bedrock model access approval

---

**Next Action:** Complete the manual model access request in AWS Console above. Your backend will work immediately once approved.
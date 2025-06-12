from fastapi import APIRouter, HTTPException, Depends, Request, Body, File, UploadFile, Form
from fastapi.responses import StreamingResponse, Response
import asyncio
import json
import traceback
from datetime import datetime, timezone
import uuid
from typing import Optional, List, Dict, Any
import jwt
from pydantic import BaseModel
import tempfile
import os
import mimetypes

from agentpress.thread_manager import ThreadManager
from services.supabase import DBConnection
from services import redis
from agent.run import run_agent
from utils.auth_utils import get_current_user_id_from_jwt, get_user_id_from_stream_auth, verify_thread_access, is_x_app_token
from utils.logger import logger
from services.billing import check_billing_status, can_use_model
from utils.config import config
from sandbox.sandbox import create_sandbox, get_or_start_sandbox
from services.llm import make_llm_api_call
from run_agent_background import run_agent_background, _cleanup_redis_response_list, update_agent_run_status
from utils.constants import MODEL_NAME_ALIASES
# Initialize shared resources
router = APIRouter()
db = None
instance_id = None # Global instance ID for this backend instance

# TTL for Redis response lists (24 hours)
REDIS_RESPONSE_LIST_TTL = 3600 * 24


class AgentStartRequest(BaseModel):
    model_name: Optional[str] = None  # Will be set from config.MODEL_TO_USE in the endpoint
    enable_thinking: Optional[bool] = False
    reasoning_effort: Optional[str] = 'low'
    stream: Optional[bool] = True
    enable_context_manager: Optional[bool] = False

class InitiateAgentResponse(BaseModel):
    thread_id: str
    agent_run_id: Optional[str] = None

class ProjectUpdateRequest(BaseModel):
    name: str

def initialize(
    _db: DBConnection,
    _instance_id: str = None
):
    """Initialize the agent API with resources from the main API."""
    global db, instance_id
    db = _db

    # Use provided instance_id or generate a new one
    if _instance_id:
        instance_id = _instance_id
    else:
        # Generate instance ID
        instance_id = str(uuid.uuid4())[:8]

    logger.info(f"Initialized agent API with instance ID: {instance_id}")

    # Note: Redis will be initialized in the lifespan function in api.py

async def cleanup():
    """Clean up resources and stop running agents on shutdown."""
    logger.info("Starting cleanup of agent API resources")

    # Use the instance_id to find and clean up this instance's keys
    try:
        if instance_id: # Ensure instance_id is set
            running_keys = await redis.keys(f"active_run:{instance_id}:*")
            logger.info(f"Found {len(running_keys)} running agent runs for instance {instance_id} to clean up")

            for key in running_keys:
                # Key format: active_run:{instance_id}:{agent_run_id}
                parts = key.split(":")
                if len(parts) == 3:
                    agent_run_id = parts[2]
                    await stop_agent_run(agent_run_id, error_message=f"Instance {instance_id} shutting down")
                else:
                    logger.warning(f"Unexpected key format found: {key}")
        else:
            logger.warning("Instance ID not set, cannot clean up instance-specific agent runs.")

    except Exception as e:
        logger.error(f"Failed to clean up running agent runs: {str(e)}")

    # Close Redis connection
    await redis.close()
    logger.info("Completed cleanup of agent API resources")

async def stop_agent_run(agent_run_id: str, error_message: Optional[str] = None):
    """Update database and publish stop signal to Redis."""
    logger.info(f"Stopping agent run: {agent_run_id}")
    client = await db.client
    final_status = "failed" if error_message else "stopped"

    # Attempt to fetch final responses from Redis
    response_list_key = f"agent_run:{agent_run_id}:responses"
    all_responses = []
    try:
        all_responses_json = await redis.lrange(response_list_key, 0, -1)
        all_responses = [json.loads(r) for r in all_responses_json]
        logger.info(f"Fetched {len(all_responses)} responses from Redis for DB update on stop/fail: {agent_run_id}")
    except Exception as e:
        logger.error(f"Failed to fetch responses from Redis for {agent_run_id} during stop/fail: {e}")
        # Try fetching from DB as a fallback? Or proceed without responses? Proceeding without for now.

    # Update the agent run status in the database
    update_success = await update_agent_run_status(
        client, agent_run_id, final_status, error=error_message, responses=all_responses
    )

    if not update_success:
        logger.error(f"Failed to update database status for stopped/failed run {agent_run_id}")

    # Send STOP signal to the global control channel
    global_control_channel = f"agent_run:{agent_run_id}:control"
    try:
        await redis.publish(global_control_channel, "STOP")
        logger.debug(f"Published STOP signal to global channel {global_control_channel}")
    except Exception as e:
        logger.error(f"Failed to publish STOP signal to global channel {global_control_channel}: {str(e)}")

    # Find all instances handling this agent run and send STOP to instance-specific channels
    try:
        instance_keys = await redis.keys(f"active_run:*:{agent_run_id}")
        logger.debug(f"Found {len(instance_keys)} active instance keys for agent run {agent_run_id}")

        for key in instance_keys:
            # Key format: active_run:{instance_id}:{agent_run_id}
            parts = key.split(":")
            if len(parts) == 3:
                instance_id_from_key = parts[1]
                instance_control_channel = f"agent_run:{agent_run_id}:control:{instance_id_from_key}"
                try:
                    await redis.publish(instance_control_channel, "STOP")
                    logger.debug(f"Published STOP signal to instance channel {instance_control_channel}")
                except Exception as e:
                    logger.warning(f"Failed to publish STOP signal to instance channel {instance_control_channel}: {str(e)}")
            else:
                 logger.warning(f"Unexpected key format found: {key}")

        # Clean up the response list immediately on stop/fail
        await _cleanup_redis_response_list(agent_run_id)

    except Exception as e:
        logger.error(f"Failed to find or signal active instances for {agent_run_id}: {str(e)}")

    logger.info(f"Successfully initiated stop process for agent run: {agent_run_id}")

# async def restore_running_agent_runs():
#     """Mark agent runs that were still 'running' in the database as failed and clean up Redis resources."""
#     logger.info("Restoring running agent runs after server restart")
#     client = await db.client
#     running_agent_runs = await client.table('agent_runs').select('id').eq("status", "running").execute()

#     for run in running_agent_runs.data:
#         agent_run_id = run['id']
#         logger.warning(f"Found running agent run {agent_run_id} from before server restart")

#         # Clean up Redis resources for this run
#         try:
#             # Clean up active run key
#             active_run_key = f"active_run:{instance_id}:{agent_run_id}"
#             await redis.delete(active_run_key)

#             # Clean up response list
#             response_list_key = f"agent_run:{agent_run_id}:responses"
#             await redis.delete(response_list_key)

#             # Clean up control channels
#             control_channel = f"agent_run:{agent_run_id}:control"
#             instance_control_channel = f"agent_run:{agent_run_id}:control:{instance_id}"
#             await redis.delete(control_channel)
#             await redis.delete(instance_control_channel)

#             logger.info(f"Cleaned up Redis resources for agent run {agent_run_id}")
#         except Exception as e:
#             logger.error(f"Error cleaning up Redis resources for agent run {agent_run_id}: {e}")

#         # Call stop_agent_run to handle status update and cleanup
#         await stop_agent_run(agent_run_id, error_message="Server restarted while agent was running")

async def check_for_active_project_agent_run(client, project_id: str):
    """
    Check if there is an active agent run for any thread in the given project.
    If found, returns the ID of the active run, otherwise returns None.
    """
    project_threads = await client.table('threads').select('thread_id').eq('project_id', project_id).execute()
    project_thread_ids = [t['thread_id'] for t in project_threads.data]

    if project_thread_ids:
        active_runs = await client.table('agent_runs').select('id').in_('thread_id', project_thread_ids).eq('status', 'running').execute()
        if active_runs.data and len(active_runs.data) > 0:
            return active_runs.data[0]['id']
    return None

async def get_agent_run_with_access_check(client, agent_run_id: str, user_id: str):
    """Get agent run data after verifying user access."""
    agent_run = await client.table('agent_runs').select('*').eq('id', agent_run_id).execute()
    if not agent_run.data:
        raise HTTPException(status_code=404, detail="Agent run not found")

    agent_run_data = agent_run.data[0]
    thread_id = agent_run_data['thread_id']
    await verify_thread_access(client, thread_id, user_id)
    return agent_run_data

@router.post("/thread/{thread_id}/agent/start")
async def start_agent(
    thread_id: str,
    request: Request,
    body: AgentStartRequest = Body(...),
    user_id: str = Depends(get_current_user_id_from_jwt)
):
    """Start an agent for a specific thread in the background."""
    global instance_id # Ensure instance_id is accessible
    if not instance_id:
        raise HTTPException(status_code=500, detail="Agent API not initialized with instance ID")

    # Use model from config if not specified in the request
    model_name = body.model_name
    logger.info(f"Original model_name from request: {model_name}")

    if model_name is None:
        model_name = config.MODEL_TO_USE
        logger.info(f"Using model from config: {model_name}")

    # Log the model name after alias resolution
    resolved_model = MODEL_NAME_ALIASES.get(model_name, model_name)
    logger.info(f"Resolved model name: {resolved_model}")

    # Update model_name to use the resolved version
    model_name = resolved_model

    logger.info(f"Starting new agent for thread: {thread_id} with config: model={model_name}, thinking={body.enable_thinking}, effort={body.reasoning_effort}, stream={body.stream}, context_manager={body.enable_context_manager} (Instance: {instance_id})")
    client = await db.client

    await verify_thread_access(client, thread_id, user_id)
    thread_result = await client.table('threads').select('project_id', 'account_id').eq('thread_id', thread_id).execute()
    if not thread_result.data:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread_data = thread_result.data[0]
    project_id = thread_data.get('project_id')
    account_id = thread_data.get('account_id')

    can_use, model_message, allowed_models = await can_use_model(client, account_id, model_name, request)
    if not can_use:
        raise HTTPException(status_code=403, detail={"message": model_message, "allowed_models": allowed_models})

    can_run, message, subscription = await check_billing_status(client, account_id, request)
    if not can_run:
        raise HTTPException(status_code=402, detail={"message": message, "subscription": subscription})

    active_run_id = await check_for_active_project_agent_run(client, project_id)
    if active_run_id:
        logger.info(f"Stopping existing agent run {active_run_id} for project {project_id}")
        await stop_agent_run(active_run_id)

    try:
        # Get project data to find sandbox ID
        project_result = await client.table('projects').select('*').eq('project_id', project_id).execute()
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = project_result.data[0]
        sandbox_info = project_data.get('sandbox', {})
        if not sandbox_info.get('id'):
            raise HTTPException(status_code=404, detail="No sandbox found for this project")
            
        sandbox_id = sandbox_info['id']
        sandbox = await get_or_start_sandbox(sandbox_id)
        logger.info(f"Successfully started sandbox {sandbox_id} for project {project_id}")
    except Exception as e:
        logger.error(f"Failed to start sandbox for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize sandbox: {str(e)}")

    agent_run = await client.table('agent_runs').insert({
        "thread_id": thread_id, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat()
    }).execute()
    agent_run_id = agent_run.data[0]['id']
    logger.info(f"Created new agent run: {agent_run_id}")

    # Register this run in Redis with TTL using instance ID
    instance_key = f"active_run:{instance_id}:{agent_run_id}"
    try:
        await redis.set(instance_key, "running", ex=redis.REDIS_KEY_TTL)
    except Exception as e:
        logger.warning(f"Failed to register agent run in Redis ({instance_key}): {str(e)}")

    # Check if we should bypass billing for x-app token users
    bypass_billing = request and is_x_app_token(request)
    
    # Run the agent in the background
    run_agent_background.send(
        agent_run_id=agent_run_id, thread_id=thread_id, instance_id=instance_id,
        project_id=project_id,
        model_name=model_name,  # Already resolved above
        enable_thinking=body.enable_thinking, reasoning_effort=body.reasoning_effort,
        stream=body.stream, enable_context_manager=body.enable_context_manager,
        bypass_billing=bypass_billing
    )

    return {"agent_run_id": agent_run_id, "status": "running"}

@router.post("/agent-run/{agent_run_id}/stop")
async def stop_agent(agent_run_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Stop a running agent."""
    logger.info(f"Received request to stop agent run: {agent_run_id}")
    client = await db.client
    await get_agent_run_with_access_check(client, agent_run_id, user_id)
    await stop_agent_run(agent_run_id)
    return {"status": "stopped"}

@router.get("/thread/{thread_id}/agent-runs")
async def get_agent_runs(thread_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get all agent runs for a thread."""
    logger.info(f"Fetching agent runs for thread: {thread_id}")
    client = await db.client
    await verify_thread_access(client, thread_id, user_id)
    agent_runs = await client.table('agent_runs').select('*').eq("thread_id", thread_id).order('created_at', desc=True).execute()
    logger.debug(f"Found {len(agent_runs.data)} agent runs for thread: {thread_id}")
    return {"agent_runs": agent_runs.data}

@router.get("/agent-run/{agent_run_id}")
async def get_agent_run(agent_run_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get agent run status and responses."""
    logger.info(f"Fetching agent run details: {agent_run_id}")
    client = await db.client
    agent_run_data = await get_agent_run_with_access_check(client, agent_run_id, user_id)
    # Note: Responses are not included here by default, they are in the stream or DB
    return {
        "id": agent_run_data['id'],
        "threadId": agent_run_data['thread_id'],
        "status": agent_run_data['status'],
        "startedAt": agent_run_data['started_at'],
        "completedAt": agent_run_data['completed_at'],
        "error": agent_run_data['error']
    }

@router.get("/agent-run/{agent_run_id}/stream")
async def stream_agent_run(
    agent_run_id: str,
    token: Optional[str] = None,
    request: Request = None
):
    """Stream the responses of an agent run using Redis Lists and Pub/Sub."""
    logger.info(f"Starting stream for agent run: {agent_run_id}")
    client = await db.client

    user_id = await get_user_id_from_stream_auth(request, token)
    agent_run_data = await get_agent_run_with_access_check(client, agent_run_id, user_id)

    response_list_key = f"agent_run:{agent_run_id}:responses"
    response_channel = f"agent_run:{agent_run_id}:new_response"
    control_channel = f"agent_run:{agent_run_id}:control" # Global control channel

    async def stream_generator():
        logger.debug(f"Streaming responses for {agent_run_id} using Redis list {response_list_key} and channel {response_channel}")
        last_processed_index = -1
        pubsub_response = None
        pubsub_control = None
        listener_task = None
        terminate_stream = False
        initial_yield_complete = False

        try:
            # 1. Fetch and yield initial responses from Redis list
            initial_responses_json = await redis.lrange(response_list_key, 0, -1)
            initial_responses = []
            if initial_responses_json:
                initial_responses = [json.loads(r) for r in initial_responses_json]
                logger.info(f"Sending {len(initial_responses)} initial responses for {agent_run_id}")
                for response in initial_responses:
                    yield f"data: {json.dumps(response)}\n\n"
                last_processed_index = len(initial_responses) - 1
            else:
                logger.info(f"No initial responses found in Redis for {agent_run_id}")
            initial_yield_complete = True

            # 2. Check run status *after* yielding initial data
            run_status = await client.table('agent_runs').select('status').eq("id", agent_run_id).maybe_single().execute()
            current_status = run_status.data.get('status') if run_status.data else None

            if current_status != 'running':
                logger.info(f"Agent run {agent_run_id} is not running (status: {current_status}). Ending stream.")
                yield f"data: {json.dumps({'type': 'status', 'status': 'completed'})}\n\n"
                return

            # 3. Set up Pub/Sub listeners for new responses and control signals
            pubsub_response = await redis.create_pubsub()
            await pubsub_response.subscribe(response_channel)
            logger.debug(f"Subscribed to response channel: {response_channel}")

            pubsub_control = await redis.create_pubsub()
            await pubsub_control.subscribe(control_channel)
            logger.debug(f"Subscribed to control channel: {control_channel}")

            # Queue to communicate between listeners and the main generator loop
            message_queue = asyncio.Queue()

            async def listen_messages():
                response_reader = pubsub_response.listen()
                control_reader = pubsub_control.listen()
                tasks = [asyncio.create_task(response_reader.__anext__()), asyncio.create_task(control_reader.__anext__())]

                while not terminate_stream:
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        try:
                            message = task.result()
                            if message and isinstance(message, dict) and message.get("type") == "message":
                                channel = message.get("channel")
                                data = message.get("data")
                                if isinstance(data, bytes): data = data.decode('utf-8')

                                if channel == response_channel and data == "new":
                                    await message_queue.put({"type": "new_response"})
                                elif channel == control_channel and data in ["STOP", "END_STREAM", "ERROR"]:
                                    logger.info(f"Received control signal '{data}' for {agent_run_id}")
                                    await message_queue.put({"type": "control", "data": data})
                                    return # Stop listening on control signal

                        except StopAsyncIteration:
                            logger.warning(f"Listener {task} stopped.")
                            # Decide how to handle listener stopping, maybe terminate?
                            await message_queue.put({"type": "error", "data": "Listener stopped unexpectedly"})
                            return
                        except Exception as e:
                            logger.error(f"Error in listener for {agent_run_id}: {e}")
                            await message_queue.put({"type": "error", "data": "Listener failed"})
                            return
                        finally:
                            # Reschedule the completed listener task
                            if task in tasks:
                                tasks.remove(task)
                                if message and isinstance(message, dict) and message.get("channel") == response_channel:
                                     tasks.append(asyncio.create_task(response_reader.__anext__()))
                                elif message and isinstance(message, dict) and message.get("channel") == control_channel:
                                     tasks.append(asyncio.create_task(control_reader.__anext__()))

                # Cancel pending listener tasks on exit
                for p_task in pending: p_task.cancel()
                for task in tasks: task.cancel()


            listener_task = asyncio.create_task(listen_messages())

            # 4. Main loop to process messages from the queue
            # Send a heartbeat message to confirm the stream is working
            yield f"data: {json.dumps({'type': 'heartbeat', 'message': 'Stream connected and waiting for responses'})}\n\n"
            
            while not terminate_stream:
                try:
                    # Add a timeout to the queue.get() to send periodic heartbeats
                    try:
                        queue_item = await asyncio.wait_for(message_queue.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        # Send heartbeat every 10 seconds if no messages
                        yield f"data: {json.dumps({'type': 'heartbeat', 'message': 'Waiting for agent responses...'})}\n\n"
                        continue

                    if queue_item["type"] == "new_response":
                        # Fetch new responses from Redis list starting after the last processed index
                        new_start_index = last_processed_index + 1
                        new_responses_json = await redis.lrange(response_list_key, new_start_index, -1)

                        if new_responses_json:
                            new_responses = [json.loads(r) for r in new_responses_json]
                            num_new = len(new_responses)
                            # logger.debug(f"Received {num_new} new responses for {agent_run_id} (index {new_start_index} onwards)")
                            for response in new_responses:
                                yield f"data: {json.dumps(response)}\n\n"
                                # Check if this response signals completion
                                if response.get('type') == 'status' and response.get('status') in ['completed', 'failed', 'stopped']:
                                    logger.info(f"Detected run completion via status message in stream: {response.get('status')}")
                                    terminate_stream = True
                                    break # Stop processing further new responses
                            last_processed_index += num_new
                        if terminate_stream: break

                    elif queue_item["type"] == "control":
                        control_signal = queue_item["data"]
                        terminate_stream = True # Stop the stream on any control signal
                        yield f"data: {json.dumps({'type': 'status', 'status': control_signal})}\n\n"
                        break

                    elif queue_item["type"] == "error":
                        logger.error(f"Listener error for {agent_run_id}: {queue_item['data']}")
                        terminate_stream = True
                        yield f"data: {json.dumps({'type': 'status', 'status': 'error'})}\n\n"
                        break

                except asyncio.CancelledError:
                     logger.info(f"Stream generator main loop cancelled for {agent_run_id}")
                     terminate_stream = True
                     break
                except Exception as loop_err:
                    logger.error(f"Error in stream generator main loop for {agent_run_id}: {loop_err}", exc_info=True)
                    terminate_stream = True
                    yield f"data: {json.dumps({'type': 'status', 'status': 'error', 'message': f'Stream failed: {loop_err}'})}\n\n"
                    break

        except Exception as e:
            logger.error(f"Error setting up stream for agent run {agent_run_id}: {e}", exc_info=True)
            # Only yield error if initial yield didn't happen
            if not initial_yield_complete:
                 yield f"data: {json.dumps({'type': 'status', 'status': 'error', 'message': f'Failed to start stream: {e}'})}\n\n"
        finally:
            terminate_stream = True
            # Graceful shutdown order: unsubscribe → close → cancel
            if pubsub_response: await pubsub_response.unsubscribe(response_channel)
            if pubsub_control: await pubsub_control.unsubscribe(control_channel)
            if pubsub_response: await pubsub_response.close()
            if pubsub_control: await pubsub_control.close()

            if listener_task:
                listener_task.cancel()
                try:
                    await listener_task  # Reap inner tasks & swallow their errors
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.debug(f"listener_task ended with: {e}")
            # Wait briefly for tasks to cancel
            await asyncio.sleep(0.1)
            logger.debug(f"Streaming cleanup complete for agent run: {agent_run_id}")

    return StreamingResponse(stream_generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "Connection": "keep-alive",
        "X-Accel-Buffering": "no", "Content-Type": "text/event-stream",
        "Access-Control-Allow-Origin": "*"
    })

async def generate_and_update_project_name(project_id: str, prompt: str):
    """Generates a project name using an LLM and updates the database."""
    logger.info(f"Starting background task to generate name for project: {project_id}")
    try:
        db_conn = DBConnection()
        client = await db_conn.client

        model_name = "openai/gpt-4o-mini"
        system_prompt = "You are a helpful assistant that generates extremely concise titles (2-4 words maximum) for chat threads based on the user's message. Respond with only the title, no other text or punctuation."
        user_message = f"Generate an extremely brief title (2-4 words only) for a chat thread that starts with this message: \"{prompt}\""
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]

        logger.debug(f"Calling LLM ({model_name}) for project {project_id} naming.")
        response = await make_llm_api_call(messages=messages, model_name=model_name, max_tokens=20, temperature=0.7)

        generated_name = None
        if response and response.get('choices') and response['choices'][0].get('message'):
            raw_name = response['choices'][0]['message'].get('content', '').strip()
            cleaned_name = raw_name.strip('\'" \n\t')
            if cleaned_name:
                generated_name = cleaned_name
                logger.info(f"LLM generated name for project {project_id}: '{generated_name}'")
            else:
                logger.warning(f"LLM returned an empty name for project {project_id}.")
        else:
            logger.warning(f"Failed to get valid response from LLM for project {project_id} naming. Response: {response}")

        if generated_name:
            update_result = await client.table('projects').update({"name": generated_name}).eq("project_id", project_id).execute()
            if hasattr(update_result, 'data') and update_result.data:
                logger.info(f"Successfully updated project {project_id} name to '{generated_name}'")
            else:
                logger.error(f"Failed to update project {project_id} name in database. Update result: {update_result}")
        else:
            logger.warning(f"No generated name, skipping database update for project {project_id}.")

    except Exception as e:
        logger.error(f"Error in background naming task for project {project_id}: {str(e)}\n{traceback.format_exc()}")
    finally:
        # No need to disconnect DBConnection singleton instance here
        logger.info(f"Finished background naming task for project: {project_id}")

@router.post("/agent/initiate", response_model=InitiateAgentResponse)
async def initiate_agent_with_files(
    request: Request,
    prompt: str = Form(...),
    model_name: Optional[str] = Form(None),  # Default to None to use config.MODEL_TO_USE
    enable_thinking: Optional[bool] = Form(False),
    reasoning_effort: Optional[str] = Form("low"),
    stream: Optional[bool] = Form(True),
    enable_context_manager: Optional[bool] = Form(False),
    files: List[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id_from_jwt)
):
    """Initiate a new agent session with optional file attachments."""
    global instance_id # Ensure instance_id is accessible
    if not instance_id:
        raise HTTPException(status_code=500, detail="Agent API not initialized with instance ID")

    # Use model from config if not specified in the request
    logger.info(f"Original model_name from request: {model_name}")

    if model_name is None:
        model_name = config.MODEL_TO_USE
        logger.info(f"Using model from config: {model_name}")

    # Log the model name after alias resolution
    resolved_model = MODEL_NAME_ALIASES.get(model_name, model_name)
    logger.info(f"Resolved model name: {resolved_model}")

    # Update model_name to use the resolved version
    model_name = resolved_model

    logger.info(f"[\033[91mDEBUG\033[0m] Initiating new agent with prompt and {len(files)} files (Instance: {instance_id}), model: {model_name}, enable_thinking: {enable_thinking}")
    client = await db.client
    
    # Ensure the user has a corresponding account in basejump.accounts
    account_id = await ensure_user_has_account(client, user_id)
    
    can_use, model_message, allowed_models = await can_use_model(client, account_id, model_name, request)
    if not can_use:
        raise HTTPException(status_code=403, detail={"message": model_message, "allowed_models": allowed_models})

    can_run, message, subscription = await check_billing_status(client, account_id, request)
    if not can_run:
        raise HTTPException(status_code=402, detail={"message": message, "subscription": subscription})

    try:
        # 1. Create Project
        placeholder_name = f"{prompt[:30]}..." if len(prompt) > 30 else prompt
        project = await client.table('projects').insert({
            "project_id": str(uuid.uuid4()), "account_id": account_id, "name": placeholder_name,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        project_id = project.data[0]['project_id']
        logger.info(f"Created new project: {project_id}")

        # 2. Create Thread
        thread = await client.table('threads').insert({
            "thread_id": str(uuid.uuid4()), "project_id": project_id, "account_id": account_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        thread_id = thread.data[0]['thread_id']
        logger.info(f"Created new thread: {thread_id}")

        # Trigger Background Naming Task
        asyncio.create_task(generate_and_update_project_name(project_id=project_id, prompt=prompt))

        # 3. Create Sandbox
        sandbox_pass = str(uuid.uuid4())
        sandbox = create_sandbox(sandbox_pass, project_id)
        sandbox_id = sandbox.id
        logger.info(f"Created new sandbox {sandbox_id} for project {project_id}")

        # Get preview links
        vnc_link = sandbox.get_preview_link(6080)
        website_link = sandbox.get_preview_link(8080)
        vnc_url = vnc_link.url if hasattr(vnc_link, 'url') else str(vnc_link).split("url='")[1].split("'")[0]
        website_url = website_link.url if hasattr(website_link, 'url') else str(website_link).split("url='")[1].split("'")[0]
        token = None
        if hasattr(vnc_link, 'token'):
            token = vnc_link.token
        elif "token='" in str(vnc_link):
            token = str(vnc_link).split("token='")[1].split("'")[0]

        # Update project with sandbox info
        update_result = await client.table('projects').update({
            'sandbox': {
                'id': sandbox_id, 'pass': sandbox_pass, 'vnc_preview': vnc_url,
                'sandbox_url': website_url, 'token': token
            }
        }).eq('project_id', project_id).execute()

        if not update_result.data:
            logger.error(f"Failed to update project {project_id} with new sandbox {sandbox_id}")
            raise Exception("Database update failed")

        # 4. Upload Files to Sandbox (if any)
        message_content = prompt
        if files:
            successful_uploads = []
            failed_uploads = []
            for file in files:
                if file.filename:
                    try:
                        safe_filename = file.filename.replace('/', '_').replace('\\', '_')
                        target_path = f"/workspace/{safe_filename}"
                        logger.info(f"Attempting to upload {safe_filename} to {target_path} in sandbox {sandbox_id}")
                        content = await file.read()
                        upload_successful = False
                        try:
                            if hasattr(sandbox, 'fs') and hasattr(sandbox.fs, 'upload_file'):
                                import inspect
                                if inspect.iscoroutinefunction(sandbox.fs.upload_file):
                                    await sandbox.fs.upload_file(target_path, content)
                                else:
                                    sandbox.fs.upload_file(target_path, content)
                                logger.debug(f"Called sandbox.fs.upload_file for {target_path}")
                                upload_successful = True
                            else:
                                raise NotImplementedError("Suitable upload method not found on sandbox object.")
                        except Exception as upload_error:
                            logger.error(f"Error during sandbox upload call for {safe_filename}: {str(upload_error)}", exc_info=True)

                        if upload_successful:
                            try:
                                await asyncio.sleep(0.2)
                                parent_dir = os.path.dirname(target_path)
                                files_in_dir = sandbox.fs.list_files(parent_dir)
                                file_names_in_dir = [f.name for f in files_in_dir]
                                if safe_filename in file_names_in_dir:
                                    successful_uploads.append(target_path)
                                    logger.info(f"Successfully uploaded and verified file {safe_filename} to sandbox path {target_path}")
                                else:
                                    logger.error(f"Verification failed for {safe_filename}: File not found in {parent_dir} after upload attempt.")
                                    failed_uploads.append(safe_filename)
                            except Exception as verify_error:
                                logger.error(f"Error verifying file {safe_filename} after upload: {str(verify_error)}", exc_info=True)
                                failed_uploads.append(safe_filename)
                        else:
                            failed_uploads.append(safe_filename)
                    except Exception as file_error:
                        logger.error(f"Error processing file {file.filename}: {str(file_error)}", exc_info=True)
                        failed_uploads.append(file.filename)
                    finally:
                        await file.close()

            if successful_uploads:
                message_content += "\n\n" if message_content else ""
                for file_path in successful_uploads: message_content += f"[Uploaded File: {file_path}]\n"
            if failed_uploads:
                message_content += "\n\nThe following files failed to upload:\n"
                for failed_file in failed_uploads: message_content += f"- {failed_file}\n"

        # 5. Add initial user message to thread
        message_id = str(uuid.uuid4())
        message_payload = {"role": "user", "content": message_content}
        await client.table('messages').insert({
            "message_id": message_id, "thread_id": thread_id, "type": "user",
            "is_llm_message": True, "content": json.dumps(message_payload),
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        # 6. Start Agent Run
        agent_run = await client.table('agent_runs').insert({
            "thread_id": thread_id, "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        agent_run_id = agent_run.data[0]['id']
        logger.info(f"Created new agent run: {agent_run_id}")

        # Register run in Redis
        instance_key = f"active_run:{instance_id}:{agent_run_id}"
        try:
            await redis.set(instance_key, "running", ex=redis.REDIS_KEY_TTL)
        except Exception as e:
            logger.warning(f"Failed to register agent run in Redis ({instance_key}): {str(e)}")

        # Check if we should bypass billing for x-app token users
        bypass_billing = request and is_x_app_token(request)
        
        # Run agent in background
        run_agent_background.send(
            agent_run_id=agent_run_id, thread_id=thread_id, instance_id=instance_id,
            project_id=project_id,
            model_name=model_name,  # Already resolved above
            enable_thinking=enable_thinking, reasoning_effort=reasoning_effort,
            stream=stream, enable_context_manager=enable_context_manager,
            bypass_billing=bypass_billing
        )

        return {"thread_id": thread_id, "agent_run_id": agent_run_id}

    except Exception as e:
        logger.error(f"Error in agent initiation: {str(e)}\n{traceback.format_exc()}")
        # TODO: Clean up created project/thread if initiation fails mid-way
        raise HTTPException(status_code=500, detail=f"Failed to initiate agent session: {str(e)}")

@router.get("/thread/{thread_id}/files/list")
async def list_thread_workspace_files(
    thread_id: str,
    path: str = "/workspace",
    user_id: str = Depends(get_current_user_id_from_jwt)
):
    """List files and directories in the thread's workspace at the specified path."""
    try:
        client = await db.client
        
        # Verify thread access
        await verify_thread_access(client, thread_id, user_id)
        
        # Get thread information to find project_id
        thread_result = await client.table('threads').select('project_id').eq('thread_id', thread_id).execute()
        if not thread_result.data:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        project_id = thread_result.data[0]['project_id']
        
        # Get project information to find sandbox_id
        project_result = await client.table('projects').select('sandbox').eq('project_id', project_id).execute()
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        sandbox_info = project_result.data[0].get('sandbox')
        if not sandbox_info or not sandbox_info.get('id'):
            raise HTTPException(status_code=404, detail="Sandbox not found for project")
        
        sandbox_id = sandbox_info['id']
        
        # Get the sandbox and list files
        sandbox = await get_or_start_sandbox(sandbox_id)
        
        try:
            # List files at the specified path
            files = sandbox.fs.list_files(path)
            result = []
            
            for file in files:
                # Convert file information to our model
                full_path = f"{path.rstrip('/')}/{file.name}" if path != '/' else f"/{file.name}"
                file_info = {
                    "name": file.name,
                    "path": full_path,
                    "is_dir": file.is_dir,
                    "size": file.size,
                    "mod_time": str(file.mod_time),
                    "permissions": getattr(file, 'permissions', None)
                }
                result.append(file_info)
            
            logger.info(f"Successfully listed {len(result)} files in thread {thread_id} workspace at path {path}")
            return {"files": result}
            
        except Exception as file_error:
            logger.error(f"Error listing files in thread {thread_id} workspace at path {path}: {str(file_error)}")
            raise HTTPException(status_code=404, detail=f"Path '{path}' not found in workspace")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing workspace files for thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list workspace files")

@router.get("/thread/{thread_id}/files/{filename:path}")
async def download_file_from_thread(
    thread_id: str,
    filename: str,
    user_id: str = Depends(get_current_user_id_from_jwt)
):
    """Download a file from the thread's project sandbox."""
    try:
        client = await db.client
        
        # Verify thread access
        await verify_thread_access(client, thread_id, user_id)
        
        # Get thread information to find project_id
        thread_result = await client.table('threads').select('project_id').eq('thread_id', thread_id).execute()
        if not thread_result.data:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        project_id = thread_result.data[0]['project_id']
        
        # Get project information to find sandbox_id
        project_result = await client.table('projects').select('sandbox').eq('project_id', project_id).execute()
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        sandbox_info = project_result.data[0].get('sandbox')
        if not sandbox_info or not sandbox_info.get('id'):
            raise HTTPException(status_code=404, detail="Sandbox not found for project")
        
        sandbox_id = sandbox_info['id']
        
        # Get the sandbox and download the file
        sandbox = await get_or_start_sandbox(sandbox_id)
        
        # Handle the file path - if it doesn't start with /workspace, prepend it
        if not filename.startswith('/workspace'):
            if filename.startswith('/'):
                file_path = f"/workspace{filename}"
            else:
                file_path = f"/workspace/{filename}"
        else:
            file_path = filename
        
        try:
            # Download file content from sandbox
            file_content = sandbox.fs.download_file(file_path)
            
            # Extract just the filename for the download header
            actual_filename = file_path.split('/')[-1]
            
            # Determine content type based on file extension
            content_type, _ = mimetypes.guess_type(actual_filename)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Return file as streaming response
            return Response(
                content=file_content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"attachment; filename={actual_filename}",
                    "Cache-Control": "no-cache"
                }
            )
            
        except Exception as file_error:
            logger.error(f"Error downloading file {file_path} from sandbox {sandbox_id}: {str(file_error)}")
            raise HTTPException(status_code=404, detail=f"File '{file_path}' not found in workspace")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file from thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download file")

@router.get("/threads")
async def get_threads(user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get all threads for the current user (supports X-app tokens)."""
    logger.info(f"Fetching threads for user: {user_id}")
    client = await db.client
    
    try:
        # Query threads filtered by account_id (user_id from X-app token)
        threads_result = await client.table('threads').select('*').eq('account_id', user_id).order('updated_at', desc=True).execute()
        
        if not threads_result.data:
            logger.info(f"No threads found for user: {user_id}")
            return []
        
        # Map database fields to ensure consistency with frontend Thread type
        mapped_threads = []
        for thread in threads_result.data:
            mapped_threads.append({
                "thread_id": thread['thread_id'],
                "account_id": thread['account_id'],
                "project_id": thread.get('project_id'),
                "is_public": thread.get('is_public', False),
                "created_at": thread['created_at'],
                "updated_at": thread['updated_at']
            })
        
        logger.info(f"Found {len(mapped_threads)} threads for user: {user_id}")
        return mapped_threads
        
    except Exception as e:
        logger.error(f"Error fetching threads for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch threads: {str(e)}")

@router.get("/projects")
async def get_projects(user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get all projects for the current user (supports X-app tokens)."""
    logger.info(f"Fetching projects for user: {user_id}")
    client = await db.client
    
    try:
        # Query projects filtered by account_id (user_id from X-app token)
        projects_result = await client.table('projects').select('*').eq('account_id', user_id).order('updated_at', desc=True).execute()
        
        if not projects_result.data:
            logger.info(f"No projects found for user: {user_id}")
            return []
        
        # Map database fields to ensure consistency with frontend Project type
        mapped_projects = []
        for project in projects_result.data:
            mapped_projects.append({
                "id": project['project_id'],
                "name": project.get('name', ''),
                "description": project.get('description', ''),
                "account_id": project['account_id'],
                "created_at": project['created_at'],
                "updated_at": project.get('updated_at'),
                "sandbox": project.get('sandbox', {}),
                "is_public": project.get('is_public', False)
            })
        
        logger.info(f"Found {len(mapped_projects)} projects for user: {user_id}")
        return mapped_projects
        
    except Exception as e:
        logger.error(f"Error fetching projects for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {str(e)}")

@router.get("/project/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get specific project details (supports X-app tokens)."""
    logger.info(f"Fetching project details for: {project_id}")
    client = await db.client
    
    try:
        # Get project data
        project_result = await client.table('projects').select('*').eq('project_id', project_id).single().execute()
        
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = project_result.data
        
        # Check if project is public or if user has access
        if not project.get('is_public'):
            account_id = project.get('account_id')
            if account_id:
                # Special case for x-api users: if the user_id matches the account_id directly,
                # they have access (this handles x-api users who own their own projects)
                if user_id != account_id:
                    # Check basejump account membership for regular users
                    account_user_result = await client.schema('basejump').from_('account_user').select('account_role').eq('user_id', user_id).eq('account_id', account_id).execute()
                    if not (account_user_result.data and len(account_user_result.data) > 0):
                        raise HTTPException(status_code=403, detail="Not authorized to access this project")
        
        # Map to consistent format
        mapped_project = {
            "id": project['project_id'],
            "name": project.get('name', ''),
            "description": project.get('description', ''),
            "account_id": project['account_id'],
            "created_at": project['created_at'],
            "updated_at": project.get('updated_at'),
            "sandbox": project.get('sandbox', {}),
            "is_public": project.get('is_public', False)
        }
        
        return mapped_project
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch project: {str(e)}")

@router.patch("/project/{project_id}")
async def update_project(
    project_id: str, 
    request: ProjectUpdateRequest,
    user_id: str = Depends(get_current_user_id_from_jwt)
):
    """Update project details (supports X-app tokens)."""
    logger.info(f"Updating project: {project_id} with name: {request.name}")
    client = await db.client
    
    try:
        # First verify the project exists and user has access
        project_result = await client.table('projects').select('*').eq('project_id', project_id).single().execute()
        
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = project_result.data
        
        # Check if project is public or if user has access
        if not project.get('is_public'):
            account_id = project.get('account_id')
            if account_id:
                # Special case for x-api users: if the user_id matches the account_id directly,
                # they have access (this handles x-api users who own their own projects)
                if user_id != account_id:
                    # Check basejump account membership for regular users
                    account_user_result = await client.schema('basejump').from_('account_user').select('account_role').eq('user_id', user_id).eq('account_id', account_id).execute()
                    if not (account_user_result.data and len(account_user_result.data) > 0):
                        raise HTTPException(status_code=403, detail="Not authorized to access this project")

        # Update the project name
        update_result = await client.table('projects').update({
            "name": request.name,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("project_id", project_id).execute()
        
        if not update_result.data:
            raise HTTPException(status_code=400, detail="Failed to update project")
        
        updated_project = update_result.data[0]
        
        # Map to consistent format
        mapped_project = {
            "id": updated_project['project_id'],
            "name": updated_project.get('name', ''),
            "description": updated_project.get('description', ''),
            "account_id": updated_project['account_id'],
            "created_at": updated_project['created_at'],
            "updated_at": updated_project.get('updated_at'),
            "sandbox": updated_project.get('sandbox', {}),
            "is_public": updated_project.get('is_public', False)
        }
        
        logger.info(f"Successfully updated project {project_id} name to '{request.name}'")
        return mapped_project
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update project: {str(e)}")

@router.get("/thread/{thread_id}")
async def get_thread(thread_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get specific thread details (supports X-app tokens)."""
    logger.info(f"Fetching thread details for: {thread_id}")
    client = await db.client
    
    try:
        # Verify thread access
        await verify_thread_access(client, thread_id, user_id)
        
        # Get thread data
        thread_result = await client.table('threads').select('*').eq('thread_id', thread_id).single().execute()
        
        if not thread_result.data:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        thread = thread_result.data
        
        # Map to consistent format
        mapped_thread = {
            "thread_id": thread['thread_id'],
            "account_id": thread['account_id'],
            "project_id": thread.get('project_id'),
            "is_public": thread.get('is_public', False),
            "created_at": thread['created_at'],
            "updated_at": thread['updated_at']
        }
        
        return mapped_thread
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch thread: {str(e)}")

@router.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Delete a thread and all associated data (supports X-app tokens)."""
    logger.info(f"Deleting thread: {thread_id}")
    client = await db.client
    
    try:
        # Verify thread access
        await verify_thread_access(client, thread_id, user_id)
        
        # Delete thread (cascade will handle messages and agent_runs)
        delete_result = await client.table('threads').delete().eq('thread_id', thread_id).execute()
        
        if not delete_result.data:
            raise HTTPException(status_code=404, detail="Thread not found or already deleted")
        
        logger.info(f"Successfully deleted thread: {thread_id}")
        return {"message": "Thread deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete thread: {str(e)}")

@router.get("/thread/{thread_id}/messages")
async def get_messages(thread_id: str, user_id: str = Depends(get_current_user_id_from_jwt)):
    """Get all messages for a thread (supports X-app tokens)."""
    logger.info(f"Fetching messages for thread: {thread_id}")
    client = await db.client
    
    try:
        # Verify thread access
        await verify_thread_access(client, thread_id, user_id)
        
        # Get messages directly from the table to match the original Supabase format
        # This returns the raw database format that the frontend expects
        messages_result = await client.table('messages').select('*').eq('thread_id', thread_id).neq('type', 'cost').neq('type', 'summary').order('created_at', desc=False).execute()
        
        if not messages_result.data:
            logger.info(f"No messages found for thread: {thread_id}")
            return []
        
        logger.info(f"Found {len(messages_result.data)} messages for thread: {thread_id}")
        return messages_result.data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching messages for thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")

@router.post("/thread/{thread_id}/messages")
async def add_message(
    thread_id: str, 
    message_data: dict,
    user_id: str = Depends(get_current_user_id_from_jwt)
):
    """Add a message to a thread (supports X-app tokens)."""
    logger.info(f"Adding message to thread: {thread_id}")
    client = await db.client
    
    try:
        # Verify thread access
        await verify_thread_access(client, thread_id, user_id)
        
        # Extract content and type from the request
        content = message_data.get('content', '')
        message_type = message_data.get('type', 'user')
        
        if not content:
            raise HTTPException(status_code=400, detail="Message content is required")
        
        # Format the message in the format the LLM expects
        message_payload = {
            "role": message_type,
            "content": content,
        }
        
        # Insert the message into the messages table
        message_id = str(uuid.uuid4())
        insert_result = await client.table('messages').insert({
            "message_id": message_id,
            "thread_id": thread_id,
            "type": message_type,
            "is_llm_message": True,
            "content": json.dumps(message_payload),
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        # Check if the insert was successful by looking at the data
        if not insert_result.data:
            logger.error(f"Error inserting message: No data returned from insert")
            raise HTTPException(status_code=500, detail="Failed to add message")
        
        logger.info(f"Successfully added message to thread {thread_id}")
        return {"message": "Message added successfully", "message_id": message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding message to thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add message: {str(e)}")

async def ensure_user_has_account(client, user_id: str) -> str:
    """
    Ensure that a user has a corresponding account in basejump.accounts.
    For x-api users, this creates a personal account if it doesn't exist.
    Returns the account_id to use.
    """
    logger.info(f"[DEBUG] ensure_user_has_account called for user_id: {user_id}")
    try:
        # First, check if the user already has an account
        logger.info(f"[DEBUG] Checking if account exists for user_id: {user_id}")
        account_result = await client.schema('basejump').from_('accounts').select('id').eq('id', user_id).execute()
        print("account_result", account_result)
        if account_result.data and len(account_result.data) > 0:
            logger.info(f"[DEBUG] Account already exists for user {user_id}")
            return user_id
        
        logger.info(f"[DEBUG] No account found for user {user_id}, creating one...")
        
        # First, check if we already have an auth user for this x-api user
        logger.info(f"[DEBUG] Checking for existing auth user for x-api user {user_id}")
        created_user_id = user_id  # Default to original user_id
        
        try:
            # Try to find existing auth user with this x_api_user_id in metadata
            logger.info(f"[DEBUG] Searching for existing auth user with x_api_user_id: {user_id}")
            users_result = await client.auth.admin.list_users()
            
            # list_users() returns a list directly, not an object with .users attribute
            if users_result and isinstance(users_result, list):
                for user in users_result:
                    user_metadata = getattr(user, 'user_metadata', {}) or {}
                    if user_metadata.get('x_api_user_id') == user_id:
                        created_user_id = user.id
                        logger.info(f"[DEBUG] Found existing auth user for x-api user {user_id}: {created_user_id}")
                        break
                else:
                    # No existing user found, create a new one
                    logger.info(f"[DEBUG] No existing auth user found, creating new one for x-api user {user_id}")
                    import time
                    timestamp = int(time.time())
                    unique_email = f"x-api-user-{user_id}-{timestamp}@placeholder.com"
                    
                    user_create_result = await client.auth.admin.create_user({
                        "email": unique_email,
                        "email_confirm": True,
                        "user_metadata": {"source": "x-api", "x_api_user_id": user_id},
                        "app_metadata": {"provider": "x-api", "providers": ["x-api"]}
                    })
                    
                    if user_create_result.user:
                        created_user_id = user_create_result.user.id
                        logger.info(f"[DEBUG] Successfully created new auth user with email {unique_email}: {created_user_id}")
                    else:
                        logger.warning(f"[DEBUG] User creation returned no user object, but no error. Proceeding with original user_id...")
            else:
                logger.warning(f"[DEBUG] list_users() returned unexpected format: {type(users_result)}")
            
        except Exception as e:
            # If anything fails, log the error but continue with original user_id
            logger.error(f"[DEBUG] Error checking/creating auth user: {str(e)}")
            logger.warning(f"[DEBUG] Proceeding with original user_id as created_user_id")
        
        # Now create the account in basejump.accounts using the created user ID
        logger.info(f"[DEBUG] Creating account in basejump.accounts with account_id={user_id} and primary_owner_user_id={created_user_id}")
        try:
            account_insert_result = await client.schema('basejump').from_('accounts').insert({
                'id': user_id,  # Keep original user_id as account_id for consistency
                'primary_owner_user_id': created_user_id,  # Use the actual created user ID
                'name': 'Personal Account',
                'personal_account': True
            }).execute()
            
            if account_insert_result.error:
                logger.error(f"[DEBUG] Error creating account: {account_insert_result.error}")
                raise Exception(f"Failed to create account: {account_insert_result.error}")
            
            logger.info(f"[DEBUG] Successfully created account for user {user_id}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Exception during account creation: {str(e)}")
            raise Exception(f"Failed to create account: {str(e)}")
        
        # Add user to account_user table
        logger.info(f"[DEBUG] Adding user {created_user_id} to account_user table for account {user_id}")
        try:
            account_user_result = await client.schema('basejump').from_('account_user').insert({
                'user_id': created_user_id,  # Use the actual created user ID
                'account_id': user_id,  # Use original user_id as account_id
                'account_role': 'owner'
            }).execute()
            
            if account_user_result.error:
                logger.warning(f"[DEBUG] Error adding user to account_user table: {account_user_result.error}")
            else:
                logger.info(f"[DEBUG] Successfully added user to account_user table")
                
        except Exception as e:
            logger.warning(f"[DEBUG] Exception adding user to account_user table: {str(e)}")
        
        logger.info(f"[DEBUG] Successfully set up account for user {user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"[DEBUG] Exception in ensure_user_has_account for user {user_id}: {str(e)}")
        # If account creation fails, we can still try to use the user_id as account_id
        # This maintains backward compatibility
        return user_id

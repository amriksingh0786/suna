from daytona_sdk import Daytona, DaytonaConfig, CreateSandboxParams, Sandbox, SessionExecuteRequest
from daytona_api_client.models.workspace_state import WorkspaceState
from dotenv import load_dotenv
from utils.logger import logger
from utils.config import config
from utils.config import Configuration
import time
import asyncio

load_dotenv()

logger.debug("Initializing Daytona sandbox configuration")
daytona_config = DaytonaConfig(
    api_key=config.DAYTONA_API_KEY,
    server_url=config.DAYTONA_SERVER_URL,
    target=config.DAYTONA_TARGET
)

if daytona_config.api_key:
    logger.debug("Daytona API key configured successfully")
else:
    logger.warning("No Daytona API key found in environment variables")

if daytona_config.server_url:
    logger.debug(f"Daytona server URL set to: {daytona_config.server_url}")
else:
    logger.warning("No Daytona server URL found in environment variables")

if daytona_config.target:
    logger.debug(f"Daytona target set to: {daytona_config.target}")
else:
    logger.warning("No Daytona target found in environment variables")

daytona = Daytona(daytona_config)
logger.debug("Daytona client initialized")

async def get_or_start_sandbox(sandbox_id: str):
    """Retrieve a sandbox by ID, check its state, and start it if needed."""
    
    logger.info(f"Getting or starting sandbox with ID: {sandbox_id}")
    
    try:
        sandbox = daytona.get_current_sandbox(sandbox_id)
        
        # Check if sandbox needs to be started
        if sandbox.instance.state == WorkspaceState.ARCHIVED or sandbox.instance.state == WorkspaceState.STOPPED:
            logger.info(f"Sandbox is in {sandbox.instance.state} state. Starting...")
            try:
                daytona.start(sandbox)
                # Wait a moment for the sandbox to initialize
                # sleep(5)
                # Refresh sandbox state after starting
                sandbox = daytona.get_current_sandbox(sandbox_id)
                
                # Start supervisord in a session when restarting
                start_supervisord_session(sandbox)
            except Exception as e:
                logger.error(f"Error starting sandbox: {e}")
                raise e
        
        logger.info(f"Sandbox {sandbox_id} is ready")
        return sandbox
        
    except Exception as e:
        logger.error(f"Error retrieving or starting sandbox: {str(e)}")
        raise e

def start_supervisord_session(sandbox: Sandbox):
    """Start supervisord in a session with better error handling."""
    session_id = "supervisord-session"
    try:
        logger.info(f"Creating session {session_id} for supervisord")
        sandbox.process.create_session(session_id)
        
        # Execute supervisord command
        sandbox.process.execute_session_command(session_id, SessionExecuteRequest(
            command="exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf",
            var_async=True
        ))
        logger.info(f"Supervisord started successfully in session {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error starting supervisord session: {str(e)}")
        logger.warning("Supervisord failed to start - sandbox can still be used manually")
        # Don't raise the exception - let the sandbox creation succeed
        return False

def create_sandbox(password: str, project_id: str = None, timeout: int = None, max_retries: int = None):
    """
    Create a new sandbox with all required services configured and running.
    
    Args:
        password: VNC password for the sandbox
        project_id: Optional project ID for labeling
        timeout: Timeout in seconds for sandbox creation (default from config)
        max_retries: Maximum number of retry attempts (default from config)
    """
    
    # Use config defaults if not provided
    if timeout is None:
        timeout = config.SANDBOX_CREATION_TIMEOUT
    if max_retries is None:
        max_retries = config.SANDBOX_MAX_RETRIES
    
    logger.info(f"Creating new Daytona sandbox environment (timeout: {timeout}s, max_retries: {max_retries})")
    logger.debug("Configuring sandbox with browser-use image and environment variables")
    
    labels = None
    if project_id:
        logger.debug(f"Using sandbox_id as label: {project_id}")
        labels = {'id': project_id}
        
    params = CreateSandboxParams(
        image=Configuration.SANDBOX_IMAGE_NAME,
        public=True,
        labels=labels,
        env_vars={
            "CHROME_PERSISTENT_SESSION": "true",
            "RESOLUTION": "1024x768x24",
            "RESOLUTION_WIDTH": "1024",
            "RESOLUTION_HEIGHT": "768",
            "VNC_PASSWORD": password,
            "ANONYMIZED_TELEMETRY": "false",
            "CHROME_PATH": "",
            "CHROME_USER_DATA": "",
            "CHROME_DEBUGGING_PORT": "9222",
            "CHROME_DEBUGGING_HOST": "localhost",
            "CHROME_CDP": ""
        },
        resources={
            "cpu": 2,
            "memory": 4,
            "disk": 5,
        }
    )
    
    # Attempt to create the sandbox with retries
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Sandbox creation attempt {attempt + 1}/{max_retries + 1}")
            start_time = time.time()
            
            # Create the sandbox with extended timeout
            sandbox = daytona.create(params)
            
            creation_time = time.time() - start_time
            logger.info(f"Sandbox created successfully with ID: {sandbox.id} (took {creation_time:.2f}s)")
            
            # Start supervisord in a session for new sandbox
            try:
                start_supervisord_session(sandbox)
                logger.info("Sandbox environment successfully initialized")
                return sandbox
            except Exception as supervisord_error:
                logger.warning(f"Failed to start supervisord but sandbox created: {supervisord_error}")
                # Return sandbox even if supervisord fails - it can be started later
                return sandbox
                
        except Exception as e:
            last_error = e
            elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
            
            logger.error(f"Sandbox creation attempt {attempt + 1} failed after {elapsed_time:.2f}s: {str(e)}")
            
            if "timeout" in str(e).lower() or "TimeoutError" in str(type(e).__name__):
                logger.warning(f"Timeout detected during sandbox creation (attempt {attempt + 1})")
            
            # If this was the last attempt, raise the error
            if attempt == max_retries:
                logger.error(f"All {max_retries + 1} sandbox creation attempts failed")
                break
            
            # Wait before retry (exponential backoff)
            wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s...
            logger.info(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    
    # If we get here, all attempts failed
    error_msg = f"Failed to create sandbox after {max_retries + 1} attempts. Last error: {last_error}"
    logger.error(error_msg)
    raise Exception(error_msg)


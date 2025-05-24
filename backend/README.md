# Suna Backend

## Running the backend

Within the backend directory, run the following command to stop and start the backend:

```bash
docker compose down && docker compose up --build
```

## Running Individual Services

You can run individual services from the docker-compose file. This is particularly useful during development:

### Running only Redis and RabbitMQ

```bash
docker compose up redis rabbitmq
```

### Running only the API and Worker

```bash
docker compose up api worker
```

## Development Setup

For local development, you might only need to run Redis and RabbitMQ, while working on the API locally. This is useful when:

- You're making changes to the API code and want to test them directly
- You want to avoid rebuilding the API container on every change
- You're running the API service directly on your machine

To run just Redis and RabbitMQ for development:

````bash
docker compose up redis rabbitmq

Then you can run your API service locally with the following commands

```sh
# On one terminal
cd backend
poetry run python3.11 api.py

# On another terminal
cd frontend
poetry run python3.11 -m dramatiq run_agent_background
````

### Environment Configuration

When running services individually, make sure to:

1. Check your `.env` file and adjust any necessary environment variables
2. Ensure Redis connection settings match your local setup (default: `localhost:6379`)
3. Ensure RabbitMQ connection settings match your local setup (default: `localhost:5672`)
4. Update any service-specific environment variables if needed

### Important: Redis Host Configuration

When running the API locally with Redis in Docker, you need to set the correct Redis host in your `.env` file:

- For Docker-to-Docker communication (when running both services in Docker): use `REDIS_HOST=redis`
- For local-to-Docker communication (when running API locally): use `REDIS_HOST=localhost`

### Important: RabbitMQ Host Configuration

When running the API locally with Redis in Docker, you need to set the correct RabbitMQ host in your `.env` file:

- For Docker-to-Docker communication (when running both services in Docker): use `RABBITMQ_HOST=rabbitmq`
- For local-to-Docker communication (when running API locally): use `RABBITMQ_HOST=localhost`

Example `.env` configuration for local development:

```sh
REDIS_HOST=localhost (instead of 'redis')
REDIS_PORT=6379
REDIS_PASSWORD=

RABBITMQ_HOST=localhost (instead of 'rabbitmq')
RABBITMQ_PORT=5672
```

## Troubleshooting

### RabbitMQ Queue Configuration Issues

If you encounter the error:

```
PRECONDITION_FAILED - inequivalent arg 'x-dead-letter-exchange' for queue 'default' in vhost '/': received the value '' of type 'longstr' but current is none
```

This indicates a conflict with existing RabbitMQ queue configurations. To fix this:

1. **Stop all services:**

   ```bash
   docker-compose down
   ```

2. **Clear RabbitMQ data:**

   ```bash
   docker volume rm backend_rabbitmq_data
   ```

3. **Or run the queue fix script:**

   ```bash
   python fix_rabbitmq_queue.py
   ```

4. **Restart services:**
   ```bash
   docker-compose up -d
   ```

The updated configuration now uses a dedicated queue name (`agent_tasks`) to avoid conflicts with the default queue.

### Sandbox Creation Timeout Issues

If you encounter Daytona sandbox creation timeouts like:

```
DaytonaError: Failed to create sandbox: Failed to create and start sandbox within 60 seconds timeout period.
```

This indicates the Daytona service is slow or overloaded. Here's how to diagnose and fix:

1. **Run the sandbox health check:**

   ```bash
   python sandbox/health_check.py
   ```

2. **Check Daytona service status:**

   - Verify your Daytona server is running and accessible
   - Check network connectivity to the Daytona server
   - Monitor server load and resources

3. **Adjust timeout settings:**

   You can increase the timeout in your `.env` file:

   ```bash
   SANDBOX_CREATION_TIMEOUT=300  # 5 minutes
   SANDBOX_MAX_RETRIES=3
   ```

### Dramatiq AsyncIO Configuration Issues

If you encounter errors like:

```
RuntimeError: Global event loop thread not set. Have you added the AsyncIO middleware to your middleware stack?
```

This has been **automatically fixed** in the current configuration. The RabbitMQ broker now includes the required AsyncIO middleware:

- ✅ **AsyncIO middleware** is properly configured for async function support
- ✅ **Custom queue name** (`agent_tasks`) prevents conflicts with default queues
- ✅ **Retry logic** with exponential backoff for failed tasks
- ✅ **Proper error handling** for both sync and async tasks

## Fixed Issues Summary

This codebase has been updated to resolve the following critical issues:

### 1. **RabbitMQ Queue Configuration Conflicts** ✅ FIXED

- **Problem**: `PRECONDITION_FAILED` errors due to conflicting dead letter exchange settings
- **Solution**: Implemented dedicated queue naming and proper broker configuration
- **Files Changed**: `run_agent_background.py`, `fix_rabbitmq_queue.py`

### 2. **Dramatiq AsyncIO Middleware Missing** ✅ FIXED

- **Problem**: `RuntimeError: Global event loop thread not set` when running async tasks
- **Solution**: Added AsyncIO middleware to RabbitMQ broker configuration
- **Files Changed**: `run_agent_background.py`

### 3. **Sandbox Creation Timeout Handling** ✅ IMPROVED

- **Problem**: 60-second timeout insufficient for sandbox creation
- **Solution**: Configurable timeouts, retry logic, and better error handling
- **Files Changed**: `sandbox/sandbox.py`, `utils/config.py`, `agent/api.py`

### 4. **Background Task Function Signature Issues** ✅ FIXED

- **Problem**: Function parameter mismatches and incorrect async/sync handling
- **Solution**: Unified function signatures and proper async task decoration
- **Files Changed**: `run_agent_background.py`, `agent/api.py`

## Verification

To verify all fixes are working:

```bash
# Test RabbitMQ broker configuration
poetry run python -c "from run_agent_background import rabbitmq_broker; print('✓ RabbitMQ broker configured')"

# Test sandbox health (requires Daytona credentials)
poetry run python sandbox/health_check.py

# Start the Dramatiq worker (in production)
poetry run python -m dramatiq run_agent_background

# Or run the full application
poetry run python main.py
```

All critical issues have been resolved and the system should now operate without the previously encountered errors.

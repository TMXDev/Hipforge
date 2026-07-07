import os
import sys
import signal
import asyncio
import logging
from app.config.settings import settings
import app.redis.client
from app.redis.keys import pending_queue_key, active_queue_key
import json
from app.workflow_engine.state_machine import WorkflowEngine
from app.workflow_engine.context import WorkflowContext

# Setup logging based on settings
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("migration_worker")

# Flag to control the infinite worker loop
running = True

def handle_shutdown(sig, frame):
    """Signal handler to trigger a graceful shutdown."""
    global running
    logger.info(f"Shutdown signal {sig} received. Preparing to stop worker gracefully after the current task finishes...")
    running = False

def register_signals():
    """Registers handlers for SIGINT, SIGTERM, and Windows SIGBREAK."""
    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        if sys.platform == "win32":
            signal.signal(signal.SIGBREAK, handle_shutdown)
    except ValueError as e:
        logger.warning(f"Could not register signal handlers (this is expected in some environments): {e}")

async def worker_heartbeat_loop():
    """Periodically writes worker heartbeat in Redis."""
    from app.redis.client import redis_client
    while running:
        try:
            await redis_client.setex("worker:heartbeat", 15, "active")
        except Exception as e:
            logger.debug(f"Failed to write worker heartbeat: {e}")
        await asyncio.sleep(5)

async def run_worker():
    """Main worker consumption and execution loop."""
    global running
    brpop_timeout = int(os.getenv("MIGRATION_WORKER_TIMEOUT", "5"))
    logger.info(f"Migration Worker starting loop with BRPOP timeout={brpop_timeout}s...")
    
    register_signals()
    
    heartbeat_task = asyncio.create_task(worker_heartbeat_loop())
    try:
        while running:
            try:
                # Step 1: Dequeue a job from the pending queue (blocks until job or timeout)
                result = await app.redis.client.redis_client.brpop(pending_queue_key(), timeout=brpop_timeout)
            except Exception as e:
                logger.warning(f"Error during BRPOP from Redis: {e}")
                await asyncio.sleep(1)
                continue

            if result is None:
                continue
                
            _, value = result
            payload = json.loads(value)
            migration_id = payload.get("migration_id")
            logger.info(f"Dequeued migration job: {migration_id}")
            
            # Step 2: Mark the job as active
            await app.redis.client.redis_client.lpush(active_queue_key(), migration_id)
            
            # Step 3: Execute the workflow engine
            try:
                workspace_path = payload.get("workspace_path")
                retry_budget = payload.get("retry_budget", settings.DEFAULT_RETRY_BUDGET)
                
                context = WorkflowContext(
                    migration_id=migration_id,
                    workspace_path=workspace_path,
                    retry_budget=retry_budget
                )
                from app.redis.keys import metadata_key
                try:
                    metadata = await app.redis.client.redis_client.hgetall(metadata_key(migration_id))
                    target_arch = metadata.get("target_architecture") if isinstance(metadata, dict) else None
                    if target_arch:
                        context.target_gpu_architecture = target_arch
                except Exception as exc:
                    logger.warning(f"Failed to read migration metadata in worker: {exc}")
                if payload.get("test_mode"):
                    context.compilation_success = True
                engine = WorkflowEngine(context)
                
                logger.info(f"Running Workflow Engine for job: {migration_id}")
                await engine.run()
                logger.info(f"Workflow Engine finished executing job: {migration_id}")
                
            except Exception as e:
                logger.exception(f"Unhandled exception during Workflow Engine execution for job {migration_id}: {e}")
                
                # In case of workflow engine failure, update status to FAILED and broadcast transition
                from app.redis.keys import status_key
                from app.redis.keys import events_channel
                from datetime import datetime, timezone
                try:
                    await app.redis.client.redis_client.set(status_key(migration_id), "FAILED")
                    timestamp = datetime.now(timezone.utc).isoformat()
                    event_payload = {
                        "type": "event",
                        "migration_id": migration_id,
                        "timestamp": timestamp,
                        "stage": "WORKER",
                        "status": "failed",
                        "message": f"Job aborted due to unhandled worker error: {str(e)}",
                        "state": "WORKER",
                        "details": f"Job aborted due to unhandled worker error: {str(e)}"
                    }
                    await app.redis.client.redis_client.publish(events_channel(migration_id), json.dumps(event_payload))
                except Exception as redis_err:
                    logger.error(f"Failed to report worker crash to Redis for job {migration_id}: {redis_err}")
                    
            finally:
                # Step 4: Ensure mark_done always runs to clean up the active job list
                logger.info(f"Cleaning up active job status for: {migration_id}")
                await app.redis.client.redis_client.lrem(active_queue_key(), 0, migration_id)
                
    except asyncio.CancelledError:
        logger.info("Worker task has been cancelled.")
    except Exception as e:
        logger.exception(f"Error encountered in worker main loop: {e}")
        # Sleep briefly to avoid tight loop on Redis connection issues
        await asyncio.sleep(1)
    finally:
        heartbeat_task.cancel()

def main():
    """Synchronous entrypoint for python execution."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Fatal exception crashed the worker: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

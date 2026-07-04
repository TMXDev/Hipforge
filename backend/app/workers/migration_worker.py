import os
import sys
import signal
import asyncio
import logging
from app.config.settings import settings
from app.redis.manager import dequeue_job, mark_active, mark_done
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

async def run_worker():
    """Main worker consumption and execution loop."""
    global running
    brpop_timeout = int(os.getenv("MIGRATION_WORKER_TIMEOUT", "5"))
    logger.info(f"Migration Worker starting loop with BRPOP timeout={brpop_timeout}s...")
    
    register_signals()
    
    while running:
        try:
            # Step 1: Dequeue a job from the pending queue (blocks until job or timeout)
            job = await dequeue_job(timeout=brpop_timeout)
            if job is None:
                continue
                
            migration_id, payload = job
            logger.info(f"Dequeued migration job: {migration_id}")
            
            # Step 2: Mark the job as active
            await mark_active(migration_id)
            
            # Step 3: Execute the workflow engine
            try:
                workspace_path = payload.get("workspace_path")
                retry_budget = payload.get("retry_budget", settings.DEFAULT_RETRY_BUDGET)
                
                context = WorkflowContext(
                    migration_id=migration_id,
                    workspace_path=workspace_path,
                    retry_budget=retry_budget
                )
                if payload.get("test_mode"):
                    context.compilation_success = True
                engine = WorkflowEngine(context)
                
                logger.info(f"Running Workflow Engine for job: {migration_id}")
                await engine.run()
                logger.info(f"Workflow Engine finished executing job: {migration_id}")
                
            except Exception as e:
                logger.exception(f"Unhandled exception during Workflow Engine execution for job {migration_id}: {e}")
                
                # In case of workflow engine failure, update status to FAILED and broadcast transition
                from app.redis.client import redis_client
                from app.redis.keys import status_key
                from app.redis.publisher import publish_event
                try:
                    await redis_client.set(status_key(migration_id), "FAILED")
                    await publish_event(
                        migration_id=migration_id,
                        stage="WORKER",
                        status="failed",
                        message=f"Job aborted due to unhandled worker error: {str(e)}"
                    )
                except Exception as redis_err:
                    logger.error(f"Failed to report worker crash to Redis for job {migration_id}: {redis_err}")
                    
            finally:
                # Step 4: Ensure mark_done always runs to clean up the active job list
                logger.info(f"Cleaning up active job status for: {migration_id}")
                await mark_done(migration_id)
                
        except asyncio.CancelledError:
            logger.info("Worker task has been cancelled.")
            break
        except Exception as e:
            logger.exception(f"Error encountered in worker main loop: {e}")
            # Sleep briefly to avoid tight loop on Redis connection issues
            await asyncio.sleep(1)

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

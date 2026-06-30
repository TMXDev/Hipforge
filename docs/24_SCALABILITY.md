# 24_SCALABILITY.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the scalability strategy and concurrency model for HIPForge. It specifies how the platform manages multi-user compilation workloads, avoids system lockups under heavy utilization, routes tasks via a queue, and maps out paths for enterprise scaling in Kubernetes environments.

---

# Goals

The scalability architecture must:

- Maintain web server responsiveness under heavy parallel upload and compilation request loads.
- Isolate compilation and translation execution (CPU and GPU intensive processes) from API processes.
- Implement a queue-based task distribution system using minimal dependencies.
- Define a worker model that allows horizontal scaling across multiple instances or GPUs.
- Outline the transition path to enterprise container workflow_engine (Kubernetes) and autoscaling.

---

# Core Concurrency Model: Redis-backed Migration Worker

Instead of compiling C++/CUDA/HIP code directly inside the web backend thread, HIPForge employs an asynchronous worker pattern leveraging Redis as a lightweight broker.

```
                  ┌───────────────────────┐
                  │   Next.js Frontend    │
                  └───────────┬───────────┘
                              │ HTTP / WS
                              ▼
                  ┌───────────────────────┐
                  │    FastAPI Backend    │
                  └───────────┬───────────┘
                              │ LPUSH
                              ▼
                  ┌───────────────────────┐
                  │ Redis Queue (pending) │
                  └───────────┬───────────┘
                              │ BRPOP
                              ▼
                  ┌───────────────────────┐
                  │   Migration Worker    │
                  └───────────┬───────────┘
                              │ Executes
                              ▼
                  ┌───────────────────────┐
                  │ hipcc / AI Agents /   │
                  │   Workspace updates   │
                  └───────────────────────┘
```

## 1. Job Enqueuing
When a migration job is initiated, the FastAPI backend:
1. Creates the workspace directories and writes the user-uploaded code.
2. Pushes a job JSON payload containing the `migration_id` to the Redis list queue (refer to [08_REDIS_ARCHITECTURE.md](file:///c:/Users/Yassi/Downloads/Docs/08_REDIS_ARCHITECTURE.md) for key definitions).
3. Returns a `202 Accepted` status code immediately to the user client, keeping the web API responsive.

## 2. Job Consumption & Concurrency Limits
A standalone Migration Worker process (`backend/app/workers/migration_worker.py`):
1. Calls a blocking pop command (`BRPOP`) on the pending job queue.
2. **Single-Job Execution Lock**: Each worker process is strictly single-threaded and executes exactly one migration at a time. It will not fetch another job until the current job reaches a terminal state (`COMPLETED` or `FAILED`), ensuring dedicated CPU/GPU compiler resources and avoiding contention.
3. Once a job is popped, the worker adds the migration ID to the active job queue and updates the job status state in Redis (refer to [08_REDIS_ARCHITECTURE.md](file:///c:/Users/Yassi/Downloads/Docs/08_REDIS_ARCHITECTURE.md)).
4. Instantiates the Workflow Engine state machine (`07_WORKFLOW_ENGINE.md`) using the job's context and begins executing translation, compilation, and repair loops.

## 3. Real-Time Status Broadcasts
To keep the UI updated without polling, the Migration Worker publishes state transition and logging payloads to the Redis Pub/Sub channels. The FastAPI backend subscribes to these channels and proxies events to the Frontend via WebSockets. All channel definitions are centralized in [08_REDIS_ARCHITECTURE.md](file:///c:/Users/Yassi/Downloads/Docs/08_REDIS_ARCHITECTURE.md).

---

# Worker Scaling and GPU Resource Allocation

Compilation (`hipcc`) and deterministic translation (`hipify-clang`) are CPU and memory-intensive, while running migration tests may require AMD GPU compute capabilities.

## 1. Local Scale-Out (Docker Compose)
In the default hackathon Docker Compose deployment, the number of worker instances can be scaled horizontally using Docker:
```bash
docker-compose up -d --scale migration-worker=3
```
Each container runs a single instance of `migration_worker.py`, consuming tasks concurrently from the single Redis list.

## 2. GPU Pinning and Isolation
If the host machine is equipped with multiple AMD GPUs, workers can be pinned to specific GPUs using ROCm environment variables.
Each worker is initialized with a distinct `ROCR_VISIBLE_DEVICES` or `HIP_VISIBLE_DEVICES` environment variable, ensuring that parallel compilation verification tasks run on isolated hardware zones without memory interference:
- Worker 1: `HIP_VISIBLE_DEVICES=0`
- Worker 2: `HIP_VISIBLE_DEVICES=1`

---

# Enterprise Scaling & Kubernetes

For large-scale enterprise deployments, HIPForge shifts from local Docker Compose to Kubernetes:

## 1. Kubernetes Workflow Engine
- **API Pods**: FastAPI backend pods run behind a standard load balancer, scaling dynamically based on HTTP request metrics.
- **Worker Pods**: Worker pods are separated into their own deployment, mounting a shared high-throughput ReadWriteMany (RWX) volume (e.g., Amazon EFS, Google Cloud Filestore, or Cephfs) for shared `/workspace` storage.

## 2. Event-Driven Autoscaling (KEDA)
Instead of scaling workers based on generic CPU/memory metrics, worker deployments are scaled using **KEDA (Kubernetes Event-driven Autoscaling)** targeting the length of the Redis pending queue:
- **Queue Length = 0**: Scale worker pods down to a minimum configuration (e.g., 1 pod to conserve GPU/CPU resources).
- **Queue Length > 5**: Automatically scale up worker pods, provisioning new GPU nodes in the cloud dynamically.

---

# Enterprise Data Strategy

When scaling beyond a single server, storage and memory requirements scale as follows:

- **Shared File System**: Workspaces must reside on shared, high-IOPS network storage so any worker container in the Kubernetes cluster can compile and edit any active workspace.
- **Redis Shared Memory**: Redis Sentinel or a managed Redis Cluster (e.g., AWS ElastiCache) is deployed to maintain shared migration state reliability.
- **LLM Rate-Limiting**: The Research and Patch Agents query the Fireworks AI endpoint. The backend worker implements an exponential backoff retry mechanism to respect Fireworks API rate limits (tokens per minute and requests per minute) under heavy concurrent usage.

---

# Dependencies

- `02_SYSTEM_ARCHITECTURE.md`
- `07_WORKFLOW_ENGINE.md`
- `08_REDIS_ARCHITECTURE.md`
- `13_BACKEND.md`
- `15_DOCKER_SETUP.md`

---

# Used By

- `21_DEPLOYMENT.md`
- `23_MONITORING.md`
- `27_MAINTENANCE.md`
- `28_COMPLIANCE.md`
- `25_DISASTER_RECOVERY.md`

---

# Acceptance Criteria

✓ API remains fully responsive under multiple parallel code uploads.
✓ Compilation jobs are dispatched asynchronously through a queue.
✓ Workers can be scaled horizontally without codebase changes.
✓ GPU isolation via environment variables is supported.
✓ Future scalability via KEDA and shared storage is documented.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.
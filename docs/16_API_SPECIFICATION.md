# 16_API_SPECIFICATION.md

Version: 1.0

Status: Pending

---

# Purpose

This document defines the complete API specification for HIPForge, encompassing both RESTful endpoints and WebSocket communication channels. It details how the frontend interacts with the backend to initiate migrations, monitor progress, and retrieve results. This specification serves as the contract between the frontend and backend services.

---

# Goals

The API must:

- Be clear and well-documented.
- Support asynchronous operations.
- Enable real-time progress updates.
- Be secure and robust.
- Facilitate easy integration for the frontend.
- Be extensible for future features.

---

# Scope

This document covers:

- REST API endpoints and their functionalities.
- WebSocket channels and message formats.
- Request and response schemas.
- Error handling mechanisms.
- High-level security considerations.

This document does NOT define:

- Internal backend logic.
- Frontend implementation details.
- Database schemas (Redis or otherwise).
- AI prompt structures.

---

# API Design Principles

The HIPForge API adheres to the following principles:

- **Stateless REST**: REST endpoints should be stateless, with all necessary information passed in the request.
- **Event-Driven WebSockets**: Real-time updates are pushed to the frontend via WebSockets, avoiding polling.
- **Clear Separation of Concerns**: REST for actions, WebSockets for notifications.
- **Structured Data**: All requests and responses, especially for AI-related data, use well-defined JSON schemas.
- **Security First**: Input validation and authentication/authorization are paramount.

---

# REST API Endpoints

All REST endpoints are exposed by the FastAPI backend.

## 1. Project Upload

- **Endpoint**: `POST /api/v1/migrate/upload`
- **Description**: Initiates a new migration by uploading CUDA source code.
- **Request Body**:
  ```json
  {
    "file": "<binary_file_content>",
    "filename": "<string>",
    "target_gpu_architecture": "<string>",
    "retry_budget": "<integer>",
    "migration_mode": "<string>"
  }
  ```
- **Response**:
  - **202 Accepted**:
    ```json
    {
      "migration_id": "<uuid>",
      "status": "initializing",
      "message": "Migration initiated successfully."
    }
    ```
  - **400 Bad Request**: Invalid input or file type.
  - **500 Internal Server Error**: Backend processing error.

## 2. Paste Code Migration

- **Endpoint**: `POST /api/v1/migrate/paste`
- **Description**: Initiates a new migration by pasting CUDA source code directly.
- **Request Body**:
  ```json
  {
    "code": "<string>",
    "filename": "<string>",
    "target_gpu_architecture": "<string>",
    "retry_budget": "<integer>",
    "migration_mode": "<string>"
  }
  ```
- **Response**:
  - **202 Accepted**:
    ```json
    {
      "migration_id": "<uuid>",
      "status": "initializing",
      "message": "Migration initiated successfully."
    }
    ```
  - **400 Bad Request**: Invalid input.
  - **500 Internal Server Error**: Backend processing error.

## 3. Migration Status

- **Endpoint**: `GET /api/v1/migrate/{migration_id}/status`
- **Description**: Retrieves the current status of a specific migration.
- **Response**:
  - **200 OK**:
    ```json
    {
      "migration_id": "<uuid>",
      "status": "<string>",
      "current_stage": "<string>",
      "progress": "<float>",
      "message": "<string>"
    }
    ```
  - **404 Not Found**: Migration ID does not exist.

## 4. Download Migration Package

- **Endpoint**: `GET /api/v1/migrate/{migration_id}/download`
- **Description**: Downloads the final migration package (ZIP archive) upon completion.
- **Response**:
  - **200 OK**: Returns `application/zip` file.
  - **404 Not Found**: Migration ID does not exist or migration not complete.

## 5. Cancel Migration

- **Endpoint**: `POST /api/v1/migrate/{migration_id}/cancel`
- **Description**: Cancels an ongoing migration.
- **Response**:
  - **200 OK**:
    ```json
    {
      "migration_id": "<uuid>",
      "status": "cancelled",
      "message": "Migration cancelled successfully."
    }
    ```
  - **404 Not Found**: Migration ID does not exist.

---

# WebSocket Communication

WebSockets provide real-time, bidirectional communication for live updates during a migration session. The frontend subscribes to specific channels for a given `migration_id`.

- **Endpoint**: `ws://<backend_host>:<port>/ws/v1/migrate/{migration_id}/stream`
- **Description**: Establishes a WebSocket connection for real-time migration events.

## Channels and Message Types

### 1. `migration:{id}:events`

- **Description**: General workflow events and status updates.
- **Message Format**:
  ```json
  {
    "type": "event",
    "timestamp": "<ISO_8601_string>",
    "stage": "<string>",
    "status": "<string>",
    "message": "<string>"
  }
  ```
  - **Example `stage` values (Refer to [26_JOB_LIFECYCLE.md](file:///c:/Users/Yassi/Downloads/Docs/26_JOB_LIFECYCLE.md))**: `QUEUED`, `PREPARING`, `HIPIFY`, `SCA`, `COMPILING`, `ANALYZING`, `PATCHING`, `RESEARCHING`, `GENERATING_REPORT`, `COMPLETED`, `FAILED`.
  - **Example `status` values**: `started`, `in_progress`, `completed`, `failed`.

### 2. `migration:{id}:compiler`

- **Description**: Streams raw compiler output (stdout/stderr).
- **Message Format**:
  ```json
  {
    "type": "compiler_log",
    "timestamp": "<ISO_8601_string>",
    "level": "<string>",
    "content": "<string>"
  }
  ```
  - **Example `level` values**: `INFO`, `WARNING`, `ERROR`.

### 3. `migration:{id}:agents`

- **Description**: Provides updates on AI agent activity.
- **Message Format**:
  ```json
  {
    "type": "agent_activity",
    "timestamp": "<ISO_8601_string>",
    "agent": "<string>",
    "action": "<string>",
    "summary": "<string>"
  }
  ```
  - **Example `agent` values**: `AnalysisAgent`, `PatchAgent`, `ResearchAgent`.
  - **Example `action` values**: `started`, `analyzing`, `patching`, `searching`, `completed`.

---

# Request/Response Schemas

All request and response bodies for REST endpoints, and message payloads for WebSockets, adhere to Pydantic models defined in the backend's `app/schemas/` directory. This ensures strict type validation and automatic documentation generation.

---

# Error Handling

API errors are returned with appropriate HTTP status codes and a standardized JSON error response body:

```json
{
  "detail": "<string>",
  "code": "<string>",
  "trace_id": "<uuid>"
}
```

- **`detail`**: A human-readable message describing the error.
- **`code`**: An internal error code for programmatic handling.
- **`trace_id`**: A unique identifier for tracing the error in backend logs.

---

# Security Considerations

- All API endpoints are protected against common web vulnerabilities (e.g., SQL injection, XSS) through FastAPI's built-in protections and explicit input validation.
- File uploads are scanned for malicious content and size-limited.
- Access to migration-specific resources (e.g., download packages, WebSocket streams) is restricted to the `migration_id` owner (implicitly handled by session in V1, future versions will use explicit authentication).
- No sensitive information (e.g., API keys) is exposed via the API or WebSocket.

---

# Dependencies

- `02_SYSTEM_ARCHITECTURE.md`
- `05_USER_FLOW.md`
- `13_BACKEND.md`
- `14_FRONTEND.md`

---

# Used By

- `17_REPORT_GENERATOR.md`
- `18_OBSERVABILITY.md`
- `19_SECURITY.md`
- `20_TESTING.md`
- `21_DEPLOYMENT.md`

---

# Acceptance Criteria

✓ All major user interactions have corresponding API endpoints.
✓ Real-time progress updates are supported via WebSockets.
✓ Request and response formats are clearly defined.
✓ Error responses are standardized.
✓ Security considerations are outlined.
✓ API design aligns with backend and frontend requirements.

---

# Implementation Status

Pending

> [!IMPORTANT]
> **Note for the AI Agent**: Do not change this status to "Completed" until you have fully implemented the requirements detailed in this specification, executed the code, run the unit/integration tests, and verified that everything behaves correctly.
# HIPForge Startup Productization Roadmap

This document outlines the engineering implementation plan to transition the HIPForge hackathon prototype into an enterprise-ready, secure, and venture-backable SaaS platform suitable for Y Combinator and commercial launch.

---

## Phase 1: Secure Sandboxed Compiler Execution
**Goal:** Prevent Arbitrary Code Execution (ACE) and compile-time system compromise from user-uploaded code.

### 1. Architectural Design
Instead of running `subprocess.run(["hipcc", ...])` directly on the host system, execution must be routed to isolated, ephemeral sandbox runners.
* **Sandboxing Tech:** Use **gVisor** (a sandboxed container runtime by Google that intercepts syscalls) or **AWS Fargate** (ephemeral virtual machines).
* **Execution Flow:**
  1. The backend worker receives a migration job.
  2. Spawns a lightweight Docker container using a pre-configured ROCm/HIP base image under a gVisor runtime (`--runtime=runsc`).
  3. Mounts the workspace `input/` and `generated/` directories as read-only and write-only volumes respectively.
  4. Limits container memory (e.g., 2GB), CPU (e.g., 2 cores), and network access (disabled).
  5. Runs the compile command inside the container, captures logs, and destroys the container instantly.

---

## Phase 2: AST Context Optimization & Diff Patching
**Goal:** Reduce LLM token consumption, avoid context limit overflows, and improve code patch accuracy.

### 1. Semantic AST Slicing (Analysis Stage)
Instead of feeding the entire 10,000+ line source file to the LLM:
* Write a Python parser using `clang.cindex` (Clang Python bindings) to extract the AST of the source file.
* Identify the exact class, function, or block containing the compilation error.
* Slice the file to only include the target function, its signature, global macros, and direct dependencies (sliding context window).

### 2. Search-and-Replace Diff Generation (Patch Stage)
* Modify the **Patch Agent** to output a target file patch (e.g., a standard Unified Diff or a structured search-and-replace block) instead of regenerating the entire file.
* Implement a robust Python-based patch applier that applies the search-and-replace block to the original source file on the server.
* **Fallback:** If the patch fails to apply cleanly, retry with a slightly wider context window.

---

## Phase 3: Enterprise Build Integration & CLI
**Goal:** Support massive real-world projects containing complex build trees (CMake, Makefiles).

### 1. Build Compilation Database (compilation_commands.json)
Real projects cannot be compiled by invoking `hipcc file.hip` directly; they require exact include paths (`-I`), compiler definitions (`-D`), and linker flags.
* Instruct users to generate a compilation database: `cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ..`.
* Parse the generated `compile_commands.json` in the backend to extract exact build parameters for every source file.

### 2. CLI Tool (`hipforge-cli`)
* Build a lightweight Python-based CLI distributed via PyPI: `pip install hipforge-cli`.
* Command: `hipforge migrate --project . --target gfx942`.
* The CLI zips the project, uploads it via the FastAPI endpoint, polls status via WebSockets, and downloads/unpacks the resulting HIP archive locally.

---

## Phase 4: Multi-tenancy, Billing, and Quotas
**Goal:** Establish SaaS infrastructure for monetization.

* **Multi-tenancy:** Set up user authentication (Auth0 / Clerk) and tenant workspace isolation.
* **Billing Integration:** Integrate **Stripe** to track subscription tiers (Free, Pro, Enterprise).
* **Token Rate-Limiting:** Track token consumption per user and apply strict rate limits to prevent API abuse.

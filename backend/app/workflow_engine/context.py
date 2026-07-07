from typing import Any, Dict, List, Optional


class WorkflowContext:
    """
    Stores the runtime in-memory state for a migration job execution.
    Passed to all states in the Workflow Engine.

    Redis remains the persistent shared state; WorkflowContext is the
    temporary in-memory working state (per docs/07_WORKFLOW_ENGINE.md).
    """

    def __init__(
        self,
        migration_id: str,
        workspace_path: str,
        redis_manager=None,
        retry_budget: int = 5,
    ):
        self.migration_id = migration_id
        self.workspace_path = workspace_path
        self.redis_manager = redis_manager
        self.retry_budget = retry_budget
        self.workflow_trace = []
        self.failed_stage = None
        self.main_error = None

        # ── Core lifecycle fields ───────────────────────────────────────
        self.current_state: str = "QUEUED"
        self.current_attempt: int = 0
        
        # ── Execution tracking & metrics ──────────────────────────────
        import time
        from datetime import datetime, timezone
        self.start_time_secs: float = time.time()
        self.start_time: str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.cuda_apis_detected: int = 0
        self.cuda_apis_converted: int = 0
        self.cuda_apis_remaining: int = 0
        self.initial_cuda_apis_detail: dict = {}
        self.remaining_cuda_apis_detail: dict = {}
        self.files_modified: list = []
        self.error_category: str = "NONE"
        self.previous_compiler_errors: list = []
        self.previous_compile_stderr: str = ""
        self.infrastructure_error: bool = False
        self.failure_reason: str = ""
        self.recommended_next_action: str = ""
        self.preflight_report: Optional[Dict[str, Any]] = None

        # ── Project scan (preflight classification) ─────────────────────
        self.project_scan: Optional[Dict[str, Any]] = None
        # Structured inventory extracted from project_scan for reporting
        self.project_inventory: Optional[Dict[str, Any]] = None

        # ── HIPIFY stage output ─────────────────────────────────────────
        # Absolute path to the translated .hip file written by hipify-clang.
        # Set by handle_hipify(); consumed by handle_sca() and handle_compiling().
        self.hipify_output_path: Optional[str] = None

        # ── SCA stage output ────────────────────────────────────────────
        # Full result dict from sca.analyze(): {"issues": [...], "score": float}
        # Set by handle_sca(); attached to AI agent context in later stages.
        self.sca_result: Optional[Dict[str, Any]] = None

        # ── COMPILING stage output ──────────────────────────────────────
        # True when hipcc exits with code 0; False otherwise.
        # Read by state_machine.py to determine success for COMPILING.
        self.compilation_success: bool = False

        # Structured CompilerError list from parse_compiler_errors().
        # Empty on success; consumed by ANALYZING agent in later sessions.
        self.compiler_errors: List[Any] = []

        # Raw stderr string from the most recent hipcc run.
        # Preserved for AI agents that need full diagnostic context.
        self.last_compile_stderr: str = ""

        # Exact compile command from the most recent hipcc/make invocation.
        self.last_compile_command: str = ""

        # ── ANALYZING stage output ──────────────────────────────────────
        # Structured result from the Analysis Agent.
        # Schema: {summary, root_cause, affected_files, affected_lines,
        #          confidence, repair_plan}
        # Set by handle_analyzing(); consumed by handle_patching() (Session 9.3).
        self.analysis_result: Optional[Dict[str, Any]] = None

        # ── Migration Journal ───────────────────────────────────────────
        # Running list of attempt records. Each entry is added after every
        # ANALYZING→PATCHING cycle so agents can avoid repeating failed fixes.
        self.migration_journal: List[Dict[str, Any]] = []

        # ── PATCHING stage output ───────────────────────────────────────
        # Absolute path to the most recently written patched .hip file.
        # Set by handle_patching(); passed as the source for the next
        # COMPILING attempt via hipify_output_path update.
        self.patched_source_path: Optional[str] = None

        # Raw source strings from all previous patch attempts (most recent last).
        # Passed to the Patch Agent so it can avoid repeating the same changes.
        self.patch_history: List[str] = []

        # ── RESEARCHING stage output ────────────────────────────────────
        # Persisted research context (findings summary) to be fed into
        # the next ANALYZING cycle.
        self.research_context: Optional[str] = None

        # ── Learning / Lesson info ───────────────────────────────────────
        # Populated when a stored lesson matches the current error.
        # Consumed by report generator to show "Learning / Previous Knowledge Used".
        self.lesson_matched: Optional[dict] = None

        # ── Compiler validation info ─────────────────────────────────────
        # NOT_RUN | PASSED | FAILED | FAILED_SETUP
        self.compile_status: str = "NOT_RUN"
        # real | test-only | unavailable
        self.compiler_mode: str = "real"

        # ── Validation confidence ────────────────────────────────────────
        # Set after COMPILING completes. See compiler/validation_confidence.py.
        # LOW | MEDIUM | HIGH | PROFILED
        self.validation_confidence: str = "LOW"
        self.validation_confidence_reason: str = "conversion happened but real compile failed or did not run"
        # NOT_RUN | PASSED | FAILED
        self.runtime_validation_status: str = "NOT_RUN"
        self.runtime_validation_reason: str = ""
        # Mirrors RUNTIME_VALIDATION_ENABLED env flag; default False for v0.
        self.runtime_validation_enabled: bool = False
        # NOT_CONFIGURED | SKIPPED | PASSED | FAILED
        self.profiling_status: str = "NOT_CONFIGURED"

        # ── Launcher safety metrics ──────────────────────────────────────
        self.launcher_expects_device_pointers: str = "N/A"
        self.kernel_launch_error_checks: str = "none"
        self.synchronization_status: str = "none"

        # ── File lifecycle tracking ──────────────────────────────────────
        self.file_lifecycle: dict = {}

        # ── Target architecture ───────────────────────────────────────────────
        # Set from Redis metadata by handle_preflight; fallback "gfx90a".
        self.target_gpu_architecture: str = "gfx90a"
        # ArchAdvice.to_dict() result set by handle_preflight after advise().
        self.architecture_advice: dict = {}
        # HIGH | MEDIUM | LOW
        self.architecture_confidence: str = "LOW"
        # Flat list of risk_warnings + recommended_actions from ArchAdvice.
        self.architecture_warnings: list = []
        # detected_gpu | user_selected | configured_default | fallback_default | unknown
        self.architecture_selection_source: str = "unknown"

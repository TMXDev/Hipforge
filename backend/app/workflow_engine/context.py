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

        # ── Core lifecycle fields ───────────────────────────────────────
        self.current_state: str = "QUEUED"
        self.current_attempt: int = 0

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

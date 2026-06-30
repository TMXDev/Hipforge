# Inconsistencies and Terminology Conflicts

This document records all inconsistencies, gaps, and terminology conflicts identified during the review of the HIPForge architecture documentation.

---

## 00_SYSTEM_SPECIFICATION.md vs. 01_PRODUCT_VISION.md

- **Terminology**: `00_SYSTEM_SPECIFICATION.md` uses 
the terms "Analysis Agent", "Patch Agent", "Research Agent", and "" for AI components in section 5.4, and "Analysis Agent", "Patch Agent", "Research Agent" in section 6. However, `09_AI_AGENTS.md` formally defines the agents as "Analysis Agent", "Patch Agent", and "Research Agent". The "Patch Agent" agent from `00_SYSTEM_SPECIFICATION.md` appears to correspond to the "Patch Agent", and "Research Agent" to "Research Agent". The role of "" is not explicitly assigned to a dedicated agent in `09_AI_AGENTS.md`, but rather implicitly handled by the compiler and the Workflow Engine.

**Action**: Unify terminology to "Analysis Agent", "Patch Agent", and "Research Agent" across all documents, and clarify the role of verification within the Workflow Engine and Compiler Pipeline.

---

## 00_SYSTEM_SPECIFICATION.md vs. 07_WORKFLOW_ENGINE.md

- **Terminology**: `00_SYSTEM_SPECIFICATION.md` refers to the central workflow_engine as "Workflow Engine" in section 7. "Major Components" and "Rule 5" in section 11. "Guiding Rules". `07_WORKFLOW_ENGINE.md` consistently uses "Workflow Engine".

**Action**: Unify terminology to "Workflow Engine" across all documents.

---

## 00_SYSTEM_SPECIFICATION.md vs. 12_MIGRATION_JOURNAL.md

- **Terminology**: `00_SYSTEM_SPECIFICATION.md` mentions "Update Migration Journal" in its high-level workflow (section 6). `12_MIGRATION_JOURNAL.md` consistently uses "Migration Journal". The concept of a "Migration Journal" is not explicitly defined or used elsewhere.

**Action**: Unify terminology to "Migration Journal" and clarify that the "Migration Journal" concept is subsumed by the Migration Journal's function of preventing repeated failures.

---

## General Inconsistency: Document Numbering and References

- Several documents (e.g., `13_BACKEND.md`, `14_FRONTEND.md`, `15_DOCKER_SETUP.md`, `16_API_SPECIFICATION.md`, `17_REPORT_GENERATOR.md`, `18_OBSERVABILITY.md`, `19_SECURITY.md`, `20_TESTING.md`, `21_DEPLOYMENT.md`, `22_INCIDENT_RESPONSE.md`, `23_MONITORING.md`, `24_SCALABILITY.md`, `25_DISASTER_RECOVERY.md`, `27_MAINTENANCE.md`, `28_COMPLIANCE.md`) refer to other documents by their numerical prefix (e.g., `16_API_SPECIFICATION.md`). While this is generally consistent, `07_WORKFLOW_ENGINE.md`'s `Used By` section lists generic subsystem names (`Backend`, `Frontend`, `Redis`, `AI Agents`, `Compiler`) instead of numbered document filenames. Additionally, `01_PRODUCT_VISION.md` references `06_UI_UX.md` and `24_PRESENTATION_AND_DEMO.md`, which were not part of the initial set of documents I received and were not generated in the sequence 15-27. This indicates a potential gap in the document set or an inconsistency in numbering/naming.

**Action**: Review all `Dependencies` and `Used By` sections across all documents to ensure consistent referencing by filename (e.g., `XX_DOCUMENT_NAME.md`). If `06_UI_UX.md` and `24_PRESENTATION_AND_DEMO.md` are indeed missing, they will need to be created or their references updated if they are covered by other documents.

---

## 00_SYSTEM_SPECIFICATION.md vs. 09_AI_AGENTS.md (AI Model Names)

- `00_SYSTEM_SPECIFICATION.md` does not specify the names of the AI models used. `04_TECHNOLOGY_DECISIONS.md` specifies "Analysis Agent: Qwen" and "Patch Agent: Kimi K2.7 Code". `09_AI_AGENTS.md` defines the roles of the Analysis, Patch, and Research Agents but does not explicitly link them to specific model names.

**Action**: Ensure `09_AI_AGENTS.md` (or a relevant AI-specific document) explicitly references the chosen AI models (Qwen for Analysis, Kimi K2.7 Code for Patch/Patch Agent) and their rationale, consistent with `04_TECHNOLOGY_DECISIONS.md`.

---

## 00_SYSTEM_SPECIFICATION.md vs. 05_USER_FLOW.md (Workflow Phases)

- `00_SYSTEM_SPECIFICATION.md` section 6, "High-Level Workflow", outlines a simplified flow. `05_USER_FLOW.md` provides a more detailed, six-phase user journey: "Project Upload", "Automatic Translation", "Compilation Validation", "Intelligent Repair", "Report Generation", and "Download". The high-level workflow in `00_SYSTEM_SPECIFICATION.md` needs to be updated to reflect the more granular and accurate phases defined in `05_USER_FLOW.md`.

**Action**: Update the high-level workflow in `00_SYSTEM_SPECIFICATION.md` to align with the six phases defined in `05_USER_FLOW.md`.

---

## 00_SYSTEM_SPECIFICATION.md vs. 04_TECHNOLOGY_DECISIONS.md (Compiler/Translator)

- `00_SYSTEM_SPECIFICATION.md` lists "Compiler: HIPCC" and "Translator: hipify-clang" in section 8. "Technology Stack". `04_TECHNOLOGY_DECISIONS.md` section "Compiler" lists both `hipify-clang` and `hipcc` as selected compilers. While `hipify-clang` is primarily a translator, it's also part of the compilation toolchain. This is a minor point but could be clarified.

**Action**: Clarify the roles of `hipify-clang` (translator) and `hipcc` (compiler) consistently, perhaps by referring to them as the "ROCm Migration and Compilation Toolchain" or similar, to avoid ambiguity.

---

## 00_SYSTEM_SPECIFICATION.md vs. 13_BACKEND.md (Framework Independence)

- `00_SYSTEM_SPECIFICATION.md` (section 5.5) states a design philosophy of "Framework Independence" for components. `13_BACKEND.md` (section "Goals") also lists "Framework-independent" as a goal. However, `13_BACKEND.md` explicitly states that the backend is implemented using FastAPI. While individual modules within the backend might be framework-independent, the backend itself is built on FastAPI. This is a nuance that needs to be clarified to avoid misinterpretation.

**Action**: Clarify that while individual modules and business logic within the backend aim for framework independence, the overall backend service leverages FastAPI as its chosen web framework, consistent with `04_TECHNOLOGY_DECISIONS.md`.

---

## 00_SYSTEM_SPECIFICATION.md vs. 15_DOCKER_SETUP.md (Docker-first)

- `00_SYSTEM_SPECIFICATION.md` (section 11, Rule 9) states "The system must remain Docker-first." `15_DOCKER_SETUP.md` details the Docker Compose setup. This is consistent, but it's worth noting that `15_DOCKER_SETUP.md` also mentions "Future Consideration: Migrate to Kubernetes for large-scale cloud deployments" in `04_TECHNOLOGY_DECISIONS.md` and "Kubernetes Workflow Engine" in `24_SCALABILITY.md`. This is not an inconsistency but a natural evolution. The 
document should clearly state that while Docker Compose is the primary deployment method for V1 and local development, the architecture is designed to be compatible with future Kubernetes deployments for scalability.

---

## 02_SYSTEM_ARCHITECTURE.md vs. 00_SYSTEM_SPECIFICATION.md (AI Agent Naming)

- `02_SYSTEM_ARCHITECTURE.md` uses "Analysis Agent → Patch Agent → Research Agent" in its overall system diagram (lines 98-99) and refers to internal implementations as `analysis_agent.py`, `patch_agent.py`, `research_agent.py` (lines 312-341). This directly conflicts with the formal names "Analysis Agent", "Patch Agent", and "Research Agent" used in `09_AI_AGENTS.md` and elsewhere in `02_SYSTEM_ARCHITECTURE.md` itself (section "AI Agent Layer"). The "" agent mentioned in `00_SYSTEM_SPECIFICATION.md` is still not explicitly defined as a separate agent here, reinforcing the need to clarify its role.

**Action**: Update the system diagram and internal implementation references in `02_SYSTEM_ARCHITECTURE.md` to consistently use "Analysis Agent", "Patch Agent", and "Research Agent". Clarify that verification is handled by the compiler and Workflow Engine, not a dedicated "" agent.

---

## 02_SYSTEM_ARCHITECTURE.md vs. 00_SYSTEM_SPECIFICATION.md and 07_WORKFLOW_ENGINE.md (Workflow Engine Terminology)

- `02_SYSTEM_ARCHITECTURE.md` uses "Workflow Engine" in its overall system diagram (line 89) but consistently refers to it as "Workflow Engine" in the text description (section "Workflow Engine"). This confirms the inconsistency with `00_SYSTEM_SPECIFICATION.md` and reinforces the need to unify to "Workflow Engine".

**Action**: Update the system diagram in `02_SYSTEM_ARCHITECTURE.md` to use "Workflow Engine" for consistency.

---

## 02_SYSTEM_ARCHITECTURE.md vs. 00_SYSTEM_SPECIFICATION.md and 12_MIGRATION_JOURNAL.md (Migration Journal vs. Migration Journal)

- `02_SYSTEM_ARCHITECTURE.md` lists "Migration Journal" under Redis storage (line 225). This confirms the inconsistency with `00_SYSTEM_SPECIFICATION.md` and `12_MIGRATION_JOURNAL.md`.

**Action**: Unify terminology to "Migration Journal" across all documents, including the Redis storage section in `02_SYSTEM_ARCHITECTURE.md`.

---

## 02_SYSTEM_ARCHITECTURE.md vs. 05_USER_FLOW.md (Workflow Phases/Diagrams)

- `02_SYSTEM_ARCHITECTURE.md` presents two workflow diagrams (lines 361-414 and 417-490). The first is a simplified flow, and the second is more detailed. Both are generally consistent with the high-level flow in `00_SYSTEM_SPECIFICATION.md` but still differ from the six-phase user journey in `05_USER_FLOW.md`. The `02_SYSTEM_ARCHITECTURE.md` text description of the Workflow Engine (lines 166-175) lists states like "Upload", "Hipify", "Compile", "Analyze", "Patch", "Search", "Report", "Complete", which are closer to the phases in `05_USER_FLOW.md` and `07_WORKFLOW_ENGINE.md`.

**Action**: Ensure all workflow diagrams and descriptions across `00_SYSTEM_SPECIFICATION.md`, `02_SYSTEM_ARCHITECTURE.md`, `05_USER_FLOW.md`, and `07_WORKFLOW_ENGINE.md` are unified to a single, consistent representation of the migration phases and states.

---

## 02_SYSTEM_ARCHITECTURE.md: Missing `Used By` References

- `02_SYSTEM_ARCHITECTURE.md` does not contain a `Used By` section, which is present in almost all other documents. This is an inconsistency in the document structure.

**Action**: Add a `Used By` section to `02_SYSTEM_ARCHITECTURE.md` listing documents that depend on it, consistent with the pattern established in other documents.

---

## 02_SYSTEM_ARCHITECTURE.md: SCA Description vs. `10_COMPILATION_PIPELINE.md`

- The description of the Semantic Compatibility Analyzer (SCA) in `02_SYSTEM_ARCHITECTURE.md` (lines 250-279) is consistent with `10_COMPILATION_PIPELINE.md` (lines 241-270). This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 02_SYSTEM_ARCHITECTURE.md: Redis Purpose vs. `08_REDIS_ARCHITECTURE.md`

- `02_SYSTEM_ARCHITECTURE.md` states "Redis is not responsible for workflow_engine" (line 228). This is consistent with `08_REDIS_ARCHITECTURE.md` which states "Redis is not responsible for workflow_engine" and "Redis does NOT: ... Coordinate workflow." This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 02_SYSTEM_ARCHITECTURE.md: Workflow Engine Design Principles vs. `07_WORKFLOW_ENGINE.md`

- The design principles for the Workflow Engine in `02_SYSTEM_ARCHITECTURE.md` (lines 195-200) are consistent with `07_WORKFLOW_ENGINE.md` (lines 485-494). This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 02_SYSTEM_ARCHITECTURE.md: Report Generator vs. `17_REPORT_GENERATOR.md`

- The description of the Report Generator in `02_SYSTEM_ARCHITECTURE.md` (lines 349-358) is a high-level summary. `17_REPORT_GENERATOR.md` provides a much more detailed breakdown. This is not an inconsistency but a difference in granularity, which is expected.

**Action**: No action needed, this is consistent in terms of high-level overview.

---

## General Inconsistency: Missing Documents in References

- The `Dependencies` and `Used By` sections in many documents (e.g., `01_PRODUCT_VISION.md`, `13_BACKEND.md`, `14_FRONTEND.md`, `15_DOCKER_SETUP.md`, `16_API_SPECIFICATION.md`, `17_REPORT_GENERATOR.md`, `18_OBSERVABILITY.md`, `19_SECURITY.md`, `20_TESTING.md`, `21_DEPLOYMENT.md`, `22_INCIDENT_RESPONSE.md`, `23_MONITORING.md`, `24_SCALABILITY.md`, `25_DISASTER_RECOVERY.md`, `27_MAINTENANCE.md`, `28_COMPLIANCE.md`) refer to documents that were not part of the original set (00-14) and were not generated in the 15-27 sequence. Specifically, `01_PRODUCT_VISION.md` references `06_UI_UX.md` and `24_PRESENTATION_AND_DEMO.md`. This indicates that the initial list of 27 documents might have had some gaps or a different numbering scheme than what was assumed. The current set of documents goes from 00 to 27, but the content of `01_PRODUCT_VISION.md` implies there should be a `06_UI_UX.md` and a `24_PRESENTATION_AND_DEMO.md` which are not present in the current numbering sequence. This is a significant inconsistency in the overall document set structure.

**Action**: After unifying terminology and fixing internal inconsistencies, a comprehensive review of all `Dependencies` and `Used By` sections will be performed to identify any truly missing documents or misnumbered references. If `06_UI_UX.md` and `24_PRESENTATION_AND_DEMO.md` are indeed intended to be part of the 27 documents, they will need to be created, or their references updated if their content is now covered by other documents (e.g., `14_FRONTEND.md` for UI/UX).
## 03_PROJECT_STRUCTURE.md vs. 00_SYSTEM_SPECIFICATION.md and 02_SYSTEM_ARCHITECTURE.md (AI Agent Naming in `agents/` folder)

- `03_PROJECT_STRUCTURE.md` (lines 198-204) lists `analysis_agent.py`, `patch_agent.py`, `research_agent.py`, and `` within the `backend/app/agents/` directory. This reinforces the inconsistency in AI agent naming with `09_AI_AGENTS.md` and `02_SYSTEM_ARCHITECTURE.md` (text description), which use "Analysis Agent", "Patch Agent", and "Research Agent". The presence of `` also suggests a dedicated verifier agent, which contradicts the implicit verification by the compiler and Workflow Engine mentioned in `00_SYSTEM_SPECIFICATION.md` and `02_SYSTEM_ARCHITECTURE.md`.

**Action**: Standardize the filenames within the `agents/` directory to reflect the formal agent names (e.g., `analysis_agent.py`, `patch_agent.py`, `research_agent.py`). Clarify the role of `` or remove it if its functionality is subsumed elsewhere.

---

## 03_PROJECT_STRUCTURE.md vs. 02_SYSTEM_ARCHITECTURE.md (Workflow Engine Folder Naming)

- `03_PROJECT_STRUCTURE.md` (line 151) defines the folder `workflow_engine/` for the custom workflow engine. This is consistent with the "Workflow Engine" diagram label in `02_SYSTEM_ARCHITECTURE.md` but inconsistent with the "Workflow Engine" text description in `02_SYSTEM_ARCHITECTURE.md` and the document `07_WORKFLOW_ENGINE.md`.

**Action**: Rename the `workflow_engine/` folder to `workflow_engine/` to align with the unified terminology.

---

## 03_PROJECT_STRUCTURE.md vs. 02_SYSTEM_ARCHITECTURE.md (Compiler Folder Naming)

- `03_PROJECT_STRUCTURE.md` (line 173) defines the folder `compiler/` for deterministic compiler tools. This is consistent with the "Compiler Pipeline" component in `02_SYSTEM_ARCHITECTURE.md`.

**Action**: No action needed, this is consistent.

---

## 03_PROJECT_STRUCTURE.md vs. 06_WORKSPACE_ARCHITECTURE.md (Workspace Structure)

- `03_PROJECT_STRUCTURE.md` (lines 434-454) defines the `workspace/` structure. This needs to be cross-referenced carefully with `06_WORKSPACE_ARCHITECTURE.md` to ensure complete consistency in subdirectories and their purposes.

**Action**: Verify that the `workspace/` structure defined in `03_PROJECT_STRUCTURE.md` is fully consistent with `06_WORKSPACE_ARCHITECTURE.md`.

---

## 03_PROJECT_STRUCTURE.md: Missing `Used By` References

- `03_PROJECT_STRUCTURE.md` does not contain a `Used By` section, which is present in most other documents. This is an inconsistency in the document structure.

**Action**: Add a `Used By` section to `03_PROJECT_STRUCTURE.md` listing documents that depend on it, consistent with the pattern established in other documents.

---

## 03_PROJECT_STRUCTURE.md: `docker/` folder vs. `15_DOCKER_SETUP.md`

- `03_PROJECT_STRUCTURE.md` (lines 460-472) describes a `docker/` folder containing `backend/`, `frontend/`, and `redis/` subdirectories for container-specific configuration. This needs to be consistent with the detailed Docker setup described in `15_DOCKER_SETUP.md`.

**Action**: Verify that the structure and content of the `docker/` folder described in `03_PROJECT_STRUCTURE.md` is fully consistent with `15_DOCKER_SETUP.md`.
## 04_TECHNOLOGY_DECISIONS.md vs. 09_AI_AGENTS.md (AI Agent Naming and Model Mapping)

- `04_TECHNOLOGY_DECISIONS.md` explicitly names AI models: "Analysis Agent: Qwen" and "Patch Agent: Kimi K2.7 Code". This provides concrete model choices for the abstract "Analysis Agent" and "Patch Agent" roles. However, `09_AI_AGENTS.md` formally defines the agents as "Analysis Agent" and "Patch Agent". The mapping between the model names and the formal agent names needs to be explicitly stated and consistently used.

**Action**: Update `09_AI_AGENTS.md` to explicitly map "Analysis Agent" to Qwen and "Patch Agent" to Kimi K2.7 Code, ensuring consistency with `04_TECHNOLOGY_DECISIONS.md`.

---

## 04_TECHNOLOGY_DECISIONS.md vs. 07_WORKFLOW_ENGINE.md (Workflow Engine Terminology)

- `04_TECHNOLOGY_DECISIONS.md` uses "Workflow Engine" as a section title and refers to the "Custom Python State Machine" as the selected technology. This is consistent with the functionality of the "Workflow Engine" (`07_WORKFLOW_ENGINE.md`) but the terminology could be unified for clarity.

**Action**: Ensure that the term "Workflow Engine" is consistently used when referring to the custom Python state machine responsible for workflow_engine across all documents.

---

## 04_TECHNOLOGY_DECISIONS.md vs. 12_MIGRATION_JOURNAL.md (Migration Journal vs. Migration Journal)

- `04_TECHNOLOGY_DECISIONS.md` lists "Migration Journal" as a responsibility of Redis under the "Shared State" section. This reinforces the inconsistency with `12_MIGRATION_JOURNAL.md` which uses "Migration Journal".

**Action**: Unify terminology to "Migration Journal" across all documents, including the Redis responsibilities in `04_TECHNOLOGY_DECISIONS.md`.

---

## 04_TECHNOLOGY_DECISIONS.md vs. 00_SYSTEM_SPECIFICATION.md (Compiler/Translator Clarification)

- `04_TECHNOLOGY_DECISIONS.md` lists `hipify-clang` and `hipcc` under the "Compiler" section, stating they are the "official ROCm migration and compilation tools". This is consistent with `00_SYSTEM_SPECIFICATION.md`. The previous action item was to clarify their roles. This document provides a good starting point for that clarification.

**Action**: Ensure that the distinction between `hipify-clang` as a translator and `hipcc` as a compiler is clearly articulated in `00_SYSTEM_SPECIFICATION.md` and `10_COMPILATION_PIPELINE.md`, consistent with the description in `04_TECHNOLOGY_DECISIONS.md`.

---

## 04_TECHNOLOGY_DECISIONS.md: Incorrect Security Document Reference

- `04_TECHNOLOGY_DECISIONS.md` (line 375) states: "Detailed implementation is defined in `19_SECURITY.md`." However, the security document I generated is `19_SECURITY.md`.

**Action**: Correct the reference in `04_TECHNOLOGY_DECISIONS.md` to `19_SECURITY.md`.

---

## 04_TECHNOLOGY_DECISIONS.md: Missing `Used By` References

- `04_TECHNOLOGY_DECISIONS.md` has a `Used By` section that broadly states "All implementation documents and prompts." This is less specific than other documents which list specific document filenames. While not a critical inconsistency, it deviates from the established pattern.

**Action**: Update the `Used By` section in `04_TECHNOLOGY_DECISIONS.md` to list specific document filenames where possible, or clarify why a general statement is used here.

---

## 04_TECHNOLOGY_DECISIONS.md: Future Consideration for Kubernetes

- `04_TECHNOLOGY_DECISIONS.md` (lines 275-277) mentions "Future Consideration: Migrate to Kubernetes for large-scale cloud deployments." This is consistent with the discussion in `15_DOCKER_SETUP.md` and `24_SCALABILITY.md` regarding the evolution from Docker Compose to Kubernetes. This is a point of consistency regarding future plans.

**Action**: No action needed, this is consistent and well-documented as a future consideration.
## 05_USER_FLOW.md vs. 00_SYSTEM_SPECIFICATION.md and 02_SYSTEM_ARCHITECTURE.md (Workflow Phases)

- `05_USER_FLOW.md` clearly defines six phases: "Project Upload", "Automatic Translation", "Compilation Validation", "Intelligent Repair", "Report Generation", and "Download". This is more detailed and structured than the "High-Level Workflow" in `00_SYSTEM_SPECIFICATION.md` and the workflow diagrams in `02_SYSTEM_ARCHITECTURE.md`. The high-level workflows in `00_SYSTEM_SPECIFICATION.md` and `02_SYSTEM_ARCHITECTURE.md` need to be updated to reflect these more granular and accurate phases.

**Action**: Update the high-level workflow in `00_SYSTEM_SPECIFICATION.md` and the workflow diagrams in `02_SYSTEM_ARCHITECTURE.md` to align with the six phases defined in `05_USER_FLOW.md`.

---

## 05_USER_FLOW.md vs. 02_SYSTEM_ARCHITECTURE.md ("Engineering Dashboard" in Workflow Diagram)

- The workflow diagram in `02_SYSTEM_ARCHITECTURE.md` (line 452) includes "Engineering Dashboard" as a step before "Export Package" in the successful compilation path. This term is not explicitly defined or used in `05_USER_FLOW.md` or `14_FRONTEND.md`. It might be an internal concept or a placeholder that needs clarification or removal for consistency.

**Action**: Clarify the meaning and purpose of "Engineering Dashboard" or remove it from the workflow diagram in `02_SYSTEM_ARCHITECTURE.md` if it's not a user-facing concept or is covered by other terms.

---

## 05_USER_FLOW.md: Phase 5 Naming vs. Workflow Logic

- `05_USER_FLOW.md` labels Phase 5 as "Research Recovery". However, the "Retry Strategy" section indicates that research is a step within a broader retry loop that can lead back to further repair attempts. This implies that "Research Recovery" might be better described as a step within the "Intelligent Repair" phase or that the phase naming should more accurately reflect its iterative nature.

**Action**: Review the naming of "Phase 5 — Research Recovery" to ensure it accurately reflects its role within the overall iterative repair and retry strategy. Consider if it should be a sub-step of "Intelligent Repair" or if the phase description needs to emphasize its role in enabling further repair attempts.

---

## 05_USER_FLOW.md: Missing `Used By` References

- `05_USER_FLOW.md` has a `Used By` section that lists specific documents. This is consistent with the established pattern.

**Action**: No action needed, this is consistent.

---

## 05_USER_FLOW.md: Consistency in AI Agent Naming

- `05_USER_FLOW.md` consistently uses "Analysis Agent", "Patch Agent", and "Research Agent", which aligns with `09_AI_AGENTS.md` and the formal names I've decided to unify to. This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 05_USER_FLOW.md: Consistency in Migration Journal Terminology

- `05_USER_FLOW.md` consistently uses "Migration Journal", which aligns with `12_MIGRATION_JOURNAL.md` and reinforces the need to unify away from "Migration Journal".

**Action**: No action needed, this is consistent.

---

## 05_USER_FLOW.md: Consistency in SCA Description

- The description of the Semantic Compatibility Analyzer (SCA) in `05_USER_FLOW.md` is consistent with `02_SYSTEM_ARCHITECTURE.md` and `10_COMPILATION_PIPELINE.md`. This is a point of consistency.

**Action**: No action needed, this is consistent.
## 06_WORKSPACE_ARCHITECTURE.md vs. 03_PROJECT_STRUCTURE.md (Workspace Structure)

- `06_WORKSPACE_ARCHITECTURE.md` (lines 92-114) defines the detailed `workspace/` structure with subdirectories like `input/`, `generated/`, `patches/`, `logs/`, `artifacts/`, `reports/`, `exports/`, and `metadata.json`. This is largely consistent with the high-level `workspace/` structure shown in `03_PROJECT_STRUCTURE.md` (lines 434-454). The `exports/` directory in `06_WORKSPACE_ARCHITECTURE.md` corresponds to the `final/` directory in `03_PROJECT_STRUCTURE.md`.

**Action**: Unify the terminology for the final downloadable package directory to either `exports/` or `final/` across both documents. Prefer `exports/` as it is used in `06_WORKSPACE_ARCHITECTURE.md` and `05_USER_FLOW.md`.

---

## 06_WORKSPACE_ARCHITECTURE.md vs. 00_SYSTEM_SPECIFICATION.md and 02_SYSTEM_ARCHITECTURE.md (AI Agent Naming in Artifact Lifecycle)

- `06_WORKSPACE_ARCHITECTURE.md` (lines 292-316) uses "Analysis Agent", "Patch Agent", and "Research Agent" in its "Artifact Lifecycle" diagram. This is consistent with the formal names and reinforces the need to update `00_SYSTEM_SPECIFICATION.md` and `02_SYSTEM_ARCHITECTURE.md`.

**Action**: No action needed, this is consistent.

---

## 06_WORKSPACE_ARCHITECTURE.md vs. 05_USER_FLOW.md (Export Package Contents)

- `06_WORKSPACE_ARCHITECTURE.md` (lines 434-448) lists the contents of the downloadable archive as `generated/`, `patches/`, `logs/`, `reports/`, `README.txt`. `05_USER_FLOW.md` (lines 471-490) lists a more comprehensive set: `converted_project/`, `migration_report.md`, `migration_journal.json`, `compatibility_report.md`, `migration_risks.json`, `build.sh`, `CMakeLists.txt`, `git_patch.diff`, `README.md`, `logs/`. There is a clear discrepancy in the listed contents.

**Action**: Unify the list of contents for the downloadable package across `05_USER_FLOW.md` and `06_WORKSPACE_ARCHITECTURE.md`. The more comprehensive list from `05_USER_FLOW.md` seems more appropriate and should be adopted.

---

## 06_WORKSPACE_ARCHITECTURE.md: Consistency in Migration ID Generation

- `06_WORKSPACE_ARCHITECTURE.md` (lines 62-82) describes the generation of a unique `migration_YYYYMMDD_HHMMSS_<SHORT_UUID>` ID for each workspace, which is also stored in Redis. This is consistent with the concept of a unique migration ID used throughout the system.

**Action**: No action needed, this is consistent.

---

## 06_WORKSPACE_ARCHITECTURE.md: Consistency in `metadata.json`

- `06_WORKSPACE_ARCHITECTURE.md` (lines 240-255) defines `metadata.json` for storing migration metadata, including `migration_id`, `status`, `created_at`, `retry_budget`, `current_attempt`, `compiler`, and `workflow_state`. This is consistent with the need for recovery support and tracking migration progress.

**Action**: No action needed, this is consistent.

---

## 06_WORKSPACE_ARCHITECTURE.md: `Used By` References

- `06_WORKSPACE_ARCHITECTURE.md` has a `Used By` section that lists specific documents. This is consistent with the established pattern.

**Action**: No action needed, this is consistent.
## 07_WORKFLOW_ENGINE.md vs. 00_SYSTEM_SPECIFICATION.md, 02_SYSTEM_ARCHITECTURE.md, and 05_USER_FLOW.md (Workflow States/Phases)

- `07_WORKFLOW_ENGINE.md` defines a detailed sequence of states (INITIALIZE, UPLOAD, HIPIFY, COMPILE, ANALYZE, PATCH, RESEARCH, UPDATE JOURNAL, REPORT, EXPORT, COMPLETE) and a state transition table. This is the most granular definition of the workflow. This needs to be reconciled with the six high-level phases in `05_USER_FLOW.md` ("Project Upload", "Automatic Translation", "Compilation Validation", "Intelligent Repair", "Report Generation", "Download") and the more abstract workflows in `00_SYSTEM_SPECIFICATION.md` and `02_SYSTEM_ARCHITECTURE.md`.

**Action**: Create a mapping between the detailed states in `07_WORKFLOW_ENGINE.md` and the higher-level phases in `05_USER_FLOW.md`. Update `00_SYSTEM_SPECIFICATION.md` and `02_SYSTEM_ARCHITECTURE.md` to reference the `05_USER_FLOW.md` phases and, where appropriate, the `07_WORKFLOW_ENGINE.md` states for detailed understanding.

---

## 07_WORKFLOW_ENGINE.md vs. 05_USER_FLOW.md and 06_WORKSPACE_ARCHITECTURE.md (Export Package Naming and Contents)

- `07_WORKFLOW_ENGINE.md` refers to the final package as `HIPForge_Migration.zip` in the EXPORT state. This is consistent with `06_WORKSPACE_ARCHITECTURE.md` but `05_USER_FLOW.md` lists `migration.zip`. Also, the contents of the export package need to be unified as identified previously.

**Action**: Unify the name of the export package to `HIPForge_Migration.zip` across all documents. Reiterate the action to unify the contents of the downloadable package across `05_USER_FLOW.md` and `06_WORKSPACE_ARCHITECTURE.md`.

---

## 07_WORKFLOW_ENGINE.md: Consistency in AI Agent Naming

- `07_WORKFLOW_ENGINE.md` consistently uses "Analysis Agent", "Patch Agent", and "Research Agent" in its state definitions, which aligns with `09_AI_AGENTS.md` and the unified terminology. This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 07_WORKFLOW_ENGINE.md: Consistency in Migration Journal Terminology

- `07_WORKFLOW_ENGINE.md` consistently uses "Migration Journal" and includes an "UPDATE JOURNAL" state, reinforcing the unification away from "Migration Journal". This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 07_WORKFLOW_ENGINE.md: Consistency in Workflow Engine/Workflow Engine Terminology

- `07_WORKFLOW_ENGINE.md` consistently uses "Workflow Engine" throughout, reinforcing the unification. This is a point of consistency.

**Action**: No action needed, this is consistent.

---

## 07_WORKFLOW_ENGINE.md: Missing `Used By` References

- `07_WORKFLOW_ENGINE.md` does not contain a `Used By` section, which is present in most other documents. This is an inconsistency in the document structure.

**Action**: Add a `Used By` section to `07_WORKFLOW_ENGINE.md` listing documents that depend on it, consistent with the pattern established in other documents.
## 08_REDIS_ARCHITECTURE.md: Contradiction in "Coordinate workflow execution"

- `08_REDIS_ARCHITECTURE.md` (line 24) lists "Coordinate workflow execution" as a goal for Redis. However, in its "Redis Philosophy" (line 58) and "Non-Responsibilities" (line 414), it explicitly states "Redis is not responsible for workflow_engine" and "Redis does NOT: ... Coordinate workflow." This is a direct contradiction.

**Action**: Remove "Coordinate workflow execution" from the Goals section of `08_REDIS_ARCHITECTURE.md` to align with the philosophy and non-responsibilities sections, which correctly state that Redis is a shared memory, not an workflow_engine.

---

## 08_REDIS_ARCHITECTURE.md vs. 12_MIGRATION_JOURNAL.md (Migration Journal vs. Migration Journal)

- `08_REDIS_ARCHITECTURE.md` (line 245) lists "Migration Journal" as a key stored in Redis. This continues the inconsistency with `12_MIGRATION_JOURNAL.md` and the unified terminology of "Migration Journal".

**Action**: Unify terminology to "Migration Journal" across all documents, including the Redis key naming in `08_REDIS_ARCHITECTURE.md`.

---

## 08_REDIS_ARCHITECTURE.md: Consistency in AI Agent Naming

- `08_REDIS_ARCHITECTURE.md` (lines 365-367) lists "Analysis Agent", "Patch Agent", and "Research Agent" activity in its Pub/Sub channels. This is consistent with the unified terminology.

**Action**: No action needed, this is consistent.

---

## 08_REDIS_ARCHITECTURE.md: `Used By` References

- `08_REDIS_ARCHITECTURE.md` lists generic component names (Workflow Engine, Frontend, Backend, Compiler, AI Agents) in its `Used By` section (lines 444-452) instead of specific document filenames. This is an inconsistency in the document structure compared to most other documents.

**Action**: Update the `Used By` section in `08_REDIS_ARCHITECTURE.md` to list specific document filenames (e.g., `07_WORKFLOW_ENGINE.md`, `13_BACKEND.md`, `14_FRONTEND.md`, `09_AI_AGENTS.md`, `10_COMPILATION_PIPELINE.md`) where possible, consistent with the pattern established in other documents.
## 09_AI_AGENTS.md vs. 00_SYSTEM_SPECIFICATION.md, 02_SYSTEM_ARCHITECTURE.md, 03_PROJECT_STRUCTURE.md, and 04_TECHNOLOGY_DECISIONS.md (AI Agent Naming and Model Mapping)

- `09_AI_AGENTS.md` consistently uses the formal names "Analysis Agent", "Patch Agent", and "Research Agent". This is the desired unified terminology. However, `00_SYSTEM_SPECIFICATION.md` uses "Analysis Agent", "Patch Agent", "Research Agent", and "". `02_SYSTEM_ARCHITECTURE.md` uses "Analysis Agent → Patch Agent → Research Agent" in its diagram and refers to internal implementations as `analysis_agent.py`, `patch_agent.py`, `research_agent.py`. `03_PROJECT_STRUCTURE.md` lists `analysis_agent.py`, `patch_agent.py`, `research_agent.py`, and `` within the `backend/app/agents/` directory. `04_TECHNOLOGY_DECISIONS.md` explicitly maps "Analysis Agent" to Qwen and "Patch Agent" to Kimi K2.7 Code.

**Action**: Unify all references to AI agents to "Analysis Agent", "Patch Agent", and "Research Agent" across all documents. Update `00_SYSTEM_SPECIFICATION.md`, `02_SYSTEM_ARCHITECTURE.md` (diagram and internal implementation references), and `03_PROJECT_STRUCTURE.md` (filenames) accordingly. Explicitly state the mapping of Qwen to Analysis Agent and Kimi K2.7 Code to Patch Agent within `09_AI_AGENTS.md`.

---

## 09_AI_AGENTS.md vs. 00_SYSTEM_SPECIFICATION.md and 03_PROJECT_STRUCTURE.md ("" Agent)

- `00_SYSTEM_SPECIFICATION.md` and `03_PROJECT_STRUCTURE.md` mention a "" agent or ``. `09_AI_AGENTS.md` does not define a separate "" agent, reinforcing the architectural principle that verification is handled by the compiler and Workflow Engine. This creates an inconsistency regarding the existence and role of a dedicated verifier agent.

**Action**: Clarify that there is no dedicated "" AI agent. Remove references to "" from `00_SYSTEM_SPECIFICATION.md` and `03_PROJECT_STRUCTURE.md`, and remove `` from the `agents/` directory structure in `03_PROJECT_STRUCTURE.md`. Explicitly state that verification is a function of the Compiler Pipeline and the Workflow Engine.

---

## 09_AI_AGENTS.md: Incorrect `Used By` Reference

- `09_AI_AGENTS.md` (line 382) lists `17_API_REFERENCE.md` in its `Used By` section. However, `17_API_SPECIFICATION.md` was generated, not `17_API_REFERENCE.md`. This is a naming inconsistency for the API document.

**Action**: Correct the reference in `09_AI_AGENTS.md` to `16_API_SPECIFICATION.md` (assuming `16_API_SPECIFICATION.md` is the correct document for API details, as `17_REPORT_GENERATOR.md` is the actual document 17). If there is a separate API Reference document intended, it needs to be created and correctly numbered.

---

## 09_AI_AGENTS.md: Consistency in Migration Journal Usage

- `09_AI_AGENTS.md` emphasizes the use of the Migration Journal by every AI agent to avoid repeating failed solutions. This is consistent with `12_MIGRATION_JOURNAL.md` and the overall system philosophy.

**Action**: No action needed, this is consistent.

---

## 09_AI_AGENTS.md: Consistency in Compiler Authority

- `09_AI_AGENTS.md` clearly states that the compiler is the final authority and its decisions override AI output. This is consistent with `00_SYSTEM_SPECIFICATION.md` and `02_SYSTEM_ARCHITECTURE.md`.

**Action**: No action needed, this is consistent.
## 10_COMPILATION_PIPELINE.md vs. 05_USER_FLOW.md (Workflow Phases and Stages)

- `10_COMPILATION_PIPELINE.md` details the compilation pipeline with stages like "Workspace Preparation", "HIP Translation", "Semantic Compatibility Analysis", "Initial Compilation", "AI Repair Pipeline", and "Research Recovery". These stages need to be explicitly mapped to the six phases defined in `05_USER_FLOW.md` ("Project Upload", "Automatic Translation", "Compilation Validation", "Intelligent Repair", "Report Generation", "Download") to ensure a consistent understanding of the workflow across documents.

**Action**: Create a clear mapping between the stages in `10_COMPILATION_PIPELINE.md` and the phases in `05_USER_FLOW.md`. Update `05_USER_FLOW.md` or `02_SYSTEM_ARCHITECTURE.md` to reference these detailed stages where appropriate.

---

## 10_COMPILATION_PIPELINE.md: Checkpoint Creation (New Concept)

- `10_COMPILATION_PIPELINE.md` introduces the concept of "Checkpoint Creation" (Stage 1.5, lines 167-213) as a mechanism for rollbacks and debugging. This is a crucial internal mechanism that is not explicitly mentioned as a distinct stage or concept in higher-level architectural documents like `00_SYSTEM_SPECIFICATION.md`, `02_SYSTEM_ARCHITECTURE.md`, `05_USER_FLOW.md`, or `07_WORKFLOW_ENGINE.md`. While it's an implementation detail, its impact on reliability and debuggability warrants at least a high-level mention in relevant architectural overviews.

**Action**: Introduce the concept of "Checkpoint Creation" in `02_SYSTEM_ARCHITECTURE.md` and `07_WORKFLOW_ENGINE.md` as a key mechanism for ensuring reliability and recoverability during the migration process. Briefly explain its purpose and how it supports rollback capabilities.

---

## 10_COMPILATION_PIPELINE.md vs. 05_USER_FLOW.md and 06_WORKSPACE_ARCHITECTURE.md (Export Package Contents)

- The "Generated Artifacts" section in `10_COMPILATION_PIPELINE.md` (lines 440-467) lists the contents of the final export. This list includes `converted_project/`, `checkpoints/`, `analysis/`, `patches/`, `research/`, `logs/`, `reports/`, `migration_risks.json`, `migration_journal.json`, `compatibility_report.md`, `git_patch.diff`, `README.md`. This list is more comprehensive than what was previously noted in `05_USER_FLOW.md` and `06_WORKSPACE_ARCHITECTURE.md`.

**Action**: Unify the list of contents for the downloadable package across `05_USER_FLOW.md`, `06_WORKSPACE_ARCHITECTURE.md`, and `10_COMPILATION_PIPELINE.md`. The most comprehensive list from `10_COMPILATION_PIPELINE.md` should be adopted as the definitive one.

---

## 10_COMPILATION_PIPELINE.md: Missing `Used By` References

- `10_COMPILATION_PIPELINE.md` does not contain a `Used By` section, which is present in most other documents. This is an inconsistency in the document structure.

**Action**: Add a `Used By` section to `10_COMPILATION_PIPELINE.md` listing documents that depend on it, consistent with the pattern established in other documents.
## 11_RESEARCH_AGENT.md vs. Other Documents (Terminology: "Research Engine" vs. "Research Agent")

- `11_RESEARCH_AGENT.md` consistently uses the term "Research Engine" in its title and throughout the document. However, `00_SYSTEM_SPECIFICATION.md`, `02_SYSTEM_ARCHITECTURE.md`, `05_USER_FLOW.md`, `07_WORKFLOW_ENGINE.md`, `08_REDIS_ARCHITECTURE.md`, `09_AI_AGENTS.md`, and `10_COMPILATION_PIPELINE.md` all refer to this component as the "Research Agent". This is a clear terminology conflict.

**Action**: Unify terminology to "Research Agent" across all documents, including `11_RESEARCH_AGENT.md`.

---

## 11_RESEARCH_AGENT.md: Consistency in `Used By` References

- `11_RESEARCH_AGENT.md` lists specific document filenames in its `Used By` section. This is consistent with the established pattern.

**Action**: No action needed, this is consistent.

---

## 11_RESEARCH_AGENT.md: Consistency with AI Agent Roles

- The responsibilities and restrictions of the "Research Engine" (which should be "Research Agent") are consistent with the high-level descriptions in `09_AI_AGENTS.md`.

**Action**: No action needed, this is consistent.
## 12_MIGRATION_JOURNAL.md vs. Other Documents (Terminology: "Migration Journal" vs. "Migration Journal")

- `12_MIGRATION_JOURNAL.md` consistently uses the term "Migration Journal". This reinforces the need to unify this terminology across all documents, specifically updating references to "Migration Journal" in `00_SYSTEM_SPECIFICATION.md`, `02_SYSTEM_ARCHITECTURE.md`, `04_TECHNOLOGY_DECISIONS.md`, and `08_REDIS_ARCHITECTURE.md`.

**Action**: Unify terminology to "Migration Journal" across all documents.

---

## 12_MIGRATION_JOURNAL.md vs. 05_USER_FLOW.md and 10_COMPILATION_PIPELINE.md (Export Package Contents)

- `12_MIGRATION_JOURNAL.md` (lines 274-280) states that the export package includes `migration_report.md` and `migration_journal.json`. This is a less comprehensive list than what is provided in `05_USER_FLOW.md` and `10_COMPILATION_PIPELINE.md`.

**Action**: Unify the list of contents for the downloadable package across `05_USER_FLOW.md`, `06_WORKSPACE_ARCHITECTURE.md`, and `10_COMPILATION_PIPELINE.md` to the most comprehensive list, and ensure `12_MIGRATION_JOURNAL.md` reflects this unified list.

---

## 12_MIGRATION_JOURNAL.md: Dependency Reference to `11_RESEARCH_AGENT.md`

- `12_MIGRATION_JOURNAL.md` (line 317) lists `11_RESEARCH_AGENT.md` as a dependency. Following the planned terminology unification, this should be updated to `11_RESEARCH_AGENT.md`.

**Action**: Update the dependency reference in `12_MIGRATION_JOURNAL.md` to `11_RESEARCH_AGENT.md`.

---

## 12_MIGRATION_JOURNAL.md: Consistency in AI Agent Naming

- `12_MIGRATION_JOURNAL.md` uses "Analysis Agent", "Patch Agent", and "Research Agent" in its journal entry example and workflow timeline, which is consistent with the unified terminology.

**Action**: No action needed, this is consistent.

---

## 12_MIGRATION_JOURNAL.md: Consistency in Compiler Authority

- `12_MIGRATION_JOURNAL.md` reiterates that the compiler always determines correctness, consistent with other documents.

**Action**: No action needed, this is consistent.
## 13_BACKEND.md vs. 00_SYSTEM_SPECIFICATION.md and 04_TECHNOLOGY_DECISIONS.md ("Framework-independent" Goal)

- `13_BACKEND.md` lists "Framework-independent" as a goal (line 27) but is explicitly implemented using FastAPI. This is a nuance previously identified in `04_TECHNOLOGY_DECISIONS.md`. While individual modules can be framework-independent, the backend service itself is built on a framework.

**Action**: Clarify in `13_BACKEND.md` that while internal modules and business logic aim for framework independence, the overall backend service leverages FastAPI as its chosen web framework, consistent with `04_TECHNOLOGY_DECISIONS.md`.

---

## 13_BACKEND.md vs. 02_SYSTEM_ARCHITECTURE.md and 07_WORKFLOW_ENGINE.md (Workflow Engine/Workflow Engine Terminology)

- `13_BACKEND.md` uses "Workflow Engine" consistently in its text and folder structure (`workflow/` at line 97). However, its 
## 13_BACKEND.md vs. 00_SYSTEM_SPECIFICATION.md and 04_TECHNOLOGY_DECISIONS.md ("Framework-independent" Goal)

- `13_BACKEND.md` lists "Framework-independent" as a goal (line 27) but is explicitly implemented using FastAPI. This is a nuance previously identified in `04_TECHNOLOGY_DECISIONS.md`. While individual modules can be framework-independent, the backend service itself is built on a framework.

**Action**: Clarify in `13_BACKEND.md` that while internal modules and business logic aim for framework independence, the overall backend service leverages FastAPI as its chosen web framework, consistent with `04_TECHNOLOGY_DECISIONS.md`.

---

## 13_BACKEND.md vs. 07_WORKFLOW_ENGINE.md (AI Workflow Engine Responsibility)

- `13_BACKEND.md` (line 513) lists "AI workflow_engine" as a responsibility of the backend. However, `07_WORKFLOW_ENGINE.md` clearly states that the Workflow Engine is responsible for coordinating AI agents and controlling workflow execution. The backend's role should be to *invoke* the Workflow Engine, which then orchestrates AI.

**Action**: Clarify the backend's responsibility regarding AI agents. The backend *invokes* the Workflow Engine, which *orchestrates* the AI agents. Update the "Responsibilities" section in `13_BACKEND.md` to reflect this.

---

## 13_BACKEND.md: Consistency in Folder Structure Naming (`workflow/`)

- `13_BACKEND.md` (lines 97 and 193) uses `workflow/` for the Workflow Engine. This is consistent with the proposed unification to "Workflow Engine".

**Action**: No action needed, this is consistent.

---

## 13_BACKEND.md: Incorrect `Used By` Reference to `15_DOCKER_SETUP.md`

- `13_BACKEND.md` (line 549) refers to `15_DOCKER_SETUP.md`. The document generated is `15_DOCKER_SETUP.md`.

**Action**: Correct the reference in `13_BACKEND.md` to `15_DOCKER_SETUP.md`.

---

## 13_BACKEND.md: Consistency in AI Agent Naming

- `13_BACKEND.md` (lines 213-217 and 354-359) uses "AnalysisAgent", "PatchAgent", and "ResearchAgent" consistently, aligning with the unified terminology.

**Action**: No action needed, this is consistent.
## 14_FRONTEND.md vs. 05_USER_FLOW.md, 06_WORKSPACE_ARCHITECTURE.md, and 10_COMPILATION_PIPELINE.md (Export Package Naming and Contents)

- `14_FRONTEND.md` refers to a "Download ZIP" and a "Download button" for the final package. This needs to be consistent with the unified name `HIPForge_Migration.zip` and the comprehensive list of contents identified from `10_COMPILATION_PIPELINE.md`.

**Action**: Ensure the frontend UI elements and any related documentation consistently refer to the final downloadable package as `HIPForge_Migration.zip` and reflect the unified contents.

---

## 14_FRONTEND.md: Incorrect `Used By` Reference to `15_DOCKER_SETUP.md`

- `14_FRONTEND.md` (line 412) refers to `15_DOCKER_SETUP.md`. The document generated is `15_DOCKER_SETUP.md`.

**Action**: Correct the reference in `14_FRONTEND.md` to `15_DOCKER_SETUP.md`.

---

## 14_FRONTEND.md: Consistency in AI Agent Naming

- `14_FRONTEND.md` (lines 224-228) uses "Analysis Agent", "Patch Agent", and "Research Agent" consistently, aligning with the unified terminology.

**Action**: No action needed, this is consistent.

---

## 14_FRONTEND.md: Consistency in Workflow Progress Stages

- The "Migration Progress" component (lines 163-197) lists stages that align well with the states defined in `07_WORKFLOW_ENGINE.md` and the phases in `05_USER_FLOW.md`.

**Action**: No action needed, this is consistent.

---

## 14_FRONTEND.md: Consistency in Migration Journal Terminology

- `14_FRONTEND.md` (lines 134, 236) consistently uses "Migration Journal", aligning with the unified terminology.

**Action**: No action needed, this is consistent.

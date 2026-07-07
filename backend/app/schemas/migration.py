from pydantic import BaseModel, Field

class UploadMigrationRequest(BaseModel):
    file: str = Field(..., description="Base64 encoded or raw content of the source file")
    filename: str = Field(..., description="Name of the file (e.g. kernel.cu)")
    target_gpu_architecture: str = Field(..., description="Target architecture, e.g. gfx90a")
    retry_budget: int = Field(default=5, ge=0, description="Max retry attempts for compilation fixes")
    migration_mode: str = Field(..., description="Migration mode")

class PasteMigrationRequest(BaseModel):
    code: str = Field(..., description="Raw CUDA source code string")
    filename: str = Field(..., description="Name of the file (e.g. kernel.cu)")
    target_gpu_architecture: str = Field(..., description="Target architecture, e.g. gfx90a")
    retry_budget: int = Field(default=5, ge=0, description="Max retry attempts for compilation fixes")
    migration_mode: str = Field(..., description="Migration mode")

class MigrationResponse(BaseModel):
    migration_id: str
    status: str
    message: str

class MigrationStatusResponse(BaseModel):
    migration_id: str
    status: str
    stage: str
    created_at: str
    updated_at: str
    current_stage: str | None = None
    progress: float = 0.0
    message: str = ""
    error_category: str | None = None
    recommended_next_action: str | None = None
    project_scan: dict | None = None
    stage_timings: dict | None = None
    validation_confidence: str | None = None
    validation_confidence_reason: str | None = None
    compile_status: str | None = None
    runtime_validation_status: str | None = None
    compiler_mode: str | None = None
    compile_command: str | None = None
    main_error: str | None = None

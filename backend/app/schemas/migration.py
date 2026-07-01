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

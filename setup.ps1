# Phase entered)
# This script is now PowerShell-compatible

# Exit immediately if any command fails
$ErrorActionPreference = "Stop"

# Colors for output
$Red = "\u001b[31m"
$Green = "\u001b[32m"
$Yellow = "\u001b[33m"
$NC = "\u001b[0m" # No Color

# Logging functions
function log { param($message) Write-Host "${Green}[HIPFORGE DEMOS]${NC} $message" }

function error { param($message) Write-Host "${Red}[ERROR]${NC} $message" -ForegroundColor Red }

function warn { param($message) Write-Host "${Yellow}[WARN]${NC} $message" -ForegroundColor Yellow }

# Detect Python executable
$pythonExe = $null
if (Get-Command python3 -ErrorAction SilentlyContinue) { $pythonExe = "python3" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pythonExe = "python" }

if (-not $pythonExe) {
    error "Python3 not found. Please install Python 3.7 or higher."
    exit 1
}

Write-Host "Using Python: $(& $pythonExe --version)"

# Store original directory
$originalDir = Get-Location

# Phase 1: Backend setup
log "Phase 1: Setting up backend environment..."

if (Test-Path "backend" -PathType Container) {
    Set-Location "backend"
} else {
    error "Cannot navigate to backend directory. Please ensure backend/ exists."
    exit 1
}

# Create and activate virtual environment
if (Test-Path "venv" -PathType Container) {
    log "Backend Python virtual environment already exists"
    # Try to activate if possible (PowerShell doesn't directly support venv activation)
    $env:VIRTUAL_ENV = (Get-Item "venv").FullName
} else {
    log "Creating backend Python virtual environment..."
    & $pythonExe -m venv venv
    if (Test-Path "venv" -PathType Container) {
        $env:VIRTUAL_ENV = (Get-Item "venv").FullName
        log "Virtual environment created"
    } else {
        error "Failed to create virtual environment"
        Set-Location "$originalDir"
        exit 1
    }
}

# Install/upgrade pip
log "Installing/updating Python dependencies..."
& $pythonExe -m pip install --upgrade pip

if (Test-Path "requirements.txt") {
    & $pythonExe -m pip install --no-cache-dir -r requirements.txt
} else {
    error "backend/requirements.txt not found. Cannot install dependencies."
    Set-Location "$originalDir"
    exit 1
}

Set-Location "$originalDir"
log "OK Backend setup complete"

# Phase 2: Frontend setup (optional)
log "Phase 2: Setting up frontend..."
if (Test-Path "frontend" -PathType Container) {
    Set-Location "frontend"
    
    if (Test-Path "node_modules" -PathType Container) {
        log "Frontend node_modules already exists"
    } else {
        log "Installing frontend dependencies..."
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            & npm install
        } else {
            warn "npm not found. Install Node.js to install frontend dependencies."
        }
    }
    
    Set-Location "$originalDir"
} else {
    warn "Cannot navigate to frontend directory. Skipping frontend setup."
}

# Phase 3: Environment configuration
log "Phase 3: Setting up environment configuration..."

cd "$originalDir"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        log "Creating .env from .env.example..."
        Copy-Item ".env.example" ".env"
    } else {
        error ".env file not found. Please create .env with required environment variables."
        exit 1
    }
} else {
    log "OK .env file exists"
}

# Check critical environment variables
$criticalVars = @("FIREWORKS_API_KEY", "REDIS_URL", "WORKSPACE_PATH")
$missingVars = @()
$content = if (Test-Path ".env") { Get-Content ".env" -Raw } else { "" }

foreach ($var in $criticalVars) {
    if (-not (Test-Path ".env")) {
        continue
    }
    
    $match = [regex]::Match($content, "(?m)^$([regex]::Escape($var))=(.*)$")
    if (-not $match.Success) {
        $missingVars += $var
    } else {
        $value = $match.Groups[1].Value.Trim()
        if ($value -eq "your_fireworks_api_key" -or [string]::IsNullOrEmpty($value)) {
            warn "Environment variable $var is unset or still set to default placeholder"
        } else {
            log "OK $var is set"
        }
    }
}

if ($missingVars.Count -gt 0) {
    Write-Host "Missing critical environment variables:"
    foreach ($var in $missingVars) {
        Write-Host "  - $var"
    }
    Write-Host "Please edit .env file to set these variables."
    Write-Host "See .env.example for examples."
}

# Phase 4: Workspace structure
log "Phase 4: Setting up workspace structure..."

$migrationId = Get-Date -Format "yyyyMMdd_HHmmss"
$workspaceDir = "workspace/$migrationId"
New-Item -ItemType Directory -Path $workspaceDir -Force | Out-Null

$inputDir = "$workspaceDir/input"
New-Item -ItemType Directory -Path $inputDir -Force | Out-Null

New-Item -ItemType Directory -Path "$workspaceDir/exports" -Force | Out-Null
New-Item -ItemType Directory -Path "workspace/logs" -Force | Out-Null
New-Item -ItemType Directory -Path "workspace/artifacts" -Force | Out-Null
New-Item -ItemType Directory -Path "workspace/generated" -Force | Out-Null
New-Item -ItemType Directory -Path "workspace/patches" -Force | Out-Null
New-Item -ItemType Directory -Path "workspace/reports" -Force | Out-Null

# Create a test CUDA file
@'
#include <cuda_runtime.h>
#include <stdio.h>

__global__ void vector_add(int *result, int *a, int *b, int n) {
    int i = threadIdx.x;
    if (i < n) {
        result[i] = a[i] + b[i];
    }
}

int main() {
    const int n = 8;
    int a[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    int b[8] = {10, 20, 30, 40, 50, 60, 70, 80};
    int result[8];

    int *dev_a, *dev_b, *dev_result;

    cudaMalloc(&dev_a, n * sizeof(int));
    cudaMalloc(&dev_b, n * sizeof(int));
    cudaMalloc(&dev_result, n * sizeof(int));

    cudaMemcpy(dev_a, a, n * sizeof(int), cudaMemcpyHostToDevice);
    cudaMemcpy(dev_b, b, n * sizeof(int), cudaMemcpyHostToDevice);

    vector_add<<<1, n>>>(dev_result, dev_a, dev_b, n);

    cudaMemcpy(result, dev_result, n * sizeof(int), cudaMemcpyDeviceToHost);

    printf("Results: ");
    for (int i = 0; i < n; ++i) {
        printf("%d ", result[i]);
    }
    printf("\n");

    cudaFree(dev_a);
    cudaFree(dev_b);
    cudaFree(dev_result);

    return 0;
}
'@ | Set-Content -Path (Join-Path $inputDir "test_cuda.cu") -Encoding UTF8

log "OK Created test CUDA project"

# Phase 5: Docker Compose verification
log "Phase 5: Checking Docker Compose configuration..."

if (Test-Path "docker-compose.yml") {
    log "Docker Compose configuration found"
    Write-Host "Note: Review docker-compose.yml for Docker socket access requirements."
    Write-Host "Worker may not be able to create sandboxes without Docker socket mounting."
} else {
    warn "docker-compose.yml not found"
}

log "=== Setup Complete ==="
Write-Host ""
Write-Host "HIPForge demo environment is now set up!"
Write-Host ""
Write-Host "To run a demo migration:"
Write-Host "1. Ensure Python virtual environment is active:"
Write-Host "   backend\\venv\\Scripts\\activate    # Windows"
Write-Host "   cd backend && python -m pip install -r requirements.txt"
Write-Host ""
Write-Host "2. Start services (if using Docker Compose):"
Write-Host "   docker-compose up -d"
Write-Host ""
Write-Host "3. Test the setup:"
Write-Host "   ./demo_test.sh all"
Write-Host ""
Write-Host "4. Upload a CUDA project or use the provided test project:"
Write-Host "   The workspace/$migrationId/input/test_cuda.cu contains a sample CUDA program."
Write-Host ""
Write-Host "For detailed documentation, see README_DEMO.md"
Write-Host "For troubleshooting, see setup issues in README_DEMO.md"

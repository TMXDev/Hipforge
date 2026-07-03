#!/bin/bash
# HIPForge Environment Setup Script
# Phase 1: Demo Readiness Setup

# Exit immediately if any command fails
exit_on_error() {
    echo "Error on line $1:"
    sed -n "$1 p" "$0" >&2
    exit 1
}

# Set up error handling
trap 'exit_on_error $LINENO' ERR

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
# Store original directory at the very beginning
ORIGINAL_DIR="$(pwd)"

log() {
    echo -e "${GREEN}[HIPFORGE]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if running with elevated privileges
if [ $EUID -ne 0 ]; then 
   echo "This script may need sudo privileges for Docker."
fi

# Start of setup
{
    log "Starting HIPForge Environment Setup..."
    log "Current directory: $(pwd)"
    log "Original directory: $ORIGINAL_DIR"
}

# Phase 1A: System and Software Prerequisites
{
    log "Phase 1A: Checking system prerequisites..."

    # Check for required commands
    for cmd in python3 python pip git docker node npm; do
        if command -v $cmd >/dev/null 2>&1; then
            version=$($cmd --version 2>&1 | head -1)
            log "✓ $cmd available: $version"
        else
            warn "$cmd not found. Install $cmd or ensure PATH includes it."
        fi
    done

    # Check for pip and Python 3.11 or higher
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo "Python version: $python_version"
}

# Phase 1B: Backend setup
{
    log "Phase 1B: Setting up backend..."
    cd backend || {
        error "Cannot navigate to backend directory. Please ensure backend/ exists."
        exit 1
    }

    # Check for virtual environment
    if [ -d "venv" ]; then
        log "Backend Python virtual environment already exists"
        source venv/bin/activate || source venv/Scripts/activate
    else
        log "Creating backend Python virtual environment..."
        python3 -m venv venv
        source venv/bin/activate || source venv/Scripts/activate

        # Upgrade pip
        pip install --upgrade pip

        # Install backend dependencies
        if [ -f "requirements.txt" ]; then
            log "Installing Python dependencies..."
            pip install --no-cache-dir -r requirements.txt
        else
            error "backend/requirements.txt not found. Cannot install Python dependencies."
            exit 1
        fi
    fi

    # Test backend imports
    log "Testing backend imports..."
    python3 - <<'PYEOF'
import sys
modules_to_test = [
    'app.diagnostics',
    'app.main',
    'app.services.migration_service',
    'app.redis.client',
    'app.compiler.hipify_runner',
    'app.compiler.hipcc_runner',
    'app.workflow_engine.state_machine'
]

all_ok = True
for module in modules_to_test:
    try:
        __import__(module)
        print(f"✓ {module} imported successfully")
    except ImportError as e:
        print(f"✗ {module} import failed: {e}")
        all_ok = False

if all_ok:
    print("\nAll backend imports work!")
else:
    print("\nSome backend imports failed. Please check the errors above.")
    sys.exit(1)
PYEOF
    cd ..
}

# Phase 1C: Frontend setup (if needed)
{
    log "Phase 1C: Setting up frontend..."
    cd frontend || {
        warn "Cannot navigate to frontend directory. Skipping frontend setup."
        cd .. && exit 0
    }

    # Check if node_modules exists
    if [ -d "node_modules" ]; then
        log "Frontend node_modules already exists"
        # Test if npm scripts work
        if command -v npm >/dev/null 2>&1 && npm run build --dry-run 2>/dev/null; then
            log "✓ Frontend npm build configuration seems valid"
        else
            warn "Frontend build configuration may be invalid"
        fi
    else
        log "Installing frontend dependencies..."
        if command -v npm >/dev/null 2>&1; then
            npm install
        else
            error "npm not found. Please install Node.js."
            cd .. && exit 1
        fi
    fi

    # Quick build test
    log "Testing frontend build..."
    if npm run build 2>&1 | tail -10 | grep -q "Build completed"; then
        log "✓ Frontend build successful"
    else
        warn "Frontend build may have issues. Check output above."
    fi
    cd ..
}

# Phase 1D: Docker compatibility check
{
    log "Phase 1D: Checking Docker compatibility..."

    if command -v docker >/dev/null 2>&1; then
        docker_version=$(docker --version 2>&1 | awk '{print $3}')
        log "Docker available: $docker_version"

        # Check Docker socket permissions (common issue)
        if [ -S /var/run/docker.sock ]; then
            log "✓ Docker socket available at /var/run/docker.sock"
        else
            warn "Docker socket not available at /var/run/docker.sock."
            warn "  Sandbox features may not work from within Docker containers."
        fi

        # Try to pull sandbox image (non-blocking)
        SANDBOX_IMAGE=$(grep -E "^HIPFORGE_SANDBOX_IMAGE=" .env | cut -d'=' -f2 | tr -d '"' 2>/dev/null)
        if [ -z "$SANDBOX_IMAGE" ]; then
            SANDBOX_IMAGE="rocm/dev-ubuntu-22.04"
        fi

        log "Testing sandbox image availability ($SANDBOX_IMAGE)..."
        docker pull $SANDBOX_IMAGE >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            log "✓ Sandbox image '$SANDBOX_IMAGE' is available"
        else
            warn "Sandbox image '$SANDBOX_IMAGE' may not be available locally."
            warn "  This may be expected if running inside a Docker container."
        fi
    else
        warn "Docker not found. Sandbox features will not work."
    fi
}

# Phase 1E: Environment configuration
{
    log "Phase 1E: Checking environment configuration..."

    cd ..

    # Check if .env exists
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            log "Creating .env from .env.example..."
            cp .env.example .env
            echo "Please edit .env to configure your environment variables."
            echo "Current .env contents:"
            cat .env
        else
            error ".env file not found and .env.example does not exist."
            echo "Please create .env with required environment variables."
        fi
    else
        log "✓ .env file exists"
    fi

    # Check for critical environment variables
    critical_vars=(FIREWORKS_API_KEY REDIS_URL WORKSPACE_PATH)
    for var in "${critical_vars[@]}"; do
        if ! grep -q "^$var=" .env 2>/dev/null; then
            warn "Environment variable $var not set in .env"
        else
            value=$(grep "^$var=" .env | cut -d'=' -f2)
            if [ "$value" = "your_fireworks_api_key" ] || [ -z "$value" ]; then
                warn "Environment variable $var is unset or still set to default placeholder"
            else
                log "✓ $var is set"
            fi
        fi
    done
}

# Phase 1F: Workspace setup
{
    log "Phase 1F: Setting up workspace structure..."

    # Create workspace directories
    workspace_base="workspace"

    mkdir -p "$workspace_base/2026/input"
    mkdir -p "$workspace_base/2026/exports"
    mkdir -p "$workspace_base/2026/logs"
    mkdir -p "$workspace_base/2026/artifacts"
    mkdir -p "$workspace_base/2026/generated"
    mkdir -p "$workspace_base/2026/patches"
    mkdir -p "$workspace_base/2026/reports"

    # Create a test input file
    mkdir -p "$workspace_base/2026/input"
    cat > "$workspace_base/2026/input/test_cuda.cu" <<'EOF'
#include <cuda_runtime.h>
#include <stdio.h>

__global__ void vector_add(int *a, int *b, int *c, int n) {
    int i = threadIdx.x;
    if (i < n) {
        c[i] = a[i] + b[i];
    }
}

int main() {
    int n = 4;
    int a[4] = {1, 2, 3, 4};
    int b[4] = {5, 6, 7, 8};
    int c[4];

    int *dev_a, *dev_b, *dev_c;
    
    cudaMalloc(&dev_a, n * sizeof(int));
    cudaMalloc(&dev_b, n * sizeof(int));
    cudaMalloc(&dev_c, n * sizeof(int));

    cudaMemcpy(dev_a, a, n * sizeof(int), cudaMemcpyHostToDevice);
    cudaMemcpy(dev_b, b, n * sizeof(int), cudaMemcpyHostToDevice);

    vector_add<<<1, n>>>(dev_a, dev_b, dev_c, n);

    cudaMemcpy(c, dev_c, n * sizeof(int), cudaMemcpyDeviceToHost);

    printf("Results: ");
    for (int i = 0; i < n; ++i) {
        printf("%d ", c[i]);
    }
    printf("\n");

    cudaFree(dev_a);
    cudaFree(dev_b);
    cudaFree(dev_c);

    return 0;
}
EOF

    log "✓ Workspace directories and test CUDA file created"
}

# Phase 1G: Docker Compose fix verification
{
    log "Phase 1G: Verifying Docker Compose configuration..."

    if [ -f "docker-compose.yml" ]; then
        # Check if migration-worker has Docker socket access
        if grep -A 10 "migration-worker:" docker-compose.yml | grep -q "volumes:" && grep -A 20 "migration-worker:" docker-compose.yml | grep -q "/var/run/docker.sock"; then
            log "✓ Docker socket is mounted in docker-compose.yml"
        else
            warn "Docker socket is not mounted. Worker may not be able to create sandboxes."
            warn "  Consider updating docker-compose.yml with:
                volumes:
                  - /var/run/docker.sock:/var/run/docker.sock
                  - ./workspace:/app/workspace"
        fi
    else
        warn "docker-compose.yml not found"
    fi
}

log "Phase 1 complete. Environment is now set up."
log "\nNext steps:"
log "1. Test the setup with: ./demo_test.sh"
log "2. Check backend status with: python -m app.main (when ready)"
log "3. Run a demo migration in mock mode (see README_DEMO.md for details)"
log "\nFor a comprehensive demo test, run:"
log "./demo_test.sh --mode comprehensive"

# Return to original directory
cd "$ORIGINAL_DIR" 2>/dev/null || cd "$(pwd | cut -d'/' -f1-3)"
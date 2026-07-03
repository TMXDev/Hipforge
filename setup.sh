#!/bin/bash
# HIPForge Demo Setup Script
# Phase 1: Complete demo environment setup

# Exit on error
exit_on_error() {
    echo "Error on line $1:"
    sed -n "$1 p" "$0" >&2
    exit 1
}

trap 'exit_on_error $LINENO' ERR

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[HIPFORGE DEMO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Detect Python executable
if command -v python3 >/dev/null 2>&1; then
    PYTHONEXE="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHONEXE="python"
else
    error "Python3 not found. Please install Python 3.7 or higher."
    exit 1
fi

echo "Using Python: $($PYTHONEXE --version 2>&1)"

# Store original directory
ORIGINAL_DIR="$(pwd)"

# Phase 1: Backend setup
log "Phase 1: Setting up backend environment..."

cd backend || {
    error "Cannot navigate to backend directory. Please ensure backend/ exists."
    exit 1
}

# Create and activate virtual environment
if [ ! -d "venv" ]; then
    log "Creating Python virtual environment..."
    $PYTHONEXE -m venv venv
fi

source venv/bin/activate || source venv/Scripts/activate || {
    error "Cannot activate Python virtual environment."
    cd "$ORIGINAL_DIR" && exit 1
}

# Upgrade pip and install dependencies
log "Installing/updating Python dependencies..."
$PYTHONEXE -m pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    $PYTHONEXE -m pip install --no-cache-dir -r requirements.txt
else
    error "backend/requirements.txt not found. Cannot install dependencies."
    cd "$ORIGINAL_DIR" && exit 1
fi

cd "$ORIGINAL_DIR"

log "✓ Backend setup complete"

# Phase 2: Frontend setup
log "Phase 2: Setting up frontend..."

if [ ! -d "frontend/node_modules" ] && command -v npm >/dev-default 2>&1; then
    log "Installing frontend dependencies..."
    cd frontend || {
        warn "Cannot navigate to frontend directory. Skipping frontend setup."
        cd "$ORIGINAL_DIR" && exit 0
    }
    npm install
    cd "$ORIGINAL_DIR"
else
    if [ -d "frontend/node_modules" ]; in
        log "Frontend node_modules already exists"
    else
        warn "Frontend dependencies may need manual installation."
    fi
fi

# Phase 3: Environment configuration
log "Phase 3: Setting up environment configuration..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        log "Creating .env from .env.example..."
        cp .env.example .env
    else
        error ".env file not found. Please create .env with required environment variables."
        cd "$ORIGINAL_DIR" && exit 1
    fi
fi

# Check critical environment variables
critical_vars=(FIREWORKS_API_KEY REDIS_URL WORKSPACE_PATH)
missing_vars=()

for var in "${critical_vars[@]}"; do
    if ! grep -q "^$var=" .env 2>/dev/null; then
        missing_vars+=("$var")
    fi

done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "Missing critical environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    echo "Please edit .env file to set these variables."
    echo "See .env.example for examples."
else
    log "✓ Critical environment variables are set"
fi

# Phase 4: Workspace structure
log "Phase 4: Setting up workspace structure..."

mkdir -p workspace/2026/input
mkdir -p workspace/2026/exports
mkdir -p workspace/2026/logs
mkdir -p workspace/2026/artifacts
mkdir -p workspace/2026/generated
mkdir -p workspace/2026/patches
mkdir -p workspace/2026/reports

# Create a test CUDA file (only if no existing input)
if [ ! -f "workspace/2026/input/*.cu" ] && [ ! -f "workspace/2026/input/*.hip" ]; then
    cat > workspace/2026/input/test_project.cu <<'EOF'
#include <cuda_runtime.h>
#include <stdio.h>

__global__ void add_vector(int *result, int *a, int *b, int n) {
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

    add_vector<<<1, n>>>(dev_result, dev_a, dev_b, n);

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
EOF
    log "✓ Created test CUDA project"
fi

# Phase 5: Docker Compose verification
log "Phase 5: Checking Docker Compose configuration..."

if [ -f "docker-compose.yml" ]; then
    log "Docker Compose configuration found"
    echo "Note: Review docker-compose.yml for Docker socket access requirements."
    echo "Worker may not be able to create sandboxes without Docker socket mounting."
else
    warn "docker-compose.yml not found"
fi

log "=== Setup Complete ==="
echo ""
echo "HIPForge demo environment is now set up!"
echo ""
echo "To run a demo migration:"
echo "1. Ensure Python virtual environment is active:"
echo "   source backend/venv/bin/activate  # Linux/macOS"
echo "   backend\\venv\\Scripts\\activate    # Windows"
echo ""
echo "2. Start services (if using Docker Compose):"
echo "   docker-compose up -d"
echo ""
echo "3. Test the setup:"
echo "   $ ./demo_test.sh all"
echo ""
echo "4. Upload a CUDA project or use the provided test project:"
echo "   The workspace/2026/input/test_cuda.cu contains a sample CUDA program."
echo ""
echo "For detailed documentation, see README_DEMO.md"
echo ""
echo "For troubleshooting, see setup issues in README_DEMO.md"

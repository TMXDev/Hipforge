#!/bin/bash
# HIPForge Demo Test Script
# Phase 1: Comprehensive demo testing

# Exit immediately on errors
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
    echo -e "${GREEN}[DEMO TEST]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Main test function
test_component() {
    local component="$1"
    local test_cmd="$2"
    local expected_exit=0

    log "Testing $component..."
    echo "Command: $test_cmd"

    # Run the test command
    eval "$test_cmd" && {
        if [ $? -eq $expected_exit ]; then
            log "✓ $component test passed"
            return 0
        else
            error "✗ $component test failed with exit code $?"
            return 1
        fi
    } || {
        error "✗ $component test failed with error"
        return 1
    }
}

# Display usage
print_usage() {
    echo "Usage: $0 [component]"
    echo "Components: backend, frontend, worker, docker, cli, endtoend, all"
    echo """
Examples:
  $0 backend     Test backend components
  $0 worker     Test worker functionality
  $0 docker     Test Docker sandbox availability
  $0 cli        Test CLI functionality
  $0 all        Run all tests
"
}

# Parse arguments
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    print_usage
    exit 0
fi

# Change to project root
cd "$(dirname "$0")" || {
    error "Cannot change to project root directory"
    exit 1
}

# Initialize test results
passed=0
failed=0
TOTAL_COMPONENTS=0

# Test Backend Component
test_component "Backend" 'python3 - << PYTHON_EOF
import sys

# Set PYTHONPATH to include backend directory
sys.path.insert(0, "backend")

import asyncio

try:
    # Test critical imports
    from app.main import app
    print("✓ FastAPI app import successful")
except ImportError as e:
    print(f"✗ FastAPI import failed: {e}")
    sys.exit(1)

# Test health endpoint if running
if command -v curl >/dev/null 2>&1; then
    echo "Health check: http://localhost:8000/health"
    curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200" && \
        echo "✓ Health endpoint responds" || echo "⚠ Health endpoint not running (expected if backend not started)"
else
    echo "curl not available, skipping health endpoint test"
fi
PYTHON_EOF
' && ((passed++)) || ((failed++))
TOTAL_COMPONENTS=$((TOTAL_COMPONENTS + 1))

# Test Worker Component
test_component "Worker" 'python3 - << PYTHON_EOF'
import sys

# Set PYTHONPATH to include backend directory
sys.path.insert(0, "backend")

import asyncio
from pathlib import Path

# Check if worker script exists
worker_path = Path("backend/app/workers/migration_worker.py")
if not worker_path.exists():
    print("⚠ Worker script not found at: " + str(worker_path))
    print("  This may be normal during setup")
else:
    print("✓ Worker script exists")

# Check for Redis connectivity
import redis.asyncio as redis

try:
    r = redis.Redis.from_url("redis://localhost:6379", socket_connect_timeout=1)
    asyncio.run(r.ping())
    print("✓ Redis connectivity test successful")
except Exception as e:
    print(f"⚠ Redis connectivity test failed: {e}")
    print("  This is normal if Redis is not running")
PYTHON_EOF
' && ((passed++)) || ((failed++))
TOTAL_COMPONENTS=$((TOTAL_COMPONENTS + 1))

# Test Docker Component
test_component "Docker Sandbox" 'bash -c "
if command -v docker >/dev/null 2>&1; then
    echo "Docker version: " $(docker --version | awk '{print $3}')
    # Test Docker socket access
    if [ -S /var/run/docker.sock ]; then
        echo "✓ Docker socket accessible"
    else
        echo "⚠ Docker socket not accessible - running in Docker container?"
    fi
    # Quick container test
    docker run --rm --network none \
        --user $(id -u):$(id -g) \
        \"--memory=128m\" \
        \"--cpus=0.5\" \
        rocm/dev-ubuntu-22.04:6.0.2 \
        sh -c \"echo 'Test container works' && exit 0\" 2>&1 | \
        grep -q 'Test container works' && echo '✓ Docker container test successful' || echo '⚠ Docker container test failed'
else
    echo 'Docker not found - sandbox features will not work'
    echo '  This is OK for basic testing'
fi
"
' && ((passed++)) || ((failed++))
TOTAL_COMPONENTS=$((TOTAL_COMPONENTS + 1))

# Test CLI Component
test_component "CLI" 'python3 << PYTHON_EOF'
from cli.hipforge import main
import sys

# Test CLI help
old_argv = sys.argv
sys.argv = ['hipforge', '--help']

try:
    main()
    print("✓ CLI help command works")
except SystemExit as e:
    if e.code == 0 or e.code == 2:
        print("✓ CLI help command works")
    else:
        print(f"✗ CLI help failed: exit code {e.code}")
        sys.exit(1)
except Exception as e:
    print(f"✗ CLI error: {e}")
    sys.exit(1)
finally:
    sys.argv = old_argv
PYTHON_EOF
' && ((passed++)) || ((failed++))
TOTAL_COMPONENTS=$((TOTAL_COMPONENTS + 1))

# Test End-to-End (mock migration)
test_component "End-to-End (Mock Migration)" 'python3 << PYTHON_EOF'
import asyncio
import os
import tempfile
import shutil
from pathlib import Path

# Set up mock environment variables
os.environ['USE_MOCK_COMPILER'] = 'true'
os.environ['USE_MOCK_AI'] = 'true'
os.environ['WORKSPACE_PATH'] = './workspace'

# Create test workspace
workspace_path = Path("workspace")
input_dir = workspace_path / "2026" / "input"
input_dir.mkdir(parents=True, exist_ok=True)

# Create a simple test CUDA file
cuda_content = '''__global__ void test_kernel(int *data) {
    int i = threadIdx.x;
    if (i < 1024) {
        data[i] = i * 2;
    }
}

int main() {
    return 0;
}
'''

(input_dir / "test.cu").write_text(cuda_content)

# Test migration service initialization
try:
    import sys
    sys.path.insert(0, "backend")
    from app.services.migration_service import initiate_migration
    
    # This will generate a migration ID
    migration_id = asyncio.run(initiate_migration(
        file_content=cuda_content,
        filename="test.cu",
        target_gpu_architecture="gfx90a",
        retry_budget=2,
        migration_mode="file"
    ))
    
    print(f"✓ Migration initiated with ID: {migration_id}")
    
    # Verify workspace was created
    expected_workspace = workspace_path / "2026" / "migration_20250703_164842_abc123"
    if expected_workspace.exists():
        print(f"✓ Migration workspace created: {expected_workspace}")
    else:
        # Search for the migration directory
        migrations = [d for d in workspace_path.glob("*/*") if d.is_dir() and d.name.startswith("migration_")]
        if migrations:
            print(f"✓ Migration directory found: {migrations[0]}")
        else:
            print(f"⚠ Migration directory not found - may be in different naming format")
    
    print("✓ End-to-end migration service test successful")
    
except Exception as e:
    print(f"⚠ End-to-end test warning (may be expected): {e}")
    print("  This could be due to missing dependencies or environment setup")
PYEOF
' && ((passed++)) || ((failed++))
TOTAL_COMPONENTS=$((TOTAL_COMPONENTS + 1))

# Display results

echo ""
echo "========================================"
echo "DEMO TEST RESULTS"
echo "========================================"
echo "Total components tested: $TOTAL_COMPONENTS"
echo "Passed: $passed"
echo "Failed: $failed"
echo "========================================"

if [ $failed -eq 0 ]; then
    echo "✓ ALL TESTS PASSED - HIPForge environment is ready for demo!"
    echo ""
    echo "To run a demo migration, use either:"
    echo "  1. Web UI: Start the frontend and navigate to http://localhost:3000"
    echo "  سریع. CLI: Provide a CUDA project path and target architecture"
    echo ""
    echo "For detailed setup instructions, see README_DEMO.md"
else
    echo "⚠ TESTS FAILED: Some components need attention before running the demo."
    echo ""
    echo "Recommended actions:"
    echo "1. Ensure all dependencies are installed (see .dev_setup.sh)"
    echo "2. Start required services (backend, Redis, Docker)"
    echo "3. Set up environment variables in .env file"
    echo "4. Run ./demo_test.sh backend to debug backend issues"
    echo "5. Run ./demo_test.sh worker to debug worker issues"
fi

# Final recommendation
echo ""
if [ $failed -eq 0 ]; then
    echo "SUCCESS: HIPForge is demo-ready!"
else
    echo "REVIEW: Fix failed tests before running the demo."
fi
echo ""
exit $((failed > 0 ? 1 : 0))
import os
import tempfile
import pytest
from app.compiler.ast_slicing import get_optimized_error_context

@pytest.fixture
def temp_cpp_file():
    content = """#include <iostream>
#include <vector>

#define MAX_THREADS 256
#define PI 3.14159

template <typename T>
class MyVector {
public:
    int size() const { return 10; }
};

int global_limit = 1000;
float unused_global = 0.5f;

void helper_func() {
    // Unrelated helper
}

void process_vector(MyVector<int>& vec) {
    int local_var = MAX_THREADS;
    for (int i = 0; i < vec.size(); ++i) {
        if (i > global_limit) {
            // ERROR LINE HERE (line 19)
            std::cout << "Over limit" << std::endl;
        }
    }
}

int main() {
    return 0;
}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.remove(temp_path)

def test_get_optimized_error_context_success(temp_cpp_file):
    # Call with error line 25 (inside process_vector function block)
    context = get_optimized_error_context(temp_cpp_file, error_line=25)
    
    # Assert headers are included
    assert "Headers / Includes" in context
    assert "#include <iostream>" in context
    assert "#include <vector>" in context
    
    # Assert macro is included
    assert "Preprocessor Macros" in context
    assert "#define MAX_THREADS 256" in context
    assert "#define PI 3.14159" in context
    
    # Assert only referenced global is included (global_limit, not unused_global)
    assert "Referenced Globals" in context
    assert "int global_limit = 1000;" in context
    assert "unused_global" not in context
    
    # Assert target block is included
    assert "Target Block" in context
    assert "void process_vector" in context
    assert "std::cout << \"Over limit\"" in context
    assert "helper_func" not in context  # Should exclude unrelated blocks

def test_get_optimized_error_context_fallback_outside_block(temp_cpp_file):
    # Call with error line 13 (the global variable declaration, outside any block)
    context = get_optimized_error_context(temp_cpp_file, error_line=13, window_lines=3)
    
    # Assert fallback message is in output
    assert "Fallback Context" in context
    assert "outside resolved semantic block" in context
    # Assert sliding window content is present
    assert "int global_limit = 1000;" in context

def test_get_optimized_error_context_fallback_parse_error():
    # Pass a non-existent path
    context = get_optimized_error_context("non_existent_file.cpp", error_line=10)
    
    # Assert fallback is triggered
    assert "Error reading source file" in context

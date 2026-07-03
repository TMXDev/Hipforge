import pytest
from app.compiler.patch_applier import apply_llm_search_replace_patch

def test_apply_patch_success():
    original_code = """int main() {
    int x = 10;
    int y = 20;
    return x + y;
}"""
    
    patch_response = """Some text from LLM...
<<<<<<< SEARCH
    int x = 10;
    int y = 20;
=======
    int x = 100;
    int y = 200;
>>>>>>> REPLACE
Other text from LLM..."""

    expected_code = """int main() {
    int x = 100;
    int y = 200;
    return x + y;
}"""

    result = apply_llm_search_replace_patch(original_code, patch_response)
    assert result == expected_code


def test_apply_patch_multiple():
    original_code = """int get_x() { return 10; }
int get_y() { return 20; }
int get_z() { return 30; }"""

    patch_response = """<<<<<<< SEARCH
int get_x() { return 10; }
=======
int get_x() { return 100; }
>>>>>>> REPLACE

Some separator text...

<<<<<<< SEARCH
int get_z() { return 30; }
=======
int get_z() { return 300; }
>>>>>>> REPLACE"""

    expected_code = """int get_x() { return 100; }
int get_y() { return 20; }
int get_z() { return 300; }"""

    result = apply_llm_search_replace_patch(original_code, patch_response)
    assert result == expected_code


def test_apply_patch_whitespace_indentation():
    original_code = """void process() {
\t\t// Some deep indentation
\t\tfloat value = 1.0f;
}"""

    patch_response = """<<<<<<< SEARCH
\t\t// Some deep indentation
\t\tfloat value = 1.0f;
=======
\t\t// Modified indentation
\t\tdouble value = 2.0;
>>>>>>> REPLACE"""

    expected_code = """void process() {
\t\t// Modified indentation
\t\tdouble value = 2.0;
}"""

    result = apply_llm_search_replace_patch(original_code, patch_response)
    assert result == expected_code


def test_apply_patch_not_found():
    original_code = """int main() { return 0; }"""
    patch_response = """<<<<<<< SEARCH
int get_val() { return 10; }
=======
int get_val() { return 100; }
>>>>>>> REPLACE"""

    with pytest.raises(ValueError) as excinfo:
        apply_llm_search_replace_patch(original_code, patch_response)
    
    assert "not found in source code" in str(excinfo.value)


def test_apply_patch_ambiguous():
    original_code = """int x = 10;
int y = 10;
int z = 20;"""

    patch_response = """<<<<<<< SEARCH
int x = 10;
=======
int x = 100;
>>>>>>> REPLACE"""

    # First one matches unique, succeeds
    result = apply_llm_search_replace_patch(original_code, patch_response)
    assert "int x = 100;" in result

    # Ambiguous block match:
    patch_response_ambiguous = """<<<<<<< SEARCH
10;
=======
100;
>>>>>>> REPLACE"""

    with pytest.raises(ValueError) as excinfo:
        apply_llm_search_replace_patch(original_code, patch_response_ambiguous)
        
    assert "matches multiple regions" in str(excinfo.value)

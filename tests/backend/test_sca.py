"""
tests/backend/test_sca.py

Unit tests for the Semantic Compatibility Analyzer (SCA).

Verifies:
  - analyze() returns the correct schema: {"issues": list, "score": float}
  - CompatibilityIssue fields match the model exactly
  - All 10 pattern categories from docs/10_COMPILATION_PIPELINE.md are detected
  - The compatibility score decreases with more issues
  - A clean file produces no issues and a score of 1.0
  - File-not-found raises FileNotFoundError
  - write_migration_risks() produces a valid JSON file

Gate: pytest tests/backend/test_sca.py -v
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.compiler.sca import analyze, write_migration_risks
from app.models.compatibility_issue import CompatibilityIssue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RISKS_FIXTURE = FIXTURE_DIR / "sca_risks.hip"
CLEAN_FIXTURE = FIXTURE_DIR / "sample.hip"  # existing clean fixture (no risks)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def get_detected_pattern_ids(result: dict) -> set:
    """Return the set of pattern_id values from an analyze() result."""
    return {issue.pattern_id for issue in result["issues"]}


# ---------------------------------------------------------------------------
# Test: return schema
# ---------------------------------------------------------------------------

class TestReturnSchema:
    """analyze() must return the correct structure."""

    def test_returns_dict_with_issues_and_score(self):
        result = analyze(str(RISKS_FIXTURE))
        assert isinstance(result, dict), "Result must be a dict"
        assert "issues" in result, "Result must contain 'issues'"
        assert "score" in result, "Result must contain 'score'"

    def test_issues_is_list(self):
        result = analyze(str(RISKS_FIXTURE))
        assert isinstance(result["issues"], list)

    def test_score_is_float(self):
        result = analyze(str(RISKS_FIXTURE))
        assert isinstance(result["score"], float)

    def test_score_in_valid_range(self):
        result = analyze(str(RISKS_FIXTURE))
        assert 0.0 <= result["score"] <= 1.0

    def test_issues_are_compatibility_issue_instances(self):
        result = analyze(str(RISKS_FIXTURE))
        for issue in result["issues"]:
            assert isinstance(issue, CompatibilityIssue), (
                f"Expected CompatibilityIssue, got {type(issue)}"
            )


# ---------------------------------------------------------------------------
# Test: CompatibilityIssue schema
# ---------------------------------------------------------------------------

class TestCompatibilityIssueSchema:
    """Every CompatibilityIssue must contain the required fields."""

    def test_issue_has_all_required_fields(self):
        result = analyze(str(RISKS_FIXTURE))
        assert result["issues"], "Expected at least one issue in the risk fixture"
        issue = result["issues"][0]

        assert hasattr(issue, "pattern_id") and isinstance(issue.pattern_id, str)
        assert hasattr(issue, "category") and isinstance(issue.category, str)
        assert hasattr(issue, "severity") and issue.severity in ("high", "medium", "low")
        assert hasattr(issue, "file") and isinstance(issue.file, str)
        assert hasattr(issue, "line")  # may be None or int
        assert hasattr(issue, "column")  # may be None or int
        assert hasattr(issue, "source_snippet") and isinstance(issue.source_snippet, str)
        assert hasattr(issue, "description") and isinstance(issue.description, str)
        assert hasattr(issue, "recommendation") and isinstance(issue.recommendation, str)

    def test_line_is_int_or_none(self):
        result = analyze(str(RISKS_FIXTURE))
        for issue in result["issues"]:
            assert issue.line is None or isinstance(issue.line, int)

    def test_column_is_int_or_none(self):
        result = analyze(str(RISKS_FIXTURE))
        for issue in result["issues"]:
            assert issue.column is None or isinstance(issue.column, int)

    def test_severity_valid_literals(self):
        result = analyze(str(RISKS_FIXTURE))
        valid = {"high", "medium", "low"}
        for issue in result["issues"]:
            assert issue.severity in valid, f"Invalid severity: {issue.severity}"


# ---------------------------------------------------------------------------
# Test: pattern detection (minimum 2 known issues from the fixture)
# ---------------------------------------------------------------------------

class TestPatternDetection:
    """
    The SCA must correctly detect each of the 10 patterns from
    docs/10_COMPILATION_PIPELINE.md.

    The fixture file sca_risks.hip contains deliberate examples of all 10.
    """

    @pytest.fixture(autouse=True)
    def run_analysis(self):
        self.result = analyze(str(RISKS_FIXTURE))
        self.detected = get_detected_pattern_ids(self.result)

    def test_detects_at_least_two_issues(self):
        """Gate requirement: at least 2 known issues correctly identified."""
        assert len(self.result["issues"]) >= 2, (
            f"Expected >= 2 issues, got {len(self.result['issues'])}"
        )

    def test_detects_inline_ptx(self):
        assert "INLINE_PTX" in self.detected, (
            "Expected INLINE_PTX pattern to be detected"
        )

    def test_detects_texture_references(self):
        assert "TEXTURE_REFERENCES" in self.detected, (
            "Expected TEXTURE_REFERENCES pattern to be detected"
        )

    def test_detects_cooperative_groups(self):
        assert "COOPERATIVE_GROUPS" in self.detected, (
            "Expected COOPERATIVE_GROUPS pattern to be detected"
        )

    def test_detects_tensor_core_intrinsics(self):
        assert "TENSOR_CORE_INTRINSICS" in self.detected, (
            "Expected TENSOR_CORE_INTRINSICS pattern to be detected"
        )

    def test_detects_thrust(self):
        assert "THRUST_USAGE" in self.detected, (
            "Expected THRUST_USAGE pattern to be detected"
        )

    def test_detects_cub(self):
        assert "CUB_USAGE" in self.detected, (
            "Expected CUB_USAGE pattern to be detected"
        )

    def test_detects_dynamic_shared_memory(self):
        assert "DYNAMIC_SHARED_MEMORY" in self.detected, (
            "Expected DYNAMIC_SHARED_MEMORY pattern to be detected"
        )

    def test_detects_surface_references(self):
        assert "SURFACE_REFERENCES" in self.detected, (
            "Expected SURFACE_REFERENCES pattern to be detected"
        )

    def test_detects_cuda_graphs(self):
        assert "CUDA_GRAPHS" in self.detected, (
            "Expected CUDA_GRAPHS pattern to be detected"
        )

    def test_detects_warp_size(self):
        warp_ids = {"WARP_SIZE_ASSUMPTION_SYMBOL", "WARP_SIZE_ASSUMPTION_LITERAL"}
        detected_warp = warp_ids & self.detected
        assert detected_warp, (
            f"Expected at least one warpSize pattern to be detected. "
            f"Detected IDs: {self.detected}"
        )

    def test_issue_file_matches_fixture_name(self):
        """Each issue's file field must equal the fixture file's basename."""
        expected_name = RISKS_FIXTURE.name
        for issue in self.result["issues"]:
            assert issue.file == expected_name, (
                f"Expected file '{expected_name}', got '{issue.file}'"
            )

    def test_issue_source_snippet_is_nonempty(self):
        for issue in self.result["issues"]:
            assert issue.source_snippet.strip(), (
                f"source_snippet should not be empty for pattern {issue.pattern_id}"
            )

    def test_issue_line_is_positive(self):
        for issue in self.result["issues"]:
            if issue.line is not None:
                assert issue.line >= 1, (
                    f"Line number must be >= 1, got {issue.line} for {issue.pattern_id}"
                )


# ---------------------------------------------------------------------------
# Test: clean file produces no issues and score = 1.0
# ---------------------------------------------------------------------------

class TestCleanFile:
    """A clean HIP source file with no risk patterns should score 1.0."""

    def test_clean_file_no_issues(self):
        # Write a minimal clean HIP source to a temp file
        clean_source = (
            "#include <hip/hip_runtime.h>\n\n"
            "__global__ void add(float* a, float* b, float* c, int n) {\n"
            "    int i = blockIdx.x * blockDim.x + threadIdx.x;\n"
            "    if (i < n) c[i] = a[i] + b[i];\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".hip", delete=False, encoding="utf-8"
        ) as f:
            f.write(clean_source)
            tmp_path = f.name

        try:
            result = analyze(tmp_path)
            assert result["issues"] == [], (
                f"Expected no issues in clean file, got: {result['issues']}"
            )
            assert result["score"] == 1.0, (
                f"Expected score 1.0 for clean file, got {result['score']}"
            )
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Test: score decreases with issues
# ---------------------------------------------------------------------------

class TestCompatibilityScore:
    """The compatibility score must be lower for files with more risk patterns."""

    def test_score_lower_than_clean(self):
        """Risk fixture score must be strictly below 1.0."""
        result = analyze(str(RISKS_FIXTURE))
        assert result["score"] < 1.0, (
            f"Score should be < 1.0 for a file with issues, got {result['score']}"
        )

    def test_score_floor_is_zero(self):
        """Score must never go below 0.0."""
        result = analyze(str(RISKS_FIXTURE))
        assert result["score"] >= 0.0


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """analyze() must raise FileNotFoundError for missing files."""

    def test_raises_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            analyze("/non/existent/path/kernel.hip")


# ---------------------------------------------------------------------------
# Test: write_migration_risks serialisation
# ---------------------------------------------------------------------------

class TestWriteMigrationRisks:
    """write_migration_risks() must produce a valid migration_risks.json."""

    def test_writes_valid_json(self, tmp_path):
        result = analyze(str(RISKS_FIXTURE))
        output_path = str(tmp_path / "migration_risks.json")
        write_migration_risks(result, output_path)

        assert Path(output_path).exists(), "migration_risks.json was not created"

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "score" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)
        assert isinstance(data["score"], float)

    def test_json_issues_have_required_fields(self, tmp_path):
        result = analyze(str(RISKS_FIXTURE))
        output_path = str(tmp_path / "migration_risks.json")
        write_migration_risks(result, output_path)

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        required_fields = {
            "pattern_id", "category", "severity", "file",
            "source_snippet", "description", "recommendation",
        }
        for issue in data["issues"]:
            missing = required_fields - set(issue.keys())
            assert not missing, f"Missing fields in JSON issue: {missing}"

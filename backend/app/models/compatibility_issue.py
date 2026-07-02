from typing import Optional, Literal
from pydantic import BaseModel


class CompatibilityIssue(BaseModel):
    """
    Structured model representing a single semantic compatibility risk detected
    by the Semantic Compatibility Analyzer (SCA).

    Produced for every pattern match in translated HIP source code.
    These are collected into migration_risks.json as part of the Workflow Context.

    Fields:
        pattern_id       Unique identifier for the detected pattern rule
                         (e.g. "WARP_SIZE_ASSUMPTION").
        category         Human-readable category name matching the SCA rule set
                         (e.g. "warpSize assumptions").
        severity         Risk severity level: "high", "medium", or "low".
        file             Source file where the pattern was detected.
        line             Line number of the match (1-indexed), or None if unknown.
        column           Column offset of the match (0-indexed), or None if unknown.
        source_snippet   The raw source line containing the match.
        description      Explanation of why this pattern is a migration risk.
        recommendation   Suggested action to resolve the compatibility issue.
    """

    pattern_id: str
    category: str
    severity: Literal["high", "medium", "low"]
    file: str
    line: Optional[int] = None
    column: Optional[int] = None
    source_snippet: str
    description: str
    recommendation: str

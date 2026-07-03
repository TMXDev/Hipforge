import re

def apply_llm_search_replace_patch(original_code: str, patch_response: str) -> str:
    """
    Parses search-and-replace blocks from an LLM response and applies them programmatically.

    Requirements:
    1. Prompt Format:
       <<<<<<< SEARCH
       [exact code lines in original file]
       =======
       [replacement code lines]
       >>>>>>> REPLACE
    2. Parsing: Locate all search-and-replace blocks inside patch_response.
    3. Validation: Verify SEARCH block matches a unique substring in original_code.
       If multiple or no matches, raise ValueError with details.
    4. Application: Replace SEARCH block with REPLACE block, preserving whitespace/indentation.
    5. Return Format: Return modified complete file contents as a string.
    """
    # Normalize all line endings to \n to ensure robust matching across OS environments
    normalized_code = original_code.replace("\r\n", "\n")
    normalized_patch = patch_response.replace("\r\n", "\n")

    # Regular expression to extract SEARCH and REPLACE blocks multiline
    pattern = re.compile(
        r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE",
        re.DOTALL
    )

    blocks = pattern.findall(normalized_patch)
    if not blocks:
        return normalized_code

    modified_code = normalized_code
    for idx, (search_block, replace_block) in enumerate(blocks):
        # Count occurrences of the exact search block in current source code
        occurrences = modified_code.count(search_block)

        if occurrences == 0:
            raise ValueError(
                f"Patch validation failed at block #{idx + 1}: SEARCH block not found in source code.\n"
                f"--- SEARCH BLOCK START ---\n{search_block}\n--- SEARCH BLOCK END ---"
            )
        elif occurrences > 1:
            raise ValueError(
                f"Patch validation failed at block #{idx + 1}: SEARCH block matches multiple regions ({occurrences} times) and is ambiguous.\n"
                f"--- SEARCH BLOCK START ---\n{search_block}\n--- SEARCH BLOCK END ---"
            )

        # Apply replacement for the unique match
        modified_code = modified_code.replace(search_block, replace_block, 1)

    return modified_code

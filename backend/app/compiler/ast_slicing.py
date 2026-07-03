import os
import logging
import clang.cindex
from typing import List, Tuple, Set

logger = logging.getLogger("ast_slicing")

def get_optimized_error_context(source_path: str, error_line: int, window_lines: int = 50) -> str:
    """
    Extracts a highly optimized semantic slice of a source file around a compilation error.

    Requirements:
    1. AST Extraction: Use clang.cindex Python bindings to parse the AST.
    2. Semantic Slicing: Locate the function, class, struct, etc., containing error_line.
    3. Context Compilation: Extract the full code of the block plus headers, macros, and referenced globals.
    4. Fallback: If AST parsing fails or the line is outside a resolved block, fall back to sliding window.
    5. Return Format: Clean string formatted for LLM context.
    """
    # 1. Read source code lines
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Error reading source file {source_path}: {e}")
        return f"/* Error reading source file: {e} */"

    # Helper function for fallback sliding window context
    def get_sliding_window_fallback(reason: str) -> str:
        logger.info(f"Using sliding window fallback for {source_path} at line {error_line} (Reason: {reason})")
        start_idx = max(0, error_line - 1 - window_lines)
        end_idx = min(len(lines), error_line - 1 + window_lines + 1)
        slice_lines = lines[start_idx:end_idx]
        slice_text = "".join(slice_lines)
        return (
            f"/* Fallback Context (Reason: {reason}) */\n"
            f"/* Error at Line {error_line} */\n"
            f"{slice_text}"
        )

    # 2. Parse AST using clang.cindex
    try:
        index = clang.cindex.Index.create()
        # Parse enabling macro and inclusion processing records
        options = clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        # Use standard C++ mode for header files and CUDA/HIP code compatibility
        args = ["-x", "c++"]
        tu = index.parse(source_path, args=args, options=options)
    except Exception as parse_err:
        return get_sliding_window_fallback(f"AST parsing failed: {parse_err}")

    # 3. Traversal logic: Find the deepest semantic block covering the error line
    interesting_kinds = {
        clang.cindex.CursorKind.FUNCTION_DECL,
        clang.cindex.CursorKind.CXX_METHOD,
        clang.cindex.CursorKind.CLASS_DECL,
        clang.cindex.CursorKind.STRUCT_DECL,
        clang.cindex.CursorKind.UNION_DECL,
        clang.cindex.CursorKind.NAMESPACE,
        clang.cindex.CursorKind.FUNCTION_TEMPLATE,
        clang.cindex.CursorKind.CLASS_TEMPLATE,
    }

    target_node = None
    headers: List[Tuple[int, int]] = []
    macros: List[Tuple[int, int]] = []

    # Canonicalize target source path
    canonical_source_path = os.path.realpath(source_path).lower()

    def traverse_ast(node):
        nonlocal target_node
        # Check if cursor is defined in the source file we are analyzing
        if node.location.file:
            node_file = os.path.realpath(node.location.file.name).lower()
            if node_file == canonical_source_path:
                start_line = node.extent.start.line
                end_line = node.extent.end.line
                
                # Record inclusions and macro definitions
                if node.kind == clang.cindex.CursorKind.INCLUSION_DIRECTIVE:
                    headers.append((start_line, end_line))
                elif node.kind == clang.cindex.CursorKind.MACRO_DEFINITION:
                    macros.append((start_line, end_line))
                
                # Locate enclosing block matching the error line
                if start_line <= error_line <= end_line:
                    if node.kind in interesting_kinds:
                        if target_node is None:
                            target_node = node
                        else:
                            # Narrow down to the deepest nested block
                            curr_start = target_node.extent.start.line
                            curr_end = target_node.extent.end.line
                            if start_line >= curr_start and end_line <= curr_end:
                                target_node = node

        for child in node.get_children():
            traverse_ast(child)

    traverse_ast(tu.cursor)

    # 4. Fallback if no surrounding block is found
    if not target_node:
        return get_sliding_window_fallback("Error line outside resolved semantic block")

    # 5. Extract referenced global variables inside target block
    referenced_globals: List[Tuple[int, int]] = []
    referenced_decls: Set[clang.cindex.Cursor] = set()

    def find_references(node):
        if node.kind == clang.cindex.CursorKind.DECL_REF_EXPR:
            ref = node.referenced
            if ref:
                referenced_decls.add(ref)
        for child in node.get_children():
            find_references(child)

    find_references(target_node)

    for decl in referenced_decls:
        # We only care about global variables defined outside the target block but inside the same file
        if decl.location.file:
            decl_file = os.path.realpath(decl.location.file.name).lower()
            if decl_file == canonical_source_path and decl.kind == clang.cindex.CursorKind.VAR_DECL:
                start_l = decl.extent.start.line
                if start_l < target_node.extent.start.line or start_l > target_node.extent.end.line:
                    referenced_globals.append((decl.extent.start.line, decl.extent.end.line))

    # Helper function to get text for line ranges
    def get_lines_text(ranges: List[Tuple[int, int]]) -> str:
        if not ranges:
            return ""
        # Sort and merge overlapping line ranges (1-indexed)
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end + 1:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

        blocks = []
        for start, end in merged:
            block = lines[start - 1 : end]
            blocks.append("".join(block))
        return "\n".join(blocks)

    # 6. Format final context string for LLM
    headers_text = get_lines_text(headers)
    macros_text = get_lines_text(macros)
    globals_text = get_lines_text(referenced_globals)
    target_text = get_lines_text([(target_node.extent.start.line, target_node.extent.end.line)])

    parts = []
    if headers_text.strip():
        parts.append("/* Headers / Includes */")
        parts.append(headers_text.strip())
    if macros_text.strip():
        parts.append("/* Preprocessor Macros */")
        parts.append(macros_text.strip())
    if globals_text.strip():
        parts.append("/* Referenced Globals */")
        parts.append(globals_text.strip())

    parts.append(f"/* Target Block (Lines {target_node.extent.start.line} - {target_node.extent.end.line}) */")
    parts.append(f"/* Error at Line {error_line} */")
    parts.append(target_text.strip())

    return "\n\n".join(parts)

import pytest
import json
from app.compiler.error_parser import classify_compiler_error
from app.learning.lesson_storage import store_lesson, find_lesson, lesson_key, normalize_error_signature


class TestLessonClassification:

    def test_classify_unsupported_arch(self):
        err = "error: unsupported HIP GPU architecture gfx940"
        assert classify_compiler_error(err) == "UNSUPPORTED_FEATURE"

    def test_classify_unsupported_arch_alt_pattern(self):
        err = "error: unknown target GPU gfx940"
        assert classify_compiler_error(err) == "UNSUPPORTED_FEATURE"

    def test_classify_undefined_symbol(self):
        err = "undefined reference to `run_gelu`"
        assert classify_compiler_error(err) == "UNRESOLVED_SYMBOL"

    def test_classify_undefined_symbol_alt(self):
        err = "undefined symbol: hipLaunchKernel"
        assert classify_compiler_error(err) == "UNRESOLVED_SYMBOL"


class TestLessonStorage:

    @pytest.mark.asyncio
    async def test_store_and_find_lesson(self, redis_test_client):
        category = "UNSUPPORTED_FEATURE"
        stderr = "error: unsupported HIP GPU architecture gfx940"
        await store_lesson(
            redis_test_client,
            category=category,
            stderr=stderr,
            target_architecture="gfx940",
            recommended_action="Use a supported architecture.",
            patch_attempted=False,
            patch_skipped_reason="Architecture not supported",
        )

        sig = normalize_error_signature(stderr)
        key = lesson_key(category, sig)
        raw = await redis_test_client.get(key)
        assert raw is not None, "Lesson should be stored in Redis"

        lesson = json.loads(raw)
        assert lesson["category"] == "UNSUPPORTED_FEATURE"
        assert lesson["target_architecture"] == "gfx940"
        assert lesson["patch_attempted"] is False
        assert lesson["patch_skipped_reason"] == "Architecture not supported"

    @pytest.mark.asyncio
    async def test_find_lesson_matches_across_categories(self, redis_test_client):
        category = "UNRESOLVED_SYMBOL"
        stderr = "undefined reference to `run_gelu`"
        await store_lesson(
            redis_test_client,
            category=category,
            stderr=stderr,
            recommended_action="Upload full project.",
            patch_attempted=False,
            patch_skipped_reason="Cannot patch single file for linker errors",
        )

        found = await find_lesson(redis_test_client, stderr)
        assert found is not None
        assert found["category"] == "UNRESOLVED_SYMBOL"
        assert found["recommended_action"] == "Upload full project."

    @pytest.mark.asyncio
    async def test_find_lesson_returns_none_for_unknown_error(self, redis_test_client):
        found = await find_lesson(redis_test_client, "some unknown error text")
        assert found is None

    @pytest.mark.asyncio
    async def test_store_patch_noop_lesson(self, redis_test_client):
        category = "PATCH_NOOP"
        stderr = "kernel.hip:42:8: error: use of undeclared identifier"
        await store_lesson(
            redis_test_client,
            category=category,
            stderr=stderr,
            patch_attempted=True,
            patch_skipped_reason="Patch Agent returned unchanged source code (no-op)",
            recommended_action="Manual intervention required.",
        )

        found = await find_lesson(redis_test_client, stderr)
        assert found is not None
        assert found["category"] == "PATCH_NOOP"
        assert found["patch_attempted"] is True

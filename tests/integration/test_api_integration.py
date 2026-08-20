"""Integration tests for appman.api -- GitHub REST client."""

# TODO: write integration test:
# A real call to https://api.github.com/repos/.../releases/latest — confirms the actual GitHub API still matches your GitHubReleasePayload TypedDict assumptions (schema drift, rate-limit headers, actual asset naming conventions across dozens of real repos like keepassxc, obsidian, etc.). This is exactly the kind of test PRD.md §10 ("MVP commands work end-to-end against real GitHub repos") is asking for, separately from this unit suite.
# Full install() flow in install.py exercising api.py + download.py + verify.py together against a real or recorded (VCR-style) GitHub response — validates module boundaries, which unit tests for api.py alone can't.
# Rate-limit behavior under API_SEMAPHORE with many concurrent real repos — timing-sensitive, non-deterministic if mocked, better suited to a controlled integration/perf test per AGENTS.md §14 (regression benchmarks for update-check latency).

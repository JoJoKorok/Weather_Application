# Changelog

## v0.3.0-rc.1 — 2026-07-24

First release candidate for the protected and packaged Weather Application.

### Added

- Normalized weather caching and concurrent-request coalescing.
- Layered per-IP, installation, query, hourly, and daily limits.
- Trusted owner capacity with cache-bypass support for development.
- Atomic SQLite persistence for global upstream budgets.
- Admin-only aggregate usage statistics.
- Anonymous persistent client identity for fair limiting.
- Python package metadata and a standalone Windows build workflow.
- Render Blueprint and proxy security configuration guide.

### Changed

- Public proxy defaults are more conservative.
- Invalid requests no longer consume protected upstream capacity.
- Cached results remain available when live refreshes are paused.
- Proxy history endpoints are disabled by default and require admin access.
- Client output identifies cached results and reports retry timing.
- Setup and launch scripts now work independently of the caller's directory.

### Fixed

- Restored the complete proxy implementation hidden by `skip-worktree`.
- Corrected proxy validation and upstream timeout behavior.
- Prevented invalid history counts and blank searches from causing bad behavior.
- Bounded rate-limit and query-lock state to prevent unbounded memory growth.
- Made PyInstaller builds isolated and failure-aware.

### Verification

- 41 automated tests.
- Ruff static analysis.
- Python bytecode compilation.
- Python wheel build.
- Standalone Windows executable build.

### Release-candidate note

This prerelease is intended for final validation of the Render deployment,
protective quotas, caching, trusted-owner access, and Windows packaging before
the stable `v0.3.0` release.

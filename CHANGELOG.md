# Changelog

## Unreleased — 2026-11-13

- Validate supported GitHub hosts and paths with URL parsing; reject credentials, query/fragment data, custom ports, ambiguous paths and unrelated URLs before any network request.
- Verify public visibility using the unauthenticated official GitHub API before the CLI sends a target to community mirrors. API errors or inconclusive results stop safely and recommend official authenticated direct access.
- Preserve existing files by default, including a destination created during transfer. Stage downloads in a temporary sibling and publish atomically; explicit `--overwrite` replaces only after successful validation.
- Clean partial data between mirror attempts and after errors. Reject empty responses, unexpected status, invalid/mismatched Content-Length and obvious HTML error pages for non-HTML targets. Preserve legitimate raw HTML downloads.
- Check the directory structure of explicit ZIP targets before publication, without extracting or validating every member's CRC or authenticity.
- Route Agent usage through the same Python safety checks; document mirror trust limits, supported paths, file preservation and the distinction between snapshots and Git clones.
- Add offline standard-library regressions and Windows/Linux CI. No mirror availability, live transfer speed or executable safety is claimed by these tests.

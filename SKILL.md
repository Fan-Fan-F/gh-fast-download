---
name: gh-fast-download
description: Download public GitHub repository snapshots, raw files, and release assets through community mirrors when direct access is slow. Use the bundled safe downloader after official unauthenticated public-repository verification. Private or unverified repositories use official authenticated GitHub access instead.
---

# gh-fast-download

Use this workflow when the user requests an actual download. Repository maintenance or review of these instructions is not a download request. Run the bundled `ghdl.py`; do not substitute handwritten proxy URLs, curl/wget commands or mirrored Git clones that bypass its checks.

## Understand the requested result

Use the GitHub URL and output directory already supplied in the conversation. Ask for the link only when the intended project cannot be identified. Resolve routine filenames and local paths yourself. Check that Python 3.8+ is already available; follow the host's authorization rules before installing software.

The script supports repository snapshots, `/blob/REF/PATH` and raw files, `/releases/download/TAG/FILE`, and ZIP archives. It does not fetch Git history. Use official `gh repo clone` when the user actually needs a clone.

## Public visibility is required

A syntactically valid URL does **not** prove that a repository is public. Never send private or unverified repository names, credentials, tokens or authenticated URLs to a community mirror.

The CLI first uses an unauthenticated request to the official `api.github.com` repository endpoint. It requires an explicit `private: false`, compatible visibility and a matching repository identity. Only after that succeeds does it contact mirrors. Treat API errors, rate limits, unexpected responses and failed public verification as a stop: use the official GitHub CLI's authenticated direct access for the requested download. Do not work around the failure by manually prefixing a mirror domain. A user statement or `gh` result can help establish intent and visibility, but does not bypass the script's public check.

Reject URLs with userinfo, query parameters, fragments, unsupported hosts/protocols/ports or unsupported paths. Do not copy a token into a new URL to make a failed request work. The script does not use or forward the user's GitHub credentials.

## Download through the shared safe path

Resolve `ghdl.py` relative to this skill directory and run it with the original GitHub URL and the chosen output directory:

```console
python <skill-directory>/ghdl.py <public-github-url> <output-directory>
```

Keep commands and dependency details Agent-handled unless the user asks for them. For a repository root, the script tries `main`, then `master`. If neither is the desired ref, resolve the actual public branch/tag with official GitHub metadata and use its explicit supported ZIP archive URL.

An existing destination is preserved by default. Prefer a distinct output directory or filename. Use `--overwrite` only when replacement was explicitly requested or authorized by the user. It replaces the destination atomically after the complete new response passes checks.

The script stages data in a temporary sibling, checks HTTP status, nonempty content and any Content-Length, rejects obvious HTML pages for non-HTML targets, and cleans partials before retrying mirrors. Explicit `.html`/`.htm` targets remain allowed. Explicit ZIP targets receive a directory-structure check without extraction or full member CRC validation. Mirror configuration belongs only in `ghdl.py`'s `PROXIES`; do not maintain a second list here.

## Verify and report

Check the script exit status and actual final file. Report its resolved path and relevant limitations plainly. For important executables or archives, compare against the publisher's official checksum/signature when available before treating content as verified. Do not execute, install or extract downloaded code just to prove that a download completed.

HTML detection is a heuristic using response type and the first 1024 bytes, skipping leading whitespace and complete HTML comments; it cannot detect every disguised error. The response checks cannot establish content authenticity or safe executable behavior. HTML targets can still receive an HTML error page, and ZIP structure alone does not validate every member or prove the publisher's identity. Public mirror speed and availability require separate current evidence; do not promise them from offline tests.

All-mirror failure leaves existing files unchanged. Continue with official GitHub direct access when that is available and authorized, carrying forward the same no-overwrite and partial-file cleanup requirements. Do not repeatedly retry community mirrors or claim success because a nonempty file exists.

## Maintenance check

Run `python -m unittest discover -s tests -v` from the repository root. The suite uses mocked HTTP only. Never use a user's private repository, API token or real mirror download as a test fixture.

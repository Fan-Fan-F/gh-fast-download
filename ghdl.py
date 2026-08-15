#!/usr/bin/env python3
"""gh-fast-download — download GitHub content fast via gh-proxy mirrors.

Usage:
    python ghdl.py <github-url> [output-dir]

Examples:
    python ghdl.py https://github.com/owner/repo
    python ghdl.py https://github.com/owner/repo/archive/refs/heads/main.zip
    python ghdl.py https://github.com/owner/repo/releases/download/v1.0/app.exe
    python ghdl.py https://github.com/owner/repo/blob/main/README.md

Zero third-party dependencies (Python 3.8+, stdlib only).
"""

import os
import re
import sys
import urllib.request

# --- editable mirror list (tried in order) ---
PROXIES = [
    "https://gh-proxy.org/",
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://ghproxy.net/",
    "https://mirror.ghproxy.com/",
]

DEFAULT_BRANCHES = ("main", "master")
USER_AGENT = "Mozilla/5.0 (gh-fast-download)"


def proxied(target_url, proxy):
    """Prepend a mirror domain to a full URL."""
    return proxy.rstrip("/") + "/" + target_url


def classify(url):
    """Classify a GitHub URL.

    Returns ("repo", owner, repo) for a repository root, else ("file", url)
    for anything directly downloadable (raw file / release asset / archive).
    """
    url = url.strip().rstrip("/")
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    if not url.startswith("https://"):
        url = "https://" + url

    if "raw.githubusercontent.com" in url:
        return ("file", url)
    if "/releases/download/" in url:
        return ("file", url)
    if "/archive/" in url and url.endswith(".zip"):
        return ("file", url)
    if "/blob/" in url:
        raw = url.replace("github.com", "raw.githubusercontent.com", 1)
        raw = re.sub(r"/blob/([^/]+)/", r"/\1/", raw)
        return ("file", raw)

    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+)", url)
    if m:
        return ("repo", m.group(1), m.group(2))
    return ("file", url)


def download_to(url, dest):
    """Download url to dest, following redirects."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp, open(dest, "wb") as fh:
        total = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            total += len(chunk)
        print("    %d bytes" % total)


def try_mirrors(target_url, dest):
    """Try each mirror in order; return True on first success."""
    for proxy in PROXIES:
        u = proxied(target_url, proxy)
        print("  try: %s" % u)
        try:
            download_to(u, dest)
            print("  OK  -> %s" % dest)
            return True
        except Exception as exc:  # report and try the next mirror
            print("  fail: %s: %s" % (type(exc).__name__, exc))
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    url = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(outdir, exist_ok=True)

    kind = classify(url)

    if kind[0] == "repo":
        _, owner, repo = kind
        if repo.endswith(".git"):
            repo = repo[:-4]
        ok = False
        for branch in DEFAULT_BRANCHES:
            target = "https://github.com/%s/%s/archive/refs/heads/%s.zip" % (
                owner, repo, branch,
            )
            dest = os.path.join(outdir, "%s-%s.zip" % (repo, branch))
            print("downloading repo %s/%s (%s):" % (owner, repo, branch))
            if try_mirrors(target, dest):
                ok = True
                break
        if not ok:
            print("all mirrors failed — try `git clone` with a proxy prefix, or update PROXIES.")
            return 2
        return 0

    _, target = kind
    fname = os.path.basename(target.rstrip("/")) or "download"
    dest = os.path.join(outdir, fname)
    print("downloading: %s" % target)
    if not try_mirrors(target, dest):
        print("all mirrors failed — update PROXIES with a live mirror.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

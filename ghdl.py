#!/usr/bin/env python3
"""gh-fast-download — download GitHub content fast via gh-proxy mirrors.

Usage:
    python ghdl.py <public-github-url> [output-dir] [--overwrite]

Examples:
    python ghdl.py https://github.com/owner/repo
    python ghdl.py https://github.com/owner/repo/archive/refs/heads/main.zip
    python ghdl.py https://github.com/owner/repo/releases/download/v1.0/app.exe
    python ghdl.py https://github.com/owner/repo/blob/main/README.md

Zero third-party dependencies (Python 3.8+, stdlib only).
"""

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit
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


class DownloadError(OSError):
    """A transfer or public-repository check could not be validated."""


def proxied(target_url, proxy):
    """Prepend a mirror domain to a full URL."""
    return proxy.rstrip("/") + "/" + target_url


def classify(url):
    """Validate supported GitHub URL syntax, not repository visibility."""
    url = url.strip()
    if not url or any(c.isspace() or ord(c) < 32 for c in url) or "\\" in url:
        raise ValueError("Use a GitHub URL without whitespace or backslashes.")
    if "://" not in url:
        url = "https://" + url
    parsed = urlsplit(url)
    host = parsed.hostname
    if (parsed.scheme not in ("http", "https")
            or host not in ("github.com", "raw.githubusercontent.com")
            or parsed.username is not None or parsed.password is not None
            or parsed.netloc.lower() != host or "?" in url or "#" in url):
        raise ValueError("Only uncredentialed GitHub HTTPS URLs without query or fragment are supported.")
    path = parsed.path.rstrip("/")
    encoded = path.split("/")[1:]
    if not encoded or any(not part or re.search(r"%(?![0-9a-fA-F]{2})", part) for part in encoded):
        raise ValueError("Unsupported GitHub path.")
    parts = [unquote(part, errors="strict") for part in encoded]
    if any(part in (".", "..") or re.search(r"%[0-9a-fA-F]{2}", part)
           or any(c in "/\\" or ord(c) < 32 for c in part) for part in parts):
        raise ValueError("Ambiguous or unsafe GitHub path.")
    if (len(parts) < 2 or not re.fullmatch(r"[A-Za-z0-9-]+", parts[0])
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[1])):
        raise ValueError("A GitHub owner and repository are required.")
    owner, repo = parts[:2]
    if host == "github.com" and len(parts) == 2:
        return ("repo", owner, repo)
    if host == "raw.githubusercontent.com":
        valid = len(parts) >= 4
    elif len(parts) >= 5 and parts[2] == "blob":
        host, parts, valid = "raw.githubusercontent.com", parts[:2] + parts[3:], True
    elif len(parts) == 6 and parts[2:4] == ["releases", "download"]:
        valid = True
    else:
        valid = (len(parts) == 4 and parts[2] == "archive" and parts[3].endswith(".zip")) or (
            len(parts) >= 6 and parts[2:4] == ["archive", "refs"]
            and parts[4] in ("heads", "tags") and parts[-1].endswith(".zip"))
    if not valid:
        raise ValueError("Use a repository root, blob/raw file, release download, or ZIP archive URL.")
    normalized = "/" + "/".join(quote(part, safe="-._~") for part in parts)
    return ("file", urlunsplit(("https", host, normalized, "", "")))


def verify_public_repository(owner, repo):
    """Fail closed unless the unauthenticated official API confirms public visibility."""
    url = "https://api.github.com/repos/%s/%s" % (quote(owner, safe=""), quote(repo, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read((1 << 20) + 1)
        if len(body) > 1 << 20:
            raise ValueError("API response too large")
        data = json.loads(body.decode("utf-8"))
        if (not isinstance(data, dict) or data.get("private") is not False
                or data.get("visibility", "public") != "public"
                or not isinstance(data.get("full_name"), str)
                or data["full_name"].lower() != (owner + "/" + repo).lower()):
            raise ValueError("Public repository was not confirmed")
    except (OSError, ValueError, UnicodeError) as exc:
        raise DownloadError("Cannot confirm a public repository through the official GitHub API (%s). "
                            "No mirror was contacted. Use GitHub CLI (gh) for authenticated direct access." % type(exc).__name__) from exc


def _check_destination(dest, overwrite):
    if os.path.lexists(dest) and not overwrite:
        raise FileExistsError("Destination already exists; choose another directory or explicitly use --overwrite.")
    if os.path.isdir(dest):
        raise IsADirectoryError("Destination is a directory.")


def _allows_html(target):
    try:
        kind = classify(target)
        return kind[0] == "file" and urlsplit(kind[1]).path.lower().endswith((".html", ".htm"))
    except ValueError:
        return False


def download_to(url, dest, overwrite=False, target_url=None):
    """Transfer into a temporary sibling and publish only a validated complete file.

    Visibility verification belongs to main() before any mirror is contacted.
    This transport helper does not authenticate or prove content authenticity.
    """
    dest = os.path.abspath(os.fspath(dest))
    _check_destination(dest, overwrite)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temporary = None
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            if resp.status != 200:
                raise DownloadError("Expected a complete HTTP 200 response.")
            length = resp.headers.get("Content-Length")
            if length is not None and not re.fullmatch(r"[0-9]+", length.strip()):
                raise DownloadError("Invalid Content-Length header.")
            expected = int(length.strip()) if length is not None else None
            descriptor, temporary = tempfile.mkstemp(prefix=".ghdl-", suffix=".part", dir=os.path.dirname(dest))
            total, prefix = 0, b""
            with os.fdopen(descriptor, "wb") as fh:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    fh.write(chunk)
                    prefix += chunk[:max(0, 1024 - len(prefix))]
                    total += len(chunk)
                    if expected is not None and total > expected:
                        raise DownloadError("Response exceeds Content-Length.")
                if not total or expected is not None and total != expected:
                    raise DownloadError("Empty or truncated response; destination was not changed.")
                html_type = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() in ("text/html", "application/xhtml+xml")
                probe = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
                # Only inspect the bounded prefix; common gateway pages prepend
                # comments before their HTML root even when labelled text/plain.
                while probe.startswith(b"<!--"):
                    end = probe.find(b"-->")
                    if end < 0:
                        break
                    probe = probe[end + 3:].lstrip()
                html_prefix = re.match(br"(?:<!doctype\s+html\b|<html\b|<head\b|<body\b)", probe, re.I)
                if not _allows_html(target_url or url) and (html_type or html_prefix):
                    raise DownloadError("Received an HTML page instead of the requested file.")
                fh.flush()
                os.fsync(fh.fileno())
        if urlsplit(target_url or url).path.lower().endswith(".zip") and not zipfile.is_zipfile(temporary):
            raise DownloadError("The requested ZIP has no valid ZIP directory structure.")
        if overwrite:
            os.replace(temporary, dest)
        elif os.name == "nt":
            # Windows rename refuses an existing destination, including a race.
            os.rename(temporary, dest)
        else:
            # POSIX rename overwrites. Hard-link creation instead fails atomically
            # if another writer created dest after our preflight check.
            os.link(temporary, dest)
        print("    %d bytes" % total)
        return total
    finally:
        if temporary is not None and os.path.lexists(temporary):
            os.unlink(temporary)


def try_mirrors(target_url, dest, overwrite=False):
    """Try mirrors for an already public-verified target; never preserve partials."""
    kind = classify(target_url)
    if kind[0] != "file":
        raise ValueError("A direct file target is required.")
    target_url = kind[1]
    _check_destination(dest, overwrite)
    for proxy in PROXIES:
        u = proxied(target_url, proxy)
        print("  try: %s" % u)
        try:
            download_to(u, dest, overwrite=overwrite, target_url=target_url)
            print("  OK  -> %s" % dest)
            return True
        except FileExistsError:
            raise
        except Exception as exc:  # report and try the next mirror
            print("  fail: %s: %s" % (type(exc).__name__, exc))
    return False


def _filename(target):
    name = unquote(urlsplit(target).path.rsplit("/", 1)[-1])
    stem = name.split(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {"%s%d" % (prefix, i) for prefix in ("COM", "LPT") for i in range(1, 10)}
    if (not name or name.endswith((" ", ".")) or stem in reserved
            or any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name)):
        raise ValueError("The target filename is not portable; use an official direct download with an explicit safe filename.")
    return name


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download public GitHub files through community mirrors after official API verification.")
    parser.add_argument("url", help="public repository root, blob/raw file, release asset or ZIP archive URL")
    parser.add_argument("output_dir", nargs="?", default=".")
    parser.add_argument("--overwrite", action="store_true", help="atomically replace an existing file only after a complete successful download")
    args = parser.parse_args(argv)
    try:
        kind = classify(args.url)
        if kind[0] == "repo":
            _, owner, repo = kind
            repo = repo[:-4] if repo.endswith(".git") else repo
            if not repo or repo in (".", ".."):
                raise ValueError("A repository name is required.")
        else:
            target = kind[1]
            owner, repo = [unquote(p) for p in urlsplit(target).path.split("/")[1:3]]
            dest = os.path.join(args.output_dir, _filename(target))
            _check_destination(dest, args.overwrite)
        # A normal-looking URL cannot establish public visibility. Do not send
        # any repository path to a community mirror before this succeeds.
        verify_public_repository(owner, repo)
        os.makedirs(args.output_dir, exist_ok=True)
        if kind[0] == "repo":
            for branch in DEFAULT_BRANCHES:
                target = "https://github.com/%s/%s/archive/refs/heads/%s.zip" % (owner, repo, branch)
                dest = os.path.join(args.output_dir, "%s-%s.zip" % (repo, branch))
                print("downloading repo %s/%s (%s):" % (owner, repo, branch))
                if try_mirrors(target, dest, overwrite=args.overwrite):
                    return 0
        else:
            print("downloading: %s" % target)
            if try_mirrors(target, dest, overwrite=args.overwrite):
                return 0
        print("All mirrors failed. Existing files are unchanged. Use official GitHub CLI (gh) direct access, or review PROXIES.")
        return 2
    except (OSError, ValueError) as exc:
        print("Download stopped: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())

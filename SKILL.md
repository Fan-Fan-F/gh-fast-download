---
name: gh-fast-download
description: High-speed GitHub downloads via gh-proxy mirrors for users whose direct GitHub access is slow or blocked (e.g. mainland China). Use whenever the user asks to download, clone, or fetch a repository, raw file, or release asset from github.com / raw.githubusercontent.com — route it through a proxy mirror instead of hitting GitHub directly.
---

# gh-fast-download

Download GitHub content at high speed by routing through gh-proxy mirrors. For users whose direct GitHub connection is slow (typical in mainland China), this turns a painfully slow `git clone` / browser download into a fast one.

## First step — ask for the link

When this skill activates and the user has not already pasted a concrete GitHub URL, begin by asking (verbatim, in Chinese):

> 您需要下载哪个github项目，请输入原github项目链接，我会帮您急速下载

Wait for their reply before doing anything else. Skip this question only if the user already included a GitHub URL in their message.

## Core rule — how to convert a URL

Prepend a mirror domain to the **full original URL, keeping its `https://`**:

```
original : https://github.com/OWNER/REPO
proxied  : https://gh-proxy.org/https://github.com/OWNER/REPO
```

Everything after the mirror's `/` is treated as the target URL. That is the entire trick.

## Mirrors (try in order until one succeeds)

1. `https://gh-proxy.org/`
2. `https://gh-proxy.com/`
3. `https://ghfast.top/`
4. `https://ghproxy.net/`
5. `https://mirror.ghproxy.com/`

These are community mirrors and rotate over time. If several fail, replace them with currently-live ones (search "gh proxy 加速" for the current list).

## Procedure

1. **Identify the target type** from the user's URL:
   - whole repository → Case A (clone) or B (zip)
   - single file → Case C
   - release asset → Case D

2. **Build the proxied URL** for that case.

3. **Download** using the right command for the OS. Always use `-L` (follow redirects).

4. **Verify**: file exists with non-zero size, or a `.git` directory exists for clones.

5. **Report** the local path to the user.

## Case A — clone a whole repository

```
git clone https://gh-proxy.org/https://github.com/OWNER/REPO.git
```

If the mirror rejects the `.git` suffix, drop it, or use Case B.

## Case B — repository snapshot as a zip (no git needed)

Default branch is usually `main`; fall back to `master`, then a tag.

```
curl -L -o repo.zip "https://gh-proxy.org/https://github.com/OWNER/REPO/archive/refs/heads/main.zip"
```

If `main.zip` 404s, try `master.zip`, then `refs/tags/<TAG>.zip`.

## Case C — single file (raw)

First convert a `blob` URL to `raw`, then proxy it:

```
github.com/OWNER/REPO/blob/BRANCH/PATH
   ↓
https://gh-proxy.org/https://raw.githubusercontent.com/OWNER/REPO/BRANCH/PATH
```

## Case D — release asset

```
https://gh-proxy.org/https://github.com/OWNER/REPO/releases/download/TAG/FILE
```

## Download commands by OS

- Windows (PowerShell): `curl.exe -L -o FILE "URL"`  (or `Invoke-WebRequest -Uri "URL" -OutFile FILE`)
- macOS / Linux: `curl -L -o FILE "URL"`  (or `wget -O FILE "URL"`)

## Fallback

If every mirror fails (404 / 503 / timeout), tell the user the mirrors may be down, then retry with the **direct** URL as a last resort (slow but functional).

## Safety

- Only route **public** URLs through these mirrors. Never send private repos, authenticated URLs, or tokens through a third-party proxy.
- Mirrors are third-party and community-run; there is no uptime guarantee.

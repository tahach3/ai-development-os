# ChatGPT GitHub Connector Setup — `tahach3/ai-development-os`

**Purpose:** Help ChatGPT / GPT access this repository (connector search or public URLs).  
**Repo:** [`tahach3/ai-development-os`](https://github.com/tahach3/ai-development-os)  
**Public URL:** https://github.com/tahach3/ai-development-os  
**Visibility:** **PUBLIC** (changed 2026-07-23)  
**Owner type:** **Personal user account** `tahach3` (not a GitHub Organization).  
**Generated:** 2026-07-23  

This document is for the **human operator**. Cursor/CLI **cannot** install the ChatGPT GitHub App on your behalf.

---

## Current status: repo is PUBLIC

| Check | Result |
| --- | --- |
| Remote / public URL | https://github.com/tahach3/ai-development-os |
| Visibility | **PUBLIC** (`isPrivate: false`) |
| Default branch | `master` |

Anyone (including GPT) can open or fetch public files via github.com URLs **without** a private GitHub grant.

**Two access paths:**

1. **Paste / fetch public URLs** — GPT can read files from the public repo via `https://github.com/tahach3/ai-development-os/...` (or raw.githubusercontent.com). No ChatGPT GitHub App install required for this path.
2. **ChatGPT GitHub connector search** — Listing “installed repos” / connector search still requires installing the GitHub app from [chatgpt.com/apps](https://chatgpt.com/apps) and including this repo. Public visibility alone does **not** populate the connector’s installed-repos list.

**Recommendation:** Connect the GitHub app if you want connector search; otherwise paste the public URL (or specific file URLs) into ChatGPT.

---

## Why you might still see 404 / “0 repositories” in the connector

The repository is **PUBLIC**, but the ChatGPT GitHub **connector** only lists repos covered by the ChatGPT GitHub App install:

- Until the app is installed on account `tahach3` **and** this repo is included, connector “installed accounts” / search may still show **0**
- That is expected for the **connector** path; it is **not** proof the repo is missing on GitHub
- For public file access, paste https://github.com/tahach3/ai-development-os instead of relying on connector listing

`gh` CLI auth ≠ ChatGPT GitHub App install. Fixing CLI login does **not** grant ChatGPT connector access.

---

## Operator click-path (connector search — optional)

1. Open **[https://chatgpt.com/apps](https://chatgpt.com/apps)** (or ChatGPT → **Settings** → **Apps**).
2. Find **GitHub** and choose **Connect** / **Install** (or open the connected GitHub app and **Configure** / **Choose repositories**).
3. Sign in to GitHub as **`tahach3`** if prompted.
4. On the GitHub App install screen (often **ChatGPT Codex Connector**):
   - Install on your **personal account** `tahach3` (this repo is **not** under an Organization).
   - Repository access: **All repositories**, **or** **Only select repositories** and include **`ai-development-os`**.
5. Approve the requested permissions (read access to selected repos).
6. Optional direct GitHub install URL if ChatGPT UI is unclear:  
   [https://github.com/apps/chatgpt-codex-connector/installations/new](https://github.com/apps/chatgpt-codex-connector/installations/new)  
   Choose account `tahach3` → include `ai-development-os` → Install.
7. Wait a short time (often under a minute; sync lists can take longer), then return to ChatGPT.
8. Send exactly:

   ```text
   check ai-development-os on GitHub now
   ```

### Alternative without connector install

Paste into ChatGPT:

```text
Public repo: https://github.com/tahach3/ai-development-os
Please inspect README.md and docs/ from that URL.
```

### If you already connected GitHub but still get 404 in the connector

1. ChatGPT → Settings → Apps → GitHub → **Choose repositories** / gear → GitHub configure page.  
2. Or: GitHub → **Settings** → **Applications** → **Installed GitHub Apps** → **ChatGPT Codex Connector** → **Configure**.  
3. Ensure **`ai-development-os`** is checked (or switch to All repositories).  
4. Retry the ChatGPT message above — or use the public URL alternative.

### Organization vs user account

| Situation | What to do |
| --- | --- |
| This repo (`tahach3/ai-development-os`) | Install on **user** `tahach3` |
| Future org-owned repos | Install the same App **again** on that **Organization** (separate install) |

---

## Priority files ChatGPT asked to inspect first

After access works (connector or public URL), GPT should prioritize:

- `README.md`
- `pyproject.toml`
- `src/ai_dev_os/cli.py`
- `src/ai_dev_os/provider_readiness_discovery.py`
- `src/ai_dev_os/ci_engine.py`
- `src/ai_dev_os/ci_runner.py`
- `src/ai_dev_os/ci_stages.py`
- `docs/CLAUDE_HANDOFF_PROGRESS.md`
- `docs/ROUND_4A_LOCAL_CI_DESIGN.md`
- `tests/`
- `schemas/`
- `.github/workflows/ci.yml`

Also useful: `docs/ARCHITECTURE.md`, `docs/PROJECT_BOUNDARIES.md`, `docs/SECURITY_MODEL.md`, `docs/ROADMAP.md`.

Example raw/public file URLs:

- https://github.com/tahach3/ai-development-os/blob/master/README.md
- https://github.com/tahach3/ai-development-os/tree/master/docs

---

## Security notes

- Repo is **PUBLIC**: anyone on the internet can read its contents. Do **not** put secrets, API keys, tokens, or `.env` files in the repo.
- ChatGPT connector (if installed) gets **read access** to every repository you select.
- Prefer selecting only intended repos if you also have other private work in the same GitHub account.
- Disconnect anytime: ChatGPT → Settings → Apps → GitHub → Disconnect; or revoke the App under GitHub → Settings → Applications.

---

## Optional CLI sanity checks

```bash
gh auth status
gh api user --jq .login
gh repo view tahach3/ai-development-os --json nameWithOwner,visibility,isPrivate,url
gh repo list tahach3 --limit 20 --json name,visibility
```

Expected: login `tahach3`; `ai-development-os` with `visibility: PUBLIC` / `isPrivate: false`.

To confirm the App install on GitHub (still not ChatGPT UI):

```bash
# Lists installations your token can see; look for ChatGPT / Codex connector
gh api user/installations --jq ".installations[] | {app: .app_slug, account: .account.login}"
```

---

## What this environment cannot do

- Install or authorize the ChatGPT GitHub App in your ChatGPT or GitHub account
- Claim the connector is “connected” without your browser grant
- Start Round 4D2 / live model prompts

**Quick path:** Paste https://github.com/tahach3/ai-development-os into ChatGPT.  
**Connector path:** Finish the click-path above, then tell ChatGPT: **`check ai-development-os on GitHub now`**.

# Repository Hygiene Audit Report

**Date:** 2026-07-31
**Branch:** `feat/repo-hygiene-audit`
**Audit scope:** Root repo `karpathy-llm-wiki` + submodule `MinerU-GUI`

## Purpose

Verify that no unintended content was pushed to the repository: `.git` internals, initialization artifacts, wiki domain keywords/data, caches, build outputs, or secrets.

## Repository structure

| Repo | Remote(s) | HEAD | Status |
|---|---|---|---|
| Root `karpathy-llm-wiki` | `origin` → `wolfmanster/karpathy-llm-wiki`<br>`upstream` → `Astro-Han/karpathy-llm-wiki` | `1c29455` | Clean, no stash |
| Submodule `MinerU-GUI` | `origin` → `wolfmanster/MinerU-GUI` | `fb4caba` | Detached HEAD, in sync with `origin/main` (ahead/behind = 0/0), clean |

## Check results

| Check | Result |
|---|---|
| Tracked files in root repo | 20 — templates, examples, checker script, docs + `assets/karpathy-tweet.png` (283 KB, thematically relevant) |
| `.git` committed into the tree | No — all `.git` entries are normal VCS metadata directories |
| Caches / build artifacts | None (`__pycache__`, `*.pyc`, `.venv`, `output/`, `.coverage`, `.coverage.*`) |
| Secrets / environment files | None (`.env`, keys, tokens) |
| Wiki domain keywords / data | None — `references/*.md` templates and examples only contain markdown placeholder fields for keywords/domains; no wiki data was committed |
| Large files | Only `assets/karpathy-tweet.png` (283 KB); no oversized files |

## Note (not blocking)

The upstream submodule repo tracks `.window_geometry.json` (GUI window position, a local-state file) in its own history. This is a property of the *upstream* repository we reference; it is not part of our workspace to clean, and the parent repo's `.gitignore` cannot ignore already-tracked files inside a submodule.

## Actions taken

- Created branch `feat/repo-hygiene-audit` from `main`.
- Added this report as the branch's first commit.

## Not done (by design)

- No cleanup of committed content — audit confirmed nothing to clean.
- No push — branch is local only.
- No modification of the submodule — it is in sync with its remote.

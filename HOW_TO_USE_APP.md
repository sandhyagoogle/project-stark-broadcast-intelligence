# Quick Start & App Guide

**Path:** /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence

## 1. Open Project in Jetski

1. **File -> Open Folder...** (Cmd + O)
2. Press **Cmd + Shift + G**
3. Paste /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence -> **Open**

## 2. Run the App

### One Command
* **cd /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence**
* **./start.sh**
* Open **http://127.0.0.1:5173**

### Two Terminals
* **Backend (127.0.0.1:8000):**
  * **cd /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence/backend**
  * **./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload**
* **Frontend (127.0.0.1:5173):**
  * **cd /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence/frontend**
  * **npm run dev**

## 3. UI Tabs Overview

| Tab | What It Shows | Action to Try |
| :--- | :--- | :--- |
| **Edits** | Timestamp and game clock log of court event -> human cut -> extracted rule. | Click left-side game moments to inspect why the human cut. |
| **Ask Agent** | Engineering Q&A ("When this happens... what should the agent do?") + YouTube reference clips. | Ask a scenario question or click a preset to watch the exact YouTube clip example. |
| **Rules** | 16 consolidated rules (DIR, RPL, GFX, ORC). | Filter by agent role (director, replay, etc.). |
| **Shadow Mode** | PRD guardrails vs. Shadow Mode diffs. | Click **Evolve Skills** to synthesize emergent rules. |
| **Skills** | 4 compiled SKILL.md files + Antigravity SDK code. | Switch agent tabs to view SKILL.md markdown. |
| **Simulator** | Multi-agent simulator generating a live EDL. | Click **Run Agents** to run Orchestrator + 3 subagents. |
| **Add Video** | Analyze 30 to 60m YouTube URLs or .mp4/.mov files + Analyzed Videos Log (54 active broadcasts). | Select 30m/45m/60m and click **Analyze YouTube Video**. |

## 4. Playlist Corpus Note (Excluded Clips Reserved for Later)

* **Included Now:** **52 Full & Condensed Broadcasts** (25 to 72 minutes each) from the NCAA College Basketball playlist, plus 2 preloaded 30-minute reference games (**54 active broadcasts**, **7,984 game moments**).
* **Excluded for Now:**
  * **409 Game Highlight Broadcasts** (8 to 20 minutes each)
  * **109 Postgame & Feature Clips**
* Both excluded groups remain saved in **backend/app/broadcast_playlist_catalog.json** with **included_in_active_corpus: false** so they can be brought in later without re-fetching the playlist.


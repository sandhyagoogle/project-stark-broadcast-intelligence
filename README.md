# CourtVision AI — College Basketball Video Intelligence & Multi-Agent Control Room

CourtVision AI analyzes 30-minute NCAA college basketball broadcasts using **Gemini 3.8 Flash (`gemini-3.8-flash`)** via the **Interactions API**, extracts how a human broadcast editor makes cuts, queues multi-angle replays, and updates the broadcast scorebug, builds an empirical **Editor Knowledge Base**, and compiles that Knowledge Base into **4 Google Antigravity `SKILL.md` Agent Packages**:

1. **`orchestrator-agent`** (`exported_skills/orchestrator-agent/SKILL.md`): Coordinates priority handoffs across live game states, dead-ball whistles, timeouts, and clutch periods.
2. **`director-agent`** (`exported_skills/director-agent/SKILL.md`): Executes live camera cuts (`CAM-1 Main Wide`, `CAM-2 Low Baseline`, `CAM-3 Slash Iso`, `CAM-4 Overhead Rim`, `CAM-5 Coach Bench`).
3. **`replay-agent`** (`exported_skills/replay-agent/SKILL.md`): Captures lookback ring-buffer markers, selects optimal replay angles and slow-motion playback rates (`0.5x`–`0.75x`), and enforces the inbound safety cutoff.
4. **`graphics-scorebug-agent`** (`exported_skills/graphics-scorebug-agent/SKILL.md`): Synchronizes the broadcast scorebug (`+1`/`+2`/`+3`, shot-clock resets, bonus/foul badges) and triggers player stat lower-thirds and scoring-run banners.

---

## Quick Start (One Command)

From `/Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence`:

```bash
# Optional: set your Gemini API key for live MP4/MOV or YouTube video analysis
export GEMINI_API_KEY="your-gemini-api-key"

# Launch both Backend (http://127.0.0.1:8000) and Studio UI (http://127.0.0.1:5173)
chmod +x start.sh
./start.sh
```

Then open **http://127.0.0.1:5173** in your browser.

---

## Running Backend & Frontend Separately

### 1. Start the FastAPI Backend (`http://127.0.0.1:8000`)
```bash
cd /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence/backend
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Start the React + Vite Broadcast Studio UI (`http://127.0.0.1:5173`)
```bash
cd /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence/frontend
npm run dev
```

### 3. Run Automated Security & API Tests
```bash
cd /Users/sandhyapatil/.gemini/jetski/scratch/hoops-broadcast-intelligence/backend
./.venv/bin/python -m pytest -v tests/test_api_and_security.py
```

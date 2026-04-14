# WeldBot — Vulcan OmniPro 220 Multimodal Reasoning Agent

A multimodal reasoning agent for the Vulcan OmniPro 220 multiprocess welder, built for the [Prox Founding Engineer Challenge](https://useprox.com/join/challenge).

## Live demo

**[https://prox-challenge-3fr8.onrender.com/](https://prox-challenge-3fr8.onrender.com/)**

Open the link in a browser to use the full app (streaming chat, diagrams, manual page images, weld photo upload). The service is hosted on [Render](https://render.com); cold starts may take ~30–60 seconds on the free tier.

---

## Local setup

```bash
git clone https://github.com/nehanataraj/prox-challenge.git
cd prox-challenge

cp .env.example .env
# Edit .env and add your Anthropic API key

pip install -r backend/requirements.txt
python backend/main.py
# → http://localhost:8000
```

**Environment:** `ANTHROPIC_API_KEY` (required). For production-style runs, set `ENV=production` (disables uvicorn reload; `PORT` is respected when set by the host).

---

## What it does

### Multimodal input
- **Text** — settings, polarity, duty cycles, troubleshooting, process selection
- **Images** — upload or drag-and-drop a weld photo for diagnosis

### Outputs (not text-only)
- **SVG** — polarity / wiring diagrams
- **Markdown tables** — duty cycles, job settings (120V vs 240V)
- **Mermaid** — troubleshooting flowcharts
- **HTML tables** — process comparison
- **Manual pages** — relevant PDF pages are rendered as images via `/manual-image/...` (PyMuPDF extracts pages at startup)

### Stack

| Layer | Tech |
|-------|------|
| Model | Claude Opus 4.6 (adaptive thinking) |
| Documents | Anthropic Files API (PDFs referenced by `file_id`) |
| Manual images | PyMuPDF → PNG, served by FastAPI |
| Backend | FastAPI, streaming SSE |
| Frontend | Vanilla HTML/CSS/JS, Mermaid, Marked |
| Deploy | Docker (`Dockerfile`), e.g. Render |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Frontend — vanilla JS, SSE, Mermaid, Marked        │
│  Renders SVG, HTML, manual images, markdown tables  │
└────────────────────────┬────────────────────────────┘
                         │ POST /chat (SSE)
┌────────────────────────▼────────────────────────────┐
│  FastAPI — sessions, Files API refs, page images    │
└────────────────────────┬────────────────────────────┘
                         │ Anthropic API
┌────────────────────────▼────────────────────────────┐
│  Claude Opus 4.6 — system prompt defines visuals   │
│  per question type + manual page image markdown     │
└─────────────────────────────────────────────────────┘
```

**Design notes:** PDFs upload once at startup; first chat turn attaches all manuals; long system prompt uses prompt caching; conversation history is trimmed while keeping the first turn (manual context).

---

## Example questions

- Duty cycle at a given amperage on 240V
- Flux-core polarity wiring step-by-step
- Porosity troubleshooting with a flowchart
- Process comparison for a given material/thickness
- *(with photo)* “What’s wrong with this bead?”

---

## Repository layout

```
prox-challenge/
├── backend/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   └── index.html
├── files/
│   ├── owner-manual.pdf
│   ├── quick-start-guide.pdf
│   └── selection-chart.pdf
├── Dockerfile
├── .dockerignore
├── .env.example
└── README.md
```

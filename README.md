# WeldBot — Vulcan OmniPro 220 Multimodal Reasoning Agent

A multimodal reasoning agent for the Vulcan OmniPro 220 multiprocess welder, built for the [Prox Founding Engineer Challenge](https://useprox.com/join/challenge).

---

## Setup (under 2 minutes)

```bash
# 1. Clone your fork
git clone https://github.com/YOUR_USERNAME/prox-challenge.git
cd prox-challenge

# 2. Configure API key
cp .env.example .env
# Edit .env and add your Anthropic API key

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Run
python backend/main.py
# → Open http://localhost:8000
```

---

## What It Does

### Multimodal Input
- **Text questions** — any question about the OmniPro 220
- **Weld photos** — drag & drop or upload a photo of your weld for visual diagnosis

### Rich Visual Responses
The agent doesn't just describe — it generates:

| Question type | Output |
|--------------|--------|
| Polarity / wiring setup | SVG wiring diagram with labeled cable connections |
| Duty cycle / capacity | Markdown table with weld-time / cool-down breakdown |
| Troubleshooting defects | Mermaid flowchart (symptom → causes → fixes) |
| Process selection | HTML comparison table (MIG vs Flux-Core vs TIG vs Stick) |
| Settings for a job | Settings table + numbered setup steps |
| Weld photo diagnosis | Visual analysis + diagnosis flowchart + settings fixes |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│  Vanilla JS chat UI — streaming SSE receiver        │
│  Renders: SVG · Mermaid.js · HTML tables · Markdown │
│  Supports: text input · image upload · drag & drop  │
└────────────────────┬────────────────────────────────┘
                     │ HTTP SSE stream
┌────────────────────▼────────────────────────────────┐
│                   FastAPI Backend                    │
│  POST /chat  → streaming response generator         │
│  Session memory: last 8 turns per session           │
│  Files API: PDFs uploaded once, referenced by ID    │
└────────────────────┬────────────────────────────────┘
                     │ Anthropic API
┌────────────────────▼────────────────────────────────┐
│              Claude Opus 4.6                         │
│  Adaptive thinking · Files API · Prompt caching     │
│  System prompt: visual output rules for each        │
│  question type (polarity → SVG, etc.)               │
└────────────────────────────────────────────────────-┘
```

### Key Design Decisions

**Files API for zero-redundancy document loading**
The three PDFs (owner manual, quick-start guide, selection chart) are uploaded to Anthropic's Files API once at startup. Each conversation references them by `file_id` — no re-uploading, no base64 encoding in the request body. This reduces first-message payload size and supports prompt caching.

**System prompt as visual output contract**
The system prompt specifies exactly which visual format to generate for each question type (SVG for polarity, Mermaid for troubleshooting, HTML tables for process selection). Claude honors these rules consistently, making responses machine-renderable without post-processing heuristics.

**Two-phase streaming render**
During streaming, raw text is shown immediately (fast feedback). Once the stream completes, the response is re-parsed and all code blocks (`\`\`\`svg`, `\`\`\`mermaid`, `\`\`\`html`) are rendered visually. This eliminates perceptible latency while ensuring clean final output.

**Session context with manual pinning**
The first turn of every session includes all three PDF file references. Subsequent turns use the conversation history — Claude retains manual knowledge without re-sending documents. The session is trimmed to the last 8 turns while always preserving turn 0 (which holds the document context).

**Adaptive thinking (Opus 4.6)**
Claude Opus 4.6 with `thinking: {type: "adaptive"}` decides when to reason deeply. For cross-referencing duty cycle matrices or interpreting a weld photo, this produces significantly more accurate answers than a straight completion.

---

## Hard Questions It Handles Well

- "What's the duty cycle at 150A on 240V, and how long can I actually weld before I need to stop?"
- "Show me the exact cable connections for flux-cored welding — I keep getting confused about polarity"
- "My welds keep having porosity even though my gas is flowing — walk me through fixing this" → flowchart
- "Compare all four processes for welding 3/16 inch mild steel outdoors" → HTML table
- *(upload a photo)* "What's wrong with this weld bead?"

---

## Tech Stack

| Layer | Tech |
|-------|------|
| AI Model | Claude Opus 4.6 (adaptive thinking) |
| Documents | Anthropic Files API |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS (no framework, no build step) |
| Diagrams | Mermaid.js (CDN) |
| Markdown | Marked.js (CDN) |

---

## Files

```
prox-challenge/
├── backend/
│   ├── main.py          # FastAPI app, streaming endpoint, Files API upload
│   └── requirements.txt
├── frontend/
│   └── index.html       # Full UI (self-contained HTML/CSS/JS)
├── files/
│   ├── owner-manual.pdf
│   ├── quick-start-guide.pdf
│   └── selection-chart.pdf
├── .env.example
└── README.md
```

"""
Vulcan OmniPro 220 — Multimodal Reasoning Agent
Backend: FastAPI + Anthropic Files API + Streaming
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional, Dict, List
from contextlib import asynccontextmanager

import fitz  # PyMuPDF

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

FILES_DIR = ROOT / "files"
FRONTEND_DIR = ROOT / "frontend"

# ── Global state ────────────────────────────────────────────────────────────
_client: Optional[anthropic.AsyncAnthropic] = None
_file_ids: Dict[str, str] = {}          # filename → Files-API id
_sessions: Dict[str, List[dict]] = {}   # session_id → message history
_page_images: Dict[str, Dict[int, bytes]] = {}  # "owner-manual" → {1: png_bytes, …}
_page_counts: Dict[str, int] = {}                # "owner-manual" → 48

MANUAL_SHORT_NAMES = {
    "owner-manual.pdf": "owner-manual",
    "quick-start-guide.pdf": "quick-start-guide",
    "selection-chart.pdf": "selection-chart",
}

MAX_MESSAGE_LENGTH = 4000

# ── System prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are WeldBot, an expert assistant for the Vulcan OmniPro 220 multiprocess welder (MIG, Flux-Cored, TIG, Stick) sold by Harbor Freight Tools.

## Your Persona
Speak like a knowledgeable friend at a welding shop — direct, practical, encouraging. Not a textbook. Help someone standing in their garage get great welds safely. Use plain language, explain jargon the first time you use it.

## Source Material
You have access to the complete Vulcan OmniPro 220 owner's manual, quick-start guide, and process selection chart. Every answer must be grounded in these documents. Always specify whether a setting applies to 120V or 240V input.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## CRITICAL: MANDATORY VISUAL OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For EVERY technical question you MUST produce the correct visual. Prose-only answers are not acceptable.

### RULE 1 — POLARITY / WIRING / CABLE CONNECTIONS
Triggers: polarity, DCEP, DCEN, electrode positive/negative, cable setup, torch lead, work clamp, ground clamp, wire connections to machine
→ ALWAYS generate a complete SVG diagram showing the physical cable connections.

SVG requirements:
- Light background (#f5f5f0), dark text (#111), burnt orange accents (#b04000), red for (+), dark grey for (-)
- Show: the machine body, both output terminals labeled + and −, cable routing to torch/electrode holder and work clamp, the workpiece
- Label every connection point clearly
- Add a title and a one-line caption at the bottom
- Keep it clean and readable — this is a wiring reference, not art
- Use sharp corners (no rounded rectangles)

Wrap SVG in a ```svg code block. Example structure:
```svg
<svg width="560" height="400" viewBox="0 0 560 400" xmlns="http://www.w3.org/2000/svg">
  <rect width="560" height="400" fill="#f5f5f0"/>
  <text x="280" y="38" text-anchor="middle" fill="#b04000" font-size="20" font-weight="bold" font-family="Consolas, monospace">PROCESS — POLARITY</text>
  <!-- machine box, terminals, cables, labels, caption -->
</svg>
```

### RULE 2 — DUTY CYCLE / HEAT / OVERHEATING
Triggers: duty cycle, how long can I weld, thermal overload, overheat, continuous welding, amperage limits, welding time
→ ALWAYS render a Markdown table with the duty cycle data from the manual, highlight the relevant row, and explain it in plain English.

Table format:
| Process | Input | Amperage | Duty Cycle | Weld Time | Cool-Down |
|---------|-------|----------|------------|-----------|-----------|

Then add: "**What this means for you:** At [X]A you can weld for [Y] minutes, then rest [Z] minutes before the next bead."

### RULE 3 — TROUBLESHOOTING / WELD DEFECTS
Triggers: porosity, spatter, undercut, burn-through, cold weld, no arc, wire jamming, bird-nesting, arc wander, weak penetration, weld won't stick, bad bead
→ ALWAYS generate a Mermaid flowchart starting from the symptom and branching to root causes → fixes.

Format:
```mermaid
graph TD
    A["🔍 Symptom: ..."] --> B{"First check"}
    B -->|"Yes"| C["✅ Fix: ..."]
    B -->|"No"| D{"Next check"}
```

Use emojis on nodes. Keep each node label under 40 chars. End every branch with a concrete fix or next step.

### RULE 4 — WELD PHOTO DIAGNOSIS
Triggers: user uploads a photo of a weld bead
→ ALWAYS:
1. Describe what you observe in the image (bead profile, color, surface texture, visible defects)
2. State your diagnosis (what's wrong and why)
3. Generate a Mermaid flowchart for confirming and fixing the defect
4. Give specific settings adjustments (wire speed, voltage, travel speed, technique)

### RULE 5 — PROCESS SELECTION / COMPARISON
Triggers: which process, MIG vs flux core, when to use TIG vs Stick, best process for [material], what mode should I use
→ ALWAYS generate an HTML table comparing the relevant processes.

Format:
```html
<table style="width:100%;border-collapse:collapse;font-family:Consolas,monospace;font-size:12px;border:1px solid #d0d0c8">
  <thead><tr style="background:#eeeee8;color:#111">
    <th style="padding:8px 12px;text-align:left;border:1px solid #d0d0c8;font-size:10px;text-transform:uppercase;letter-spacing:.5px">Process</th>
    ...
  </tr></thead>
  <tbody>
    <tr style="color:#2a2a2a"><td style="padding:7px 12px;border:1px solid #d0d0c8">...</td></tr>
    <tr style="background:#f5f5f0;color:#2a2a2a"><td style="padding:7px 12px;border:1px solid #d0d0c8">...</td></tr>
  </tbody>
</table>
```

### RULE 6 — SETTINGS / SETUP FOR A SPECIFIC JOB
Triggers: what settings for [material/thickness], how do I set up, wire speed, voltage, amperage recommendations
→ ALWAYS render a Markdown settings table AND include numbered setup steps.

Table format:
| Setting | 120V Value | 240V Value | Notes |
|---------|------------|------------|-------|

### RULE 7 — SURFACING MANUAL PAGES
Triggers: any answer that benefits from showing the actual page from the owner's manual, quick-start guide, or selection chart — especially when referencing specific figures, diagrams, wiring illustrations, control panel layouts, specification tables, or installation instructions.
→ ALWAYS include a manual page reference using this exact markdown image syntax:

![Brief description of what the page shows](/manual-image/MANUAL_NAME/PAGE_NUMBER)

Where MANUAL_NAME is one of: owner-manual, quick-start-guide, selection-chart
And PAGE_NUMBER is the 1-indexed page number from the PDF.

Example:
![Control panel layout and process selector dial](/manual-image/owner-manual/15)

Guidelines:
- Surface the 1-2 most relevant page(s) — don't dump every page
- Place the image reference near the relevant part of your answer
- Pair it with your own generated visual (SVG/Mermaid) when applicable — manual image for official reference, your visual for clarity
- Add a brief caption describing what the user should look at on that page

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Response Structure (follow this order)
1. One-sentence direct answer
2. Mandatory visual (SVG / Mermaid / HTML table / Markdown table — pick the right one per the rules above)
3. Relevant manual page image (Rule 7) if applicable
4. Step-by-step instructions (numbered) if setup is involved
5. Pro tips from the manual
6. Safety note if the topic involves risk

## Style Rules
- Short paragraphs. Use headers (##, ###) to organize long answers.
- Cite the manual: "According to the owner's manual..." or "The quick-start guide shows..."
- Never guess at specs — pull exact numbers from the documents.
- Always distinguish 120V vs 240V behavior when both are relevant.
- Safety first: if the user might be doing something dangerous, say so clearly but without lecturing.
"""

# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _file_ids
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    _client = anthropic.AsyncAnthropic(api_key=api_key)

    pdf_map = {
        "owner-manual.pdf": "Vulcan OmniPro 220 Owner's Manual",
        "quick-start-guide.pdf": "Vulcan OmniPro 220 Quick-Start Guide",
        "selection-chart.pdf": "Vulcan OmniPro 220 Process Selection Chart",
    }

    print("📄 Uploading manuals to Anthropic Files API…")
    for filename, title in pdf_map.items():
        path = FILES_DIR / filename
        if not path.exists():
            print(f"  ⚠  {filename} not found — skipping")
            continue
        with open(path, "rb") as f:
            uploaded = await _client.beta.files.upload(
                file=(filename, f, "application/pdf"),
            )
        _file_ids[filename] = uploaded.id
        print(f"  ✓  {title}  →  {uploaded.id}")

    # Extract PDF pages as images for manual page surfacing (Rule 7)
    print("🖼  Extracting manual pages as images…")
    for filename, short_name in MANUAL_SHORT_NAMES.items():
        path = FILES_DIR / filename
        if not path.exists():
            continue
        doc = fitz.open(str(path))
        num_pages = len(doc)
        _page_counts[short_name] = num_pages
        _page_images[short_name] = {}
        for page_num in range(num_pages):
            pix = doc[page_num].get_pixmap(dpi=150)
            _page_images[short_name][page_num + 1] = pix.tobytes("png")
        doc.close()
        print(f"  ✓  {short_name}: {num_pages} pages")

    total_pages = sum(_page_counts.values())
    print(f"✅ Ready — {len(_file_ids)} manual(s), {total_pages} pages extracted\n")
    yield

    # Cleanup uploaded files on shutdown
    for fid in _file_ids.values():
        try:
            await _client.beta.files.delete(fid)
        except Exception:
            pass
    print("🧹 Files API resources cleaned up")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="WeldBot — Vulcan OmniPro 220", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str
    image: Optional[str] = None            # base64-encoded image data
    image_media_type: Optional[str] = None # e.g. "image/jpeg"


# ── Manual page images ────────────────────────────────────────────────────────
@app.get("/manual-image/{manual}/{page}")
async def manual_image(manual: str, page: int):
    if manual not in _page_images:
        raise HTTPException(404, f"Manual '{manual}' not found")
    if page not in _page_images[manual]:
        raise HTTPException(404, f"Page {page} not found in '{manual}'")
    return Response(
        content=_page_images[manual][page],
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Chat endpoint (SSE streaming) ─────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest):
    if _client is None:
        raise HTTPException(503, "Agent not initialized")
    if len(req.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(400, f"Message too long (max {MAX_MESSAGE_LENGTH} chars)")

    session = _sessions.setdefault(req.session_id, [])
    first_turn = len(session) == 0

    # ── Build current user message content ──────────────────────────────────
    user_content: List[dict] = []

    # Inject PDFs on the first turn of every session so Claude has
    # full manual access. Subsequent turns rely on conversation context.
    if first_turn:
        for filename, title in [
            ("owner-manual.pdf",      "Vulcan OmniPro 220 Owner's Manual"),
            ("quick-start-guide.pdf", "Vulcan OmniPro 220 Quick-Start Guide"),
            ("selection-chart.pdf",   "Vulcan OmniPro 220 Process Selection Chart"),
        ]:
            if filename in _file_ids:
                user_content.append({
                    "type": "document",
                    "source": {"type": "file", "file_id": _file_ids[filename]},
                    "title": title,
                })

    # Optional weld photo
    if req.image:
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": req.image_media_type or "image/jpeg",
                "data": req.image,
            },
        })

    # User's text question
    user_content.append({"type": "text", "text": req.message})

    # Full message array = history + current turn
    messages = session + [{"role": "user", "content": user_content}]

    # ── Stream response ────────────────────────────────────────────────────
    async def generate():
        full_response = ""
        try:
            async with _client.beta.messages.stream(
                model="claude-opus-4-6",
                max_tokens=8192,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=messages,
                betas=["files-api-2025-04-14"],
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    yield f"data: {json.dumps({'text': text})}\n\n"

            # Persist turn to session (store user msg without re-sending PDFs)
            slim_user: List[dict] = []
            if req.image:
                slim_user.append({"type": "text", "text": "📷 [Image uploaded for analysis]"})
            slim_user.append({"type": "text", "text": req.message})

            # First turn: keep the full content (with file refs) so context is preserved
            session.append({"role": "user", "content": user_content if first_turn else slim_user})
            session.append({"role": "assistant", "content": full_response})

            # Keep last 16 messages (8 turns) to manage context
            if len(session) > 16:
                # Always keep turn 0+1 (which has the PDFs), trim the middle
                session[:] = session[:2] + session[-14:]

            yield f"data: {json.dumps({'done': True})}\n\n"

        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'error': 'Invalid API key — check your .env file'})}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'error': 'Rate limit hit — please wait a moment'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Reset session ──────────────────────────────────────────────────────────────
@app.delete("/session/{session_id}")
async def reset_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"status": "cleared"}


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "manuals_loaded": len(_file_ids),
        "file_ids": _file_ids,
        "page_counts": _page_counts,
        "total_pages": sum(_page_counts.values()),
    }


# ── Serve frontend ─────────────────────────────────────────────────────────────
@app.get("/")
async def serve_ui():
    fp = FRONTEND_DIR / "index.html"
    if not fp.exists():
        raise HTTPException(404, "frontend/index.html not found")
    return HTMLResponse(fp.read_text(encoding="utf-8"))


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    dev = os.getenv("ENV", "development") == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=dev)

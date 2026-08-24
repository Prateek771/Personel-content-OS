"""Interactive N8N Visual Studio with 3 Source Adapters, 14-Pt Reasoner, Visual/Carousel Generator, and 1-Click Approval."""

import os
import json
import time
import uuid
import secrets
import threading
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from intelligence_os.config.settings import get_settings
from intelligence_os.core.health import run_health_check
from intelligence_os.core.logger import logger
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import DiscoveryRecord, ContentDraftRecord, ResearchCoreData
from intelligence_os.storage.repositories import (
    DiscoveryRepository,
    ContentDraftRepository,
    PublishingQueueRepository,
    AnalyticsRepository,
)
from intelligence_os.visuals.carousel_renderer import CarouselRenderer

app = FastAPI(title="AI Content Intelligence OS — Scrapling Studio")

# In-flight OAuth state tokens (single-user local app)
_linkedin_oauth_states: set[str] = set()

# Background job registry so the UI can show REAL pipeline progress
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _update_job(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated_at"] = time.time()


def _push_job_event(job_id: str, stage: str, label: str, detail: str = "") -> None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j is not None:
            j.setdefault("events", []).append({"ts": time.time(), "stage": stage, "label": label, "detail": detail})
            j["updated_at"] = time.time()


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return None
        # shallow copy but deep-copy events/snapshots so caller can't mutate
        c = dict(j)
        c["events"] = list(j.get("events", []))
        if "snapshots" in j:
            c["snapshots"] = dict(j["snapshots"])
        return c


# Ensure output directories exist and mount static media
output_dir = Path("output")
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / "carousels").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(output_dir.resolve())), name="media")


def _save_env_values(updates: dict[str, str]) -> None:
    """Persist key-values into the local .env file (secrets store for personal use)."""
    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for key, value in updates.items():
        prefixed = f"{key}="
        replaced = False
        for i, line in enumerate(lines):
            if line.startswith(prefixed):
                lines[i] = f"{key}={value}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_db():
    settings = get_settings()
    db = Database(settings.database_path)
    run_migrations(db)
    return db


class GenerateRequest(BaseModel):
    platform: str = "x"  # "x", "linkedin", or "both"
    topic: str | None = None
    url: str | None = None


class PublishRequest(BaseModel):
    draft_id: str


class DraftUpdateRequest(BaseModel):
    draft_id: str
    generated_copy: str


@app.post("/api/drafts/update")
def update_draft_endpoint(req: DraftUpdateRequest):
    """Persist human edits to a draft's copy before publishing."""
    try:
        db = get_db()
        repo = ContentDraftRepository(db)
        draft = repo.get_by_id(req.draft_id)
        if not draft:
            return JSONResponse(status_code=200, content={"status": "error", "message": "Draft not found."})
        with db.session() as conn:
            conn.execute(
                "UPDATE content_drafts SET generated_copy = ?, updated_at = datetime('now') WHERE id = ?;",
                (req.generated_copy, req.draft_id),
            )
        return JSONResponse(content={"status": "success"})
    except Exception as e:
        logger.error(f"Draft update failed: {e}")
        return JSONResponse(status_code=200, content={"status": "error", "message": str(e)})


@app.post("/api/harvest")
def harvest_endpoint():
    """Start a harvest job across all enabled sources.yaml sources; UI polls for progress."""
    job_id = f"harv-{uuid.uuid4().hex[:10]}"
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "stage": "scrapling",
            "stage_label": "Queued",
            "detail": "",
            "events": [],
            "stats": None,
            "error": None,
            "started_at": time.time(),
        }
    _push_job_event(job_id, "queued", "Queued", "Harvest queued")
    thread = threading.Thread(target=_run_harvest_job, args=(job_id,), daemon=True)
    thread.start()
    return JSONResponse(content={"status": "queued", "job_id": job_id})


def _run_harvest_job(job_id: str) -> None:
    """Background worker running one full harvest cycle with live per-node events."""
    try:
        from intelligence_os.config.sources_manager import SourceManager
        from intelligence_os.research.harvest_engine import HarvestEngine
        from intelligence_os.research.adapters.scrapling import ScraplingAdapter
        from intelligence_os.research.adapters.rss import RSSAdapter
        from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
        from intelligence_os.research.adapters.github import GitHubAdapter
        from intelligence_os.research.adapters.x import XAdapter

        settings = get_settings()
        db = get_db()

        def _on_progress(stage: str, label: str, detail: str = ""):
            _update_job(job_id, status="running", stage=stage, stage_label=label, detail=detail)
            _push_job_event(job_id, stage, label, detail)

        _on_progress("scrapling", "Starting Harvest", "Initializing adapters...")

        engine = HarvestEngine(
            source_manager=SourceManager(),
            db=db,
            scrapling_adapter=ScraplingAdapter(),
            rss_adapter=RSSAdapter(),
            agent_reach_adapter=AgentReachAdapter(
                base_url=settings.agent_reach_base_url,
                api_key=settings.agent_reach_api_key,
            ),
            github_adapter=GitHubAdapter(token=settings.github_token),
            x_adapter=XAdapter(
                consumer_key=settings.x_consumer_key or settings.x_api_key,
                consumer_secret=settings.x_consumer_secret or settings.x_api_secret,
                access_token=settings.x_access_token,
                access_token_secret=settings.x_access_token_secret,
            ),
        )
        stats = engine.run_harvest_cycle(on_progress=_on_progress)
        _update_job(
            job_id,
            status="success",
            stage="scrapling",
            stage_label="Harvest Complete",
            detail=f"{stats['new_inserted']} new / {stats['items_harvested']} items",
            stats=stats,
        )
        _push_job_event(job_id, "scrapling", "Harvest Complete", f"{stats['new_inserted']} new / {stats['items_harvested']} items")
    except Exception as e:
        logger.error(f"Harvest error: {e}\n{traceback.format_exc()}")
        _update_job(job_id, status="error", stage_label="Harvest Failed", error=str(e))


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Content Intelligence OS — LinkedIn Carousel Studio</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');
body { font-family: 'Plus Jakarta Sans', sans-serif; background: #0b1020; color: #e2e8f0; }
.font-mono { font-family: 'JetBrains Mono', monospace; }
.canvas-bg { background: radial-gradient(1200px 600px at 70% -10%, #16224a 0%, #0b1020 60%); }
.n8n-node {
  position: absolute; width: 168px; background: #111a33; border: 1.5px solid #243154;
  border-radius: 14px; padding: 12px 14px; box-shadow: 0 10px 30px rgba(0,0,0,.35);
  transition: all .35s ease; cursor: pointer; z-index: 5;
}
.n8n-node:hover { border-color: #3b82f6; transform: translateY(-2px); }
.n8n-node .dot { width: 12px; height: 12px; border-radius: 50%; background: #334155; box-shadow: 0 0 0 4px rgba(51,65,85,.25); }
.n8n-node .title { font-weight: 800; font-size: 12.5px; margin-top: 8px; color: #f1f5f9; }
.n8n-node .sub { font-size: 10.5px; color: #94a3b8; margin-top: 3px; line-height: 1.3; }
.n8n-node .idx { position: absolute; top: -10px; left: -10px; width: 22px; height: 22px; border-radius: 50%; background: #1e293b; border: 1.5px solid #334155; color: #94a3b8; font-size: 11px; font-weight: 800; display: flex; align-items: center; justify-content: center; }
.n8n-node.done { border-color: #10b981; }
.n8n-node.done .dot { background: #10b981; box-shadow: 0 0 0 5px rgba(16,185,129,.18); }
.n8n-node.done .idx { background: #10b981; border-color: #10b981; color: #04140d; }
.n8n-node.running { border-color: #3b82f6; box-shadow: 0 0 0 5px rgba(59,130,246,.25), 0 10px 30px rgba(0,0,0,.35); animation: pulse 1.3s infinite; }
.n8n-node.running .dot { background: #3b82f6; box-shadow: 0 0 0 6px rgba(59,130,246,.3); }
.n8n-node.running .idx { background: #3b82f6; border-color: #3b82f6; color: #fff; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 5px rgba(59,130,246,.25), 0 10px 30px rgba(0,0,0,.35);} 50% { box-shadow: 0 0 0 10px rgba(59,130,246,.05), 0 10px 30px rgba(0,0,0,.35);} }
#connectors { position: absolute; inset: 0; z-index: 1; pointer-events: none; }
#connectors path { fill: none; stroke: #2a3a63; stroke-width: 3; stroke-linecap: round; transition: stroke .4s ease; }
#connectors path.lit { stroke: #3b82f6; stroke-dasharray: 600; stroke-dashoffset: 600; animation: draw .6s forwards; filter: drop-shadow(0 0 6px rgba(59,130,246,.5)); }
@keyframes draw { to { stroke-dashoffset: 0; } }
.tl-step { flex: 1; text-align: center; padding: 8px 6px; border-radius: 10px; border: 1.5px solid #243154; background: #111a33; font-size: 10px; font-weight: 700; color: #64748b; }
.tl-step.active { border-color: #3b82f6; background: #15244a; color: #bfdbfe; }
.tl-step.done { border-color: #10b981; background: #0f2e22; color: #6ee7b7; }
#log-box { font-family: 'JetBrains Mono', monospace; font-size: 11px; line-height: 1.5; max-height: 170px; overflow-y: auto; }
.dot-ready { background: #10b981; box-shadow: 0 0 0 4px rgba(16,185,129,.2); }
.dot-busy { background: #3b82f6; animation: blink 1s infinite; }
@keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.spin { width: 16px; height: 16px; border: 2px solid #334155; border-top-color: #3b82f6; border-radius: 50%; display: inline-block; animation: rot .8s linear infinite; vertical-align: middle; }
@keyframes rot { to { transform: rotate(360deg); } }
.slide-card { background: #0f1830; border: 1px solid #243154; border-radius: 12px; overflow: hidden; }
.slide-card img { width: 100%; display: block; }
</style>
</head>
<body class="canvas-bg min-h-screen flex flex-col">
<nav class="flex items-center justify-between px-6 py-4 border-b border-[#1c2742] sticky top-0 z-20 bg-[#0b1020]/95 backdrop-blur">
  <div class="flex items-center gap-3">
    <div style="width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,#f97316,#e11d48,#4f46e5);padding:2px;display:flex;align-items:center;justify-content:center"><div style="background:#0b1020;width:100%;height:100%;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800;color:#ea580c">◈</div></div>
    <div>
      <div style="font-weight:800;font-size:15px">AI Content Intelligence OS <span style="font-size:10px;background:#0f2e22;color:#6ee7b7;padding:2px 8px;border-radius:999px;border:1px solid #14532d;margin-left:6px">LinkedIn Carousel Studio</span></div>
      <div style="font-size:11px;color:#64748b">Topic → Web + Social Scrape → 14-Pt Analysis → Copy → 5-Slide Visuals → Approval → LinkedIn</div>
    </div>
  </div>
  <a href="/auth/linkedin/start" id="btn-li-connect" style="display:none;background:#0ea5e9;color:white;padding:8px 14px;border-radius:11px;font-weight:700;font-size:12px;text-decoration:none">Connect LinkedIn</a>
</nav>

<div style="max-width:1180px;margin:0 auto;padding:18px;width:100%;display:flex;flex-direction:column;gap:16px">
  <!-- Topic bar -->
  <div style="background:#111a33;border:1.5px solid #243154;border-radius:16px;padding:14px 16px;display:flex;flex-wrap:wrap;align-items:center;gap:12px">
    <span class="font-mono" style="font-size:11px;color:#64748b">TOPIC</span>
    <input id="topic-input" type="text" placeholder="Type a topic and press Enter  (e.g. 'browser-use agent', 'kubernetes autoscaling', 'AI agent memory')" style="flex:1;min-width:320px;font-size:13px;padding:10px 14px;border-radius:12px;border:1.5px solid #334155;background:#0b1020;color:#e2e8f0;outline:none">
    <span id="live-dot" class="dot dot-ready"></span>
    <strong id="live-status" class="font-mono" style="font-size:12px">READY</strong>
    <span id="live-detail" style="font-size:11px;color:#94a3b8;margin-left:4px"></span>
  </div>

  <!-- N8N canvas -->
  <div id="canvas" style="position:relative;height:480px;background:#0d1428;border:1.5px solid #1c2742;border-radius:22px;overflow:hidden">
    <svg id="connectors"></svg>
    <div class="n8n-node" id="node-scrapling" data-stage="scrapling" onclick="selectNode('scrapling')" style="left:24px;top:300px"><div class="idx">1</div><div class="dot"></div><div class="title">Scrape</div><div class="sub">Web + Social (Agent Reach)</div></div>
    <div class="n8n-node" id="node-reasoner" data-stage="reasoner" onclick="selectNode('reasoner')" style="left:222px;top:60px"><div class="idx">2</div><div class="dot"></div><div class="title">14-Pt Analysis</div><div class="sub">Grounded reasoner</div></div>
    <div class="n8n-node" id="node-content" data-stage="content" onclick="selectNode('content')" style="left:430px;top:300px"><div class="idx">3</div><div class="dot"></div><div class="title">Copywriting</div><div class="sub">Hook + 5 slides</div></div>
    <div class="n8n-node" id="node-visuals" data-stage="visuals" onclick="selectNode('visuals')" style="left:638px;top:60px"><div class="idx">4</div><div class="dot"></div><div class="title">Visuals</div><div class="sub">Grok bg + overlay</div></div>
    <div class="n8n-node" id="node-review" data-stage="review" onclick="selectNode('review')" style="left:846px;top:300px"><div class="idx">5</div><div class="dot"></div><div class="title">Approval Gate</div><div class="sub">Review & approve</div></div>
    <div class="n8n-node" id="node-dispatch_li" data-stage="dispatch_li" onclick="selectNode('dispatch_li')" style="left:1010px;top:60px"><div class="idx">6</div><div class="dot"></div><div class="title">Publish</div><div class="sub">LinkedIn</div></div>
  </div>

  <!-- Live timeline -->
  <div id="timeline-box" style="display:none;background:#111a33;border:1.5px solid #243154;border-radius:16px;padding:14px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><strong style="font-size:12px">🔴 Live Pipeline Log</strong><span id="timeline-status" class="font-mono" style="font-size:11px;color:#94a3b8">Idle</span></div>
    <div id="timeline-steps" style="display:flex;gap:6px;overflow-x:auto;padding-bottom:6px"></div>
    <div id="log-box" style="margin-top:8px;background:#0b1020;border:1px solid #1c2742;border-radius:10px;padding:10px"></div>
  </div>

  <!-- Inspector -->
  <div style="background:#111a33;border:1.5px solid #243154;border-radius:18px;padding:18px">
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1c2742;padding-bottom:10px;gap:12px;flex-wrap:wrap">
      <div style="display:flex;gap:10px;align-items:center">
        <div id="ins-icon" style="width:38px;height:38px;border-radius:11px;background:#15244a;display:flex;align-items:center;justify-content:center;font-size:18px">⚡</div>
        <div><div style="display:flex;gap:8px;align-items:center"><strong id="ins-title" style="font-size:15px">Scrape</strong><span id="ins-badge" style="font-size:10px;background:#15244a;color:#bfdbfe;padding:2px 8px;border-radius:999px;font-weight:700">STAGE 1</span></div><div id="ins-desc" style="font-size:11px;color:#94a3b8">Click a node to inspect. Press Enter in the topic box to start.</div></div>
      </div>
      <div style="display:flex;gap:8px"><button id="btn-cards" onclick="setView('cards')" style="padding:6px 12px;border-radius:8px;font-size:11px;font-weight:700;background:#3b82f6;color:white">Cards</button><button id="btn-json" onclick="setView('json')" style="padding:6px 12px;border-radius:8px;font-size:11px;font-weight:700;background:#1e293b;color:#94a3b8">JSON</button></div>
    </div>
    <div id="ins-content" style="margin-top:14px;min-height:240px">Loading…</div>
  </div>
</div>

<script>
let TELE = null;
let ACTIVE = 'scrapling';
let VIEW = 'cards';
let JOB = null;
function imgFail(img){ try { img.style.display='none'; } catch(e){} }
window.addEventListener('error', function(e){
  let b = document.getElementById('err-banner');
  if (!b) { b = document.createElement('div'); b.id='err-banner'; b.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#dc2626;color:white;font-size:12px;padding:10px 16px;z-index:9999;font-family:monospace'; document.body.appendChild(b); }
  b.textContent = 'JS ERROR: ' + (e.message||e.error) + ' (open console)';
});

const NODES = {
  scrapling: { title: 'Scrape (Web + Social)', badge: 'STAGE 1', desc: 'Searches the web (Scrapling/DuckDuckGo) and social (Agent Reach / Hacker News) for your topic. Recency filtered to last ~14 days.', icon: '⚡' },
  reasoner: { title: '14-Point Grounded Analysis', badge: 'STAGE 2', desc: 'Audits the aggregated sources for novelty, utility, and evidence. Builds the factual core.', icon: '🧠' },
  content: { title: 'Copywriting Studio', badge: 'STAGE 3', desc: 'Writes a hook and the 5-slide LinkedIn carousel copy from the research core.', icon: '✎' },
  visuals: { title: 'Visual & Carousel Studio', badge: 'STAGE 4', desc: 'Generates a contextual image (Grok) and overlays slide text on it — exactly 5 slides.', icon: '🖼' },
  review: { title: 'Approval Gate', badge: 'STAGE 5', desc: 'Fact-check + review. Edit the copy, then Approve & Publish to LinkedIn.', icon: '🛡' },
  dispatch_li: { title: 'Publish → LinkedIn', badge: 'STAGE 6', desc: 'Posts the approved carousel to your LinkedIn account via OAuth.', icon: '🔗' }
};
const NODE_ORDER = ['scrapling','reasoner','content','visuals','review','dispatch_li'];
const STAGE_INDEX = { scrapling:0, reasoner:1, content:2, visuals:3, review:4, dispatch_li:5 };

function selectNode(k){
  ACTIVE = k;
  document.querySelectorAll('.n8n-node').forEach(n => n.classList.remove('active'));
  const el = document.getElementById('node-' + k); if (el) el.classList.add('active');
  const m = NODES[k];
  if (m){
    document.getElementById('ins-title').textContent = m.title;
    document.getElementById('ins-badge').textContent = m.badge;
    document.getElementById('ins-desc').textContent = m.desc;
    document.getElementById('ins-icon').textContent = m.icon;
  }
  renderInspector();
}
function setView(v){
  VIEW = v;
  document.getElementById('btn-cards').style.background = v==='cards' ? '#3b82f6' : '#1e293b';
  document.getElementById('btn-cards').style.color = v==='cards' ? 'white' : '#94a3b8';
  document.getElementById('btn-json').style.background = v==='json' ? '#3b82f6' : '#1e293b';
  document.getElementById('btn-json').style.color = v==='json' ? 'white' : '#94a3b8';
  renderInspector();
}

function getDataForNode(k){
  if (!TELE) return [];
  if (k==='scrapling') return TELE.discoveries.filter(d => ['scrapling','web','agent_reach','firecrawl','rss'].includes(d.source_type));
  if (k==='reasoner') return TELE.discoveries.map(d => ({ title:d.title, source:d.source_url, notes:d.verification_notes, author:d.author }));
  if (k==='content'||k==='visuals'||k==='review') return TELE.drafts;
  if (k==='dispatch_li') return TELE.drafts.filter(d => d.platform==='linkedin');
  return [];
}

function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function renderInspector(){
  const c = document.getElementById('ins-content');
  if (JOB && (JOB.status==='running'||JOB.status==='queued')){
    const snap = JOB.snapshots || {};
    if (ACTIVE==='scrapling'){
      const evs = (JOB.events||[]).filter(e => ['scrapling','web','agent_reach'].includes(e.stage));
      let html = '<div style="font-size:12px;color:#94a3b8;margin-bottom:8px">Scraping the web + social for your topic…</div>';
      if (JOB.status==='running' && (!evs.length)) html += '<div class="spin"></div> <span style="font-size:12px;color:#94a3b8">Digesting sources…</span>';
      if (evs.length) html += '<div style="display:flex;flex-direction:column;gap:6px">' + evs.slice(-8).map(e => '<div style="background:#0f1830;border:1px solid #243154;border-radius:10px;padding:10px;font-size:12px"><span style="color:#38bdf8">['+esc(e.stage)+']</span> '+esc(e.detail)+'</div>').join('') + '</div>';
      c.innerHTML = html; return;
    }
    if (ACTIVE==='reasoner' && snap.analysis) { c.innerHTML = analysisCard(snap.analysis); return; }
    if (ACTIVE==='content' && snap.linkedin) { c.innerHTML = '<div style="background:#0f1830;border:1px solid #243154;border-radius:12px;padding:14px;font-size:12px"><b>'+esc(snap.linkedin.topic_title)+'</b><br>Slides: '+esc(snap.linkedin.slides)+'<br><span style="color:#94a3b8">'+esc(snap.linkedin.post_copy_head)+'</span></div>'; return; }
    if (ACTIVE==='visuals'){
      const slides = (JOB.events||[]).filter(e => e.stage==='visuals');
      let html = '<div style="font-size:12px;color:#94a3b8;margin-bottom:8px">Building carousel slides (step by step)…</div>';
      if (JOB.status==='running' && slides.length===0) html += '<div class="spin"></div> <span style="font-size:12px;color:#94a3b8">Generating background image…</span>';
      html += '<div style="display:flex;gap:8px;flex-wrap:wrap">' + slides.map(e => '<div class="slide-card" style="width:130px"><img src="/media/carousels/'+ (JOB.created_drafts&&JOB.created_drafts[0]||'') +'/'+esc(e.detail)+'" onerror="imgFail(this)"><div style="padding:4px 6px;font-size:10px;color:#94a3b8">'+esc(e.detail)+'</div></div>').join('') + '</div>';
      c.innerHTML = html; return;
    }
    if (ACTIVE==='review' || ACTIVE==='dispatch_li'){
      if (snap.linkedin){ c.innerHTML = draftCards(TELE ? TELE.drafts.filter(d=>d.platform==='linkedin') : []); return; }
    }
  }
  if (!TELE){ c.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">Loading pipeline data…</div>'; return; }
  let data = getDataForNode(ACTIVE);
  if (VIEW==='json'){ c.innerHTML = '<pre style="background:#0b1020;color:#e2e8f0;padding:14px;border-radius:12px;overflow:auto;max-height:360px;font-size:11px">'+esc(JSON.stringify(data,null,2))+'</pre>'; return; }
  if (ACTIVE==='review' || ACTIVE==='dispatch_li'){ c.innerHTML = draftCards(data); return; }
  if (!data.length){ c.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">No records yet. Type a topic above and press Enter.</div>'; return; }
  c.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;max-height:400px;overflow:auto;padding-right:4px">' +
    data.map(item => '<div style="background:#0f1830;border:1px solid #243154;border-radius:12px;padding:12px"><div style="display:flex;justify-content:space-between"><span style="font-size:10px;font-weight:700;background:#15244a;color:#bfdbfe;padding:2px 6px;border-radius:999px">'+esc(item.source_type||item.platform||'item')+'</span><span style="font-size:10px;color:#64748b">'+esc(item.author?'@'+item.author:'')+'</span></div><div style="font-weight:700;font-size:12px;margin-top:6px">'+esc(item.title||item.hook||item.id||'Untitled')+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">'+esc(item.summary||item.notes||item.verification_notes||'')+'</div>'+(item.source||item.source_url?'<a href="'+esc(item.source||item.source_url)+'" target="_blank" style="font-size:11px;color:#38bdf8">View evidence →</a>':'')+'</div>').join('') + '</div>';
}

function analysisCard(a){
  return '<div style="background:#0f1830;border:1px solid #243154;border-radius:14px;padding:16px;font-size:12px;line-height:1.6"><div style="color:#38bdf8;font-weight:700;margin-bottom:6px">Content Angle: '+esc(a.angle)+'  •  Sources: '+esc(a.sources)+'</div><div><b>Core insight:</b> '+esc(a.insight)+'</div><div style="margin-top:8px"><b>Practical takeaway:</b> '+esc(a.takeaway)+'</div><div style="margin-top:8px;color:#fca5a5"><b>Limitations:</b> '+esc(a.limitations)+'</div></div>';
}
function draftCards(drafts){
  if (!drafts || !drafts.length){ return '<div style="text-align:center;padding:40px;color:#94a3b8">No LinkedIn draft yet. Run a topic to generate the 5-slide carousel.</div>'; }
  return '<div style="display:flex;flex-direction:column;gap:14px">' + drafts.map(d => {
    const slides = [1,2,3,4,5].map(n => '<div class="slide-card" style="width:120px"><img src="/media/carousels/'+d.id+'/slide_'+String(n).padStart(2,'0')+'.png" onerror="imgFail(this)"><div style="padding:3px 5px;font-size:9px;color:#64748b">slide '+n+'</div></div>').join('');
    return '<div style="background:#0f1830;border:1px solid #243154;border-radius:16px;padding:14px"><div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1c2742;padding-bottom:8px;margin-bottom:8px"><span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;background:#0ea5e9;color:white">LinkedIn Carousel</span><span style="font-size:11px;background:#0f2e22;color:#6ee7b7;padding:2px 8px;border-radius:999px">Score '+Math.round((d.review_score||0)*100)+'%</span></div>' +
      '<div style="display:flex;gap:8px;overflow-x:auto;padding:6px 0">'+slides+'</div>' +
      '<textarea id="copy-'+d.id+'" style="width:100%;min-height:110px;font-size:12px;padding:10px;border-radius:10px;border:1px solid #334155;background:#0b1020;color:#e2e8f0">'+esc(d.generated_copy||'')+'</textarea>' +
      '<div style="display:flex;gap:8px;margin-top:8px"><button onclick="saveDraft(&#39;'+d.id+'&#39;)" style="padding:6px 12px;border-radius:8px;background:#4f46e5;color:white;font-size:11px;font-weight:700">Save Edits</button><button onclick="doPublish(&#39;'+d.id+'&#39;)" style="padding:6px 14px;border-radius:8px;background:#059669;color:white;font-size:11px;font-weight:700">Approve &amp; Publish Live</button></div>' +
      '<div style="font-size:11px;color:#94a3b8;font-style:italic;margin-top:6px">'+esc(d.review_feedback||'')+'</div></div>';
  }).join('') + '</div>';
}

async function loadTelemetry(){
  try{
    const r = await fetch('/api/telemetry');
    TELE = await r.json();
    document.getElementById('m-drafts') && (document.getElementById('m-drafts').textContent = TELE.stats.approved_drafts);
    if (!TELE.linkedin_ready) document.getElementById('btn-li-connect').style.display = 'inline-block';
    renderInspector();
  } catch(e){ console.error(e); document.getElementById('ins-content').innerHTML = '<div style="color:#dc2626;padding:20px">Failed to load telemetry: '+esc(e.message)+'</div>'; }
}

function setRunningNode(key){
  document.querySelectorAll('.n8n-node').forEach(n => n.classList.remove('running'));
  if (key && STAGE_INDEX[key]!==undefined){ const el = document.getElementById('node-'+key); if (el) el.classList.add('running'); }
}
function computeStageIndex(){
  if (JOB && JOB.status==='success') return NODE_ORDER.length-1;
  const hit = new Set();
  if (JOB && JOB.stage) hit.add(JOB.stage);
  (JOB?JOB.events||[]:[]).forEach(e => hit.add(e.stage));
  let idx = -1;
  NODE_ORDER.forEach((s,i)=>{ if (hit.has(s)) idx = Math.max(idx,i); });
  return idx;
}
function updatePipelineVisual(){
  const idx = computeStageIndex();
  NODE_ORDER.forEach((s,i)=>{
    const el = document.getElementById('node-'+s);
    if (!el) return;
    el.classList.remove('done','running');
    if (i < idx) el.classList.add('done');
    else if (i === idx && JOB && JOB.status==='running') el.classList.add('running');
    else if (i === idx && JOB && JOB.status==='success') el.classList.add('done');
  });
  // light connectors up to reached node
  document.querySelectorAll('#connectors path').forEach((p,i)=>{
    if (idx >= i+1) p.classList.add('lit'); else p.classList.remove('lit');
  });
}
function drawConnectors(){
  const canvas = document.getElementById('canvas');
  const svg = document.getElementById('connectors');
  const cr = canvas.getBoundingClientRect();
  svg.setAttribute('width', cr.width); svg.setAttribute('height', cr.height);
  svg.innerHTML = '';
  for (let i=0;i<NODE_ORDER.length-1;i++){
    const a = document.getElementById('node-'+NODE_ORDER[i]);
    const b = document.getElementById('node-'+NODE_ORDER[i+1]);
    if (!a||!b) continue;
    const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
    const x1 = ar.left - cr.left + ar.width/2, y1 = ar.top - cr.top + ar.height/2;
    const x2 = br.left - cr.left + br.width/2, y2 = br.top - cr.top + br.height/2;
    const mx = (x1+x2)/2;
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d', 'M '+x1+' '+y1+' C '+mx+' '+y1+', '+mx+' '+y2+', '+x2+' '+y2);
    path.id = 'conn-'+i;
    svg.appendChild(path);
  }
}
function renderTimeline(job){
  if (!job) return;
  const box = document.getElementById('timeline-box');
  const stepsEl = document.getElementById('timeline-steps');
  const logEl = document.getElementById('log-box');
  const statusEl = document.getElementById('timeline-status');
  if (!box||!stepsEl) return;
  box.style.display='block';
  statusEl.textContent = (job.stage_label||job.status||'') + (job.detail?' — '+job.detail:'');
  const seen = new Set((job.events||[]).map(e=>e.stage)); if (job.stage) seen.add(job.stage);
  stepsEl.innerHTML = NODE_ORDER.map(s => { const done = (job.events||[]).some(e=>e.stage===s); const active = job.stage===s; const cls = active?'active':(done?'done':''); const label = {scrapling:'Scrape',reasoner:'Analyze',content:'Copy',visuals:'Visuals',review:'Review',dispatch_li:'Publish'}[s]; return '<div class="tl-step '+cls+'">'+label+'</div>'; }).join('');
  if (job.events){
    logEl.innerHTML = job.events.slice(-30).map(e => { const t = new Date(e.ts*1000).toLocaleTimeString(); return '<div><span style="color:#64748b">'+t+'</span> <b>'+esc(e.stage)+'</b> — '+esc(e.label)+(e.detail?' : '+esc(e.detail):'')+'</div>'; }).join('') || '<span style="color:#64748b">Waiting…</span>';
    logEl.scrollTop = logEl.scrollHeight;
  }
}
async function pollJob(jobId){
  while (true){
    let job;
    try { const r = await fetch('/api/jobs/'+jobId); job = await r.json(); } catch(e){ await new Promise(r=>setTimeout(r,1200)); continue; }
    JOB = job;
    setRunningNode(job.stage);
    updatePipelineVisual();
    document.getElementById('live-status').textContent = (job.stage_label||'WORKING').toUpperCase();
    document.getElementById('live-detail').textContent = job.detail || '';
    document.getElementById('live-dot').className = 'dot dot-busy';
    renderTimeline(job);
    renderInspector();
    if (job.status==='success') return job;
    if (job.status==='error') throw new Error(job.error||'Job failed');
    await new Promise(r=>setTimeout(r,1100));
  }
}
async function startTopic(){
  const topic = document.getElementById('topic-input').value.trim();
  if (!topic){ alert('Please type a topic first.'); return; }
  document.getElementById('live-dot').className='dot dot-busy';
  try{
    const r = await fetch('/api/generate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ platform:'linkedin', topic:topic }) });
    const j = await r.json();
    if (!j.job_id) throw new Error(j.message||'No job');
    await pollJob(j.job_id);
    await loadTelemetry();
    selectNode('review');
  } catch(e){ alert('Generate failed: '+e.message); console.error(e); }
  finally { document.getElementById('live-dot').className='dot dot-ready'; document.getElementById('live-status').textContent='READY'; JOB=null; updatePipelineVisual(); }
}
async function saveDraft(id){
  const ta = document.getElementById('copy-'+id); if (!ta) return;
  const r = await fetch('/api/drafts/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ draft_id:id, generated_copy: ta.value }) });
  const j = await r.json();
  alert(j.status==='success'?'Saved':'Save failed: '+j.message);
}
async function doPublish(id){
  const ta = document.getElementById('copy-'+id);
  if (ta) await fetch('/api/drafts/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ draft_id:id, generated_copy: ta.value }) });
  try{
    const r = await fetch('/api/publish/live', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ draft_id:id }) });
    const j = await r.json();
    if (j.status==='success'){ alert('Published to '+j.platform+': '+j.post_id); }
    else {
      const m = (j.message||'').toLowerCase();
      if (m.indexOf('not permitted')>=0 || m.indexOf('403')>=0 || m.indexOf('forbidden')>=0) alert('LinkedIn rejected the post. Check your LinkedIn access token / app permissions in .env, then reconnect and try again.');
      else if (m.indexOf('token')>=0) alert('LinkedIn not connected. Click Connect LinkedIn (top bar), authorize, then Approve again.');
      else alert('Publish note: '+j.message);
    }
  } catch(e){ alert('Publish error: '+e.message); }
}

window.addEventListener('resize', drawConnectors);
loadTelemetry();
selectNode('scrapling');
drawConnectors();
document.getElementById('topic-input').addEventListener('keydown', e => { if (e.key==='Enter') startTopic(); });
</script>
</body>
</html>

"""
@app.get("/", response_class=HTMLResponse)
def index():
    """Render the Scrapling visual studio dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/auth/linkedin/start")
def linkedin_auth_start(request: Request):
    """Kick off the 3-legged LinkedIn OAuth flow in the user's browser."""
    settings = get_settings()
    if not (settings.linkedin_client_id and settings.linkedin_client_secret):
        return HTMLResponse("<h3>LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET missing in .env</h3>", status_code=400)

    redirect_uri = str(request.base_url).rstrip("/") + "/auth/linkedin/callback"
    state = secrets.token_urlsafe(16)
    _linkedin_oauth_states.add(state)
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid profile w_member_social",
    }
    return RedirectResponse(f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}")


@app.get("/auth/linkedin/callback")
def linkedin_auth_callback(request: Request):
    """Exchange the OAuth code for an access token, fetch identity, persist to .env."""
    settings = get_settings()
    params = parse_qs(urlparse(str(request.url)).query)
    code = params.get("code", [None])[0]
    state = params.get("state", [None])[0]

    if not code or not state or state not in _linkedin_oauth_states:
        return HTMLResponse("<h3>Invalid or expired OAuth state.</h3>", status_code=400)
    _linkedin_oauth_states.discard(state)

    redirect_uri = str(request.base_url).rstrip("/") + "/auth/linkedin/callback"
    try:
        with httpx.Client(timeout=30.0) as client:
            token_resp = client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token")

            identity_resp = client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            sub = identity_resp.json().get("sub", "") if identity_resp.status_code == 200 else ""

        author_urn = f"urn:li:person:{sub}" if sub else ""
        _save_env_values({"LINKEDIN_ACCESS_TOKEN": access_token, "LINKEDIN_AUTHOR_URN": author_urn})
        who = identity_resp.json().get("email", "your account") if identity_resp.status_code == 200 else "your account"
        return HTMLResponse(
            f"<h2 style='font-family:sans-serif'>LinkedIn connected for {who}</h2>"
            "<p style='font-family:sans-serif'>Token saved to .env. You can now publish carousels.</p>"
            "<a href='/'>Back to dashboard</a>"
        )
    except Exception as e:
        logger.error(f"LinkedIn OAuth failed: {e}")
        return HTMLResponse(f"<h3>OAuth exchange failed: {e}</h3>", status_code=400)


@app.get("/api/telemetry")
def get_telemetry():
    """Return live system telemetry data."""
    db = get_db()
    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)

    discoveries = disc_repo.list_recent(limit=100)
    drafts = draft_repo.list_by_status("APPROVED", limit=50)
    if not drafts:
        drafts = draft_repo.list_by_status("DRAFTED", limit=50)
    pending_queue = queue_repo.get_pending(limit=50)

    settings = get_settings()
    health = run_health_check(settings)

    return JSONResponse(
        content={
            "stats": {
                "total_discoveries": len(discoveries),
                "approved_drafts": len(drafts),
                "pending_queue": len(pending_queue),
            },
            "discoveries": [d.model_dump() for d in discoveries[:100]],
            "drafts": [dr.model_dump() for dr in drafts[:10]],
            "health": health,
            "linkedin_ready": bool(settings.linkedin_access_token and settings.linkedin_access_token.strip()),
        }
    )


@app.post("/api/generate")
def generate_endpoint(req: GenerateRequest):
    """Start a generation job and return immediately; UI polls /api/jobs/{id} for real progress."""
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "stage": None,
            "stage_label": "Queued",
            "detail": "",
            "created_drafts": [],
            "error": None,
            "events": [],
            "snapshots": {},
            "started_at": time.time(),
        }
    _push_job_event(job_id, "queued", "Queued", (req.topic or req.url or "trending")[:60])
    thread = threading.Thread(
        target=_run_generation_job,
        args=(job_id, req.platform, req.topic, req.url),
        daemon=True,
    )
    thread.start()
    return JSONResponse(content={"status": "queued", "job_id": job_id})


def _derive_tags(topic: str | None, analysis) -> list[str]:
    """Build a small, topic-derived hashtag set (cap 5)."""
    stop = {"the", "and", "for", "with", "from", "this", "that", "into", "your", "what",
            "how", "why", "when", "build", "using", "agent", "agents", "about", "make"}
    tags: list[str] = []
    for w in (topic or "").replace("#", " ").split():
        w = w.strip(".,;-:#()")
        if len(w) > 3 and w.lower() not in stop:
            tags.append("#" + w[0].upper() + w[1:].lower())
        if len(tags) >= 4:
            break
    tags.append("#AIAgents")
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:5]


def _run_generation_job(job_id: str, platform: str, topic: str | None, url: str | None) -> None:
    """Background worker: topic-scrape -> analyze -> write -> render -> review.

    LinkedIn-only pipeline (X removed). Scraping is topic-driven across web + social
    with recency filtering, and the research core is aggregated from all sources so
    content reflects the typed topic rather than a hardcoded default.
    """
    try:
        from intelligence_os.intelligence.openrouter import OpenRouterClient
        from intelligence_os.content.linkedin import LinkedInGenerator, LinkedInCarouselSlide
        from intelligence_os.review.verifier import ReviewVerifier
        from intelligence_os.research.live_scraper import LiveTaskScraper
        from intelligence_os.intelligence.analyzer import IntelligenceAnalyzer

        db = get_db()
        settings = get_settings()
        draft_repo = ContentDraftRepository(db)
        renderer = CarouselRenderer(output_base_dir=output_dir / "carousels")

        # Product decision: LinkedIn only — X generation removed from the pipeline.
        platform = "linkedin"

        def _stage(stage: str, label: str, detail: str = ""):
            _update_job(job_id, status="running", stage=stage, stage_label=label, detail=detail)
            _push_job_event(job_id, stage, label, detail)

        # 1. Topic-driven multi-source scrape (web + social), recency filtered.
        _stage("scrapling", "Scraping Web + Social", (topic or "topic")[:70])
        scraper = LiveTaskScraper(db, github_token=settings.github_token)
        discoveries = scraper.scrape_topic(topic or "AI agents", max_items=8)
        if not discoveries:
            raise ValueError(f"No scraped evidence found for topic '{topic}'. Try a more specific topic.")
        # Surface each scraped source as a live note so the UI shows what was gathered.
        for d in discoveries[:8]:
            _push_job_event(job_id, d.source_type, f"Scraped ({d.source_type})", (d.title or d.source_url)[:120])

        # Persist discoveries so the draft's discovery_id foreign key resolves and the
        # UI scrape node can render the gathered evidence.
        try:
            disc_repo = DiscoveryRepository(db)
            for d in discoveries:
                try:
                    disc_repo.insert(d)
                except Exception:
                    pass  # dedupe / unique constraint — keep the first occurrence
        except Exception as disc_err:
            logger.warning(f"Could not persist discoveries: {disc_err}")

        # 2. Grounded analysis on the most TOPIC-RELEVANT source (ranked, not by fame).
        anchor = discoveries[0]
        _stage("reasoner", "14-Point Grounded Analysis", (topic or anchor.title)[:60])
        client = OpenRouterClient(settings)
        verifier = ReviewVerifier(client)
        analysis = None
        try:
            analysis = IntelligenceAnalyzer(client).analyze_discovery(anchor)
            disc_repo = DiscoveryRepository(db)
            disc_repo.update_scores_and_status(
                discovery_id=anchor.id,
                novelty=analysis.novelty_score,
                utility=analysis.utility_score,
                evidence=analysis.evidence_score,
                potential=(analysis.novelty_score + analysis.utility_score + analysis.evidence_score) / 3,
                status="ANALYZED",
                content_angle=analysis.strongest_content_angle,
                verification_notes=analysis.summary_insight[:400],
            )
        except Exception as analyze_err:
            logger.warning(f"Grounded analysis failed, using raw-content fallback: {analyze_err}")

        other_context = " ".join(d.summary for d in discoveries[1:4] if d.summary)[:900]
        if analysis:
            core = ResearchCoreData(
                hook=topic or anchor.title,
                core_insight=f"Topic: {topic or anchor.title}. {analysis.what_is_actually_new} {analysis.why_useful} Context: {other_context[:300]}".strip(),
                evidence=[d.source_url for d in discoveries if d.source_url],
                practical_takeaway=analysis.why_useful or "See sources for implementation details.",
                limitations=analysis.limitations or "Cross-check claims against primary sources.",
                content_angle=analysis.strongest_content_angle or "workflow",
                tags=_derive_tags(topic, analysis),
            )
        else:
            core = ResearchCoreData(
                hook=topic or anchor.title,
                core_insight=f"Topic: {topic or anchor.title}. {(anchor.summary + ' ' + other_context)[:600]}",
                evidence=[d.source_url for d in discoveries if d.source_url],
                practical_takeaway=discoveries[0].summary[:300],
                limitations="Cross-check claims against primary sources.",
                content_angle="workflow",
                tags=_derive_tags(topic, None),
            )

        with _jobs_lock:
            if job_id in _jobs:
                try:
                    _jobs[job_id].setdefault("snapshots", {})["analysis"] = {
                        "angle": core.content_angle,
                        "insight": core.core_insight[:250],
                        "takeaway": core.practical_takeaway[:200],
                        "limitations": core.limitations[:200],
                        "sources": len(core.evidence),
                    }
                except Exception:
                    pass

        # 3. LinkedIn carousel copy — 4 topic-focused content slides.
        _stage("content", "Writing LinkedIn Carousel", "hook + 4 content slides...")
        li_gen = LinkedInGenerator(client)
        li_res = li_gen.generate(core, preferred_format="carousel")

        # Append the deterministic 5th call-to-action slide (generic, no third-party branding).
        cta = LinkedInCarouselSlide(
            slide_number=len(li_res.carousel_data.slides) + 1,
            title="Enjoyed this?",
            subtitle=f"Follow for more {topic} breakdowns",
            bullet_points=[],
            takeaway="",
        )
        li_res.carousel_data.slides.append(cta)
        li_res.carousel_data.total_slides = len(li_res.carousel_data.slides)

        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].setdefault("snapshots", {})["linkedin"] = {
                    "post_copy_head": li_res.post_copy[:250],
                    "topic_title": li_res.carousel_data.topic_title,
                    "slides": len(li_res.carousel_data.slides),
                }

        li_draft_id = f"draft-li-{uuid.uuid4().hex[:8]}"

        # 4. Visuals — render every slide as a complete, finished image (Grok), with a
        #    shared locked art-direction so the set stays visually linked. Step-by-step.
        _stage("visuals", "Rendering 1024x1024 Slides", "Grok per-slide artwork...")
        from intelligence_os.visuals.openrouter_image import OpenRouterImageGenerator, CAROUSEL_ART_DIRECTION
        image_gen = OpenRouterImageGenerator(settings)

        slide_paths: list[str] = []
        try:
            slide_paths = image_gen.generate_carousel_images(
                li_res.carousel_data.slides, CAROUSEL_ART_DIRECTION, li_draft_id,
                on_slide_rendered=lambda n, p: _push_job_event(
                    job_id, "visuals", f"Built slide {n}/{li_res.carousel_data.total_slides}", f"slide_{n:02d}.png"
                ),
            )
        except Exception as render_err:
            logger.warning(f"Carousel image generation issue: {render_err}")
        if not slide_paths:
            try:
                slide_paths = renderer.render_carousel(
                    li_res.carousel_data, li_draft_id,
                    on_slide_rendered=lambda n, p: _push_job_event(
                        job_id, "visuals", f"Built slide {n}/{li_res.carousel_data.total_slides}", f"slide_{n:02d}.png"
                    ),
                )
            except Exception as render_err2:
                logger.warning(f"Fallback carousel rendering issue: {render_err2}")

        # 5. Review gate.
        _stage("review", "Fact-Checking LinkedIn Draft", "review gate audit...")
        li_review = verifier.verify_draft(li_res.post_copy, core, "linkedin")

        li_draft = ContentDraftRecord(
            id=li_draft_id,
            discovery_id=anchor.id,
            research_core=core.model_dump(),
            generated_copy=li_res.post_copy,
            platform="linkedin",
            format="carousel",
            review_score=li_review.overall_score,
            review_feedback=li_review.feedback,
            visual_asset_path=slide_paths[0] if slide_paths else None,
            status="APPROVED" if li_review.is_approved else "DRAFTED",
        )
        draft_repo.insert(li_draft)

        # Keep only this draft for a clean dashboard experience.
        draft_repo.delete_excluding([li_draft_id])

        _update_job(
            job_id,
            status="success",
            stage="review",
            stage_label="Ready for Approval",
            detail="1 LinkedIn carousel (5 slides) created",
            created_drafts=[li_draft_id],
            discovery_id=anchor.id,
        )

    except Exception as e:
        logger.error(f"Generation error: {e}\n{traceback.format_exc()}")
        _update_job(job_id, status="error", stage_label="Failed", error=str(e))


@app.get("/api/jobs/{job_id}")
def get_job_endpoint(job_id: str):
    """Poll a background job's live status for pipeline progress rendering."""
    job = _get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Unknown job."})
    return JSONResponse(content=job)


@app.post("/api/publish/live")
def publish_live_endpoint(req: PublishRequest):
    """Publish an approved draft live to X (Twitter API v2) or LinkedIn."""
    try:
        from intelligence_os.publishing.x import XPublisher
        from intelligence_os.publishing.linkedin import LinkedInPublisher

        db = get_db()
        settings = get_settings()
        draft_repo = ContentDraftRepository(db)

        draft = draft_repo.get_by_id(req.draft_id)
        if not draft:
            return JSONResponse(
                status_code=200,
                content={"status": "error", "message": f"Draft {req.draft_id} not found."},
            )

        if draft.platform == "x":
            x_pub = XPublisher(settings)
            if not x_pub.is_configured():
                return JSONResponse(
                    status_code=200,
                    content={"status": "error", "message": "X API credentials not configured in .env."},
                )
            post_id = x_pub.publish(draft)
            return JSONResponse(
                content={
                    "status": "success",
                    "platform": "x",
                    "post_id": post_id,
                }
            )

        elif draft.platform == "linkedin":
            li_pub = LinkedInPublisher(settings)
            post_id = li_pub.publish(draft)
            return JSONResponse(
                content={
                    "status": "success",
                    "platform": "linkedin",
                    "post_id": post_id,
                }
            )

        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": f"Unsupported platform: {draft.platform}"},
        )

    except Exception as e:
        logger.error(f"Live publishing failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": f"Publishing failed: {str(e)}"},
        )

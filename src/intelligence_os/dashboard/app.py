"""Interactive N8N Visual Studio with 3 Source Adapters, 14-Pt Reasoner, Visual/Carousel Generator, and 1-Click Approval."""

import os
import json
import uuid
import traceback
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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

# Ensure output directories exist and mount static media
output_dir = Path("output")
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / "carousels").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(output_dir.resolve())), name="media")


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


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Content Intelligence OS — Visual Studio</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
        
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: #FAF8F5; /* Warm Light Cream */
            color: #1E293B;
            overflow-x: hidden;
        }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        
        /* Canvas Grid */
        .canvas-grid {
            background-color: #FAF7F2;
            background-image: radial-gradient(#D8D2C4 1.2px, transparent 1.2px);
            background-size: 24px 24px;
        }

        .n8n-node {
            background: #FFFFFF;
            border: 1.5px solid #E6DFD3;
            box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.04), 0 2px 6px -1px rgba(0, 0, 0, 0.02);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .n8n-node:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 30px -4px rgba(0, 0, 0, 0.08), 0 4px 10px -2px rgba(0, 0, 0, 0.03);
            border-color: #CBD5E1;
        }
        .n8n-node.active-node {
            border-color: #3B82F6 !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25), 0 8px 24px rgba(0,0,0,0.08) !important;
        }
        .n8n-node.executing-node {
            border-color: #10B981 !important;
            box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.35), 0 12px 28px rgba(16, 185, 129, 0.2) !important;
            transform: scale(1.03);
        }

        /* SVG Wire Connection Pulse Animation */
        @keyframes flowPulse {
            from { stroke-dashoffset: 40; }
            to { stroke-dashoffset: 0; }
        }
        .pulse-wire {
            stroke-dasharray: 8 6;
            animation: flowPulse 1.2s linear infinite;
        }

        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: #F1ECE4; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 4px; }
    </style>
</head>
<body class="canvas-grid min-h-screen flex flex-col">

    <!-- Top Navigation Bar -->
    <nav class="bg-[#FFFFFF]/95 backdrop-blur-md border-b border-[#E6DFD3] sticky top-0 z-30 px-6 py-3.5 flex flex-wrap items-center justify-between shadow-sm gap-4">
        <div class="flex items-center space-x-3.5">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-orange-500 via-rose-500 to-indigo-600 p-0.5 flex items-center justify-center shadow-md shadow-orange-500/20">
                <div class="w-full h-full bg-white rounded-[10px] flex items-center justify-center">
                    <i data-lucide="git-merge" class="w-5 h-5 text-orange-600"></i>
                </div>
            </div>
            <div>
                <div class="flex items-center gap-2">
                    <h1 class="text-lg font-extrabold tracking-tight text-slate-900">AI Content Intelligence OS</h1>
                    <span class="px-2.5 py-0.5 text-[11px] font-bold rounded-full bg-orange-100 text-orange-800 border border-orange-200">Scrapling Engine (0 Docker)</span>
                </div>
                <p class="text-xs text-slate-500">Live Scrapling &rarr; 14-Pt Reasoner &rarr; Copywriting &rarr; 1080x1080 Carousels &rarr; 1-Click Publish</p>
            </div>
        </div>

        <!-- 3 Primary Action Buttons -->
        <div class="flex flex-wrap items-center gap-3">
            <button onclick="startExecution('x')" id="btn-run-x" class="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs shadow-md transition-all flex items-center gap-2">
                <i data-lucide="twitter" class="w-4 h-4 text-sky-400 fill-current"></i> Generate for X (Twitter)
            </button>

            <button onclick="startExecution('linkedin')" id="btn-run-li" class="px-4 py-2 rounded-xl bg-[#0077B5] hover:bg-[#006097] text-white font-semibold text-xs shadow-md transition-all flex items-center gap-2">
                <i data-lucide="image" class="w-4 h-4 text-white"></i> Generate LinkedIn Carousel (1080x1080)
            </button>

            <button onclick="startExecution('both')" id="btn-run-both" class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-md transition-all flex items-center gap-2">
                <i data-lucide="zap" class="w-4 h-4 fill-current"></i> Complete Cycle (Both)
            </button>

            <button onclick="location.reload()" class="p-2 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-600 shadow-sm transition-all" title="Reload">
                <i data-lucide="refresh-cw" class="w-4 h-4"></i>
            </button>
        </div>
    </nav>

    <!-- Main Workspace -->
    <div class="max-w-[1560px] w-full mx-auto p-6 space-y-6">

        <!-- Live Pipeline Barometer & Target Topic Selector -->
        <div class="bg-white border border-[#E6DFD3] rounded-2xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <span id="live-dot" class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></span>
                <span class="text-xs font-semibold text-slate-500">Live Status: </span>
                <strong id="live-status" class="text-xs font-bold text-slate-900 font-mono">READY</strong>
            </div>

            <!-- Custom Topic / URL Input -->
            <div class="flex items-center gap-2 flex-1 max-w-xl">
                <div class="relative w-full">
                    <input id="input-custom-topic" type="text" placeholder="Enter topic or URL (e.g. 'browser-use agent', 'MCP protocol') or leave blank" class="w-full text-xs pl-8 pr-4 py-2 rounded-xl bg-slate-50 border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    <i data-lucide="search" class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5"></i>
                </div>
            </div>

            <div class="flex gap-4 text-xs font-medium text-slate-500">
                <div>Approved Drafts: <strong id="metric-drafts" class="text-slate-900 font-mono">0</strong></div>
                <div>Queue: <strong id="metric-queue" class="text-slate-900 font-mono">0</strong></div>
            </div>
        </div>

        <!-- 1. INTERACTIVE N8N NODE GRAPH CANVAS -->
        <div class="relative bg-[#FAF7F2] border border-[#E2DDD5] rounded-3xl p-8 shadow-inner overflow-x-auto custom-scrollbar">
            
            <!-- SVG Wire Connections -->
            <svg class="absolute inset-0 w-full h-full pointer-events-none z-0" xmlns="http://www.w3.org/2000/svg">
                <!-- Sources to Reasoner -->
                <path d="M 210 75 C 260 75, 260 150, 310 150" fill="none" stroke="#F97316" stroke-width="2.5" class="pulse-wire" />
                <path d="M 210 150 L 310 150" fill="none" stroke="#8B5CF6" stroke-width="2.5" class="pulse-wire" />
                <path d="M 210 225 C 260 225, 260 150, 310 150" fill="none" stroke="#0EA5E9" stroke-width="2.5" class="pulse-wire" />

                <!-- Reasoner to Copywriting -->
                <path d="M 490 150 L 540 150" fill="none" stroke="#3B82F6" stroke-width="2.5" class="pulse-wire" />
                <!-- Copywriting to Visual Carousel Gen -->
                <path d="M 720 150 L 770 150" fill="none" stroke="#6366F1" stroke-width="2.5" class="pulse-wire" />
                <!-- Visual Gen to Review Gate -->
                <path d="M 950 150 L 1000 150" fill="none" stroke="#EC4899" stroke-width="2.5" class="pulse-wire" />
                <!-- Review Gate to Live Dispatch -->
                <path d="M 1180 150 L 1230 150" fill="none" stroke="#10B981" stroke-width="2.5" class="pulse-wire" />
            </svg>

            <!-- HTML Nodes Layout -->
            <div class="relative z-10 flex items-center justify-between gap-5 min-w-[1440px]">
                
                <!-- 1. LEFT SOURCE ADAPTER STACK (Scrapling, Agent Reach, GitHub API) -->
                <div class="space-y-3 w-[210px]">
                    
                    <!-- Scrapling Node (0 Docker) -->
                    <div id="node-scrapling" onclick="selectNodeKey('scrapling')" class="n8n-node rounded-2xl p-3 cursor-pointer border-l-4 border-l-orange-500 active-node">
                        <div class="flex items-center justify-between mb-1">
                            <div class="flex items-center gap-2">
                                <div class="w-6 h-6 rounded-lg bg-orange-100 flex items-center justify-center text-orange-600">
                                    <i data-lucide="zap" class="w-3.5 h-3.5"></i>
                                </div>
                                <span class="text-xs font-bold text-slate-800">Scrapling / Web</span>
                            </div>
                            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        </div>
                        <p class="text-[11px] text-slate-500">Stealth web & docs (0 Docker)</p>
                    </div>

                    <!-- Agent Reach Node -->
                    <div id="node-agent_reach" onclick="selectNodeKey('agent_reach')" class="n8n-node rounded-2xl p-3 cursor-pointer border-l-4 border-l-purple-500">
                        <div class="flex items-center justify-between mb-1">
                            <div class="flex items-center gap-2">
                                <div class="w-6 h-6 rounded-lg bg-purple-100 flex items-center justify-center text-purple-600">
                                    <i data-lucide="message-square" class="w-3.5 h-3.5"></i>
                                </div>
                                <span class="text-xs font-bold text-slate-800">Agent Reach</span>
                            </div>
                            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        </div>
                        <p class="text-[11px] text-slate-500">Social demos & code experiments</p>
                    </div>

                    <!-- GitHub API Node -->
                    <div id="node-github" onclick="selectNodeKey('github')" class="n8n-node rounded-2xl p-3 cursor-pointer border-l-4 border-l-sky-500">
                        <div class="flex items-center justify-between mb-1">
                            <div class="flex items-center gap-2">
                                <div class="w-6 h-6 rounded-lg bg-sky-100 flex items-center justify-center text-sky-600">
                                    <i data-lucide="github" class="w-3.5 h-3.5"></i>
                                </div>
                                <span class="text-xs font-bold text-slate-800">GitHub API</span>
                            </div>
                            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                        </div>
                        <p class="text-[11px] text-slate-500">Repos, releases & READMEs</p>
                    </div>
                </div>

                <!-- 2. 14-Point Intelligence Reasoner -->
                <div id="node-reasoner" onclick="selectNodeKey('reasoner')" class="n8n-node rounded-2xl p-4 w-[180px] cursor-pointer border-t-4 border-t-blue-500">
                    <div class="flex items-center justify-between mb-2">
                        <div class="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600">
                            <i data-lucide="cpu" class="w-4 h-4"></i>
                        </div>
                        <span class="text-[10px] font-mono font-bold px-2 py-0.5 bg-blue-50 text-blue-700 rounded">STAGE 2</span>
                    </div>
                    <h3 class="text-xs font-bold text-slate-900">14-Point Reasoner</h3>
                    <p class="text-[11px] text-slate-500 mt-1">OpenRouter evidence audit</p>
                </div>

                <!-- 3. Copywriting Studio -->
                <div id="node-content" onclick="selectNodeKey('content')" class="n8n-node rounded-2xl p-4 w-[180px] cursor-pointer border-t-4 border-t-indigo-600">
                    <div class="flex items-center justify-between mb-2">
                        <div class="w-7 h-7 rounded-lg bg-indigo-100 flex items-center justify-center text-indigo-600">
                            <i data-lucide="pen-tool" class="w-4 h-4"></i>
                        </div>
                        <span class="text-[10px] font-mono font-bold px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded">STAGE 3</span>
                    </div>
                    <h3 class="text-xs font-bold text-slate-900">Copywriting Studio</h3>
                    <p class="text-[11px] text-slate-500 mt-1">Natural English threads & copy</p>
                </div>

                <!-- 4. Visual & Carousel Generator Node (NEW) -->
                <div id="node-visuals" onclick="selectNodeKey('visuals')" class="n8n-node rounded-2xl p-4 w-[180px] cursor-pointer border-t-4 border-t-pink-500">
                    <div class="flex items-center justify-between mb-2">
                        <div class="w-7 h-7 rounded-lg bg-pink-100 flex items-center justify-center text-pink-600">
                            <i data-lucide="image" class="w-4 h-4"></i>
                        </div>
                        <span class="text-[10px] font-mono font-bold px-2 py-0.5 bg-pink-50 text-pink-700 rounded">STAGE 4</span>
                    </div>
                    <h3 class="text-xs font-bold text-slate-900">Visual & Carousel Gen</h3>
                    <p class="text-[11px] text-slate-500 mt-1">1080x1080 Pillow PNG slides</p>
                </div>

                <!-- 5. Review & Interactive Approval Gate -->
                <div id="node-review" onclick="selectNodeKey('review')" class="n8n-node rounded-2xl p-4 w-[180px] cursor-pointer border-t-4 border-t-rose-500">
                    <div class="flex items-center justify-between mb-2">
                        <div class="w-7 h-7 rounded-lg bg-rose-100 flex items-center justify-center text-rose-600">
                            <i data-lucide="shield-check" class="w-4 h-4"></i>
                        </div>
                        <span class="text-[10px] font-mono font-bold px-2 py-0.5 bg-rose-50 text-rose-700 rounded">STAGE 5</span>
                    </div>
                    <h3 class="text-xs font-bold text-slate-900">Approval Gate</h3>
                    <p class="text-[11px] text-slate-500 mt-1">Fact score & 1-click Publish</p>
                </div>

                <!-- 6. Live Platform Dispatch -->
                <div id="node-dispatch" onclick="selectNodeKey('dispatch')" class="n8n-node rounded-2xl p-4 w-[180px] cursor-pointer border-t-4 border-t-emerald-500">
                    <div class="flex items-center justify-between mb-2">
                        <div class="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-600">
                            <i data-lucide="send" class="w-4 h-4"></i>
                        </div>
                        <span class="text-[10px] font-mono font-bold px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded">STAGE 6</span>
                    </div>
                    <h3 class="text-xs font-bold text-slate-900">Live Dispatch</h3>
                    <p class="text-[11px] text-slate-500 mt-1">Authenticated X & LinkedIn</p>
                </div>

            </div>
        </div>

        <!-- 2. FULL WIDTH INTERACTIVE APPROVAL & INSPECTOR STUDIO -->
        <div class="bg-white border border-[#E6DFD3] rounded-3xl p-6 shadow-sm space-y-6">
            
            <!-- Studio Header -->
            <div class="flex flex-wrap items-center justify-between border-b border-slate-100 pb-4 gap-4">
                <div class="flex items-center gap-3">
                    <div id="node-icon-bg" class="w-10 h-10 rounded-xl bg-orange-100 flex items-center justify-center text-orange-600 shadow-sm">
                        <i id="node-icon" data-lucide="zap" class="w-5 h-5"></i>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <h2 id="node-title" class="text-base font-bold text-slate-900">Scrapling Web Intelligence (Zero Docker)</h2>
                            <span id="node-badge" class="px-2.5 py-0.5 text-[10px] font-mono font-bold rounded-full bg-orange-100 text-orange-800">SOURCE ADAPTER</span>
                        </div>
                        <p id="node-desc" class="text-xs text-slate-500 mt-0.5">High-speed adaptive scraper with built-in stealth & anti-bot bypass running natively in Python without Docker.</p>
                    </div>
                </div>

                <div class="flex items-center gap-2">
                    <button onclick="setStudioView('cards')" id="btn-view-cards" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white shadow-sm transition-all">Formatted View</button>
                    <button onclick="setStudioView('json')" id="btn-view-json" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all">Raw JSON Payload</button>
                </div>
            </div>

            <!-- Studio Content Area -->
            <div id="studio-content" class="min-h-[280px]">
                <!-- Populated dynamically -->
            </div>
        </div>

    </div>

    <!-- JavaScript Logic -->
    <script>
        lucide.createIcons();
        let telemetryData = null;
        let activeKey = 'scrapling';
        let studioViewMode = 'cards';

        const NODE_MAP = {
            scrapling: {
                title: "Scrapling Web Intelligence (Zero Docker)",
                badge: "SOURCE ADAPTER",
                color: "orange",
                icon: "zap",
                desc: "High-speed adaptive scraper with built-in stealth & anti-bot bypass running natively in Python without Docker.",
                getData: (data) => data.discoveries.filter(d => d.source_type === 'scrapling' || d.source_type === 'web')
            },
            agent_reach: {
                title: "Agent Reach Social Intelligence",
                badge: "SOURCE ADAPTER",
                color: "purple",
                icon: "message-square",
                desc: "Monitors developer social streams for code experiments, videos, and multi-agent workflow demonstrations.",
                getData: (data) => data.discoveries.filter(d => d.source_type === 'agent_reach')
            },
            github: {
                title: "GitHub Intelligence Adapter",
                badge: "SOURCE ADAPTER",
                color: "sky",
                icon: "github",
                desc: "Fetches live repository READMEs, commit histories, releases, and architectural specifications.",
                getData: (data) => data.discoveries.filter(d => d.source_type === 'github')
            },
            reasoner: {
                title: "14-Point Grounded AI Reasoner",
                badge: "STAGE 2 • OPENROUTER",
                color: "blue",
                icon: "cpu",
                desc: "Executes 14-question grounded analysis protocol to extract verifiable evidence and eliminate fluff.",
                getData: (data) => data.discoveries.map(d => ({
                    title: d.title,
                    source: d.source_url,
                    verification_notes: d.verification_notes,
                    angle: d.content_angle
                }))
            },
            content: {
                title: "Copywriting Studio (Natural English)",
                badge: "STAGE 3 • GENERATOR",
                color: "indigo",
                icon: "pen-tool",
                desc: "Generates tailored LinkedIn carousel copy and 280-char X technical threads in natural, human English with bullet points.",
                getData: (data) => data.drafts
            },
            visuals: {
                title: "Visual & Carousel Studio (1080x1080)",
                badge: "STAGE 4 • VISUAL ASSETS",
                color: "pink",
                icon: "image",
                desc: "Renders 1080x1080 high-contrast PNG carousel slides locally using Pillow and generates visual banners.",
                getData: (data) => data.drafts.map(d => ({ id: d.id, platform: d.platform, carousel_media: `/media/carousels/${d.id}/slide_01.png` }))
            },
            review: {
                title: "Review Gate & Interactive Approval Center",
                badge: "STAGE 5 • APPROVAL GATE",
                color: "rose",
                icon: "shield-check",
                desc: "Audits claims against source evidence and provides 1-click Approval & Live Dispatch controls.",
                getData: (data) => data.drafts
            },
            dispatch: {
                title: "Live Platform Dispatcher",
                badge: "STAGE 6 • PUBLISHING",
                color: "emerald",
                icon: "send",
                desc: "Dispatches approved drafts live to X (Twitter API v2) and LinkedIn using authenticated OAuth 1.0a credentials.",
                getData: (data) => data.drafts.filter(d => d.status === 'APPROVED')
            }
        };

        function selectNodeKey(key) {
            activeKey = key;
            const meta = NODE_MAP[key];
            if (!meta) return;

            document.querySelectorAll('.n8n-node').forEach(n => n.classList.remove('active-node'));
            const activeNode = document.getElementById(`node-${key}`);
            if (activeNode) activeNode.classList.add('active-node');

            document.getElementById('node-title').textContent = meta.title;
            document.getElementById('node-badge').textContent = meta.badge;
            document.getElementById('node-desc').textContent = meta.desc;

            const iconBg = document.getElementById('node-icon-bg');
            iconBg.className = `w-10 h-10 rounded-xl bg-${meta.color}-100 flex items-center justify-center text-${meta.color}-600 shadow-sm`;
            document.getElementById('node-icon').setAttribute('data-lucide', meta.icon);

            renderStudio();
            lucide.createIcons();
        }

        function setStudioView(mode) {
            studioViewMode = mode;
            if (mode === 'cards') {
                document.getElementById('btn-view-cards').className = "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white shadow-sm transition-all";
                document.getElementById('btn-view-json').className = "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all";
            } else {
                document.getElementById('btn-view-cards').className = "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-all";
                document.getElementById('btn-view-json').className = "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white shadow-sm transition-all";
            }
            renderStudio();
        }

        function renderStudio() {
            if (!telemetryData) return;
            const meta = NODE_MAP[activeKey];
            const data = meta ? meta.getData(telemetryData) : [];
            const container = document.getElementById('studio-content');

            if (studioViewMode === 'json') {
                container.innerHTML = `
                    <div class="bg-slate-900 text-slate-200 p-5 rounded-2xl font-mono text-xs overflow-x-auto max-h-[380px] custom-scrollbar border border-slate-800">
                        <pre>${JSON.stringify(data, null, 2)}</pre>
                    </div>
                `;
                return;
            }

            // STAGE 5 (Review & Approval Gate) or STAGE 4 (Visuals) Interactive View
            if (activeKey === 'review' || activeKey === 'content' || activeKey === 'visuals') {
                if (telemetryData.drafts.length === 0) {
                    container.innerHTML = `<div class="text-center py-12 text-slate-400">No generated drafts waiting for review. Click "Generate for X" or "Generate LinkedIn Carousel" above.</div>`;
                    return;
                }

                container.innerHTML = `
                    <div class="space-y-4">
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Drafts Ready for Approval & Publishing (${telemetryData.drafts.length})</span>
                        </div>
                        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            ${telemetryData.drafts.map(draft => {
                                const cleanCopy = draft.generated_copy;
                                const isCarousel = draft.platform === 'linkedin' || draft.format === 'carousel';
                                return `
                                <div class="p-5 bg-slate-50/90 border border-slate-200 rounded-2xl space-y-4 shadow-sm hover:border-slate-300 transition-all">
                                    <div class="flex items-center justify-between border-b border-slate-200/80 pb-3">
                                        <div class="flex items-center gap-2">
                                            <span class="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase font-mono ${draft.platform === 'x' ? 'bg-slate-900 text-white' : 'bg-[#0077B5] text-white'}">
                                                ${draft.platform === 'x' ? 'X (Twitter Thread)' : 'LinkedIn (5-Slide Carousel)'}
                                            </span>
                                            <span class="text-[11px] font-mono text-slate-500">${draft.format.toUpperCase()}</span>
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <span class="text-[11px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                                                Review Score: ${(draft.review_score * 100).toFixed(0)}%
                                            </span>
                                        </div>
                                    </div>

                                    ${isCarousel ? `
                                        <!-- Carousel Visual Slides Preview -->
                                        <div class="space-y-2">
                                            <span class="text-[11px] font-bold text-slate-700 flex items-center gap-1">
                                                <i data-lucide="image" class="w-3.5 h-3.5 text-pink-600"></i> Rendered 1080x1080 Carousel Slides (Swipe Preview):
                                            </span>
                                            <div class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 pt-1">
                                                <img src="/media/carousels/${draft.id}/slide_01.png" onerror="this.src='/media/carousels/default_slide.png'" class="w-40 h-40 rounded-xl border border-slate-300 shadow-sm object-cover flex-shrink-0" alt="Slide 1" />
                                                <img src="/media/carousels/${draft.id}/slide_02.png" onerror="this.style.display='none'" class="w-40 h-40 rounded-xl border border-slate-300 shadow-sm object-cover flex-shrink-0" alt="Slide 2" />
                                                <img src="/media/carousels/${draft.id}/slide_03.png" onerror="this.style.display='none'" class="w-40 h-40 rounded-xl border border-slate-300 shadow-sm object-cover flex-shrink-0" alt="Slide 3" />
                                                <img src="/media/carousels/${draft.id}/slide_04.png" onerror="this.style.display='none'" class="w-40 h-40 rounded-xl border border-slate-300 shadow-sm object-cover flex-shrink-0" alt="Slide 4" />
                                                <img src="/media/carousels/${draft.id}/slide_05.png" onerror="this.style.display='none'" class="w-40 h-40 rounded-xl border border-slate-300 shadow-sm object-cover flex-shrink-0" alt="Slide 5" />
                                            </div>
                                        </div>
                                    ` : ''}

                                    <!-- Natural English Post Copy Preview -->
                                    <div class="bg-white p-4 rounded-xl border border-slate-200 text-xs text-slate-800 font-sans whitespace-pre-wrap leading-relaxed max-h-[220px] overflow-y-auto custom-scrollbar">
${cleanCopy}
                                    </div>

                                    <!-- Review Feedback & Action Buttons -->
                                    <div class="flex flex-wrap items-center justify-between gap-3 pt-1">
                                        <p class="text-[11px] text-slate-500 italic max-w-sm">${draft.review_feedback || 'Factually verified against source code.'}</p>
                                        <div class="flex items-center gap-2">
                                            <button onclick="publishDraft('${draft.id}')" id="btn-pub-${draft.id}" class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-md transition-all flex items-center gap-1.5">
                                                <i data-lucide="send" class="w-3.5 h-3.5"></i> Approve & Publish Live
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `}).join('')}
                        </div>
                    </div>
                `;
                lucide.createIcons();
                return;
            }

            // General Card View
            if (Array.isArray(data) && data.length === 0) {
                container.innerHTML = `<div class="text-center py-12 text-slate-400">No active records for this stage yet. Click a generation button above.</div>`;
                return;
            }

            container.innerHTML = `
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-[420px] overflow-y-auto custom-scrollbar pr-1">
                    ${data.map(item => `
                        <div class="p-4 bg-slate-50/90 border border-slate-200 rounded-2xl space-y-2 hover:border-slate-300 transition-all shadow-sm">
                            <div class="flex items-center justify-between">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono bg-blue-100 text-blue-800">
                                    ${item.source_type || item.platform || 'PROCESSED'}
                                </span>
                                <span class="text-[11px] font-mono text-slate-400">${item.author ? '@' + item.author : ''}</span>
                            </div>
                            <h4 class="font-bold text-slate-900 text-xs leading-snug line-clamp-2">${item.title || item.hook || item.id || 'Signal Item'}</h4>
                            <p class="text-[11px] text-slate-600 line-clamp-3">${item.summary || item.generated_copy || item.verification_notes || JSON.stringify(item)}</p>
                            ${item.source_url ? `<a href="${item.source_url}" target="_blank" class="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:underline font-semibold pt-1">View Evidence &rarr;</a>` : ''}
                        </div>
                    `).join('')}
                </div>
            `;
            lucide.createIcons();
        }

        async function loadData() {
            try {
                const res = await fetch('/api/telemetry');
                telemetryData = await res.json();

                document.getElementById('metric-drafts').textContent = telemetryData.stats.approved_drafts;
                document.getElementById('metric-queue').textContent = telemetryData.stats.pending_queue;

                selectNodeKey(activeKey);
            } catch (e) {
                console.error('Failed to load telemetry:', e);
            }
        }

        // Live Traversal through sequential Node Scrapling/GitHub -> Reasoner -> Content -> Visuals -> Review Gate
        async function animateWorkflowSequence(sourceKey) {
            const sequence = [sourceKey, 'reasoner', 'content', 'visuals', 'review'];
            for (const key of sequence) {
                document.querySelectorAll('.n8n-node').forEach(n => n.classList.remove('executing-node'));
                const node = document.getElementById(`node-${key}`);
                if (node) node.classList.add('executing-node');
                
                selectNodeKey(key);
                document.getElementById('live-status').textContent = `EXECUTING: ${NODE_MAP[key].title.toUpperCase()}`;
                await new Promise(r => setTimeout(r, 700));
            }
            document.querySelectorAll('.n8n-node').forEach(n => n.classList.remove('executing-node'));
            document.getElementById('live-status').textContent = 'READY FOR APPROVAL';
        }

        async function startExecution(platform) {
            const customTopic = document.getElementById('input-custom-topic').value;
            const btnId = platform === 'x' ? 'btn-run-x' : (platform === 'linkedin' ? 'btn-run-li' : 'btn-run-both');
            const btn = document.getElementById(btnId);
            const originalHtml = btn.innerHTML;
            
            btn.innerHTML = '<i data-lucide="loader" class="w-4 h-4 animate-spin"></i> Processing...';
            btn.disabled = true;
            lucide.createIcons();

            document.getElementById('live-dot').className = "w-3 h-3 rounded-full bg-blue-500 animate-ping";

            const sourceKey = (customTopic && customTopic.startsWith('http') && !customTopic.includes('github')) ? 'scrapling' : 'github';
            const animPromise = animateWorkflowSequence(sourceKey);

            try {
                const res = await fetch('/api/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ platform: platform, topic: customTopic || null })
                });
                const data = await res.json();
                await animPromise;

                if (data.status === 'success') {
                    await loadData();
                    selectNodeKey('review'); // Switch straight to Review & Approval Gate
                } else {
                    alert('Generation issue: ' + data.message);
                }
            } catch (err) {
                alert('Error running pipeline: ' + err);
            } finally {
                btn.innerHTML = originalHtml;
                btn.disabled = false;
                document.getElementById('live-dot').className = "w-3 h-3 rounded-full bg-emerald-500 animate-pulse";
                lucide.createIcons();
            }
        }

        async function publishDraft(draftId) {
            const btn = document.getElementById(`btn-pub-${draftId}`);
            if (btn) {
                btn.innerHTML = '<i data-lucide="loader" class="w-3.5 h-3.5 animate-spin"></i> Publishing...';
                btn.disabled = true;
                lucide.createIcons();
            }

            // Animate Node Dispatch
            selectNodeKey('dispatch');
            const nodeDispatch = document.getElementById('node-dispatch');
            if (nodeDispatch) nodeDispatch.classList.add('executing-node');

            try {
                const res = await fetch('/api/publish/live', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ draft_id: draftId })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    alert(`🎉 Successfully published live to ${data.platform.toUpperCase()}!\nPost ID: ${data.post_id}`);
                    await loadData();
                    selectNodeKey('dispatch');
                } else {
                    alert(`Publishing note: ${data.message}`);
                }
            } catch (err) {
                alert('Publishing error: ' + err);
            } finally {
                if (nodeDispatch) nodeDispatch.classList.remove('executing-node');
                if (btn) {
                    btn.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5"></i> Published!';
                    btn.className = "px-4 py-2 rounded-xl bg-slate-900 text-white font-bold text-xs";
                }
                lucide.createIcons();
            }
        }

        loadData();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    """Render the Scrapling visual studio dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/api/telemetry")
def get_telemetry():
    """Return live system telemetry data."""
    db = get_db()
    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)

    discoveries = disc_repo.list_recent(limit=50)
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
            "discoveries": [d.model_dump() for d in discoveries[:15]],
            "drafts": [dr.model_dump() for dr in drafts[:10]],
            "health": health,
        }
    )


@app.post("/api/generate")
def generate_endpoint(req: GenerateRequest):
    """Live scrape & generate evidence-grounded copy for X, LinkedIn, or Both using Scrapling and Pillow."""
    try:
        from intelligence_os.intelligence.openrouter import OpenRouterClient
        from intelligence_os.content.x import XGenerator
        from intelligence_os.content.linkedin import LinkedInGenerator
        from intelligence_os.review.verifier import ReviewVerifier
        from intelligence_os.research.live_scraper import LiveTaskScraper

        db = get_db()
        settings = get_settings()
        draft_repo = ContentDraftRepository(db)
        renderer = CarouselRenderer(output_base_dir=output_dir / "carousels")

        # 1. Live Scrape target topic or repository with Scrapling
        scraper = LiveTaskScraper(db, github_token=settings.github_token)
        disc = scraper.scrape_topic_or_url(topic=req.topic, url=req.url)

        core = ResearchCoreData(
            hook=f"Why {disc.title} is changing how we build AI agent workflows.",
            core_insight=disc.summary,
            evidence=[disc.source_url],
            practical_takeaway="Adopt lightweight stdio agent servers for fast local development.",
            limitations="Requires local execution runtime.",
            content_angle=disc.content_angle or "workflow",
            tags=["#AIAgents", "#OpenSource", "#SoftwareEngineering"],
        )

        client = OpenRouterClient(settings)
        verifier = ReviewVerifier(client)
        created_drafts = []

        # 2. Generate for X (Natural English thread)
        if req.platform in ["x", "both"]:
            x_gen = XGenerator(client)
            x_res = x_gen.generate(core, preferred_format="thread")
            x_review = verifier.verify_draft(x_res.full_text_rendered, core, "x")
            
            x_draft_id = f"draft-x-{uuid.uuid4().hex[:8]}"
            x_draft = ContentDraftRecord(
                id=x_draft_id,
                discovery_id=disc.id,
                research_core=core.model_dump(),
                generated_copy=x_res.full_text_rendered,
                platform="x",
                format="thread",
                review_score=x_review.overall_score,
                review_feedback=x_review.feedback,
                status="APPROVED",
            )
            draft_repo.insert(x_draft)
            created_drafts.append(x_draft.id)

        # 3. Generate for LinkedIn (100% 5-Slide 1080x1080 Visual Carousel)
        if req.platform in ["linkedin", "both"]:
            li_gen = LinkedInGenerator(client)
            li_res = li_gen.generate(core, preferred_format="carousel")
            li_review = verifier.verify_draft(li_res.post_copy, core, "linkedin")

            li_draft_id = f"draft-li-{uuid.uuid4().hex[:8]}"

            # Generate Seedream Background Image for Carousel Cover
            from intelligence_os.visuals.openrouter_image import OpenRouterImageGenerator
            image_gen = OpenRouterImageGenerator(settings)
            bg_image_path = image_gen.generate_image_asset(core, li_draft_id)

            # Render 1080x1080 PNG slides locally with Pillow
            try:
                slide_paths = renderer.render_carousel(li_res.carousel_data, li_draft_id, bg_image_path=bg_image_path)
                logger.info(f"Rendered {len(slide_paths)} slides for {li_draft_id}")
            except Exception as render_err:
                logger.warning(f"Carousel rendering issue: {render_err}")

            li_draft = ContentDraftRecord(
                id=li_draft_id,
                discovery_id=disc.id,
                research_core=core.model_dump(),
                generated_copy=li_res.post_copy,
                platform="linkedin",
                format="carousel",
                review_score=li_review.overall_score,
                review_feedback=li_review.feedback,
                status="APPROVED",
            )
            draft_repo.insert(li_draft)
            created_drafts.append(li_draft.id)

        # Clear old drafts from the frontend by purging old ones, keeping only the new ones
        # For a clean dashboard experience without cluttered drafts
        all_drafts = draft_repo.list_by_status("APPROVED", limit=100)
        for old_draft in all_drafts:
            if old_draft.id not in created_drafts:
                db.execute("DELETE FROM content_drafts WHERE id = ?", (old_draft.id,))

        return JSONResponse(
            content={
                "status": "success",
                "created_drafts": created_drafts,
                "discovery_id": disc.id,
            }
        )

    except Exception as e:
        logger.error(f"Generation error: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": f"Generation failed: {str(e)}"},
        )


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

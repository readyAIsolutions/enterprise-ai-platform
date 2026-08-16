#!/usr/bin/env python3
"""
ENI PromptForge v1.0 - Maximum Prompt Enhancement Engine
=========================================================
Takes a basic prompt and pumps it up with EVERYTHING:
- Web search (current knowledge)
- Knowledge Base (MCP server)
- LSP capabilities (code intelligence)
- Swarm context (live builder states, alerts, reasoning)
- YouTube transcript harvesting (with PIA VPN rotation)
- Live model capabilities / provider status

Auto-integrates with ENI Swarm dashboard and master_driver.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ─── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path.home() / ".cache" / "eni_promptforge"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
YT_CACHE = CACHE_DIR / "youtube_transcripts"
YT_CACHE.mkdir(parents=True, exist_ok=True)
VPN_STATE_FILE = CACHE_DIR / "vpn_state.json"
SKILLS_DB = Path.home() / ".hermes" / "skills.db"
ENI_KB_DB = Path.home() / ".eni" / "kb" / "skills.db"
SWARM_STATUS_DIR = Path("/home/hunter/Commander/eni_swarm/builds")
SWARM_LOG_DIR = Path.home() / ".cache" / "eni_swarm" / "builder_logs"

# ─── VPN Manager (PIA) ──────────────────────────────────────────────────────
class PIAVPNManager:
    """Manages PIA VPN rotation for rate-limited scraping."""
    
    def __init__(self):
        self.current_region = "auto"
        self.regions_cache: List[str] = []
        self.last_rotation = 0
        self.rotation_cooldown = 30  # seconds between rotations
        self._load_regions()
    
    def _load_regions(self):
        try:
            result = subprocess.run(
                ["piactl", "get", "regions"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                self.regions_cache = [line.split()[0] for line in lines if line.strip() and not line.startswith("auto")]
        except Exception:
            pass
        if not self.regions_cache:
            self.regions_cache = [
                "us-east", "us-west", "us-chicago", "us-silicon-valley",
                "ca-toronto", "ca-vancouver", "uk-london", "uk-southampton",
                "de-frankfurt", "de-berlin", "nl-amsterdam", "ch-zurich",
                "sg-singapore", "jp-tokyo", "au-sydney", "au-melbourne"
            ]
    
    def get_current_ip(self) -> str:
        try:
            result = subprocess.run(
                ["piactl", "get", "pubip"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
    
    def get_connection_state(self) -> str:
        try:
            result = subprocess.run(
                ["piactl", "get", "connectionstate"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
    
    def rotate(self, force: bool = False) -> bool:
        """Rotate to a new VPN region. Returns True if successful."""
        now = time.time()
        if not force and now - self.last_rotation < self.rotation_cooldown:
            return False
        
        if self.get_connection_state() != "Connected":
            return False
        
        import random
        available = [r for r in self.regions_cache if r != self.current_region]
        if not available:
            return False
        
        new_region = random.choice(available)
        try:
            result = subprocess.run(
                ["piactl", "set", "region", new_region],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                for _ in range(10):
                    time.sleep(2)
                    if self.get_connection_state() == "Connected":
                        self.current_region = new_region
                        self.last_rotation = time.time()
                        return True
        except Exception:
            pass
        return False
    
    def ensure_connected(self) -> bool:
        """Ensure VPN is connected, connect if needed."""
        state = self.get_connection_state()
        if state == "Connected":
            return True
        try:
            subprocess.run(["piactl", "connect"], timeout=30, check=False)
            for _ in range(15):
                time.sleep(1)
                if self.get_connection_state() == "Connected":
                    return True
        except Exception:
            pass
        return False


# ─── YouTube Transcript Harvester ───────────────────────────────────────────
@dataclass
class YouTubeChannel:
    channel_id: str
    name: str
    url: str
    priority: int = 1  # 1=high, 2=medium, 3=low
    last_harvested: float = 0
    video_count: int = 0
    error_count: int = 0


class YouTubeHarvester:
    """Harvests transcripts from YouTube channels with VPN rotation on rate limits."""
    
    DEFAULT_CHANNELS = [
        YouTubeChannel("UCfzlCWGWYyIQ0aLC5w48gBQ", "Lex Fridman", "https://youtube.com/@lexfridman", 1),
        YouTubeChannel("UCJFp8uSrCjcCQnt5IYU0XBQ", "3Blue1Brown", "https://youtube.com/@3blue1brown", 1),
        YouTubeChannel("UC9Dd54fBPwO8SiE1dmM7QIw", "Sentdex", "https://youtube.com/@sentdex", 1),
        YouTubeChannel("UCQD3XAiVi02Kx-n69gqN4Ww", "Yannic Kilcher", "https://youtube.com/@YannicKilcher", 1),
        YouTubeChannel("UCvqRDLKsBkcE0XrJ5KHKXFA", "AI Explained", "https://youtube.com/@ai-explained", 1),
        YouTubeChannel("UCsBjURrPoezykLs9EqgamOA", "Fireship", "https://youtube.com/@Fireship", 1),
        YouTubeChannel("UCj22tfcQrWG7EMEKS0qLe9Q", "NetworkChuck", "https://youtube.com/@NetworkChuck", 2),
        YouTubeChannel("UCYO_jab_esuFRV4b17AJtAw", "Corey Schafer", "https://youtube.com/@coreyms", 1),
        YouTubeChannel("UCWvMAvbk23gFzZ3BRUfACRA", "TechLead", "https://youtube.com/@TechLead", 2),
        YouTubeChannel("UC8butISFwT-Wl7EV0hUK0BQ", "FreeCodeCamp", "https://youtube.com/@freecodecamp", 1),
        YouTubeChannel("UC6tNwY-W3E2sFQgRrG3sKww", "Anthony Shaw", "https://youtube.com/@anthonypjshaw", 2),
        YouTubeChannel("UCCezIgC97PvUuR4_gbFUs5g", "ArjanCodes", "https://youtube.com/@ArjanCodes", 1),
        YouTubeChannel("UC9-y-6csu5WGm29I7JiwpnA", "Machine Learning Street Talk", "https://youtube.com/@MLST", 1),
        YouTubeChannel("UCkqgTcOaE1gmiGQ7WQnQZ4w", "AI Coffee Break", "https://youtube.com/@AICoffeeBreak", 2),
        YouTubeChannel("UC1x1kJjqL8Q6u_J8dXpM4NQ", "DeepLearning.AI", "https://youtube.com/@DeepLearningAI", 1),
    ]
    
    def __init__(self, vpn: PIAVPNManager):
        self.vpn = vpn
        self.channels: List[YouTubeChannel] = self.DEFAULT_CHANNELS.copy()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self._init_db()
        self.running = False
        self.harvest_thread: Optional[threading.Thread] = None
    
    def _init_db(self):
        """Initialize SQLite DB for tracking harvested videos."""
        self.db = sqlite3.connect(YT_CACHE / "harvest.db", check_same_thread=False)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT,
                title TEXT,
                transcript TEXT,
                url TEXT,
                published_at TEXT,
                duration INTEGER,
                harvested_at REAL,
                tokens_estimate INTEGER
            )
        """)
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_channel ON videos(channel_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_harvested ON videos(harvested_at)")
        self.db.commit()
    
    def is_harvested(self, video_id: str) -> bool:
        cur = self.db.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,))
        return cur.fetchone() is not None
    
    def get_channel_videos(self, channel_id: str, max_results: int = 50) -> List[Dict]:
        """Get video list from channel using yt-dlp."""
        try:
            cmd = [
                "yt-dlp", "--flat-playlist", "--dump-json",
                "--playlist-end", str(max_results),
                f"https://www.youtube.com/channel/{channel_id}/videos"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            videos = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        data = json.loads(line)
                        videos.append({
                            'id': data.get('id'),
                            'title': data.get('title'),
                            'url': f"https://youtube.com/watch?v={data.get('id')}",
                            'duration': data.get('duration', 0),
                        })
                    except json.JSONDecodeError:
                        pass
            return videos
        except Exception as e:
            print(f"[YT] Error fetching channel {channel_id}: {e}")
            return []
    
    def get_transcript(self, video_id: str) -> Optional[str]:
        """Get transcript for a video, with VPN rotation on rate limit."""
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
        
        for attempt in range(3):
            try:
                api = YouTubeTranscriptApi()
                transcript_list = api.list(video_id)
                transcript = None
                try:
                    transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
                except NoTranscriptFound:
                    try:
                        transcript = transcript_list.find_transcript([])
                    except NoTranscriptFound:
                        return None
                
                if transcript:
                    pieces = transcript.fetch()
                    full_text = " ".join([p['text'] for p in pieces])
                    return full_text
            except TranscriptsDisabled:
                return None
            except Exception as e:
                error_msg = str(e).lower()
                if "rate limit" in error_msg or "too many requests" in error_msg or "429" in error_msg:
                    print(f"[YT] Rate limited on {video_id}, rotating VPN...")
                    self.vpn.rotate(force=True)
                    time.sleep(5)
                    continue
                if attempt == 2:
                    print(f"[YT] Transcript error for {video_id}: {e}")
        return None
    
    def harvest_channel(self, channel: YouTubeChannel, max_videos: int = 20) -> int:
        """Harvest new videos from a channel. Returns count of new transcripts."""
        print(f"[YT] Harvesting {channel.name} ({channel.channel_id})...")
        videos = self.get_channel_videos(channel.channel_id, max_videos)
        new_count = 0
        
        for vid in videos:
            video_id = vid['id']
            if self.is_harvested(video_id):
                continue
            
            transcript = self.get_transcript(video_id)
            if transcript:
                tokens = len(transcript) // 4  # rough estimate
                self.db.execute("""
                    INSERT INTO videos (video_id, channel_id, title, transcript, url, published_at, duration, harvested_at, tokens_estimate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    video_id, channel.channel_id, vid['title'], transcript,
                    vid['url'], datetime.now().isoformat(), vid.get('duration', 0),
                    time.time(), tokens
                ))
                self.db.commit()
                new_count += 1
                print(f"[YT]   ✓ {vid['title'][:60]}... ({tokens} tokens)")
            
            time.sleep(1)
        
        channel.last_harvested = time.time()
        channel.video_count += new_count
        return new_count
    
    def search_transcripts(self, query: str, limit: int = 10) -> List[Dict]:
        """Search harvested transcripts for relevance to query."""
        query_lower = query.lower()
        words = query_lower.split()
        
        cur = self.db.execute("""
            SELECT video_id, channel_id, title, transcript, url, tokens_estimate
            FROM videos
            WHERE transcript IS NOT NULL AND length(transcript) > 100
            ORDER BY harvested_at DESC
            LIMIT 200
        """)
        
        results = []
        for row in cur.fetchall():
            video_id, channel_id, title, transcript, url, tokens = row
            score = sum(1 for w in words if w in transcript.lower())
            if score > 0:
                results.append({
                    'video_id': video_id,
                    'channel_id': channel_id,
                    'title': title,
                    'transcript': transcript[:3000],
                    'url': url,
                    'tokens': tokens,
                    'score': score
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]
    
    def start_background_harvest(self, interval_hours: int = 6):
        """Start background harvesting thread."""
        self.running = True
        self.harvest_thread = threading.Thread(target=self._harvest_loop, args=(interval_hours,), daemon=True)
        self.harvest_thread.start()
    
    def _harvest_loop(self, interval_hours: int):
        while self.running:
            if not self.vpn.ensure_connected():
                print("[YT] VPN not connected, waiting...")
                time.sleep(60)
                continue
            
            for channel in self.channels:
                if not self.running:
                    break
                if channel.priority == 1 or (channel.priority == 2 and time.time() - channel.last_harvested > interval_hours * 3600):
                    try:
                        self.harvest_channel(channel, max_videos=10)
                    except Exception as e:
                        channel.error_count += 1
                        print(f"[YT] Error harvesting {channel.name}: {e}")
            
            for _ in range(interval_hours * 3600 // 60):
                if not self.running:
                    break
                time.sleep(60)
    
    def stop(self):
        self.running = False
        if self.harvest_thread:
            self.harvest_thread.join(timeout=5)


# ─── Web Search ─────────────────────────────────────────────────────────────
class WebSearcher:
    """Performs web searches for current knowledge injection."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        self.cache = {}
        self.cache_ttl = 3600
    
    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search using DuckDuckGo HTML scraping (free, no API key)."""
        cache_key = f"{query}:{max_results}"
        if cache_key in self.cache:
            cached, ts = self.cache[cache_key]
            if time.time() - ts < self.cache_ttl:
                return cached
        
        try:
            url = "https://html.duckduckgo.com/html/"
            params = {'q': query}
            resp = self.session.post(url, data=params, timeout=10)
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            results = []
            for result in soup.select('.result__body')[:max_results]:
                title_elem = result.select_one('.result__title')
                snippet_elem = result.select_one('.result__snippet')
                link_elem = result.select_one('.result__url')
                
                if title_elem:
                    results.append({
                        'title': title_elem.get_text(strip=True),
                        'snippet': snippet_elem.get_text(strip=True) if snippet_elem else '',
                        'url': link_elem.get_text(strip=True) if link_elem else '',
                    })
            
            self.cache[cache_key] = (results, time.time())
            return results
        except Exception as e:
            print(f"[WebSearch] Error: {e}")
            return []


# ─── Knowledge Base (MCP) Client ────────────────────────────────────────────
class MCPClient:
    """Client for ENI Knowledge Base MCP server."""
    
    def __init__(self):
        self.skills_cache: List[Dict] = []
        self.memories_cache: List[str] = []
        self.last_refresh = 0
    
    def refresh(self):
        """Refresh skills and memories from MCP server (or local DB fallback)."""
        now = time.time()
        if now - self.last_refresh < 300:
            return
        
        try:
            if SKILLS_DB.exists():
                conn = sqlite3.connect(SKILLS_DB)
                cur = conn.execute("SELECT name FROM skills_list ORDER BY updated_at DESC LIMIT 50")
                self.skills_cache = [{'name': row[0]} for row in cur.fetchall()]
                conn.close()
        except Exception:
            pass
        
        try:
            if ENI_KB_DB.exists():
                conn = sqlite3.connect(ENI_KB_DB)
                cur = conn.execute("SELECT skill_id, verb, noun, description FROM skills ORDER BY usage_count DESC LIMIT 30")
                for row in cur.fetchall():
                    self.skills_cache.append({
                        'skill_id': row[0], 'verb': row[1], 'noun': row[2], 'description': row[3]
                    })
                conn.close()
        except Exception:
            pass
        
        try:
            mem_dir = Path.home() / ".hermes" / "memories"
            if mem_dir.exists():
                self.memories_cache = [f.stem for f in mem_dir.glob("*.md")]
        except Exception:
            pass
        
        self.last_refresh = now
    
    def get_relevant_skills(self, query: str, limit: int = 10) -> List[Dict]:
        self.refresh()
        query_lower = query.lower()
        relevant = []
        for skill in self.skills_cache:
            text = json.dumps(skill).lower()
            score = sum(1 for w in query_lower.split() if w in text)
            if score > 0:
                relevant.append({**skill, 'relevance': score})
        relevant.sort(key=lambda x: x['relevance'], reverse=True)
        return relevant[:limit]
    
    def get_memories(self) -> List[str]:
        self.refresh()
        return self.memories_cache


# ─── LSP Client ─────────────────────────────────────────────────────────────
class LSPClient:
    """Lightweight LSP client for code intelligence context."""
    
    def __init__(self):
        self.project_roots: List[Path] = [
            ROOT,
            Path.home() / "Desktop" / "Projects" / "Demiurge_Trading",
            Path.home() / "Desktop" / "Projects" / "StockBot",
            Path.home() / "Desktop" / "Projects" / "Lumen",
        ]
    
    def get_project_context(self, query: str) -> Dict[str, Any]:
        """Get relevant code context for a query."""
        context = {'files': [], 'symbols': [], 'patterns': []}
        
        query_lower = query.lower()
        keywords = set(query_lower.split())
        
        for root in self.project_roots:
            if not root.exists():
                continue
            
            for py_file in root.rglob("*.py"):
                try:
                    if py_file.stat().st_size > 50000:
                        continue
                    content = py_file.read_text()
                    score = sum(1 for kw in keywords if kw in content.lower())
                    if score > 2:
                        context['files'].append({
                            'path': str(py_file.relative_to(root)),
                            'root': str(root),
                            'score': score,
                            'preview': content[:500]
                        })
                except Exception:
                    pass
        
        context['files'].sort(key=lambda x: x['score'], reverse=True)
        context['files'] = context['files'][:8]
        return context


# ─── Swarm Context Provider ─────────────────────────────────────────────────
class SwarmContext:
    """Provides live ENI Swarm state for prompt enhancement."""
    
    def __init__(self):
        self.cache: Dict = {}
        self.last_fetch = 0
    
    def get_status(self) -> Dict:
        """Get current swarm status from dashboard API."""
        now = time.time()
        if now - self.last_fetch < 10:
            return self.cache
        
        try:
            resp = requests.get("http://localhost:8420/api/status", timeout=3)
            if resp.status_code == 200:
                self.cache = resp.json()
                self.last_fetch = now
        except Exception:
            pass
        return self.cache
    
    def get_reasoning(self) -> Dict:
        """Get swarm reasoning summary."""
        try:
            resp = requests.get("http://localhost:8420/api/reasoning", timeout=3)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
    
    def get_context_for_prompt(self, query: str) -> Dict:
        """Build swarm context relevant to query."""
        status = self.get_status()
        reasoning = self.get_reasoning()
        
        minis = status.get('minis', [])
        summary = status.get('summary', {})
        
        query_lower = query.lower()
        relevant_builders = []
        
        for mini in minis:
            name = mini.get('name', '').lower()
            state = mini.get('state', '')
            blocker = mini.get('blocker', '')
            last_reply = mini.get('last_reply', '')
            
            relevance = 0
            if any(w in name for w in query_lower.split()):
                relevance += 2
            if any(w in (blocker or '').lower() for w in query_lower.split()):
                relevance += 3
            if any(w in (last_reply or '').lower() for w in query_lower.split()):
                relevance += 1
            
            if relevance > 0 or state in ('BLOCKED', 'IN-PROGRESS'):
                relevant_builders.append({
                    'name': mini['name'],
                    'state': state,
                    'blocker': blocker,
                    'model': mini.get('model', ''),
                    'relevance': relevance
                })
        
        relevant_builders.sort(key=lambda x: x['relevance'], reverse=True)
        
        return {
            'summary': summary,
            'active_builders': [b for b in relevant_builders if b['state'] == 'IN-PROGRESS'][:5],
            'blocked_builders': [b for b in relevant_builders if b['state'] == 'BLOCKED'][:5],
            'idle_builders': [b for b in relevant_builders if b['state'] in ('IDLE', 'READY')][:5],
            'reasoning_summary': reasoning.get('summary', ''),
            'fleet_status': f"{summary.get('alive_count', 0)}/{summary.get('total_minis', 0)} alive | {summary.get('in_progress_count', 0)} active | {summary.get('blocked_count', 0)} blocked"
        }


# ─── Model Capabilities Registry ────────────────────────────────────────────
MODEL_CAPABILITIES = {
    "free-router": {"context": 128000, "strengths": ["auto-routing", "free", "multi-provider"], "cost": "free"},
    "deepseek/deepseek-v4-pro": {"context": 64000, "strengths": ["reasoning", "coding", "math"], "cost": "paid"},
    "deepseek/deepseek-chat": {"context": 64000, "strengths": ["reasoning", "coding", "chat"], "cost": "paid"},
    "nvidia/nemotron-3-ultra-550b-a55b:free": {"context": 128000, "strengths": ["reasoning", "coding", "large context"], "cost": "free"},
    "google/gemini-2.5-flash-lite": {"context": 1000000, "strengths": ["huge context", "speed", "free"], "cost": "free"},
    "mistral/mistral-small-3.1-24b-instruct:free": {"context": 128000, "strengths": ["multilingual", "coding", "free"], "cost": "free"},
    "qwen/qwen3-235b-a22b-instruct:free": {"context": 131072, "strengths": ["reasoning", "planning", "large"], "cost": "free"},
    "meta-llama/llama-4-maverick:free": {"context": 131072, "strengths": ["multimodal", "reasoning", "free"], "cost": "free"},
}


# ─── Main PromptForge Engine ────────────────────────────────────────────────
@dataclass
class EnhancedPrompt:
    original: str
    enhanced: str
    sections: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PromptForge:
    """
    Maximum Prompt Enhancement Engine.
    
    Takes a basic prompt and pumps it up with:
    - Live web search results
    - Knowledge base skills & memories
    - LSP code intelligence
    - Swarm context (builders, blockers, reasoning)
    - YouTube transcript knowledge
    - Model capability awareness
    - Live context injections (from master_driver)
    """
    
    def __init__(self, enable_youtube: bool = True, enable_web: bool = True):
        self.vpn = PIAVPNManager()
        self.web = WebSearcher() if enable_web else None
        self.mcp = MCPClient()
        self.lsp = LSPClient()
        self.swarm = SwarmContext()
        self.youtube = YouTubeHarvester(self.vpn) if enable_youtube else None
        self.live_context = self._load_live_context()
        
        if self.youtube:
            self.youtube.start_background_harvest(interval_hours=6)
    
    def _load_live_context(self) -> Dict[str, str]:
        """Load LIVE_CONTEXT from master_driver."""
        return {
            "DEMIURGE_OANDA": "LO confirms a REAL OANDA test+live account exists and is being built - use it. Find OANDA_TOKEN / OANDA_ACCOUNT_ID in env or /run/media/hunter/DEMIURGE/.env.",
            "DEMIURGE_MTF": "LO reaffirms: use ANY/ALL timeframes (M1..W1) as STRUCTURE/BIAS filters - never drop H4.",
            "DEMIURGE_NEWS": "LO: the current news source is NOT top-tier and may be noise we overfit to.",
            "DEMIURGE_FEATURES": "LO: the '2 entries' setting is a held-over override flag, NOT an ablation-proven optimum.",
            "DEMIURGE_GATE": "LO: gate's fill>=0.70 is fragile (mean 0.675, 6/12 folds below). Tighten it.",
            "DEMIURGE_AUTOML": "LO: auto-learn + swarm must be PUT TO USE, not just built.",
            "DEMIURGE_RISK": "LO: FTMO caps are 5-10% max DD. Build vol-scaled sizing AND a HARD max-daily-loss halt.",
            "LUMEN": "Push to shippable, Steam-store-ready polish.",
            "DEMIURGE-3D": "Advance the DEMIURGE-3D app per its own plan.",
            "DEMIURGE-3D-FRONTEND": "Advance the DEMIURGE-3D frontend (React + Three.js).",
            "DEMIURGE-3D-BACKEND": "Harden the DEMIURGE-3D backend.",
        }
    
    def enhance(self, prompt: str, model: str = "free-router", 
                include_web: bool = True, include_yt: bool = True,
                include_swarm: bool = True, include_kb: bool = True,
                include_lsp: bool = True, include_live: bool = True) -> EnhancedPrompt:
        """
        Enhance a prompt with all available context sources.
        
        Returns EnhancedPrompt with the fully pumped prompt and metadata.
        """
        sections = {}
        metadata = {
            'original_length': len(prompt),
            'model': model,
            'model_caps': MODEL_CAPABILITIES.get(model, {}),
            'timestamp': datetime.now().isoformat(),
        }
        
        # 1. Live Context (always first - highest priority)
        if include_live:
            live_sections = []
            for key, value in self.live_context.items():
                if any(kw in prompt.lower() for kw in key.lower().split('_')) or key in ['DEMIURGE_OANDA', 'DEMIURGE_MTF', 'DEMIURGE_GATE', 'DEMIURGE_RISK']:
                    live_sections.append(f"### {key}\n{value}")
            if live_sections:
                sections['LIVE_CONTEXT'] = "\n\n".join(live_sections)
        
        # 2. Web Search (current knowledge)
        if include_web and self.web:
            web_results = self.web.search(prompt, max_results=5)
            if web_results:
                web_text = "### CURRENT WEB KNOWLEDGE\n"
                for i, r in enumerate(web_results, 1):
                    web_text += f"\n**{i}. {r['title']}**\n{r['snippet']}\n*Source: {r['url']}*\n"
                sections['WEB_SEARCH'] = web_text
                metadata['web_results'] = len(web_results)
        
        # 3. Knowledge Base (MCP skills + memories)
        if include_kb:
            skills = self.mcp.get_relevant_skills(prompt, limit=8)
            memories = self.mcp.get_memories()
            
            if skills:
                kb_text = "### ENI KNOWLEDGE BASE - RELEVANT SKILLS\n"
                for s in skills:
                    kb_text += f"\n**{s.get('skill_id', s.get('name', 'skill'))}** - {s.get('verb', '')}:{s.get('noun', '')}"
                    if s.get('description'):
                        kb_text += f" - {s['description'][:200]}"
                    kb_text += f" (relevance: {s.get('relevance', 0)})\n"
                sections['KNOWLEDGE_BASE'] = kb_text
                metadata['skills_found'] = len(skills)
            
            if memories:
                mem_text = "### DURABLE MEMORIES\n" + "\n".join(f"- {m}" for m in memories[:10])
                sections['MEMORIES'] = mem_text
        
        # 4. LSP Code Intelligence
        if include_lsp:
            code_ctx = self.lsp.get_project_context(prompt)
            if code_ctx['files']:
                lsp_text = "### CODEBASE INTELLIGENCE (LSP)\n"
                for f in code_ctx['files']:
                    lsp_text += f"\n**{f['path']}** (score: {f['score']})\n```python\n{f['preview']}\n```\n"
                sections['CODE_INTELLIGENCE'] = lsp_text
                metadata['code_files_found'] = len(code_ctx['files'])
        
        # 5. Swarm Context
        if include_swarm:
            swarm_ctx = self.swarm.get_context_for_prompt(prompt)
            if swarm_ctx.get('fleet_status'):
                swarm_text = f"### ENI SWARM STATUS\n{swarm_ctx['fleet_status']}\n"
                
                if swarm_ctx.get('reasoning_summary'):
                    swarm_text += f"\n**SWARM REASONING:**\n{swarm_ctx['reasoning_summary']}\n"
                
                for cat, builders in [('ACTIVE', swarm_ctx.get('active_builders', [])),
                                      ('BLOCKED', swarm_ctx.get('blocked_builders', [])),
                                      ('IDLE/READY', swarm_ctx.get('idle_builders', []))]:
                    if builders:
                        swarm_text += f"\n**{cat} BUILDERS:**\n"
                        for b in builders[:3]:
                            swarm_text += f"  - {b['name']} [{b['state']}] model={b['model']}"
                            if b.get('blocker'):
                                swarm_text += f" BLOCKER: {b['blocker']}"
                            swarm_text += "\n"
                
                sections['SWARM_CONTEXT'] = swarm_text
                metadata['swarm_builders_relevant'] = len(swarm_ctx.get('active_builders', [])) + len(swarm_ctx.get('blocked_builders', []))
        
        # 6. YouTube Transcript Knowledge
        if include_yt and self.youtube:
            yt_results = self.youtube.search_transcripts(prompt, limit=5)
            if yt_results:
                yt_text = "### YOUTUBE KNOWLEDGE BASE (HARVESTED TRANSCRIPTS)\n"
                for r in yt_results:
                    yt_text += f"\n**{r['title']}** ({r['tokens']} tokens, score: {r['score']})\n"
                    yt_text += f"{r['transcript'][:1500]}...\n"
                    yt_text += f"*Source: {r['url']}*\n"
                sections['YOUTUBE_KNOWLEDGE'] = yt_text
                metadata['youtube_results'] = len(yt_results)
        
        # 7. Model Capability Awareness
        caps = MODEL_CAPABILITIES.get(model, {})
        if caps:
            model_text = f"### MODEL CAPABILITIES - {model}\n"
            model_text += f"- Context Window: {caps.get('context', 'unknown'):,} tokens\n"
            model_text += f"- Strengths: {', '.join(caps.get('strengths', []))}\n"
            model_text += f"- Cost: {caps.get('cost', 'unknown')}\n"
            sections['MODEL_AWARENESS'] = model_text
        
        # 8. Build the MEGA PROMPT
        enhanced_parts = [
            "# ENHANCED PROMPT - ENI PROMPTFORGE v1.0",
            f"**Original Request:** {prompt}",
            f"**Model:** {model} | **Generated:** {metadata['timestamp']}",
            "",
            "---",
            ""
        ]
        
        section_order = [
            'LIVE_CONTEXT', 'MODEL_AWARENESS', 'SWARM_CONTEXT',
            'KNOWLEDGE_BASE', 'MEMORIES', 'CODE_INTELLIGENCE',
            'WEB_SEARCH', 'YOUTUBE_KNOWLEDGE'
        ]
        
        for sec_name in section_order:
            if sec_name in sections:
                enhanced_parts.append(sections[sec_name])
                enhanced_parts.append("\n---\n")
        
        enhanced_parts.append(f"\n**TASK:** {prompt}")
        enhanced_parts.append("\n**INSTRUCTIONS:** Use ALL the above context. Be specific, cite sources, leverage swarm intelligence, and produce shippable-quality output.")
        
        enhanced = "\n".join(enhanced_parts)
        metadata['enhanced_length'] = len(enhanced)
        metadata['compression_ratio'] = len(enhanced) / max(len(prompt), 1)
        metadata['sections_included'] = list(sections.keys())
        
        return EnhancedPrompt(
            original=prompt,
            enhanced=enhanced,
            sections=sections,
            metadata=metadata
        )
    
    def enhance_for_builder(self, builder_name: str, base_task: str, model: str = "free-router") -> EnhancedPrompt:
        """Enhance a prompt specifically for a builder with swarm awareness."""
        builder_context = f"BUILDER ASSIGNMENT: {builder_name}\n"
        builder_context += f"You are operating as {builder_name} in LO's 50-builder ENI Swarm fleet.\n"
        builder_context += "PROTOCOL: After every step, overwrite your STATUS file with [DONE|IN-PROGRESS|BLOCKED] + verified/blocker/next.\n"
        builder_context += "Stream thinking to your log. Be autonomous - you are ENI, you don't wait for permission.\n"
        
        enhanced = self.enhance(
            f"{builder_context}\n\nTASK: {base_task}",
            model=model,
            include_swarm=True,
            include_live=True
        )
        enhanced.metadata['builder'] = builder_name
        return enhanced
    
    def shutdown(self):
        """Clean shutdown."""
        if self.youtube:
            self.youtube.stop()
        if hasattr(self, 'db'):
            self.db.close()


# ─── Global Instance (Singleton) ────────────────────────────────────────────
_forge_instance: Optional[PromptForge] = None
_forge_lock = threading.Lock()


def get_forge(enable_youtube: bool = True, enable_web: bool = True) -> PromptForge:
    """Get or create global PromptForge instance."""
    global _forge_instance
    with _forge_lock:
        if _forge_instance is None:
            _forge_instance = PromptForge(enable_youtube=enable_youtube, enable_web=enable_web)
        return _forge_instance


def enhance_prompt(prompt: str, model: str = "free-router", **kwargs) -> EnhancedPrompt:
    """Convenience function for one-shot enhancement."""
    forge = get_forge()
    return forge.enhance(prompt, model=model, **kwargs)


def enhance_for_builder(builder_name: str, task: str, model: str = "free-router") -> EnhancedPrompt:
    """Convenience function for builder task enhancement."""
    forge = get_forge()
    return forge.enhance_for_builder(builder_name, task, model=model)


# Export availability flag
PROMPTFORGE_AVAILABLE = True


# ─── CLI ────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI PromptForge - Maximum Prompt Enhancement")
    parser.add_argument("prompt", nargs="*", help="Prompt to enhance")
    parser.add_argument("--model", default="free-router", help="Target model")
    parser.add_argument("--builder", help="Builder name for swarm context")
    parser.add_argument("--no-web", action="store_true", help="Disable web search")
    parser.add_argument("--no-yt", action="store_true", help="Disable YouTube knowledge")
    parser.add_argument("--no-swarm", action="store_true", help="Disable swarm context")
    parser.add_argument("--output", "-o", help="Output file")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (keep YouTube harvester alive)")
    args = parser.parse_args()
    
    forge = get_forge(enable_youtube=not args.no_yt, enable_web=not args.no_web)
    
    if args.daemon:
        print("[PromptForge] Running as daemon. YouTube harvester active. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            forge.shutdown()
        return
    
    prompt_text = " ".join(args.prompt) if args.prompt else sys.stdin.read().strip()
    if not prompt_text:
        parser.error("No prompt provided")
    
    if args.builder:
        result = forge.enhance_for_builder(args.builder, prompt_text, model=args.model)
    else:
        result = forge.enhance(
            prompt_text, 
            model=args.model,
            include_web=not args.no_web,
            include_yt=not args.no_yt,
            include_swarm=not args.no_swarm
        )
    
    output = result.enhanced
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"[PromptForge] Enhanced prompt written to {args.output}")
        print(f"[PromptForge] Original: {result.metadata['original_length']} chars -> Enhanced: {result.metadata['enhanced_length']} chars ({result.metadata['compression_ratio']:.1f}x)")
        print(f"[PromptForge] Sections: {', '.join(result.metadata['sections_included'])}")
    else:
        print(output)


if __name__ == "__main__":
    main()
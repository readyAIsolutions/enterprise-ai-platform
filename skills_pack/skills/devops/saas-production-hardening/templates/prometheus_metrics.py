"""
Prometheus Metrics for SaaS Production Hardening.

Provides comprehensive metrics with:
- Counters, Gauges, Histograms, Summaries
- Label support for multi-dimensional metrics
- Custom business metrics (voice, email, CRM, campaigns)
- System metrics (HTTP, DB, Redis, resilience patterns)
- Model/router metrics (requests, tokens, cost)
- Compliance metrics (opt-outs, DNC, consent)
- Health check metrics
- Business KPI metrics (revenue, ROI, conversion, pipeline)
"""

from __future__ import annotations

import asyncio
import time
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)


# =============================================================================
# CUSTOM REGISTRY
# =============================================================================

# Create a dedicated registry for our metrics
METRICS_REGISTRY = CollectorRegistry()

# Auto-register with default registry as well
DEFAULT_REGISTRY = REGISTRY


# =============================================================================
# BUSINESS METRICS
# =============================================================================

# Voice Metrics
voice_calls_total = Counter(
    "saas_voice_calls_total",
    "Total voice calls processed",
    ["direction", "provider", "status", "workspace"],
    registry=METRICS_REGISTRY,
)

voice_call_duration_seconds = Histogram(
    "saas_voice_call_duration_seconds",
    "Voice call duration in seconds",
    ["direction", "provider", "workspace"],
    buckets=[5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=METRICS_REGISTRY,
)

voice_concurrent_calls = Gauge(
    "saas_voice_concurrent_calls",
    "Currently active voice calls",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

voice_call_cost_usd = Counter(
    "saas_voice_call_cost_usd_total",
    "Total voice call cost in USD",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

# Email Metrics
email_sent_total = Counter(
    "saas_email_sent_total",
    "Total emails sent",
    ["provider", "status", "template", "workspace"],
    registry=METRICS_REGISTRY,
)

email_delivered_total = Counter(
    "saas_email_delivered_total",
    "Total emails delivered",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

email_bounced_total = Counter(
    "saas_email_bounced_total",
    "Total emails bounced",
    ["provider", "bounce_type", "workspace"],
    registry=METRICS_REGISTRY,
)

email_opened_total = Counter(
    "saas_email_opened_total",
    "Total emails opened",
    ["provider", "template", "workspace"],
    registry=METRICS_REGISTRY,
)

email_clicked_total = Counter(
    "saas_email_clicked_total",
    "Total email links clicked",
    ["provider", "template", "workspace"],
    registry=METRICS_REGISTRY,
)

email_replied_total = Counter(
    "saas_email_replied_total",
    "Total email replies received",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

email_unsubscribed_total = Counter(
    "saas_email_unsubscribed_total",
    "Total email unsubscribes",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

email_complained_total = Counter(
    "saas_email_complained_total",
    "Total spam complaints",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

email_cost_usd = Counter(
    "saas_email_cost_usd_total",
    "Total email cost in USD",
    ["provider", "workspace"],
    registry=METRICS_REGISTRY,
)

# CRM Metrics
crm_leads_created_total = Counter(
    "saas_crm_leads_created_total",
    "Total CRM leads created",
    ["source", "stage", "workspace"],
    registry=METRICS_REGISTRY,
)

crm_leads_updated_total = Counter(
    "saas_crm_leads_updated_total",
    "Total CRM leads updated",
    ["field", "workspace"],
    registry=METRICS_REGISTRY,
)

crm_sync_duration_seconds = Histogram(
    "saas_crm_sync_duration_seconds",
    "CRM sync duration in seconds",
    ["operation", "workspace"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
    registry=METRICS_REGISTRY,
)

# Campaign Metrics
campaigns_created_total = Counter(
    "saas_campaigns_created_total",
    "Total campaigns created",
    ["channel", "approval_mode", "workspace"],
    registry=METRICS_REGISTRY,
)

campaigns_started_total = Counter(
    "saas_campaigns_started_total",
    "Total campaigns started",
    ["channel", "workspace"],
    registry=METRICS_REGISTRY,
)

campaigns_paused_total = Counter(
    "saas_campaigns_paused_total",
    "Total campaigns paused",
    ["reason", "workspace"],
    registry=METRICS_REGISTRY,
)

campaign_prospects = Gauge(
    "saas_campaign_prospects",
    "Prospects in active campaigns",
    ["campaign_id", "channel", "workspace"],
    registry=METRICS_REGISTRY,
)

campaign_bookings_total = Counter(
    "saas_campaign_bookings_total",
    "Total bookings from campaigns",
    ["campaign_id", "channel", "workspace"],
    registry=METRICS_REGISTRY,
)

# System Metrics
http_requests_total = Counter(
    "saas_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status", "workspace"],
    registry=METRICS_REGISTRY,
)

http_request_duration_seconds = Histogram(
    "saas_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "workspace"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=METRICS_REGISTRY,
)

http_request_size_bytes = Histogram(
    "saas_http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "path"],
    buckets=[100, 1000, 10000, 100000, 1000000],
    registry=METRICS_REGISTRY,
)

http_response_size_bytes = Histogram(
    "saas_http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "path"],
    buckets=[100, 1000, 10000, 100000, 1000000],
    registry=METRICS_REGISTRY,
)

# Database Metrics
db_query_duration_seconds = Histogram(
    "saas_db_query_duration_seconds",
    "Database query duration in seconds",
    ["query_type", "table", "workspace"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    registry=METRICS_REGISTRY,
)

db_connections_active = Gauge(
    "saas_db_connections_active",
    "Active database connections",
    ["pool", "workspace"],
    registry=METRICS_REGISTRY,
)

db_connections_idle = Gauge(
    "saas_db_connections_idle",
    "Idle database connections",
    ["pool", "workspace"],
    registry=METRICS_REGISTRY,
)

# Redis Metrics
redis_operations_total = Counter(
    "saas_redis_operations_total",
    "Total Redis operations",
    ["operation", "status", "workspace"],
    registry=METRICS_REGISTRY,
)

redis_latency_seconds = Histogram(
    "saas_redis_latency_seconds",
    "Redis operation latency in seconds",
    ["operation", "workspace"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
    registry=METRICS_REGISTRY,
)

# Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    "saas_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["name", "workspace"],
    registry=METRICS_REGISTRY,
)

circuit_breaker_failures_total = Counter(
    "saas_circuit_breaker_failures_total",
    "Circuit breaker failure count",
    ["name", "workspace"],
    registry=METRICS_REGISTRY,
)

# Rate Limiter Metrics
rate_limiter_requests_total = Counter(
    "saas_rate_limiter_requests_total",
    "Rate limiter request outcomes",
    ["key", "result", "workspace"],
    registry=METRICS_REGISTRY,
)

rate_limiter_tokens = Gauge(
    "saas_rate_limiter_tokens",
    "Current tokens in rate limiter bucket",
    ["key", "workspace"],
    registry=METRICS_REGISTRY,
)

# Bulkhead Metrics
bulkhead_active = Gauge(
    "saas_bulkhead_active",
    "Active executions in bulkhead",
    ["name", "workspace"],
    registry=METRICS_REGISTRY,
)

bulkhead_queued = Gauge(
    "saas_bulkhead_queued",
    "Queued requests in bulkhead",
    ["name", "workspace"],
    registry=METRICS_REGISTRY,
)

bulkhead_rejected_total = Counter(
    "saas_bulkhead_rejected_total",
    "Rejected requests due to bulkhead limit",
    ["name", "workspace"],
    registry=METRICS_REGISTRY,
)

# Model/Router Metrics
model_requests_total = Counter(
    "saas_model_requests_total",
    "Total model requests",
    ["provider", "model", "task", "status", "workspace"],
    registry=METRICS_REGISTRY,
)

model_request_duration_seconds = Histogram(
    "saas_model_request_duration_seconds",
    "Model request duration in seconds",
    ["provider", "model", "task", "workspace"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=METRICS_REGISTRY,
)

model_tokens_total = Counter(
    "saas_model_tokens_total",
    "Total tokens used",
    ["provider", "model", "type", "workspace"],
    registry=METRICS_REGISTRY,
)

model_cost_usd = Counter(
    "saas_model_cost_usd_total",
    "Total model cost in USD",
    ["provider", "model", "workspace"],
    registry=METRICS_REGISTRY,
)

# Compliance Metrics
compliance_opt_outs_total = Counter(
    "saas_compliance_opt_outs_total",
    "Total opt-out requests",
    ["channel", "reason", "jurisdiction", "workspace"],
    registry=METRICS_REGISTRY,
)

compliance_dnc_scrubs_total = Counter(
    "saas_compliance_dnc_scrubs_total",
    "Total DNC list scrubs",
    ["list_source", "workspace"],
    registry=METRICS_REGISTRY,
)

compliance_consent_checks_total = Counter(
    "saas_compliance_consent_checks_total",
    "Total consent verification checks",
    ["channel", "result", "jurisdiction", "workspace"],
    registry=METRICS_REGISTRY,
)

# =============================================================================
# METRICS HELPER FUNCTIONS
# =============================================================================

def get_workspace_label() -> str:
    """Get workspace label from config or context."""
    try:
        from saas.config import get_config
        config = get_config()
        return config.workspace.company_name.lower().replace(" ", "-") or "default"
    except Exception:
        return "default"


def record_voice_call(
    direction: str,
    provider: str,
    status: str,
    duration_seconds: float = 0,
    cost_usd: float = 0,
    workspace: str = None,
):
    """Record voice call metrics."""
    ws = workspace or get_workspace_label()
    voice_calls_total.labels(
        direction=direction,
        provider=provider,
        status=status,
        workspace=ws,
    ).inc()
    
    if duration_seconds > 0:
        voice_call_duration_seconds.labels(
            direction=direction,
            provider=provider,
            workspace=ws,
        ).observe(duration_seconds)
    
    if cost_usd > 0:
        voice_call_cost_usd.labels(
            provider=provider,
            workspace=ws,
        ).inc(cost_usd)


def record_email_sent(
    provider: str,
    status: str,
    template: str = "unknown",
    workspace: str = None,
):
    """Record email sent metric."""
    ws = workspace or get_workspace_label()
    email_sent_total.labels(
        provider=provider,
        status=status,
        template=template,
        workspace=ws,
    ).inc()


def record_email_event(
    event: str,  # delivered, bounced, opened, clicked, replied, unsubscribed, complained
    provider: str,
    template: str = "unknown",
    workspace: str = None,
    bounce_type: str = None,
):
    """Record email event metric."""
    ws = workspace or get_workspace_label()
    
    if event == "delivered":
        email_delivered_total.labels(provider=provider, workspace=ws).inc()
    elif event == "bounced":
        email_bounced_total.labels(
            provider=provider,
            bounce_type=bounce_type or "unknown",
            workspace=ws,
        ).inc()
    elif event == "opened":
        email_opened_total.labels(
            provider=provider,
            template=template,
            workspace=ws,
        ).inc()
    elif event == "clicked":
        email_clicked_total.labels(
            provider=provider,
            template=template,
            workspace=ws,
        ).inc()
    elif event == "replied":
        email_replied_total.labels(provider=provider, workspace=ws).inc()
    elif event == "unsubscribed":
        email_unsubscribed_total.labels(provider=provider, workspace=ws).inc()
    elif event == "complained":
        email_complained_total.labels(provider=provider, workspace=ws).inc()


def record_crm_lead(
    action: str,  # created, updated
    source: str = "unknown",
    stage: str = "unknown",
    field: str = None,
    workspace: str = None,
):
    """Record CRM lead metric."""
    ws = workspace or get_workspace_label()
    
    if action == "created":
        crm_leads_created_total.labels(
            source=source,
            stage=stage,
            workspace=ws,
        ).inc()
    elif action == "updated" and field:
        crm_leads_updated_total.labels(field=field, workspace=ws).inc()


def record_campaign_metric(
    action: str,  # created, started, paused, booking
    campaign_id: str = "",
    channel: str = "unknown",
    workspace: str = None,
    reason: str = "",
):
    """Record campaign metric."""
    ws = workspace or get_workspace_label()
    
    if action == "created":
        campaigns_created_total.labels(
            channel=channel,
            approval_mode="unknown",
            workspace=ws,
        ).inc()
    elif action == "started":
        campaigns_started_total.labels(channel=channel, workspace=ws).inc()
    elif action == "paused":
        campaigns_paused_total.labels(reason=reason, workspace=ws).inc()
    elif action == "booking":
        campaign_bookings_total.labels(
            campaign_id=campaign_id,
            channel=channel,
            workspace=ws,
        ).inc()


def record_model_request(
    provider: str,
    model: str,
    task: str,
    status: str,
    duration_seconds: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0,
    workspace: str = None,
):
    """Record model request metrics."""
    ws = workspace or get_workspace_label()
    
    model_requests_total.labels(
        provider=provider,
        model=model,
        task=task,
        status=status,
        workspace=ws,
    ).inc()
    
    model_request_duration_seconds.labels(
        provider=provider,
        model=model,
        task=task,
        workspace=ws,
    ).observe(duration_seconds)
    
    if input_tokens > 0:
        model_tokens_total.labels(
            provider=provider,
            model=model,
            type="input",
            workspace=ws,
        ).inc(input_tokens)
    
    if output_tokens > 0:
        model_tokens_total.labels(
            provider=provider,
            model=model,
            type="output",
            workspace=ws,
        ).inc(output_tokens)
    
    if cost_usd > 0:
        model_cost_usd.labels(
            provider=provider,
            model=model,
            workspace=ws,
        ).inc(cost_usd)


def record_compliance_event(
    event: str,  # opt_out, dnc_scrub, consent_check
    channel: str,
    result: str = "success",
    reason: str = "",
    jurisdiction: str = "unknown",
    workspace: str = None,
):
    """Record compliance event metric."""
    ws = workspace or get_workspace_label()
    
    if event == "opt_out":
        compliance_opt_outs_total.labels(
            channel=channel,
            reason=reason,
            jurisdiction=jurisdiction,
            workspace=ws,
        ).inc()
    elif event == "dnc_scrub":
        compliance_dnc_scrubs_total.labels(
            list_source=reason,
            workspace=ws,
        ).inc()
    elif event == "consent_check":
        compliance_consent_checks_total.labels(
            channel=channel,
            result=result,
            jurisdiction=jurisdiction,
            workspace=ws,
        ).inc()


# =============================================================================
# METRICS MIDDLEWARE
# =============================================================================

async def metrics_middleware(request, call_next):
    """ASGI middleware for automatic HTTP metrics collection."""
    from starlette.requests import Request
    from starlette.responses import Response
    
    start_time = time.time()
    workspace = getattr(request.state, "workspace", "default")
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        http_requests_total.labels(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            workspace=workspace,
        ).inc()
        
        http_request_duration_seconds.labels(
            method=request.method,
            path=request.url.path,
            workspace=workspace,
        ).observe(duration)
        
        # Record request/response sizes
        request_size = request.headers.get("content-length", 0)
        if request_size:
            http_request_size_bytes.labels(
                method=request.method,
                path=request.url.path,
            ).observe(int(request_size))
        
        response_size = response.headers.get("content-length", 0)
        if response_size:
            http_response_size_bytes.labels(
                method=request.method,
                path=request.url.path,
            ).observe(int(response_size))
        
        return response
    except Exception as e:
        duration = time.time() - start_time
        http_requests_total.labels(
            method=request.method,
            path=request.url.path,
            status=500,
            workspace=workspace,
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method,
            path=request.url.path,
            workspace=workspace,
        ).observe(duration)
        raise


# =============================================================================
# METRICS ENDPOINT
# =============================================================================

def metrics_endpoint() -> tuple[bytes, dict]:
    """Generate Prometheus metrics endpoint response."""
    output = generate_latest(METRICS_REGISTRY)
    return output, {"Content-Type": CONTENT_TYPE_LATEST}


# =============================================================================
# METRICS COLLECTOR FOR CUSTOM METRICS
# =============================================================================

class MetricsCollector:
    """Background collector for system metrics."""
    
    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start background collection."""
        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
    
    async def stop(self):
        """Stop background collection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _collect_loop(self):
        while self._running:
            try:
                await self._collect_system_metrics()
            except Exception as e:
                logging.getLogger(__name__).error(f"Metrics collection error: {e}")
            await asyncio.sleep(self.interval)
    
    async def _collect_system_metrics(self):
        """Collect system-level metrics."""
        import psutil
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory
        mem = psutil.virtual_memory()
        
        # Disk
        disk = psutil.disk_usage('/')
        
        # Network
        net = psutil.net_io_counters()


# =============================================================================
# DECORATORS FOR AUTOMATIC METRICS
# =============================================================================

def track_metrics(
    counter: Counter = None,
    histogram: Histogram = None,
    gauge: Gauge = None,
    labels: Callable = None,
):
    """
    Decorator to automatically track metrics for a function.
    
    Usage:
        @track_metrics(
            counter=my_counter,
            histogram=my_histogram,
            labels=lambda *args, **kwargs: {"operation": "my_op"}
        )
        async def my_function(...):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Determine labels
            lbls = labels(*args, **kwargs) if labels else {}
            
            start = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                if counter:
                    counter.labels(**lbls, status=status).inc()
                if histogram:
                    histogram.labels(**lbls).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            lbls = labels(*args, **kwargs) if labels else {}
            start = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                if counter:
                    counter.labels(**lbls, status=status).inc()
                if histogram:
                    histogram.labels(**lbls).observe(duration)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# =============================================================================
# HEALTH CHECK METRICS
# =============================================================================

health_check_status = Gauge(
    "saas_health_check_status",
    "Health check status (1=healthy, 0=unhealthy)",
    ["check", "workspace"],
    registry=METRICS_REGISTRY,
)

health_check_duration_seconds = Histogram(
    "saas_health_check_duration_seconds",
    "Health check duration in seconds",
    ["check", "workspace"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    registry=METRICS_REGISTRY,
)


async def record_health_check(
    check_name: str,
    healthy: bool,
    duration_seconds: float,
    workspace: str = None,
):
    """Record health check result."""
    ws = workspace or get_workspace_label()
    health_check_status.labels(check=check_name, workspace=ws).set(1 if healthy else 0)
    health_check_duration_seconds.labels(check=check_name, workspace=ws).observe(duration_seconds)


# =============================================================================
# BUSINESS KPI METRICS
# =============================================================================

# Revenue/ROI Metrics
revenue_usd = Counter(
    "saas_revenue_usd_total",
    "Total revenue in USD",
    ["source", "workspace"],
    registry=METRICS_REGISTRY,
)

cost_usd = Counter(
    "saas_cost_usd_total",
    "Total operational cost in USD",
    ["category", "workspace"],
    registry=METRICS_REGISTRY,
)

roi_ratio = Gauge(
    "saas_roi_ratio",
    "Return on investment ratio",
    ["workspace"],
    registry=METRICS_REGISTRY,
)

# Conversion Metrics
conversion_rate = Gauge(
    "saas_conversion_rate",
    "Conversion rate (bookings / prospects)",
    ["campaign_id", "channel", "workspace"],
    registry=METRICS_REGISTRY,
)

cost_per_booking = Gauge(
    "saas_cost_per_booking_usd",
    "Cost per booking in USD",
    ["campaign_id", "channel", "workspace"],
    registry=METRICS_REGISTRY,
)

# Pipeline Metrics
pipeline_leads = Gauge(
    "saas_pipeline_leads",
    "Leads in pipeline by stage",
    ["stage", "workspace"],
    registry=METRICS_REGISTRY,
)

pipeline_value_usd = Gauge(
    "saas_pipeline_value_usd",
    "Pipeline value in USD",
    ["stage", "workspace"],
    registry=METRICS_REGISTRY,
)


# =============================================================================
# METRICS UTILITIES
# =============================================================================

def get_metrics_summary() -> dict:
    """Get summary of all registered metrics."""
    metrics_info = {
        "counters": [],
        "gauges": [],
        "histograms": [],
        "summaries": [],
    }
    
    for collector in METRICS_REGISTRY._collector_to_names:
        for name in METRICS_REGISTRY._collector_to_names[collector]:
            metric = collector._metrics.get(name)
            if metric:
                metric_type = type(metric).__name__.lower()
                if "counter" in metric_type:
                    metrics_info["counters"].append(name)
                elif "gauge" in metric_type:
                    metrics_info["gauges"].append(name)
                elif "histogram" in metric_type:
                    metrics_info["histograms"].append(name)
                elif "summary" in metric_type:
                    metrics_info["summaries"].append(name)
    
    return metrics_info


def export_metrics_prometheus() -> bytes:
    """Export all metrics in Prometheus format."""
    return generate_latest(METRICS_REGISTRY)


def export_metrics_json() -> dict:
    """Export metrics as JSON for debugging."""
    return {"status": "not_implemented"}


# =============================================================================
# METRICS SERVER
# =============================================================================

async def start_metrics_server(port: int = 9090):
    """Start Prometheus metrics HTTP server."""
    from aiohttp import web
    
    async def metrics_handler(request):
        return web.Response(
            body=generate_latest(METRICS_REGISTRY),
            content_type=CONTENT_TYPE_LATEST,
        )
    
    async def health_handler(request):
        return web.json_response({"status": "healthy"})
    
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    return runner


# =============================================================================
# EXPORT ALL METRICS
# =============================================================================

__all__ = [
    # Registry
    "METRICS_REGISTRY",
    "DEFAULT_REGISTRY",
    
    # Voice
    "voice_calls_total",
    "voice_call_duration_seconds",
    "voice_concurrent_calls",
    "voice_call_cost_usd",
    
    # Email
    "email_sent_total",
    "email_delivered_total",
    "email_bounced_total",
    "email_opened_total",
    "email_clicked_total",
    "email_replied_total",
    "email_unsubscribed_total",
    "email_complained_total",
    "email_cost_usd",
    
    # CRM
    "crm_leads_created_total",
    "crm_leads_updated_total",
    "crm_sync_duration_seconds",
    
    # Campaign
    "campaigns_created_total",
    "campaigns_started_total",
    "campaigns_paused_total",
    "campaign_prospects_total",
    "campaign_bookings_total",
    
    # System
    "http_requests_total",
    "http_request_duration_seconds",
    "http_request_size_bytes",
    "http_response_size_bytes",
    
    # Database
    "db_query_duration_seconds",
    "db_connections_active",
    "db_connections_idle",
    
    # Redis
    "redis_operations_total",
    "redis_latency_seconds",
    
    # Resilience
    "circuit_breaker_state",
    "circuit_breaker_failures_total",
    "rate_limiter_requests_total",
    "rate_limiter_tokens",
    "bulkhead_active",
    "bulkhead_queued",
    "bulkhead_rejected_total",
    
    # Models
    "model_requests_total",
    "model_request_duration_seconds",
    "model_tokens_total",
    "model_cost_usd",
    
    # Compliance
    "compliance_opt_outs_total",
    "compliance_dnc_scrubs_total",
    "compliance_consent_checks_total",
    
    # Health
    "health_check_status",
    "health_check_duration_seconds",
    
    # Business
    "revenue_usd",
    "cost_usd",
    "roi_ratio",
    "conversion_rate",
    "cost_per_booking",
    "pipeline_leads",
    "pipeline_value_usd",
    
    # Functions
    "get_workspace_label",
    "record_voice_call",
    "record_email_sent",
    "record_email_event",
    "record_crm_lead",
    "record_campaign_metric",
    "record_model_request",
    "record_compliance_event",
    "record_health_check",
    
    # Middleware
    "metrics_middleware",
    "metrics_endpoint",
    
    # Decorators
    "track_metrics",
    
    # Collector
    "MetricsCollector",
    
    # Server
    "start_metrics_server",
    
    # Utilities
    "get_metrics_summary",
    "export_metrics_prometheus",
    "export_metrics_json",
]
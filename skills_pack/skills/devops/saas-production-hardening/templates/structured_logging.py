"""
Structured Logging with Correlation IDs for SaaS Production Hardening.

Provides:
- JSON-structured logging with consistent fields
- Correlation ID propagation across async boundaries
- Request/response logging with timing
- Security-sensitive field redaction
- Structured audit trail integration
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Callable

# =============================================================================
# CORRELATION ID CONTEXT
# =============================================================================

# Context variable for correlation ID propagation across async boundaries
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Context variable for user/session context
user_context_var: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "user_context", default={}
)

# Context variable for request context
request_context_var: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "request_context", default={}
)


def get_correlation_id() -> str:
    """Get current correlation ID, generating one if not set."""
    cid = correlation_id_var.get()
    if cid is None:
        cid = str(uuid.uuid4())
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set correlation ID for current context."""
    if cid is None:
        cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    correlation_id_var.set(None)


def get_user_context() -> dict:
    """Get current user context."""
    return user_context_var.get()


def set_user_context(user_id: str, email: str = "", roles: list = None, workspace_id: str = "") -> dict:
    """Set user context for current request."""
    context = {
        "user_id": user_id,
        "email": email,
        "roles": roles or [],
        "workspace_id": workspace_id,
    }
    user_context_var.set(context)
    return context


def get_request_context() -> dict:
    """Get current request context."""
    return request_context_var.get()


def set_request_context(
    method: str = "",
    path: str = "",
    query_params: dict = None,
    headers: dict = None,
    client_ip: str = "",
    user_agent: str = "",
) -> dict:
    """Set request context for current request."""
    context = {
        "method": method,
        "path": path,
        "query_params": query_params or {},
        "headers": headers or {},
        "client_ip": client_ip,
        "user_agent": user_agent,
    }
    request_context_var.set(context)
    return context


# =============================================================================
# STRUCTURED LOG FORMATTER
# =============================================================================

# Fields to redact in logs
SENSITIVE_FIELDS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "credential",
    "private_key",
    "secret_key",
    "ssn",
    "social_security",
    "credit_card",
    "card_number",
    "cvv",
    "pin",
    "otp",
    "code",
    "verification",
    "csrf",
    "xsrf",
    "jwt",
    "bearer",
    "basic",
    "digest",
    "hmac",
    "signature",
    "signing_key",
    "encryption_key",
    "decryption_key",
    "master_key",
    "root_key",
    "vault_token",
    "consul_token",
    "etcd_token",
}


def redact_sensitive(data: Any, max_depth: int = 10) -> Any:
    """Recursively redact sensitive fields from data structure."""
    if max_depth <= 0:
        return "<max_depth_exceeded>"
    
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(value, max_depth - 1)
        return redacted
    elif isinstance(data, (list, tuple)):
        return [redact_sensitive(item, max_depth - 1) for item in data]
    elif isinstance(data, set):
        return {redact_sensitive(item, max_depth - 1) for item in data}
    else:
        return data


class StructuredLogFormatter(logging.Formatter):
    """JSON-structured log formatter with correlation IDs and redaction."""
    
    def __init__(self, service_name: str = "saas-app", include_trace: bool = True):
        super().__init__()
        self.service_name = service_name
        self.include_trace = include_trace
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add correlation ID
        cid = correlation_id_var.get()
        if cid:
            log_entry["correlation_id"] = cid
        
        # Add user context
        user_ctx = user_context_var.get()
        if user_ctx:
            log_entry["user"] = {k: v for k, v in user_ctx.items() if k != "roles"}
        
        # Add request context
        req_ctx = request_context_var.get()
        if req_ctx:
            log_entry["request"] = {
                k: v for k, v in req_ctx.items() 
                if k not in ("headers", "query_params") or not any(
                    s in str(v).lower() for s in SENSITIVE_FIELDS
                )
            }
        
        # Add extra fields from record
        if hasattr(record, "extra_fields"):
            log_entry.update(redact_sensitive(record.extra_fields))
        
        # Add exception info
        if record.exc_info and self.include_trace:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "traceback": self.formatException(record.exc_info),
            }
        
        # Add performance timing if present
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code
        
        # Redact any remaining sensitive data
        log_entry = redact_sensitive(log_entry)
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_structured_logging(
    level: str = "INFO",
    service_name: str = "saas-app",
    json_output: bool = True,
    include_trace: bool = True,
) -> logging.Logger:
    """Configure structured logging for the application."""
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if json_output:
        formatter = StructuredLogFormatter(service_name=service_name, include_trace=include_trace)
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Set specific log levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    return root_logger


# =============================================================================
# LOGGING HELPERS
# =============================================================================

@dataclass
class LogContext:
    """Context manager for adding structured fields to logs."""
    extra_fields: dict = field(default_factory=dict)
    
    def __enter__(self):
        self._old_extra = getattr(logging.LogRecord, "extra_fields", {})
        merged = {**self._old_extra, **self.extra_fields}
        logging.LogRecord.extra_fields = merged
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.LogRecord.extra_fields = self._old_extra


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra_fields,
) -> None:
    """Log message with additional structured fields."""
    extra = {"extra_fields": extra_fields}
    logger.log(level, message, extra=extra)


def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **extra_fields,
) -> None:
    """Log HTTP request with standard fields."""
    log_with_context(
        logger,
        logging.INFO,
        f"{method} {path} {status_code}",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **extra_fields,
    )


def log_error(
    logger: logging.Logger,
    message: str,
    error: Exception,
    **extra_fields,
) -> None:
    """Log error with exception info."""
    extra = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        **extra_fields,
    }
    logger.error(message, extra={"extra_fields": extra}, exc_info=True)


def log_audit(
    logger: logging.Logger,
    actor: str,
    action: str,
    resource: str = "",
    resource_id: str = "",
    result: str = "success",
    **extra_fields,
) -> None:
    """Log audit event with standard fields."""
    log_with_context(
        logger,
        logging.INFO,
        f"AUDIT: {actor} {action} {resource}",
        audit=True,
        actor=actor,
        action=action,
        resource=resource,
        resource_id=resource_id,
        result=result,
        **extra_fields,
    )


# =============================================================================
# MIDDLEWARE FOR ASYNC FRAMEWORKS
# =============================================================================

@asynccontextmanager
async def request_logging_context(
    method: str = "",
    path: str = "",
    query_params: dict = None,
    headers: dict = None,
    client_ip: str = "",
    user_agent: str = "",
    user_id: str = "",
    email: str = "",
    roles: list = None,
    workspace_id: str = "",
):
    """
    Context manager for request-scoped logging.
    Sets up correlation ID, user context, and request context.
    """
    # Generate correlation ID
    cid = set_correlation_id()
    
    # Set user context
    if user_id:
        set_user_context(user_id, email, roles or [], workspace_id)
    
    # Set request context
    set_request_context(
        method=method,
        path=path,
        query_params=query_params,
        headers=headers,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    
    start_time = time.perf_counter()
    
    logger = logging.getLogger("saas.request")
    
    try:
        logger.info(
            f"Request started: {method} {path}",
            extra={"extra_fields": {
                "method": method,
                "path": path,
                "client_ip": client_ip,
            }}
        )
        yield
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        log_error(
            logging.getLogger("saas.request"),
            f"Request failed: {method} {path}",
            e,
            method=method,
            path=path,
            duration_ms=duration_ms,
        )
        raise
    else:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Request completed: {method} {path}",
            extra={"extra_fields": {
                "method": method,
                "path": path,
                "duration_ms": duration_ms,
            }}
        )
    finally:
        # Clear contexts
        clear_correlation_id()
        user_context_var.set({})
        request_context_var.set({})


# =============================================================================
# PERFORMANCE TIMING DECORATOR
# =============================================================================

from functools import wraps

def timed(logger: Optional[logging.Logger] = None, level: int = logging.DEBUG):
    """Decorator to log function execution time."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            log = logger or logging.getLogger(func.__module__)
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                log.log(
                    level,
                    f"{func.__name__} completed in {duration_ms:.2f}ms",
                    extra={"extra_fields": {"function": func.__name__, "duration_ms": duration_ms}},
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            log = logger or logging.getLogger(func.__module__)
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                log.log(
                    level,
                    f"{func.__name__} completed in {duration_ms:.2f}ms",
                    extra={"extra_fields": {"function": func.__name__, "duration_ms": duration_ms}},
                )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# =============================================================================
# METRICS COLLECTION
# =============================================================================

class MetricsCollector:
    """Simple in-memory metrics collector with Prometheus-compatible output."""
    
    def __init__(self):
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()
    
    async def increment(self, name: str, value: int = 1, labels: dict = None):
        """Increment a counter."""
        key = self._make_key(name, labels)
        async with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value
    
    async def set_gauge(self, name: str, value: float, labels: dict = None):
        """Set a gauge value."""
        key = self._make_key(name, labels)
        async with self._lock:
            self._gauges[key] = value
    
    async def observe(self, name: str, value: float, labels: dict = None):
        """Observe a histogram value."""
        key = self._make_key(name, labels)
        async with self._lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)
            # Keep only last 1000 observations
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
    
    def _make_key(self, name: str, labels: dict = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    async def get_metrics(self) -> str:
        """Get metrics in Prometheus text format."""
        async with self._lock:
            lines = []
            
            # Counters
            for key, value in self._counters.items():
                lines.append(f"# TYPE {key} counter")
                lines.append(f"{key} {value}")
            
            # Gauges
            for key, value in self._gauges.items():
                lines.append(f"# TYPE {key} gauge")
                lines.append(f"{key} {value}")
            
            # Histograms
            for key, values in self._histograms.items():
                if not values:
                    continue
                lines.append(f"# TYPE {key} histogram")
                lines.append(f'{key}_count {len(values)}')
                lines.append(f'{key}_sum {sum(values):.6f}')
                # Calculate quantiles
                sorted_vals = sorted(values)
                for q in [0.5, 0.9, 0.95, 0.99]:
                    idx = int(len(sorted_vals) * q)
                    lines.append(f'{key}_bucket{{le="{q}"}} {sorted_vals[idx]:.6f}')
                lines.append(f'{key}_bucket{{le="+Inf"}} {len(values)}')
            
            return "\n".join(lines) + "\n"


# Global metrics collector
metrics = MetricsCollector()


# =============================================================================
# REQUEST/RESPONSE LOGGING MIDDLEWARE
# =============================================================================

async def log_http_request(
    request: Any,  # httpx.Request or similar
    response: Any,  # httpx.Response or similar
    duration_ms: float,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Log HTTP request/response pair."""
    log = logger or logging.getLogger("saas.http")
    
    log_with_context(
        log,
        logging.INFO,
        f"HTTP {request.method} {request.url.path}",
        method=request.method,
        path=str(request.url.path),
        status_code=response.status_code,
        duration_ms=duration_ms,
        request_size=len(request.content) if request.content else 0,
        response_size=len(response.content) if hasattr(response, 'content') and response.content else 0,
    )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

AUDIT_LOGGER = logging.getLogger("saas.audit")


def audit_log(
    actor: str,
    action: str,
    resource: str,
    resource_id: str = "",
    result: str = "success",
    inputs: dict = None,
    outputs: dict = None,
    metadata: dict = None,
    correlation_id: str = None,
) -> None:
    """Log audit event with full structured data."""
    audit_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id or get_correlation_id(),
        "actor": actor,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "result": result,
        "inputs": redact_sensitive(inputs or {}),
        "outputs": redact_sensitive(outputs or {}),
        "metadata": metadata or {},
    }
    
    AUDIT_LOGGER.info("AUDIT", extra={"extra_fields": audit_entry})


# =============================================================================
# LOGGING CONFIGURATION FOR DIFFERENT ENVIRONMENTS
# =============================================================================

def configure_logging_for_environment(env: str = "production") -> None:
    """Configure logging based on environment."""
    configs = {
        "development": {
            "level": "DEBUG",
            "json_output": False,
            "include_trace": True,
        },
        "staging": {
            "level": "INFO",
            "json_output": True,
            "include_trace": True,
        },
        "production": {
            "level": "INFO",
            "json_output": True,
            "include_trace": False,  # Don't include full traces in production
        },
        "test": {
            "level": "WARNING",
            "json_output": False,
            "include_trace": True,
        },
    }
    
    config = configs.get(env, configs["production"])
    setup_structured_logging(**config)
#!/usr/bin/env python3
"""Enterprise Secret Broker Module — local-first secret handling.

A stdlib-only, local-first architecture for keeping secrets away from remote
LLM/API calls. The core idea (documented in LOCAL_FIRST_SECRET_ARCHITECTURE.md)
is:

    detect -> substitute -> call model (with placeholders) -> reverse-substitute

so that a raw secret NEVER crosses the wire to a remote model. This module
provides four cooperating components:

* :class:`SecretDetector` — regex + Shannon-entropy detection of API keys,
  tokens, AWS access keys, GitHub tokens, Slack tokens, private keys and
  password assignments inside an arbitrary text blob. Returns structured hits
  with a secret type and character location.

* :class:`PlaceholderSubstituter` — replaces every detected secret with a
  unique reversible placeholder token (``__SECRET_<hash>__``) while keeping a
  reversible ``{placeholder -> secret}`` map. Substitution is deterministic and
  idempotent (redacting an already-redacted blob introduces no new secrets).

* :class:`SecretBroker` — the local-first facade. ``redact()`` returns
  ``{redacted_text, map}``; ``restore()`` reverses it. ``guard_outbound()``
  raises or redacts if a live secret would otherwise be sent to a remote model.

* :class:`OutboundSecretLeakError` — raised by the outbound guard to fail a
  call rather than leak a secret.

All components are stdlib-only (``re``, ``math``, ``hashlib``, ``secrets``,
``dataclasses``) with zero external dependencies.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from enterprise.platform_kernel import HealthStatus, Module, module

logger = logging.getLogger("enterprise.secret_broker")

__version__ = "1.0.0"


# =============================================================================
# Detection
# =============================================================================


@dataclass
class SecretHit:
    """A single secret detection: where it is and what kind it is."""

    type: str
    start: int
    end: int
    value: str
    entropy: float = 0.0

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"SecretHit(type={self.type!r}, span=({self.start},{self.end}), value={self.value!r})"
        )


def _shannon_entropy(data: str) -> float:
    """Compute Shannon entropy (bits per char) of a string."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    for _char in set(data):
        p = data.count(_char) / length
        entropy -= p * math.log2(p)
    return entropy


class SecretDetector:
    """Regex + entropy detection of secrets inside a text blob.

    The detector combines:

    1. **Regex recognisers** for well-known secret formats (OpenAI/Sk- keys,
       AWS access keys, GitHub PATs, Slack tokens, JWT bearer tokens, Stripe
       keys, generic ``KEY=value`` assignment patterns).
    2. **Entropy heuristic** — any bareword of sufficient length (>= threshold)
       whose Shannon entropy exceeds a high bar (strong random character mix) is
       flagged as a high-entropy token (covers formats the regexes miss).

    Detection is entirely local: nothing is ever read off-box.
    """

    # Well-known secret formats. Order matters: longest/most-specific first so
    # a generic later pattern doesn't swallow a more specific one (we pick the
    # leftmost, then longest match per region when assembling the final list).
    _PATTERNS: list[tuple] = [
        # (type, compiled regex)
        ("openai_api_key", re.compile(r"\b(?:sk|sk-[A-Za-z0-9])-[A-Za-z0-9]{20,}\b")),
        ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        (
            "aws_secret_key",
            re.compile(
                r"\b(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*=\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"
            ),
        ),
        ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
        ("github_fine_grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
        ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
        ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
        ("stripe_secret", re.compile(r"\bsk_live_[0-9a-zA-Z]{24,}\b")),
        ("stripe_publishable", re.compile(r"\bpk_live_[0-9a-zA-Z]{24,}\b")),
        (
            "jwt_bearer",
            re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        ),
        ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        (
            "generic_key_value",
            re.compile(
                r"\b(?:api[_-]?key|apikey|token|secret|password|passwd|client[_-]?secret|access[_-]?token)"
                r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+]{12,})['\"]?"
            ),
        ),
        ("ssh_private_key", re.compile(r"\b-----BEGIN OPENSSH PRIVATE KEY-----")),
    ]

    def __init__(
        self,
        min_entropy: float = 3.8,
        entropy_token_min_len: int = 16,
        max_results: int = 1000,
    ) -> None:
        self.min_entropy = min_entropy
        self.entropy_token_min_len = entropy_token_min_len
        self.max_results = max_results

    # -- public API -------------------------------------------------------- #

    def detect(self, text: str) -> list[SecretHit]:
        """Scan ``text`` and return an ordered list of secret hits.

        Hits are sorted by start position (ascending) so a patterns can be
        substituted left-to-right without overlap conflicts.
        """
        if not text:
            return []

        hits: list[SecretHit] = []

        # 1) Regex recognisers.
        for secret_type, pattern in self._PATTERNS:
            for m in pattern.finditer(text):
                value = m.group(0)
                start = m.start()
                end = m.end()
                if m.lastindex:  # capture-group patterns: only the secret value
                    for g in m.groups():
                        if g:
                            value = g
                            start = m.start(m.lastindex)
                            end = m.end(m.lastindex)
                            break
                hits.append(
                    SecretHit(
                        type=secret_type,
                        start=start,
                        end=end,
                        value=value,
                        entropy=_shannon_entropy(value),
                    )
                )

        # 2) Entropy heuristic for bare long high-entropy tokens.
        hits.extend(self._entropy_scan(text))

        # 3) Never treat existing placeholder tokens as fresh secrets — this is
        #    what keeps re-detection (and thus re-substitution) idempotent.
        placeholder_spans = [(pm.start(), pm.end()) for pm in self._PLACEHOLDER_RE.finditer(text)]
        if placeholder_spans:
            hits = [h for h in hits if not self._overlaps_any(h, placeholder_spans)]

        # De-duplicate overlapping hits, keep the most specific / longest, then
        # sort by start position.
        hits = self._dedupe(hits)
        hits.sort(key=lambda h: h.start)

        if len(hits) > self.max_results:
            hits = hits[: self.max_results]
        return hits

    _PLACEHOLDER_RE = re.compile(r"__SECRET_[0-9a-f]{12}__")

    @staticmethod
    def _overlaps_any(hit: SecretHit, spans: list[tuple[int, int]]) -> bool:
        return any(hit.start < e and s < hit.end for s, e in spans)

    def contains_secret(self, text: str) -> bool:
        """Fast boolean: does this blob contain any detected secret?"""
        return bool(self.detect(text))

    # -- internals --------------------------------------------------------- #

    def _entropy_scan(self, text: str) -> list[SecretHit]:
        """Bareword entropy pass: flag long random-looking tokens."""
        hits: list[SecretHit] = []
        # Barewords: alphanumeric runs that may include [-_./+=].
        word_re = re.compile(r"[A-Za-z0-9_\-./+]{16,}")
        for m in word_re.finditer(text):
            word = m.group(0)
            ent = _shannon_entropy(word)
            if ent >= self.min_entropy:
                hits.append(
                    SecretHit(
                        type="high_entropy_token",
                        start=m.start(),
                        end=m.end(),
                        value=word,
                        entropy=ent,
                    )
                )
        return hits

    @staticmethod
    def _dedupe(hits: list[SecretHit]) -> list[SecretHit]:
        """Drop overlapping hits keeping the longest (most specific) one."""
        hits = sorted(hits, key=lambda h: (h.start, -(h.end - h.start)))
        kept: list[SecretHit] = []
        # We want to keep non-overlapping spans. A greedy sweep over spans
        # sorted by start (longest first within same start) picks the maximal
        # non-overlapping set by start order but we then also drop any hit that
        # falls inside an already-kept span.
        for h in hits:
            if any(k.start <= h.start < k.end or h.start <= k.start < h.end for k in kept):
                continue
            kept.append(h)
        return kept


# =============================================================================
# Substitution
# =============================================================================


class PlaceholderSubstituter:
    """Replace detected secrets with unique reversible placeholder tokens.

    Each secret is mapped to a deterministic placeholder of the form
    ``__SECRET_<sha256[0:12]>__`` (the digest is a short hash of the secret
    value, so identical secrets map to identical placeholders — giving us
    idempotency for free). The mapping is stored in a reversible dict exposed
    as the **map** used by :class:`SecretBroker.restore`.
    """

    PREFIX = "__SECRET_"
    SUFFIX = "__"
    _PLACEHOLDER_RE = re.compile(r"__SECRET_[0-9a-f]{12}__")

    def __init__(self, detector: SecretDetector | None = None) -> None:
        self.detector = detector or SecretDetector()
        self._map: dict[str, str] = {}  # placeholder -> secret

    def placeholder_for(self, secret: str) -> str:
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]
        return f"{self.PREFIX}{digest}{self.SUFFIX}"

    def substitute(self, text: str) -> SubstitutionResult:
        """Return a substitute result dataclass.

        Implementation detail: for convenience we reuse ``SecretBroker.redact``'s
        result shape via :class:`SubstitutionResult`.
        """
        passes = 0
        working = text
        placeholder_map: dict[str, str] = {}

        # Iterate until a fixed point: substitution shrinks the surface of
        # secrets (placeholders are not secrets) so this terminates quickly.
        while True:
            hits = self.detector.detect(working)
            if not hits:
                break
            passes += 1
            if passes > 20:  # defensive bound
                break
            # Substitute right-to-left so earlier indices remain valid.
            for h in sorted(hits, key=lambda x: x.start, reverse=True):
                place = self.placeholder_for(h.value)
                working = working[: h.start] + place + working[h.end :]
                placeholder_map[place] = h.value
                self._map[place] = h.value  # persist for internal-map restore()

        return SubstitutionResult(redacted_text=working, map=placeholder_map)

    def is_placeholder(self, token: str) -> bool:
        return bool(self._PLACEHOLDER_RE.fullmatch(token))

    def restore(self, redacted_text: str, mapping: dict[str, str] | None = None) -> str:
        """Reverse the substitution using ``mapping`` (placeholder -> secret).

        If ``mapping`` is ``None`` the substituter's own internal map is used
        (populated during a prior :meth:`substitute` call).
        """
        mapping = mapping if mapping is not None else self._map
        out = redacted_text
        for place, secret in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
            out = out.replace(place, secret)
        return out


@dataclass
class SubstitutionResult:
    """Result of a substitution: the redacted text and its reversible map."""

    redacted_text: str
    map: dict[str, str] = field(default_factory=dict)


# =============================================================================
# Broker facade
# =============================================================================


class OutboundSecretLeakError(RuntimeError):
    """Raised when a live secret would be sent outbound (leak attempt)."""


class SecretBroker:
    """Local-first secret handling facade.

    The canonical flow::

        ```python
        broker = SecretBroker()
        result = broker.redact(user_text)           # {redacted_text, map}
        model_reply = call_model(result["redacted_text"])
        safe_reply = broker.restore(model_reply, result["map"])
        ```

    Because every secret is replaced by a placeholder *before* the text reaches
    the model, no raw secret can ever leak. The broker is:

    * **reversible** — ``restore(redact(t).redacted_text, redact(t).map) == t``.
    * **idempotent** — redacting an already-redacted blob returns the same
      blob (placeholders are not secrets, so re-detection finds nothing new).
    """

    def __init__(
        self,
        detector: SecretDetector | None = None,
        substituter: PlaceholderSubstituter | None = None,
        guard_mode: str = "raise",  # 'raise' | 'redact' | 'off'
    ) -> None:
        self.detector = detector or SecretDetector()
        self.substituter = substituter or PlaceholderSubstituter(self.detector)
        self.guard_mode = guard_mode
        self._guard_count = 0

    # -- redact / restore -------------------------------------------------- #

    def redact(self, text: str) -> dict[str, Any]:
        """Detect + substitute secrets in ``text``.

        Returns ``{"redacted_text": str, "map": {placeholder: secret}}``.
        Idempotent: redacting already-redacted text is a no-op for the text.
        """
        sub = self.substituter.substitute(text)
        return {"redacted_text": sub.redacted_text, "map": dict(sub.map)}

    def restore(self, redacted_text: str, mapping: dict[str, str] | None = None) -> str:
        """Reverse a prior :meth:`redact` using its map.

        Returns the original text (with secrets restored locally).
        """
        return self.substituter.restore(redacted_text, mapping)

    # -- outbound guard ---------------------------------------------------- #

    def detect_outbound(
        self, text: str, known_secrets: dict[str, str] | None = None
    ) -> list[SecretHit]:
        """Find secrets that would be sent outbound.

        ``known_secrets`` is an optional ``{placeholder: secret}`` map (e.g. the
        one returned by :meth:`redact`); any of those raw values found in
        ``text`` is treated as a leak even if the generic detector misses it.
        """
        hits = self.detector.detect(text)
        if known_secrets:
            for secret in known_secrets.values():
                idx = text.find(secret)
                if idx != -1:
                    hits.append(
                        SecretHit(
                            type="known_secret_leak",
                            start=idx,
                            end=idx + len(secret),
                            value=secret,
                            entropy=_shannon_entropy(secret),
                        )
                    )
        return self.detector._dedupe(hits)

    def guard_outbound(
        self,
        text: str,
        known_secrets: dict[str, str] | None = None,
        mode: str | None = None,
    ) -> str:
        """Guard a string destined for a remote model.

        * ``mode="raise"`` (default): raise :class:`OutboundSecretLeakError` if
          any secret is found.
        * ``mode="redact"``: return a redacted copy instead of raising.
        * ``mode="off"``: pass through unchanged.

        Returns the (possibly redacted) outbound text.
        """
        mode = mode or self.guard_mode
        hits = self.detect_outbound(text, known_secrets)
        if not hits or mode == "off":
            return text
        self._guard_count += 1
        if mode == "raise":
            leaked = ", ".join(sorted({h.type for h in hits}))
            msg = f"refusing outbound send: {len(hits)} secret(s) found ({leaked})"
            raise OutboundSecretLeakError(msg)
        # redact mode: strip the secrets (do not send them)
        return self.redact(text)["redacted_text"]

    def assert_clean(self, text: str, known_secrets: dict[str, str] | None = None) -> None:
        """Raise if ``text`` contains a live secret (strict outbound guard)."""
        self.guard_outbound(text, known_secrets, mode="raise")

    @property
    def guarded_count(self) -> int:
        return self._guard_count


# =============================================================================
# Kernel module
# =============================================================================


@module(name="secret_broker", version="1.0.0")
class SecretBrokerModule(Module):
    """Kernel-registered module exposing the SecretBroker to the platform."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._config = config or {}
        self.broker = self._build_broker()

    def _build_broker(self) -> SecretBroker:
        cfg = self._config or {}
        detector_cfg = cfg.get("detector", {}) or {}
        guard_mode = cfg.get("guard_mode", "raise")
        detector = SecretDetector(
            min_entropy=detector_cfg.get("min_entropy", 3.8),
            entropy_token_min_len=detector_cfg.get("entropy_token_min_len", 16),
            max_results=detector_cfg.get("max_results", 1000),
        )
        return SecretBroker(detector=detector, guard_mode=guard_mode)

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        self.broker = self._build_broker()
        self._status = HealthStatus.HEALTHY
        logger.info("Secret Broker Module initialized.")

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        logger.info("Secret Broker Module shutdown complete.")

    # Convenience passthroughs for platform consumers.
    def redact(self, text: str) -> dict[str, Any]:
        return self.broker.redact(text)

    def restore(self, redacted_text: str, mapping: dict[str, str] | None = None) -> str:
        return self.broker.restore(redacted_text, mapping)

    def guard_outbound(
        self,
        text: str,
        known_secrets: dict[str, str] | None = None,
        **kw: Any,  # noqa: ANN401
    ) -> str:
        return self.broker.guard_outbound(text, known_secrets, **kw)

    def detect(self, text: str) -> list[SecretHit]:
        return self.broker.detector.detect(text)

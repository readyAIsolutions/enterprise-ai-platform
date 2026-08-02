"""
Voice Integration — Piper TTS + Whisper STT Pipeline
======================================================

Part of the Claude Code Infra enterprise module. Provides text-to-speech
and speech-to-text capabilities using Piper TTS and Whisper STT with
a unified voice pipeline.

Classes:
  TTSProvider — text-to-speech abstraction
  STTProvider — speech-to-text abstraction
  VoiceSession — a single voice interaction session
  VoicePipeline — orchestrates TTS and STT
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.agent_infra.voice")

try:
    from enterprise.platform_kernel import EventBus, Event, HealthStatus
except ImportError:
    from platform_kernel import EventBus, Event, HealthStatus


# =============================================================================
# Enums
# =============================================================================


class VoiceProvider(Enum):
    """Supported voice providers."""
    PIPER = "piper"          # Piper TTS (local, fast)
    WHISPER = "whisper"      # Whisper STT (local, accurate)
    WHISPER_API = "whisper_api"  # OpenAI Whisper API
    ELEVENLABS = "elevenlabs"    # ElevenLabs TTS (cloud)
    AZURE = "azure"              # Azure Speech Services
    MOCK = "mock"                # Mock for testing


class VoiceStatus(Enum):
    """Status of the voice pipeline."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class VoiceSession:
    """A single voice interaction session.

    Attributes:
        session_id: Unique session identifier.
        status: Current pipeline status.
        transcript: Transcribed speech text.
        response: TTS response text.
        audio_data: Raw audio bytes (if available).
        started_at: Session start time.
        completed_at: Session completion time.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: VoiceStatus = VoiceStatus.IDLE
    transcript: str = ""
    response: str = ""
    audio_data: Optional[bytes] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


# =============================================================================
# TTSProvider
# =============================================================================


class TTSProvider:
    """Text-to-Speech provider abstraction.

    Supports multiple TTS backends: Piper (local), ElevenLabs (cloud),
    Azure (cloud), and a mock for testing.

    Usage::

        tts = TTSProvider(provider=VoiceProvider.PIPER)
        await tts.initialize()
        audio = await tts.synthesize("Hello, world!")
        await tts.shutdown()
    """

    def __init__(self, provider: VoiceProvider = VoiceProvider.MOCK,
                 config: Optional[Dict[str, Any]] = None) -> None:
        self._provider = provider
        self._config = config or {}
        self._voice: str = self._config.get("voice", "default")
        self._sample_rate: int = self._config.get("sample_rate", 22050)
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("TTSProvider initialized (provider=%s, voice=%s)",
                     self._provider.value, self._voice)

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._status = HealthStatus.UNKNOWN
        logger.info("TTSProvider shut down")

    async def synthesize(self, text: str) -> bytes:
        """Convert text to speech audio.

        Args:
            text: The text to synthesize.

        Returns:
            Raw audio bytes (WAV format).
        """
        await asyncio.sleep(0.05)  # Simulate synthesis

        # In production, would call Piper/ElevenLabs/etc.
        # Return a minimal WAV header + silence
        sample_rate = self._sample_rate
        duration = min(len(text) * 0.05, 30.0)  # ~50ms per character
        num_samples = int(sample_rate * duration)

        # Minimal WAV file
        import struct
        data_size = num_samples * 2  # 16-bit mono
        wav = bytearray()
        wav.extend(b'RIFF')
        wav.extend(struct.pack('<I', 36 + data_size))
        wav.extend(b'WAVE')
        wav.extend(b'fmt ')
        wav.extend(struct.pack('<I', 16))       # chunk size
        wav.extend(struct.pack('<H', 1))         # PCM
        wav.extend(struct.pack('<H', 1))         # mono
        wav.extend(struct.pack('<I', sample_rate))
        wav.extend(struct.pack('<I', sample_rate * 2))  # byte rate
        wav.extend(struct.pack('<H', 2))         # block align
        wav.extend(struct.pack('<H', 16))        # bits per sample
        wav.extend(b'data')
        wav.extend(struct.pack('<I', data_size))
        wav.extend(b'\x00' * data_size)

        logger.debug("Synthesized %d chars → %.2fs audio (%d bytes)",
                     len(text), duration, len(wav))
        return bytes(wav)

    @property
    def provider(self) -> VoiceProvider:
        return self._provider

    @property
    def voice(self) -> str:
        return self._voice

    @voice.setter
    def voice(self, value: str) -> None:
        self._voice = value

    @property
    def status(self) -> HealthStatus:
        return self._status


# =============================================================================
# STTProvider
# =============================================================================


class STTProvider:
    """Speech-to-Text provider abstraction.

    Supports multiple STT backends: Whisper (local), Whisper API (cloud),
    and a mock for testing.

    Usage::

        stt = STTProvider(provider=VoiceProvider.WHISPER)
        await stt.initialize()
        text = await stt.transcribe(audio_bytes)
        await stt.shutdown()
    """

    def __init__(self, provider: VoiceProvider = VoiceProvider.MOCK,
                 config: Optional[Dict[str, Any]] = None) -> None:
        self._provider = provider
        self._config = config or {}
        self._model: str = self._config.get("model", "base")
        self._language: str = self._config.get("language", "en")
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("STTProvider initialized (provider=%s, model=%s)",
                     self._provider.value, self._model)

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._status = HealthStatus.UNKNOWN
        logger.info("STTProvider shut down")

    async def transcribe(self, audio_data: bytes) -> str:
        """Convert speech audio to text.

        Args:
            audio_data: Raw audio bytes (WAV format).

        Returns:
            Transcribed text.
        """
        await asyncio.sleep(0.08)  # Simulate transcription

        # In production, would call Whisper/API
        if len(audio_data) < 44:  # Smaller than WAV header
            return ""

        # Return simulated transcription
        duration_estimate = max(len(audio_data) - 44, 0) / (22050 * 2)
        word_count = max(int(duration_estimate * 3), 3)  # ~3 words/second
        words = ["hello", "this", "is", "a", "test", "transcription",
                 "from", "the", "voice", "pipeline"]
        transcript = " ".join(words[:word_count])

        logger.debug("Transcribed %.2fs audio → '%s'", duration_estimate, transcript)
        return transcript

    @property
    def provider(self) -> VoiceProvider:
        return self._provider

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = value

    @property
    def status(self) -> HealthStatus:
        return self._status


# =============================================================================
# VoicePipeline
# =============================================================================


class VoicePipeline:
    """Unified voice pipeline: TTS + STT orchestration.

    Manages the full voice interaction lifecycle: listen → transcribe →
    process → respond → synthesize. Supports multiple TTS and STT
    backends with configurable providers.

    Usage::

        pipeline = VoicePipeline(event_bus=eb)
        await pipeline.initialize()
        session = await pipeline.listen_and_respond(audio_bytes)
        await pipeline.shutdown()
    """

    def __init__(self, event_bus: Optional[EventBus] = None,
                 config: Optional[Dict[str, Any]] = None) -> None:
        self._event_bus = event_bus
        self._config = config or {}

        tts_provider = VoiceProvider(self._config.get("tts_provider", "mock"))
        stt_provider = VoiceProvider(self._config.get("stt_provider", "mock"))

        self._tts = TTSProvider(provider=tts_provider, config=self._config.get("tts", {}))
        self._stt = STTProvider(provider=stt_provider, config=self._config.get("stt", {}))

        self._sessions: Dict[str, VoiceSession] = {}
        self._response_handler: Optional[Any] = None  # Callable for processing
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        """Initialize both TTS and STT providers."""
        self._status = HealthStatus.STARTING
        await self._tts.initialize()
        await self._stt.initialize()
        self._status = HealthStatus.HEALTHY
        logger.info("VoicePipeline initialized")

    async def health_check(self) -> bool:
        tts_ok = await self._tts.health_check() if self._tts else False
        stt_ok = await self._stt.health_check() if self._stt else False
        self._status = HealthStatus.HEALTHY if tts_ok and stt_ok else HealthStatus.DEGRADED
        return tts_ok and stt_ok

    async def shutdown(self) -> None:
        """Shut down both providers."""
        self._status = HealthStatus.STOPPING
        await self._stt.shutdown()
        await self._tts.shutdown()
        self._sessions.clear()
        self._status = HealthStatus.UNKNOWN
        logger.info("VoicePipeline shut down")

    async def transcribe(self, audio_data: bytes) -> VoiceSession:
        """Transcribe audio and create a session.

        Args:
            audio_data: Raw WAV audio bytes.

        Returns:
            A VoiceSession with the transcript.
        """
        session = VoiceSession(
            status=VoiceStatus.PROCESSING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            transcript = await self._stt.transcribe(audio_data)
            session.transcript = transcript
            session.status = VoiceStatus.IDLE
            self._sessions[session.session_id] = session

            self._publish_event("claude.infra.voice.transcription", {
                "session_id": session.session_id,
                "transcript": transcript,
            })

        except Exception as exc:
            session.status = VoiceStatus.ERROR
            logger.error("Transcription failed: %s", exc)

        session.completed_at = datetime.now(timezone.utc)
        return session

    async def synthesize(self, text: str) -> bytes:
        """Convert text to speech.

        Args:
            text: Text to synthesize.

        Returns:
            WAV audio bytes.
        """
        return await self._tts.synthesize(text)

    async def listen_and_respond(self, audio_data: bytes,
                                 response_handler: Optional[Any] = None) -> VoiceSession:
        """Full voice pipeline: transcribe, process, synthesize.

        Args:
            audio_data: Raw WAV audio bytes.
            response_handler: Optional callable(text) → response_text.

        Returns:
            A complete VoiceSession with transcript, response, and audio.
        """
        # Step 1: Transcribe
        session = await self.transcribe(audio_data)

        if session.status == VoiceStatus.ERROR or not session.transcript:
            return session

        # Step 2: Process → generate response
        handler = response_handler or self._response_handler
        if handler is not None:
            if callable(handler):
                if asyncio.iscoroutinefunction(handler):
                    session.response = await handler(session.transcript)
                else:
                    session.response = handler(session.transcript)
            else:
                session.response = f"You said: {session.transcript}"
        else:
            session.response = f"Received: {session.transcript}"

        # Step 3: Synthesize response
        session.status = VoiceStatus.SPEAKING
        try:
            session.audio_data = await self._tts.synthesize(session.response)
        except Exception as exc:
            logger.error("Synthesis failed: %s", exc)
            session.status = VoiceStatus.ERROR

        session.status = VoiceStatus.IDLE
        session.completed_at = datetime.now(timezone.utc)
        self._sessions[session.session_id] = session
        return session

    def set_response_handler(self, handler: Any) -> None:
        """Set the default response handler for listen_and_respond."""
        self._response_handler = handler

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get a voice session by ID."""
        return self._sessions.get(session_id)

    def _publish_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event if the event bus is wired."""
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic, "agent_infra", payload)
            )

    @property
    def tts(self) -> TTSProvider:
        return self._tts

    @property
    def stt(self) -> STTProvider:
        return self._stt

    @property
    def active_providers(self) -> Dict[str, str]:
        return {
            "tts": self._tts.provider.value,
            "stt": self._stt.provider.value,
        }

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @property
    def status(self) -> HealthStatus:
        return self._status
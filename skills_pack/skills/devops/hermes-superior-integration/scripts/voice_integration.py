#!/usr/bin/env python3
"""
Voice Integration - TTS/STT for Hermes
Superior to Claude Code's lack of voice support
"""

import asyncio
import os
import tempfile
import subprocess
from typing import Optional, AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator


@dataclass
class VoiceConfig:
    """Configuration for voice engines."""
    # TTS
    tts_engine: str = "piper"  # piper, espeak, edge-tts, elevenlabs
    piper_model: str = "en_US-lessac-medium"
    piper_speaker: int = 0
    edge_voice: str = "en-US-AriaNeural"
    elevenlabs_voice_id: str = ""
    elevenlabs_api_key: str = ""
    
    # STT
    stt_engine: str = "whisper"  # whisper, vosk, google
    whisper_model: str = "base"  # tiny, base, small, medium, large
    whisper_device: str = "cpu"  # cpu, cuda
    vosk_model_path: str = ""
    
    # Audio
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024


class VoiceManager:
    """Manage TTS and STT for Hermes."""
    
    def __init__(self, config: VoiceConfig = None):
        self.config = config or VoiceConfig()
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check which engines are available."""
        self.available_tts = []
        self.available_stt = []
        
        # Check Piper
        try:
            subprocess.run(["piper", "--help"], capture_output=True, check=True)
            self.available_tts.append("piper")
        except:
            pass
        
        # Check espeak
        try:
            subprocess.run(["espeak", "--version"], capture_output=True, check=True)
            self.available_tts.append("espeak")
        except:
            pass
        
        # Check edge-tts
        try:
            import edge_tts
            self.available_tts.append("edge-tts")
        except:
            pass
        
        # Check Whisper
        try:
            import whisper
            self.available_stt.append("whisper")
        except:
            pass
        
        # Check Vosk
        try:
            import vosk
            self.available_stt.append("vosk")
        except:
            pass
    
    # =========================================================================
    # TEXT TO SPEECH
    # =========================================================================
    
    async def speak(self, text: str, output_file: Optional[str] = None) -> str:
        """Convert text to speech and play/save."""
        engine = self.config.tts_engine
        
        if engine not in self.available_tts:
            # Fallback to first available
            if self.available_tts:
                engine = self.available_tts[0]
            else:
                raise RuntimeError("No TTS engine available")
        
        if output_file is None:
            output_file = tempfile.mktemp(suffix=".wav")
        
        if engine == "piper":
            await self._piper_tts(text, output_file)
        elif engine == "edge-tts":
            await self._edge_tts(text, output_file)
        elif engine == "espeak":
            await self._espeak_tts(text, output_file)
        elif engine == "elevenlabs":
            await self._elevenlabs_tts(text, output_file)
        
        return output_file
    
    async def _piper_tts(self, text: str, output_file: str):
        """Piper TTS - fast, local, high quality."""
        cmd = [
            "piper",
            "--model", self.config.piper_model,
            "--speaker", str(self.config.piper_speaker),
            "--output_file", output_file
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate(input=text.encode())
        if proc.returncode != 0:
            raise RuntimeError(f"Piper failed: {proc.returncode}")
    
    async def _edge_tts(self, text: str, output_file: str):
        """Microsoft Edge TTS - cloud, high quality."""
        import edge_tts
        communicate = edge_tts.Communicate(text, self.config.edge_voice)
        await communicate.save(output_file)
    
    async def _espeak_tts(self, text: str, output_file: str):
        """eSpeak - basic, always available."""
        cmd = [
            "espeak",
            "-w", output_file,
            "-s", "150",  # speed
            "-v", "en+f3",  # voice
            text
        ]
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()
    
    async def _elevenlabs_tts(self, text: str, output_file: str):
        """ElevenLabs - premium cloud TTS."""
        import aiohttp
        
        if not self.config.elevenlabs_api_key:
            raise RuntimeError("ElevenLabs API key not configured")
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.config.elevenlabs_api_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"ElevenLabs error: {resp.status}")
                with open(output_file, "wb") as f:
                    f.write(await resp.read())
    
    async def speak_streaming(self, text: str) -> AsyncIterator[bytes]:
        """Stream audio chunks for real-time playback."""
        # Use edge-tts for streaming
        import edge_tts
        communicate = edge_tts.Communicate(text, self.config.edge_voice)
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    
    # =========================================================================
    # SPEECH TO TEXT
    # =========================================================================
    
    async def transcribe(self, audio_file: str) -> str:
        """Transcribe audio file to text."""
        engine = self.config.stt_engine
        
        if engine not in self.available_stt:
            if self.available_stt:
                engine = self.available_stt[0]
            else:
                raise RuntimeError("No STT engine available")
        
        if engine == "whisper":
            return await self._whisper_stt(audio_file)
        elif engine == "vosk":
            return await self._vosk_stt(audio_file)
        elif engine == "google":
            return await self._google_stt(audio_file)
    
    async def _whisper_stt(self, audio_file: str) -> str:
        """Whisper STT - local, accurate."""
        import whisper
        
        model = whisper.load_model(self.config.whisper_model, device=self.config.whisper_device)
        result = model.transcribe(audio_file)
        return result["text"]
    
    async def _vosk_stt(self, audio_file: str) -> str:
        """Vosk STT - offline, lightweight."""
        import vosk
        import wave
        import json
        
        if not self.config.vosk_model_path:
            raise RuntimeError("Vosk model path not configured")
        
        model = vosk.Model(self.config.vosk_model_path)
        rec = vosk.KaldiRecognizer(model, self.config.sample_rate)
        
        with wave.open(audio_file, "rb") as wf:
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)
        
        result = json.loads(rec.FinalResult())
        return result.get("text", "")
    
    async def _google_stt(self, audio_file: str) -> str:
        """Google Cloud STT - cloud, accurate."""
        from google.cloud import speech
        
        client = speech.SpeechClient()
        
        with open(audio_file, "rb") as f:
            content = f.read()
        
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.config.sample_rate,
            language_code="en-US"
        )
        
        response = client.recognize(config=config, audio=audio)
        return " ".join(r.alternatives[0].transcript for r in response.results)
    
    # =========================================================================
    # REAL-TIME AUDIO
    # =========================================================================
    
    async def record_audio(self, duration: float = 5.0) -> str:
        """Record audio from microphone."""
        import sounddevice as sd
        import soundfile as sf
        
        output_file = tempfile.mktemp(suffix=".wav")
        
        recording = sd.rec(
            int(duration * self.config.sample_rate),
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype='int16'
        )
        sd.wait()
        sf.write(output_file, recording, self.config.sample_rate)
        
        return output_file
    
    async def listen_continuous(self, callback, silence_threshold: float = 0.01, silence_duration: float = 1.0):
        """Continuous listening with voice activity detection."""
        import sounddevice as sd
        import numpy as np
        
        chunk_size = int(self.config.sample_rate * 0.1)  # 100ms chunks
        silence_chunks = int(silence_duration / 0.1)
        
        recording = False
        buffer = []
        silence_count = 0
        
        def audio_callback(indata, frames, time, status):
            nonlocal recording, buffer, silence_count
            
            volume = np.abs(indata).mean()
            
            if volume > silence_threshold:
                if not recording:
                    recording = True
                    buffer = []
                buffer.append(indata.copy())
                silence_count = 0
            elif recording:
                silence_count += 1
                buffer.append(indata.copy())
                if silence_count >= silence_chunks:
                    # Process recorded audio
                    audio_data = np.concatenate(buffer)
                    # Save and transcribe
                    import soundfile as sf
                    temp_file = tempfile.mktemp(suffix=".wav")
                    sf.write(temp_file, audio_data, self.config.sample_rate)
                    
                    asyncio.create_task(self._process_recording(temp_file, callback))
                    
                    recording = False
                    buffer = []
                    silence_count = 0
        
        with sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            callback=audio_callback,
            blocksize=chunk_size
        ):
            while True:
                await asyncio.sleep(0.1)
    
    async def _process_recording(self, audio_file: str, callback):
        """Process recorded audio."""
        try:
            text = await self.transcribe(audio_file)
            if text.strip():
                await callback(text)
        finally:
            os.unlink(audio_file)


# =============================================================================
# HERMES INTEGRATION
# =============================================================================

class HermesVoice:
    """Voice integration for Hermes agent."""
    
    def __init__(self, config: VoiceConfig = None):
        self.voice = VoiceManager(config)
        self.listening = False
    
    async def say(self, text: str):
        """Speak text."""
        await self.voice.speak(text)
    
    async def listen(self, duration: float = 5.0) -> str:
        """Listen for specified duration."""
        audio_file = await self.voice.record_audio(duration)
        try:
            return await self.voice.transcribe(audio_file)
        finally:
            os.unlink(audio_file)
    
    async def listen_continuous(self, callback):
        """Continuous listening with VAD."""
        self.listening = True
        await self.voice.listen_continuous(callback)
    
    def stop_listening(self):
        self.listening = False


# =============================================================================
# USAGE
# =============================================================================

async def demo():
    """Demo voice capabilities."""
    config = VoiceConfig(
        tts_engine="piper",
        stt_engine="whisper",
        piper_model="en_US-lessac-medium"
    )
    
    voice = HermesVoice(config)
    
    # Test TTS
    print("Testing TTS...")
    await voice.say("Hello! This is Hermes with voice support.")
    
    # Test STT (requires microphone)
    print("Listening for 5 seconds...")
    text = await voice.listen(5.0)
    print(f"You said: {text}")


if __name__ == "__main__":
    asyncio.run(demo())
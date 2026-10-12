# app/components/stt/component.py

import asyncio
import logging
from typing import AsyncGenerator, Optional

import numpy as np

from app.components.base import BaseSTT
from config.config import settings

logger = logging.getLogger(__name__)


class FunASRSTT(BaseSTT):
    """基于 FunASR Paraformer Online 的流式/非流式 STT"""

    def __init__(self, config=None):
        super().__init__(config or settings.stt)
        self._model = None
        self._cache: dict = {}
        self._audio_buffer = np.array([], dtype=np.float32)
        self._streaming_active = False
        cfg = self.config
        self.sample_rate = getattr(cfg, "sample_rate", 16000)
        chunk_size = getattr(cfg, "chunk_size", None) or [0, 10, 5]
        self.chunk_size = chunk_size
        self._chunk_stride = chunk_size[1] * 960

    async def startup(self) -> None:
        from funasr import AutoModel

        cfg = self.config
        model_id = getattr(cfg, "model_id", "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online")
        device = getattr(cfg, "device", "cpu")

        def _load():
            self._model = AutoModel(
                model=model_id,
                device=device,
                disable_update=True,
            )

        await asyncio.to_thread(_load)
        self._ready = True
        logger.info("FunASRSTT ready (model=%s, device=%s).", model_id, device)

    async def teardown(self) -> None:
        del self._model
        self._model = None
        self._cache = {}
        self._audio_buffer = np.array([], dtype=np.float32)
        self._streaming_active = False
        self._ready = False

    def _bytes_to_float32(self, audio_data: bytes) -> np.ndarray:
        return np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    def _sync_generate(self, speech: np.ndarray, is_final: bool, cache: dict) -> str:
        result = self._model.generate(
            input=speech,
            cache=cache,
            is_final=is_final,
            chunk_size=self.chunk_size,
        )
        if result and "text" in result[0]:
            return (result[0]["text"] or "").strip()
        return ""

    # ── BaseSTT async interface ──────────────────

    async def transcribe(self, audio_data: bytes) -> str:
        if not audio_data:
            return ""
        speech = self._bytes_to_float32(audio_data)
        if speech.size == 0:
            return ""
        return await asyncio.to_thread(self._sync_generate, speech, True, {})

    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
    ) -> AsyncGenerator[str, None]:
        self._streaming_active = True
        self._cache = {}
        self._audio_buffer = np.array([], dtype=np.float32)

        async for audio_frame in audio_stream:
            if not audio_frame:
                continue
            frame = self._bytes_to_float32(audio_frame)
            self._audio_buffer = np.concatenate([self._audio_buffer, frame])

            while self._audio_buffer.size >= self._chunk_stride:
                chunk = self._audio_buffer[:self._chunk_stride]
                self._audio_buffer = self._audio_buffer[self._chunk_stride:]
                text = await asyncio.to_thread(self._sync_generate, chunk, False, self._cache)
                if text:
                    yield text

        # flush remaining
        if self._audio_buffer.size > 0:
            text = await asyncio.to_thread(
                self._sync_generate, self._audio_buffer, True, self._cache
            )
            if text:
                yield text

        self._streaming_active = False
        self._cache = {}

    async def force_finalize(self) -> str:
        if not self._streaming_active:
            return ""
        text = await asyncio.to_thread(
            self._sync_generate, np.array([], dtype=np.float32), True, self._cache
        )
        self._cache = {}
        return text

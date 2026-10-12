# app/components/tts/component.py

import io
import os
import asyncio
import logging
from typing import AsyncGenerator, Optional

import numpy as np

from app.components.base import BaseTTS
from app.components.utils import sentence_buffer
from config.config import settings

logger = logging.getLogger(__name__)


class EdgeTTS(BaseTTS):
    """基于微软 Edge 接口的在线 TTS"""

    def __init__(self, config=None):
        super().__init__(config or settings.tts)
        self.voice = getattr(self.config, "voice", "zh-CN-XiaoxiaoNeural")
        self.proxy_url = os.environ.get("https_proxy") or getattr(self.config, "proxy", None)

    async def startup(self) -> None:
        self._ready = True
        logger.info("EdgeTTS ready (voice=%s).", self.voice)

    async def teardown(self) -> None:
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=self.voice, proxy=self.proxy_url)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        return audio_bytes

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in sentence_buffer(text_stream):
            pcm = await self.synthesize(sentence)
            if pcm:
                yield pcm


class KokoroTTS(BaseTTS):
    """基于 Kokoro-82M 的本地轻量化 TTS"""

    def __init__(self, config=None):
        super().__init__(config or settings.tts)
        self.pipeline = None
        self.voice = getattr(self.config, "voice", "zf_xiaoxiao")

    async def startup(self) -> None:
        from kokoro import KPipeline

        def _load():
            self.pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
            list(self.pipeline("预热完成。", voice=self.voice, speed=1.0))

        await asyncio.to_thread(_load)
        self._ready = True
        logger.info("KokoroTTS ready.")

    async def teardown(self) -> None:
        del self.pipeline
        self.pipeline = None
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        def _infer():
            gen = self.pipeline(text, voice=self.voice, speed=1.0)
            for _, _, audio in gen:
                return audio.tobytes()
            return b""

        return await asyncio.to_thread(_infer)

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in sentence_buffer(text_stream):
            audio = await self.synthesize(sentence)
            if audio:
                yield audio


class QwenTTS(BaseTTS):
    """基于 Qwen3-TTS 的本地高拟真 TTS"""

    def __init__(self, config=None):
        super().__init__(config or settings.tts)
        self.model = None

    async def startup(self) -> None:
        import torch
        import torchaudio
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel

        torchaudio.load = lambda f, *a, **kw: (
            torch.from_numpy(sf.read(f)[0]).float().unsqueeze(0),
            sf.read(f)[1],
        )

        def _load():
            self.model = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                device_map=getattr(self.config, "device", "cpu"),
                dtype=torch.float32,
            )
            torch.set_num_threads(8)
            self.model.generate_custom_voice(
                text="预热。", language="Chinese", speaker="Vivian", instruct=""
            )

        await asyncio.to_thread(_load)
        self._ready = True
        logger.info("QwenTTS ready.")

    async def teardown(self) -> None:
        del self.model
        self.model = None
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        def _infer():
            wavs, _ = self.model.generate_custom_voice(
                text=text, language="Chinese", speaker="Vivian", instruct=""
            )
            return wavs[0].tobytes()

        return await asyncio.to_thread(_infer)

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in sentence_buffer(text_stream):
            audio = await self.synthesize(sentence)
            if audio:
                yield audio


class CosyVoiceTTS(BaseTTS):
    """阿里 CosyVoice 语音大模型 TTS"""

    def __init__(self, config=None):
        super().__init__(config or settings.tts)
        self.cosyvoice = None
        self.default_spk = "中文女"

    async def startup(self) -> None:
        from cosyvoice.cli.cosyvoice import CosyVoice

        def _load():
            model_path = getattr(self.config, "model_id", "iic/CosyVoice-300M")
            self.cosyvoice = CosyVoice(model_path)

        await asyncio.to_thread(_load)
        self._ready = True
        logger.info("CosyVoiceTTS ready.")

    async def teardown(self) -> None:
        del self.cosyvoice
        self.cosyvoice = None
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        import torchaudio

        def _infer():
            output = self.cosyvoice.inference_sft(text, self.default_spk)
            audio_tensor = output['tts_speech']
            buf = io.BytesIO()
            torchaudio.save(buf, audio_tensor, 22050, format="wav")
            return buf.getvalue()

        return await asyncio.to_thread(_infer)

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in sentence_buffer(text_stream):
            audio = await self.synthesize(sentence)
            if audio:
                yield audio


class CloudTTS(BaseTTS):
    """云端 TTS API (OpenAI 兼容 v1/audio/speech 接口)"""

    def __init__(self, config=None):
        super().__init__(config or settings.tts)
        self.client = None
        self.default_voice = "alloy"

    async def startup(self) -> None:
        from openai import AsyncOpenAI

        cfg = self.config
        self.client = AsyncOpenAI(
            api_key=cfg.cloud_apikey or "sk-placeholder",
            base_url=cfg.cloud_url,
        )
        self._ready = True
        logger.info("CloudTTS ready.")

    async def teardown(self) -> None:
        self.client = None
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        response = await self.client.audio.speech.create(
            model="tts-1",
            voice=self.default_voice,
            input=text,
            response_format="mp3",
        )
        return response.read()

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in sentence_buffer(text_stream):
            audio = await self.synthesize(sentence)
            if audio:
                yield audio

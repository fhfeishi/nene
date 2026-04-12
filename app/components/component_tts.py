# app/components/component_tts.py 

import io
import os 
import asyncio 
import logging 
import numpy as np 
from typing import AsyncGenerator, Optional

from config.config import settings 
from app.components.base import BaseTTS 


# ─────────────────────────────────────────────
# 辅助工具：流式标点分句器
# ─────────────────────────────────────────────
async def _sentence_buffer(text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """
    接收 LLM 逐字输出的文本流，按标点符号组装成完整的句子再 yield，
    保证 TTS 引擎能读出正常的语调。
    """
    buffer = ""
    punctuation_pattern = re.compile(r'([。？！；\?\!;]+)') 
    
    async for chunk in text_stream:
        buffer += chunk
        parts = punctuation_pattern.split(buffer)
        if len(parts) > 1:
            buffer = parts.pop()  # 剩余未完结的部分放回 buffer
            for i in range(0, len(parts), 2):
                if i + 1 < len(parts):
                    sentence = parts[i] + parts[i+1]
                    if sentence.strip():
                        yield sentence.strip()
    
    if buffer.strip():
        yield buffer.strip()
        

class KokoroTTS(BaseTTS):
    """基于 Kokoro-82M 的本地轻量化 TTS"""
    
    def __init__(self, config: settings) -> None:
        super().__init__(config)
        self.pipeline = None
        
        # 直接从你的 config 中读取，若没有则给默认值
        self.cfg = settings.tts 
        self.voice = getattr(self.cfg, "voice", "zf_xiaoxiao")

    async def setup(self) -> None:
        self.logger.info("Setting up KokoroTTS...")
        from kokoro import KPipeline
        import warnings
        warnings.filterwarnings("ignore")
        
        def _load():
            self.pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
            list(self.pipeline("预热完成。", voice=self.voice, speed=1.0))
            
        await asyncio.to_thread(_load)
        self._ready = True
        self.logger.info("KokoroTTS setup complete.")

    async def teardown(self) -> None:
        self.logger.info("Tearing down KokoroTTS...")
        del self.pipeline
        self.pipeline = None
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        def sync_infer():
            generator = self.pipeline(text, voice=self.voice, speed=1.0)
            for _, _, audio in generator:
                return audio.tobytes()   # numpy float32 数组转为 bytes
            return b""
        return await asyncio.to_thread(sync_infer)

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in _sentence_buffer(text_stream):
            audio_bytes = await self.synthesize(sentence)
            if audio_bytes:
                yield audio_bytes
    


class EdgeTTS(BaseTTS):
    """基于微软 Edge 接口的在线 TTS"""
    
    def __init__(self, config: settings) -> None:
        super().__init__()
        self.cfg = settings.tts 
        self.voice = getattr(self.cfg "voice", "zh-CN-XiaoxiaoNeural")
        self.proxy_url = os.environ.get("https_proxy") or getattr(self.cfg, "proxy", "http://127.0.0.1:7890")

    async def startup(self) -> None:
        self.logger.info(f"Setting up EdgeTTS... Using proxy: {self.proxy_url}")
        self._ready = True

    async def teardown(self) -> None:
        self.logger.info("Tearing down EdgeTTS...")
        self._ready = False

    async def _decode_to_pcm(self, audio_bytes: bytes) -> bytes:
        """将 EdgeTTS 下发的 MP3 解码为项目通用的 Float32 PCM"""
        if not audio_bytes:
            return b""
        from pydub import AudioSegment
        
        def _decode():
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio_segment = audio_segment.set_frame_rate(16000).set_channels(1) # 建议取自 config.sample_rate
            samples = np.array(audio_segment.get_array_of_samples()).astype(np.float32)
            samples /= np.iinfo(audio_segment.array_type).max
            return samples.tobytes()
            
        return await asyncio.to_thread(_decode)

    async def synthesize(self, text: str) -> bytes:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice=self.voice, proxy=self.proxy_url)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
                
        return await self._decode_to_pcm(audio_bytes)

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in _sentence_buffer(text_stream):
            pcm_bytes = await self.synthesize(sentence)
            if pcm_bytes:
                yield pcm_bytes


class QwenTTS(BaseTTS):
    """基于 Qwen3-TTS 的本地高拟真 TTS"""
    
    def __init__(self, config: settings) -> None:
        super().__init__()
        self.model = None

    async def startup(self) -> None:
        self.logger.info("Setting up Qwen3-TTS...")
        
        def _load():
            import torch
            import torchaudio
            import soundfile as sf
            from qwen_tts import Qwen3TTSModel
            
            # 处理 Ubuntu ffmpeg 冲突补丁
            torchaudio.load = lambda f, *a, **kw: (torch.from_numpy(sf.read(f)[0]).float().unsqueeze(0), sf.read(f)[1])
            
            self.model = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                device_map=getattr(self.config, "device", "cpu"),
                dtype=torch.float32
            )
            torch.set_num_threads(8)
            self.model.generate_custom_voice(text="预热。", language="Chinese", speaker="Vivian", instruct="")
            
        await asyncio.to_thread(_load)
        self._ready = True
        self.logger.info("Qwen3-TTS setup complete.")

    async def teardown(self) -> None:
        self.logger.info("Tearing down Qwen3-TTS...")
        del self.model
        self.model = None
        self._ready = False

    async def synthesize(self, text: str) -> bytes:
        def sync_infer():
            wavs, _ = self.model.generate_custom_voice(
                text=text, language="Chinese", speaker="Vivian", instruct=""
            )
            return wavs[0].tobytes()
            
        return await asyncio.to_thread(sync_infer)

    async def synthesize_stream(self, text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        async for sentence in _sentence_buffer(text_stream):
            audio_bytes = await self.synthesize(sentence)
            if audio_bytes:
                yield audio_bytes  






if __name__ == "__main__":
    
    edge = EdgeTTS()
    
    kokoro = KokoroTTS()
    
    qwen = QwenTTS()

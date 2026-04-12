# scripts/llm_tts_grpc/tts_server.py
# gRPC TTS 微服务
# 启动方式: python tts_server.py
# coding=utf-8
"""
独立的 TTS gRPC 服务进程。
- 管理所有 TTS 引擎的生命周期（懒加载 + 缓存）
- 通过 gRPC Server Streaming 向 Gateway 传输 PCM 音频块
- 与 FastAPI Gateway 完全解耦，可独立扩展/重启
"""
import asyncio
import io
import os
import sys
import time
from typing import AsyncIterator, Dict, Optional

import grpc
import numpy as np
import torch
from grpc import aio as grpc_aio
from loguru import logger

# 确保 proto 生成的模块可被找到（与本文件同目录下的 generated/）
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))
from generated import tts_pb2
from generated import  tts_pb2_grpc

# ==========================================
# 配置
# ==========================================
GRPC_PORT = 50051
AUDIO_SAMPLE_RATE = 24000

# WSL2 下通过 Clash 代理访问外网（EdgeTTS 需要）
# 如果 TUN 模式失效，显式走 HTTP 代理
PROXY_URL = "http://127.0.0.1:7890"


# ==========================================
# TTS 引擎实现
# ==========================================
class BaseTTS:
    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        raise NotImplementedError


class KokoroTTS(BaseTTS):
    def __init__(self):
        logger.info("Initializing KokoroTTS...")
        import warnings
        warnings.filterwarnings("ignore")
        from kokoro import KPipeline
        self.pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
        self.voice = "zf_xiaoxiao"
        # 预热：首次推理会编译 JIT，提前做掉
        list(self.pipeline("预热", voice=self.voice, speed=1.0))
        logger.info("KokoroTTS ready ✅")

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        def sync_infer():
            for _, _, audio in self.pipeline(text, voice=self.voice, speed=1.0):
                return audio
            return None
        return await asyncio.to_thread(sync_infer)


class EdgeTTS(BaseTTS):
    """
    修复 WSL2 + Clash TUN 网络问题：
    TUN 模式只接管 Windows 侧网卡，WSL2 的 eth0 不在 TUN 管辖范围。
    必须显式将代理 URL 传给 aiohttp session，才能让流量走到 Clash。
    """
    def __init__(self):
        logger.info(f"Initializing EdgeTTS (proxy={PROXY_URL})...")
        self.voice = "zh-CN-XiaoxiaoNeural"
        self.proxy = PROXY_URL
        logger.info("EdgeTTS ready ✅")

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        import edge_tts
        from pydub import AudioSegment

        communicate = edge_tts.Communicate(text, voice=self.voice, proxy=self.proxy)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        if not audio_bytes:
            logger.warning(f"EdgeTTS returned empty audio for: {text!r}")
            return None

        def decode_mp3():
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            seg = seg.set_frame_rate(AUDIO_SAMPLE_RATE).set_channels(1)
            samples = np.array(seg.get_array_of_samples()).astype(np.float32)
            samples /= np.iinfo(seg.array_type).max  # 归一化到 [-1, 1]
            return samples

        return await asyncio.to_thread(decode_mp3)


class QwenTTS(BaseTTS):
    def __init__(self):
        logger.info("Initializing Qwen3-TTS...")
        import torchaudio, soundfile as sf
        from qwen_tts import Qwen3TTSModel
        # Ubuntu 环境下防止 torchaudio ffmpeg 冲突的补丁
        torchaudio.load = lambda f, *a, **kw: (
            torch.from_numpy(sf.read(f)[0]).float().unsqueeze(0),
            sf.read(f)[1]
        )
        self.model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            device_map="cpu",
            dtype=torch.float32
        )
        torch.set_num_threads(8)
        logger.info("QwenTTS ready ✅")

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        def sync_infer():
            wavs, _ = self.model.generate_custom_voice(
                text=text, language="Chinese", speaker="Vivian", instruct=""
            )
            return wavs[0]
        return await asyncio.to_thread(sync_infer)


# ==========================================
# 引擎池（懒加载 + 线程安全缓存）
# ==========================================
class EnginePool:
    def __init__(self):
        self._engines: Dict[str, BaseTTS] = {}
        self._lock = asyncio.Lock()
        # 启动时预加载 Kokoro
        self._preload_engines = ["kokoro"]

    async def warmup(self):
        for name in self._preload_engines:
            await self.get(name)
        logger.info(f"Engine pool warmed up: {list(self._engines.keys())}")

    async def get(self, name: str) -> BaseTTS:
        if name not in self._engines:
            async with self._lock:
                # 双重检查，防止并发初始化
                if name not in self._engines:
                    logger.info(f"Lazy-loading TTS engine: {name}")
                    if name == "kokoro":
                        self._engines[name] = await asyncio.to_thread(KokoroTTS)
                    elif name == "edge":
                        self._engines[name] = EdgeTTS()  # EdgeTTS 构造函数是同步的
                    elif name == "qwen":
                        self._engines[name] = await asyncio.to_thread(QwenTTS)
                    else:
                        raise ValueError(f"Unknown TTS engine: {name!r}")
        return self._engines[name]

    def loaded(self):
        return list(self._engines.keys())


engine_pool = EnginePool()

# PCM 块大小：每次 gRPC 流发送约 0.5s 的音频（减少内存积压）
CHUNK_SAMPLES = AUDIO_SAMPLE_RATE // 2  # 12000 samples = 0.5s


# ==========================================
# gRPC Servicer 实现
# ==========================================
class TTSServicer(tts_pb2_grpc.TTSServiceServicer):

    async def Synthesize(
        self,
        request: tts_pb2.SynthesizeRequest,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[tts_pb2.AudioChunk]:
        """
        Server Streaming RPC:
        1. 选择引擎
        2. 推理得到 Float32 NumPy 数组
        3. 按 CHUNK_SAMPLES 分块，逐块 yield 给调用方
        """
        text = request.text.strip()
        engine_name = request.engine or "kokoro"

        if not text:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "text is empty")
            return

        logger.info(f"[gRPC Synthesize] engine={engine_name} text={text!r}")
        t0 = time.time()

        try:
            engine = await engine_pool.get(engine_name)
            audio: Optional[np.ndarray] = await engine.synthesize(text)
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
            return
        except Exception as e:
            logger.exception("TTS inference error")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
            return

        if audio is None:
            # 合成失败时返回空块+结束标志，而不是直接断开，让调用方优雅处理
            yield tts_pb2.AudioChunk(pcm_data=b"", sample_rate=AUDIO_SAMPLE_RATE, is_last=True)
            return

        # Tensor → NumPy
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        audio = audio.astype(np.float32)

        # 分块 yield
        total_chunks = (len(audio) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES
        for i in range(0, len(audio), CHUNK_SAMPLES):
            chunk = audio[i: i + CHUNK_SAMPLES]
            is_last = (i + CHUNK_SAMPLES) >= len(audio)
            yield tts_pb2.AudioChunk(
                pcm_data=chunk.tobytes(),
                sample_rate=AUDIO_SAMPLE_RATE,
                is_last=is_last
            )

        logger.info(
            f"[gRPC Synthesize] done in {time.time()-t0:.3f}s, "
            f"{total_chunks} chunks, {len(audio)} samples"
        )

    async def HealthCheck(
        self,
        request: tts_pb2.HealthRequest,
        context: grpc.aio.ServicerContext
    ) -> tts_pb2.HealthResponse:
        return tts_pb2.HealthResponse(
            ok=True,
            message="TTS gRPC server is healthy",
            loaded_engines=engine_pool.loaded()
        )


# ==========================================
# 服务启动入口
# ==========================================
async def serve():
    server = grpc_aio.server(
        options=[
            # 最大接收消息：4MB（防止超长文本）
            ("grpc.max_receive_message_length", 4 * 1024 * 1024),
            # 最大发送消息：16MB（大音频块）
            ("grpc.max_send_message_length", 16 * 1024 * 1024),
            # 保活：防止长时间空闲时被中间件断连
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_timeout_ms", 10_000),
            ("grpc.keepalive_permit_without_calls", True),
        ]
    )
    tts_pb2_grpc.add_TTSServiceServicer_to_server(TTSServicer(), server)
    listen_addr = f"0.0.0.0:{GRPC_PORT}"
    server.add_insecure_port(listen_addr)

    logger.info(f"🎙️  TTS gRPC server starting on {listen_addr}")
    await server.start()

    # 预热引擎（Kokoro）
    await engine_pool.warmup()
    logger.info("✅ TTS gRPC server is ready!")

    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
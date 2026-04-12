# scripts/llm_tts/llm_tts.py
# FastAPI Gateway：LLM 推理 + gRPC TTS 客户端 + WebSocket 服务
# 启动方式: python llm_tts.py
# coding=utf-8
"""
架构：
  Browser ←──WebSocket──→ FastAPI Gateway ←──gRPC Stream──→ TTS gRPC Server
                                  │
                          llama.cpp (子进程)

职责分离：
  - Gateway 只负责 LLM 推理 + 文本流转发 + 协调 TTS gRPC 调用
  - TTS Server 专注音频合成，可独立重启/扩容
"""
import asyncio
import base64
import io
import os
import re
import subprocess
import sys
import time
import atexit
import urllib.request
import urllib.error
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Optional

import grpc
from grpc import aio as grpc_aio
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# gRPC 生成代码路径（与本文件同目录下的 generated/）
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))
from generated import tts_pb2
from generated import  tts_pb2_grpc


# ==========================================
# 1. 配置
# ==========================================
class AppSettings(BaseSettings):
    gguf_file: str = "/mnt/e/local_models/huggingface/local/Qwen3.5-4B-Q4_1.gguf"
    llamacpp_bin: str = "/home/baheas/githubrepos/llama.cpp/build/bin/llama-server"
    llm_port: int = 8080
    ctx_size: int = 4096

    # TTS gRPC 服务地址（同机部署）
    tts_grpc_addr: str = "localhost:50051"

    audio_sample_rate: int = 24000

    model_config = SettingsConfigDict(env_prefix="NENE_")


settings = AppSettings()


# ==========================================
# 2. 文本分块器（按标点截断成句）
# ==========================================
class TextChunker:
    def __init__(self):
        self.split_pattern = re.compile(r'([。！？；，,!?;\n])')

    async def chunk_stream(self, token_queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        buffer = ""
        while True:
            token = await token_queue.get()
            if token is None:
                if buffer.strip():
                    yield buffer.strip()
                break
            buffer += token
            if self.split_pattern.search(token):
                if buffer.strip():
                    yield buffer.strip()
                buffer = ""


# ==========================================
# 3. LLM 引擎（llama.cpp 子进程）
# ==========================================
class LlamaCppServerLLM:
    def __init__(self):
        self.server_process = None
        self.client: Optional[AsyncOpenAI] = None
        self._start_server()
        self._init_client()

    def _start_server(self):
        command = [
            settings.llamacpp_bin,
            "-m", settings.gguf_file,
            "-c", str(settings.ctx_size),
            "--port", str(settings.llm_port),
            "--chat-template", "chatml",
        ]
        logger.info(f"Starting llama-server on port {settings.llm_port}...")
        self.server_process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        atexit.register(self._cleanup_process)
        self._wait_for_health()

    def _wait_for_health(self, timeout: int = 120):
        url = f"http://localhost:{settings.llm_port}/health"
        start = time.time()
        while time.time() - start < timeout:
            try:
                urllib.request.urlopen(url)
                model_name = settings.gguf_file.rsplit(os.sep, 1)[-1]
                logger.info(f"LLM [{model_name}] server ready ✅")
                return
            except (urllib.error.URLError, ConnectionResetError):
                time.sleep(1)
        self._cleanup_process()
        raise TimeoutError("llama-server failed to start within timeout.")

    def _init_client(self):
        self.client = AsyncOpenAI(
            base_url=f"http://localhost:{settings.llm_port}/v1",
            api_key="sk-local",
        )

    def _cleanup_process(self):
        if self.server_process and self.server_process.poll() is None:
            logger.info("Terminating llama-server...")
            self.server_process.terminate()
            self.server_process.wait()

    async def astream_chat(self, prompt: str) -> AsyncGenerator[str, None]:
        response = await self.client.chat.completions.create(
            model="local",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=0.7,
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ==========================================
# 4. gRPC TTS 客户端（连接 TTS gRPC Server）
# ==========================================
class GrpcTTSClient:
    """
    封装对 TTS gRPC Server 的流式调用。
    channel 在 Gateway 启动时创建，复用整个生命周期（HTTP/2 多路复用）。
    """
    def __init__(self, addr: str):
        self._addr = addr
        self._channel: Optional[grpc_aio.Channel] = None
        self._stub: Optional[tts_pb2_grpc.TTSServiceStub] = None

    async def connect(self):
        self._channel = grpc_aio.insecure_channel(
            self._addr,
            options=[
                ("grpc.max_receive_message_length", 16 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 30_000),
                ("grpc.keepalive_timeout_ms", 10_000),
                ("grpc.keepalive_permit_without_calls", True),
            ],
        )
        self._stub = tts_pb2_grpc.TTSServiceStub(self._channel)
        # 验证连接
        resp = await self._stub.HealthCheck(tts_pb2.HealthRequest())
        logger.info(
            f"TTS gRPC connected: {resp.message}, "
            f"loaded engines: {list(resp.loaded_engines)}"
        )

    async def close(self):
        if self._channel:
            await self._channel.close()

    async def synthesize_stream(
        self, text: str, engine: str
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        调用 TTS gRPC Server，以 Server Streaming 方式接收音频块。
        每个块是 Float32 PCM bytes，直接解码成 NumPy 数组后 yield。
        """
        request = tts_pb2.SynthesizeRequest(
            text=text,
            engine=engine,
            sample_rate=settings.audio_sample_rate,
        )
        try:
            async for chunk in self._stub.Synthesize(request):
                if chunk.pcm_data:
                    audio = np.frombuffer(chunk.pcm_data, dtype=np.float32).copy()
                    yield audio
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC TTS error: {e.code()} - {e.details()}")


# ==========================================
# 5. 全局单例
# ==========================================
llm_engine: Optional[LlamaCppServerLLM] = None
tts_client: Optional[GrpcTTSClient] = None


# ==========================================
# 6. 生命周期
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_engine, tts_client

    logger.info("🚀 启动 Gateway 服务...")

    # 启动 LLM
    llm_engine = LlamaCppServerLLM()

    # 连接 TTS gRPC Server
    tts_client = GrpcTTSClient(settings.tts_grpc_addr)
    await tts_client.connect()

    logger.info("✅ Gateway 全部服务就绪！")
    yield

    logger.info("🛑 关闭 Gateway，清理资源...")
    if llm_engine:
        llm_engine._cleanup_process()
    if tts_client:
        await tts_client.close()
    logger.info("👋 安全退出。")


# ==========================================
# 7. FastAPI 实例
# ==========================================
app = FastAPI(title="Nene Gateway - LLM & TTS", lifespan=lifespan)


# ==========================================
# 8. 后台 TTS Worker（从 token 队列消费 → gRPC → 推送音频给前端）
# ==========================================
async def background_tts_worker(
    websocket: WebSocket,
    token_queue: asyncio.Queue,
    engine: str,
    ws_lock: asyncio.Lock,
    cancel_event: asyncio.Event,
):
    chunker = TextChunker()
    try:
        async for sentence in chunker.chunk_stream(token_queue):
            if cancel_event.is_set():
                break

            logger.debug(f"[TTS] 合成句子: {sentence!r}")
            t0 = time.time()

            # 收集这一句的所有音频块（gRPC 流）
            audio_chunks = []
            async for pcm in tts_client.synthesize_stream(sentence, engine):
                if cancel_event.is_set():
                    break
                audio_chunks.append(pcm)

            if not audio_chunks or cancel_event.is_set():
                continue

            # 拼接成完整音频并转 Base64
            full_audio = np.concatenate(audio_chunks)
            b64_audio = base64.b64encode(full_audio.tobytes()).decode("utf-8")

            if websocket.client_state.name == "CONNECTED":
                async with ws_lock:
                    await websocket.send_json({
                        "type": "audio",
                        "data": b64_audio,
                        "sample_rate": settings.audio_sample_rate,
                    })
                logger.debug(
                    f"[TTS] {engine} 合成+发送耗时: {time.time()-t0:.3f}s, "
                    f"{len(full_audio)} samples"
                )

    except asyncio.CancelledError:
        logger.warning("⚠️ TTS Worker 被取消（前端已断开）")
    except Exception:
        logger.exception("❌ TTS Worker 异常")


# ==========================================
# 9. WebSocket 接入点
# ==========================================
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("🟢 前端 WebSocket 已连接")

    ws_lock = asyncio.Lock()
    cancel_event = asyncio.Event()
    tts_task = None

    try:
        # 接收握手参数
        data = await websocket.receive_json()
        original_prompt = data.get("prompt", "你好")
        tts_engine = data.get("tts_type", "kokoro")

        # 监听前端"停止"信号的子任务
        async def listen_for_stop():
            try:
                while True:
                    msg = await websocket.receive_json()
                    if msg.get("action") == "stop":
                        logger.warning("🚨 收到停止信号，取消生成")
                        cancel_event.set()
                        break
            except Exception:
                pass  # 连接断开时正常退出

        listener_task = asyncio.create_task(listen_for_stop())

        # 系统提示词
        prompt = (
            f"你是一个中文语音助手。请直接给出简短的回答，"
            f"绝对不要输出任何思考过程或分析。"
            f"请用简短、自然、口语化的中文回答。用户问：{original_prompt}"
        )

        token_queue: asyncio.Queue = asyncio.Queue()

        # 启动后台 TTS Worker
        tts_task = asyncio.create_task(
            background_tts_worker(
                websocket=websocket,
                token_queue=token_queue,
                engine=tts_engine,
                ws_lock=ws_lock,
                cancel_event=cancel_event,
            )
        )

        # 主循环：LLM 生成 → 推送文字 + 入队
        async for chunk in llm_engine.astream_chat(prompt):
            if cancel_event.is_set():
                break
            async with ws_lock:
                await websocket.send_json({"type": "text", "content": chunk})
            await token_queue.put(chunk)

        # 发送结束信号给 TTS Worker
        await token_queue.put(None)
        # 等待所有音频发送完毕
        await tts_task

        listener_task.cancel()

        if not cancel_event.is_set():
            async with ws_lock:
                await websocket.send_json({"type": "done"})

        logger.info("✅ 本次会话完成")

    except WebSocketDisconnect:
        logger.info("🔴 前端断开连接")
    except Exception:
        logger.exception("❌ WebSocket 异常")
    finally:
        cancel_event.set()
        if tts_task and not tts_task.done():
            tts_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
# textgen2tts.py

import os
import torch
import asyncio
import re
import numpy as np
import sounddevice as sd
from fastapi import FastAPI
from pydantic import BaseModel
from openai import AsyncOpenAI
from loguru import logger
from qwen_tts import Qwen3TTSModel
import time 

# --- 1. 环境与路径配置 ---
HUGGINGFACE_ROOT = r"E:\local_models\huggingface\cache\hub"
tts_model = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
def get_hf_path(model_name: str) -> str:
    dir_name = "models--" + model_name.replace("/", "--")
    snapshots_dir = os.path.join(HUGGINGFACE_ROOT, dir_name, "snapshots")
    hashes = os.listdir(snapshots_dir)
    return os.path.normpath(os.path.join(snapshots_dir, hashes[0]))

# --- 2. 初始化模型 ---
tts_path = get_hf_path(tts_model)
logger.info(f"Loading TTS from: {tts_path}")

# 加载 TTS (建议全局加载一次)
tts_model = Qwen3TTSModel.from_pretrained(
    tts_path,
    device_map="cpu",
    dtype=torch.float32,
    attn_implementation="sdpa",
    trust_remote_code=True
)

llm_client = AsyncOpenAI(base_url="http://127.0.0.1:8080/v1", api_key="sk-none")

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

# --- 3. 音频播放辅助 ---
def play_audio(samples, sr):
    """直接驱动本地声卡播放"""
    try:
        sd.play(samples, sr)
        sd.wait() # 等待当前片段播完，防止重叠
    except Exception as e:
        logger.error(f"Playback error: {e}")

# --- 4. 核心流式处理逻辑 ---
async def stream_text_to_speech(user_input: str):
    full_response = ""
    buffer = ""
    
    # 句子切割符号
    split_pats = re.compile(r'([。,，！？\n])')

    logger.info("Starting LLM stream...")
    
    # A. 获取 LLM 流
    response = await llm_client.chat.completions.create(
        model="qwen3-1.7b",
        messages=[
            {"role": "system", "content": "你是一个亲切的语音助手。请用简短口语回复。"},
            {"role": "user", "content": user_input}
        ],
        stream=True # 开启流式
    )

    async for chunk in response:
        content = chunk.choices[0].delta.content or ""
        if not content: continue
        
        full_response += content
        buffer += content
        
        # B. 检查是否凑齐了一个句子
        if split_pats.search(buffer):
            # 按标点切分
            parts = split_pats.split(buffer)
            # 最后一个部分可能是不完整的句子，留在 buffer 里
            to_speak = "".join(parts[:-1]).strip()
            buffer = parts[-1]

            if to_speak:
                tt = time.perf_counter()
                await process_and_play(to_speak)
                logger.info(f"TTS Generated: {text} in {time.perf_counter() - tt:.4f} seconds")
    
    # C. 处理最后剩下的 buffer
    if buffer.strip():
        await process_and_play(buffer.strip())
    
    return full_response

async def process_and_play(text):
    """TTS 生成并直接播放"""
    logger.info(f"TTS Generating: {text}")
    # 注意：在 CPU 上这一步会耗时，异步环境下建议用 run_in_executor
    loop = asyncio.get_event_loop()
    
    # 运行 TTS 推理
    wavs, sr = await loop.run_in_executor(
        None, 
        lambda: tts_model.generate_custom_voice(
            text=text,
            language="Chinese",
            speaker="Vivian"
        )
    )
    
    # 播放音频
    logger.info(f"Playing audio segment...")
    await loop.run_in_executor(None, play_audio, wavs[0], sr)

# --- 5. API 接口 ---
@app.post("/api/chat_voice")
async def chat_voice_endpoint(request: ChatRequest):
    logger.info(f"User: {request.message}")
    
    # 这里会阻塞直到所有音频播完，如果需要前端立即响应，可以改用 BackgroundTasks
    final_text = await stream_text_to_speech(request.message)
    
    return {"status": "success", "reply": final_text}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)


# F5-TTS 

# coding=utf-8
import time
import torch
import numpy as np
import re
import os
import threading
import queue
import pyaudio
from cached_path import cached_path
from loguru import logger 

import torchaudio
import soundfile as sf

# ====== 🪄 魔法补丁：强制使用 soundfile 替换崩溃的 torchaudio.load ======
# 注意：如果在 Ubuntu 环境下部署且 FFmpeg 完备，可移除此补丁
def safe_audio_load(filepath, *args, **kwargs):
    data, sr = sf.read(filepath)
    tensor = torch.from_numpy(data).float()
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0) 
    else:
        tensor = tensor.transpose(0, 1)
    return tensor, sr

torchaudio.load = safe_audio_load
# ====================================================================

# F5-TTS 核心依赖
from f5_tts.infer.utils_infer import (
    infer_process,
    load_model,
    load_vocoder,
    preprocess_ref_audio_text,
)
from f5_tts.model import DiT

class AudioPlayer:
    """音频流式播放器"""
    def __init__(self, sample_rate=24000):
        self.sample_rate = sample_rate
        self.p = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self.is_playing = True
        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()

    def _play_loop(self):
        stream = self.p.open(format=pyaudio.paFloat32,
                            channels=1,
                            rate=self.sample_rate,
                            output=True)
        while self.is_playing:
            try:
                data = self.queue.get(timeout=1)
                if data is not None:
                    stream.write(data.astype(np.float32).tobytes())
                self.queue.task_done()
            except queue.Empty:
                continue
        stream.stop_stream()
        stream.close()

    def add_to_queue(self, audio_data):
        self.queue.put(audio_data)

class TextChunker:
    """文本分块器"""
    def __init__(self):
        # GPU 速度足够快，可以适当增加断句的连贯性，遇到这些标点才合成
        self.split_pattern = re.compile(r'([。！？；!?;])')

    def chunk_stream(self, token_stream):
        buffer = ""
        for token in token_stream:
            buffer += token
            if self.split_pattern.search(token):
                yield buffer.strip()
                buffer = ""
        if buffer.strip():
            yield buffer.strip()

class F5TTSGPUController:
    """F5-TTS 控制器：处理模型加载与推理 (GPU 优化版)"""
    def __init__(self, ref_audio_path: str, ref_text: str):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[F5-TTS Benchmark] 正在加载 Vocoder 和 F5-TTS 模型到 {self.device.upper()}...")
        t0 = time.time()
        
        # 1. 加载 Vocoder (默认会自动推断并放到 GPU)
        self.vocoder = load_vocoder()
        
        # 2. 加载 F5-TTS 权重
        ckpt_path = str(cached_path("hf://SWivid/F5-TTS/F5TTS_v1_Base/model_1250000.safetensors"))
        model_cfg = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)
        self.model = load_model(DiT, model_cfg, ckpt_path)
        
        # 确保模型在 GPU 上并开启评估模式
        self.model.to(self.device).eval()
        
        logger.info(f"[F5-TTS Benchmark] 模型加载完成，耗时: {time.time() - t0:.2f}s")
        
        # 3. 预处理参考音频
        logger.info("[F5-TTS Benchmark] 正在处理参考音频...")
        self.ref_audio, self.ref_text = preprocess_ref_audio_text(ref_audio_path, ref_text)
        logger.info("参考音频处理完毕。")
        
        # 4. GPU 预热 (Warm-up)，防止首句延迟过高
        self._warmup()

    def _warmup(self):
        logger.info("[F5-TTS Benchmark] 正在预热 GPU...")
        with torch.no_grad():
            infer_process(
                ref_audio=self.ref_audio,
                ref_text=self.ref_text,
                gen_text="测试",
                model_obj=self.model,
                vocoder=self.vocoder,
                nfe_step=8,
                speed=1.0,
                show_info=lambda x: None,
            )
        torch.cuda.synchronize()
        logger.info("[F5-TTS Benchmark] GPU 预热完成。")

    def generate(self, text, chunk_idx, nfe_step=32):
        """
        生成单句语音
        在 GPU 上，nfe_step 可以放心设置为 32 甚至 64 以保证最佳音质
        """
        logger.info(f"\n[推理中] Chunk {chunk_idx}: {text}")
        
        torch.cuda.synchronize()
        t0 = time.time()
        
        # 开启推理上下文，避免计算梯度，节省显存并加速
        with torch.no_grad():
            final_wave, final_sample_rate, _ = infer_process(
                ref_audio=self.ref_audio,
                ref_text=self.ref_text,
                gen_text=text,
                model_obj=self.model,
                vocoder=self.vocoder,
                nfe_step=nfe_step,
                speed=1.0,
                cross_fade_duration=0.15,
                show_info=lambda x: None,
            )
        
        torch.cuda.synchronize()
        cost_time = time.time() - t0
        
        audio_data = final_wave.squeeze()
        audio_duration = len(audio_data) / final_sample_rate
        rtf = cost_time / audio_duration if audio_duration > 0 else 0
        
        status = "🟢 实时" if rtf < 1 else "🔴 延迟 (RTF > 1)"
        logger.info(f"[推理完成] 耗时: {cost_time:.3f}s | 时长: {audio_duration:.2f}s | RTF: {rtf:.3f} [{status}]")
        
        return audio_data, final_sample_rate

def main():
    # ==== 配置区 ====
    REF_AUDIO_PATH = "ref.wav" 
    REF_TEXT = "其实我真的有发现，我是一个特别善于观察别人情绪的人。" 
    
    TEST_TEXT = "你好，我是你的专属语音助手。我接入了全新的 F5-TTS 引擎，现在的我运行在强大的 GPU 上，你可以尽情享受极速且自然的语音反馈了！"
    # ===============

    if not os.path.exists(REF_AUDIO_PATH):
        logger.info(f"❌ 错误: 找不到参考音频文件 '{REF_AUDIO_PATH}'。")
        return

    try:
        tts_controller = F5TTSGPUController(REF_AUDIO_PATH, REF_TEXT)
    except Exception as e:
        logger.info(f"❌ 加载失败，请检查 CUDA 环境或依赖: {e}")
        return

    player = AudioPlayer(sample_rate=24000)
    chunker = TextChunker()
    
    def mock_llm_stream():
        for char in TEST_TEXT:
            yield char
            time.sleep(0.05)
            
    logger.info("\n>>> 开始 F5-TTS GPU 流式语音测试 (按 Ctrl+C 停止) <<<")
    
    sentences = chunker.chunk_stream(mock_llm_stream())
    
    for i, sentence in enumerate(sentences):
        # 享受 GPU 带来的红利：直接把 nfe_step 设置为 32
        audio, sr = tts_controller.generate(sentence, i, nfe_step=32)
        
        if i == 0: player.sample_rate = sr
        player.add_to_queue(audio)

    player.queue.join()
    logger.info("\n>>> 所有音频播放完毕 <<<")

if __name__ == "__main__":
    main()

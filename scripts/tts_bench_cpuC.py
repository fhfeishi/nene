#  tts_bench_cpuC.py    # F5-TTs

# coding=utf-8
import time
import torch
import numpy as np
import re
import os
import threading
import queue
import pyaudio
import json
from importlib.resources import files
from cached_path import cached_path
from loguru import logger 


import torchaudio
import soundfile as sf
# ====== 🪄 魔法补丁：强制使用 soundfile 替换崩溃的 torchaudio.load ======
def safe_audio_load(filepath, *args, **kwargs):
    # 使用 soundfile 读取 wav 文件
    data, sr = sf.read(filepath)
    # 转换为 PyTorch Tensor (torchaudio 期望的格式)
    tensor = torch.from_numpy(data).float()
    # 调整形状为 (channels, frames)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0) 
    else:
        tensor = tensor.transpose(0, 1)
    return tensor, sr

# 劫持并替换原函数
torchaudio.load = safe_audio_load

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
    """文本分块器（针对 CPU 和 DiT 优化）"""
    def __init__(self):
        # 建议短句截断，DiT 处理过长文本在 CPU 上显存/内存消耗很大
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

class F5TTSCPUController:
    """F5-TTS 控制器：处理模型加载与推理"""
    def __init__(self, ref_audio_path: str, ref_text: str):
        logger.info("[F5-TTS Benchmark] 正在加载 Vocoder 和 F5-TTS 模型到 CPU...")
        t0 = time.time()
        
        # 强制 CPU 优化设置
        torch.set_num_threads(8) 
        
        # 1. 加载 Vocoder
        self.vocoder = load_vocoder()
        
        # 2. 加载 F5-TTS 权重 (使用官方默认的 Base 模型)
        ckpt_path = str(cached_path("hf://SWivid/F5-TTS/F5TTS_v1_Base/model_1250000.safetensors"))
        model_cfg = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)
        self.model = load_model(DiT, model_cfg, ckpt_path)
        
        logger.info(f"[F5-TTS Benchmark] 模型加载完成，耗时: {time.time() - t0:.2f}s")
        
        # 3. 预处理参考音频 (只做一次，保持音色绝对一致)
        logger.info("[F5-TTS Benchmark] 正在处理参考音频...")
        self.ref_audio, self.ref_text = preprocess_ref_audio_text(ref_audio_path, ref_text)
        logger.info("参考音频处理完毕。")

    def generate(self, text, chunk_idx, nfe_step=16):
        """
        生成单句语音
        nfe_step: 降噪步数。默认是32，在CPU上建议降低到 8-16 以加快速度。
        """
        logger.info(f"\n[推理中] Chunk {chunk_idx}: {text}")
        t0 = time.time()
        
        # 调用核心推断逻辑
        final_wave, final_sample_rate, _ = infer_process(
            ref_audio=self.ref_audio,
            ref_text=self.ref_text,
            gen_text=text,
            model_obj=self.model,
            vocoder=self.vocoder,
            nfe_step=nfe_step, # CPU 提速的关键
            speed=1.0,         # 语速
            cross_fade_duration=0.15,
            show_info=lambda x: None, # 屏蔽进度条打印，保持控制台整洁
        )
        
        # F5-TTS 可能会有一点前后的静音，可以直接返回
        # audio_data = final_wave.squeeze().cpu().numpy()    #  final_wave 本来就是 numpy.ndarray
        audio_data = final_wave.squeeze()
        
        # 计算性能
        cost_time = time.time() - t0
        audio_duration = len(audio_data) / final_sample_rate
        rtf = cost_time / audio_duration if audio_duration > 0 else 0
        
        status = "🟢 实时" if rtf < 1 else "🔴 延迟 (RTF > 1)"
        logger.info(f"[推理完成] 耗时: {cost_time:.2f}s | 时长: {audio_duration:.2f}s | RTF: {rtf:.2f} [{status}]")
        
        return audio_data, final_sample_rate

def main():
    # ==== 配置区 ====
    # 【非常重要】：请准备一个 3-5 秒的声音干净的 wav 文件，并填入它对应的文字
    REF_AUDIO_PATH = "ref.wav" 
    REF_TEXT = "其实我真的有发现，我是一个特别善于观察别人情绪的人。" 
    
    # RAG 测试长文本
    TEST_TEXT = "你好，我是你的专属语音助手。我接入了全新的 F5-TTS 引擎，你可以听听看我的声音是否足够自然？如果在普通处理器上运行，你可以稍微调低迭代步数来加快响应。"
    # ===============

    if not os.path.exists(REF_AUDIO_PATH):
        logger.info(f"❌ 错误: 找不到参考音频文件 '{REF_AUDIO_PATH}'。请先准备一个简短的 wav 录音放入同级目录。")
        return

    # 初始化
    try:
        tts_controller = F5TTSCPUController(REF_AUDIO_PATH, REF_TEXT)
    except Exception as e:
        logger.info(f"❌ 加载失败，请确保 F5-TTS 及其依赖已正确安装: {e}")
        return

    player = AudioPlayer(sample_rate=24000)
    chunker = TextChunker()
    
    # 模拟 LLM 吐字
    def mock_llm_stream():
        for char in TEST_TEXT:
            yield char
            time.sleep(0.05)
            
    logger.info("\n>>> 开始 F5-TTS 流式语音测试 (按 Ctrl+C 停止) <<<")
    
    sentences = chunker.chunk_stream(mock_llm_stream())
    
    for i, sentence in enumerate(sentences):
        # ⚠️ CPU 性能调节：如果觉得太慢，把 nfe_step 从 16 改成 8 试试
        audio, sr = tts_controller.generate(sentence, i, nfe_step=8)
        
        if i == 0: player.sample_rate = sr
        player.add_to_queue(audio)

    player.queue.join()
    logger.info("\n>>> 所有音频播放完毕 <<<")

if __name__ == "__main__":
    main()



# coding=utf-8

#  Qwen3-TTS 


import time
import torch
import numpy as np
import re
import os
import threading
import queue
import pyaudio
import soundfile as sf
from loguru import logger 

from qwen_tts import Qwen3TTSModel

class AudioPlayer:
    """音频播放器：使用队列实现异步连续播放"""
    def __init__(self, sample_rate=24000):
        self.sample_rate = sample_rate
        self.p = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self.is_playing = True
        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()

    def _play_loop(self):
        # 打开音频流
        stream = self.p.open(format=pyaudio.paFloat32,
                            channels=1,
                            rate=self.sample_rate,
                            output=True)
        while self.is_playing:
            try:
                # 从队列获取音频数据（numpy array）
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

    def stop(self):
        self.is_playing = False

class TextChunker:
    """文本分块器：专门针对 CPU 速度优化断句"""
    def __init__(self):
        # 建议仅在强标点处断句，保证语气的连贯和 CPU 的效率
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

class QwenTTSCPUController:
    """TTS 控制器：处理模型推理与音色稳定性"""
    def __init__(self, model_path="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"):
        self.device = "cpu"
        # 强制使用 float32 保证 CPU 兼容性
        self.model = Qwen3TTSModel.from_pretrained(
            model_path,
            device_map=self.device,
            dtype=torch.float32    # torch_dtype dtype
        )
        torch.set_num_threads(8)
        
        # --- 音色保持关键参数 ---
        self.default_speaker = "Vivian" 
        self.default_instruct = "用自然、连贯的语气交流，保持音色稳定。"
        # 如果模型支持，可以在这里预载入一个 seed 或 prompt 音频（取决于 Qwen3-TTS 具体实现）

    def generate(self, text, chunk_idx):
        logger.info(f"\n[推理中] Segment {chunk_idx}: {text}")
        t0 = time.time()
        
        # 为了音色一致性，确保每次调用的参数完全一致
        # 如果 Qwen3 提供了特征提取，建议提取一次后在后续调用中重复传入
        wavs, sr = self.model.generate_custom_voice(
            text=text,
            language="Chinese",
            speaker=self.default_speaker,
            instruct=self.default_instruct, # 每一段都带上相同的 instruct
        )
        
        rtf = (time.time() - t0) / (len(wavs[0]) / sr)
        logger.info(f"[推理完成] RTF: {rtf:.2f}")
        return wavs[0], sr

def main():
    # 模拟 RAG 输出的长文本
    raw_text = "你好！很高兴为你服务。关于你提到的 RAG 系统声音插件，我建议第一步先测试 CPU 的实时率。如果音色不一致，我们可以尝试固定提示词。你觉得这个方案怎么样？"
    
    # 1. 初始化组件
    tts_controller = QwenTTSCPUController()
    player = AudioPlayer(sample_rate=24000) # 注意：采样率需与模型输出一致
    chunker = TextChunker()
    
    # 2. 模拟 LLM 流
    def mock_llm_stream():
        for char in raw_text:
            yield char
            time.sleep(0.05) # 模拟生成速度

    logger.info("\n>>> 开始实时语音测试 (按 Ctrl+C 停止) <<<")
    
    sentences = chunker.chunk_stream(mock_llm_stream())
    
    for i, sentence in enumerate(sentences):
        # 执行推理
        audio, sr = tts_controller.generate(sentence, i)
        
        # 更新播放器采样率（如果是第一次）
        if i == 0: player.sample_rate = sr
        
        # 丢进播放队列，代码会立即进入下一句的推理，而背景线程在唱歌
        player.add_to_queue(audio)

    # 等待播放完成
    player.queue.join()
    logger.info("\n>>> 所有音频播放完毕 <<<")

if __name__ == "__main__":
    main()
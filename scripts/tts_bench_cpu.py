# scripts/tts_bench_cpu.py

# coding=utf-8
import time
import torch
import soundfile as sf
import re
import os
import platform
import pyaudio
from loguru import logger 

# 官方 tts 接口
from qwen_tts import Qwen3TTSModel



model_path: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
# model_path = r"E:\local_models\huggingface\cache\hub\models--SWivid--F5-TTS\snapshots\84e5a410d9cead4de2f847e7c9369a6440bdfaca"


class LLMStreamSimulator:
    """模拟 LLM 流式输出文本 token 的生成器"""
    def __init__(self, full_text: str, tokens_per_second: int = 5):
        self.full_text = full_text
        self.delay = 1.0 / tokens_per_second

    def generate(self):
        for char in self.full_text:
            time.sleep(self.delay)
            yield char

class TextChunker:
    """文本分块器：遇到强标点符号触发 TTS"""
    def __init__(self):
        # CPU 速度慢，建议只在句号、问号、感叹号处断句，减少调用次数
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

class QwenTTSCPUBenchmarker:
    """针对 CPU 优化的 TTS 基准测试封装"""
    def __init__(self, model_path: str = model_path):
        self.device = "cpu"
        logger.info(f"[CPU Benchmark] 正在加载 Qwen3-TTS 模型到 CPU...")
        
        # CPU 优化：
        # 1. 使用 float32 (CPU上bfloat16通常没有加速，除非是极新的Intel CPU)
        # 2. 移除 flash_attention_2 (那是给 NVIDIA GPU 用的)
        t_start = time.time()
        self.tts = Qwen3TTSModel.from_pretrained(
            model_path,
            device_map=self.device,
            dtype=torch.float32, 
        )
        # 限制线程数，避免过度竞争导致变慢 (通常设置为物理核心数)
        torch.set_num_threads(8) 
        
        logger.info(f"[CPU Benchmark] 模型加载完成，耗时: {time.time() - t_start:.2f}s")
        self._warmup()

    def _warmup(self):
        logger.info("[CPU Benchmark] 正在进行 CPU 预热（首次计算耗时较长）...")
        self.tts.generate_custom_voice(
            text="你好", language="Chinese", speaker="Vivian", instruct=""
        )
        logger.info("[CPU Benchmark] 预热完成。")

    def synthesize_chunk(self, text_chunk: str, speaker: str = "Vivian", chunk_idx: int = 0):
        logger.info(f"\n[{chunk_idx}] CPU 合成开始: '{text_chunk}'")
        
        t0 = time.time()
        # CPU 推理
        wavs, sr = self.tts.generate_custom_voice(
            text=text_chunk,
            language="Chinese",
            speaker=speaker,
            instruct="", # CPU 负载高时，建议先关闭复杂的指令引导
        )
        t1 = time.time()
        
        cost_time = t1 - t0
        audio_data = wavs[0]
        audio_duration = len(audio_data) / sr 
        rtf = cost_time / audio_duration if audio_duration > 0 else 0
        
        # 性能评估颜色标记
        status = "🟢 实时" if rtf < 1 else "🔴 延迟 (RTF > 1)"
        logger.info(f"[{chunk_idx}] 耗时: {cost_time:.2f}s | 音频长度: {audio_duration:.2f}s | RTF: {rtf:.2f} [{status}]")
        
        os.makedirs("output_cpu", exist_ok=True)
        out_path = f"output_cpu/chunk_{chunk_idx}.wav"
        sf.write(out_path, audio_data, sr)
        
        return cost_time

def main():
    # 测试文本：短句更有利于 CPU 响应
    test_text = "你好，我是你的AI助手。今天有什么我可以帮你的吗？"
    
    llm_simulator = LLMStreamSimulator(test_text)
    chunker = TextChunker()
    
    try:
        tts_bench = QwenTTSCPUBenchmarker()
    except Exception as e:
        logger.info(f"❌ 加载失败: {e}\n提示: 请确保已安装 torch 和 qwen_tts 库。")
        return
    
    logger.info("\n" + "="*50)
    logger.info(f"💻 CPU 性能测试开始 (系统: {platform.processor()})")
    logger.info("="*50)
    
    sentence_stream = chunker.chunk_stream(llm_simulator.generate())
    
    for idx, sentence in enumerate(sentence_stream):
        tts_bench.synthesize_chunk(sentence, chunk_idx=idx)

if __name__ == "__main__":
    main()
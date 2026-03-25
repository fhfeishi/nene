# scripts/tts_bench.py 
# 测试 tts 模型 

import time
import torch 
import soundfile as sf 
import re 
import os 
import numpy as np 
from loguru import logger 

# 官方 tts-api
from qwen_tts import Qwen3TTSModel 



class LLMStreamSimulator:
    """模拟 LLM 流式输出文本 token 的生成器"""
    def __init__(self, full_text: str, tokens_per_second: int = 20):
        self.full_text = full_text
        self.delay = 1.0 / tokens_per_second

    def generate(self):
        """模拟 generator，逐字（或逐token）yield 文本"""
        logger.info("[LLM Simulator] 开始流式输出...")
        for char in self.full_text:
            time.sleep(self.delay) # 模拟推理延迟
            yield char

class TextChunker:
    """文本分块器：将流式 token 聚合成完整的句子，遇到标点触发"""
    def __init__(self):
        # 定义触发 TTS 合成的断句标点
        self.split_pattern = re.compile(r'([。！？；，,!?])')

    def chunk_stream(self, token_stream):
        """接收 token 流，yield 完整的句子片段"""
        buffer = ""
        for token in token_stream:
            buffer += token
            # 如果 buffer 最后一个字符是断句标点
            if self.split_pattern.match(token):
                yield buffer.strip()
                buffer = ""
        # 处理最后剩余的文本
        if buffer.strip():
            yield buffer.strip()


class QwenTTSBenchmarker:
    """TTS 引擎与基准测试封装"""
    def __init__(self, model_path: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/", device: str = "cuda:0"):
        self.device = device
        logger.info(f"[TTS Benchmark] 正在加载 Qwen3-TTS 模型 ({device})...")
        t_start = time.time()
        self.tts = Qwen3TTSModel.from_pretrained(
            model_path,
            device_map=self.device,
            dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )
        logger.info(f"[TTS Benchmark] 模型加载完成，耗时: {time.time() - t_start:.2f}s")
        # 预热模型 (Warm-up)，避免第一次推理过慢影响测试准确性
        self._warmup()

    def _warmup(self):
        logger.info("[TTS Benchmark] 正在预热模型...")
        self.tts.generate_custom_voice(
            text="测试", language="Chinese", speaker="Vivian", instruct=""
        )
        torch.cuda.synchronize()
        logger.info("[TTS Benchmark] 预热完成。")

    def synthesize_chunk(self, text_chunk: str, speaker: str = "Vivian", instruct: str = "", chunk_idx: int = 0):
        """合成单个句子并记录性能指标"""
        logger.info(f"\n[{chunk_idx}] 开始合成: '{text_chunk}'")
        
        torch.cuda.synchronize()
        t0 = time.time()
        
        # 调用 Qwen3-TTS 生成
        wavs, sr = self.tts.generate_custom_voice(
            text=text_chunk,
            language="Chinese",
            speaker=speaker,
            instruct=instruct,
        )
        
        torch.cuda.synchronize()
        t1 = time.time()
        
        # 计算指标
        cost_time = t1 - t0
        audio_data = wavs[0]
        # 音频时长 = 采样点数 / 采样率
        audio_duration = len(audio_data) / sr 
        # RTF (Real-Time Factor): 合成耗时 / 音频时长。越低越好，< 1 表示可以实时播放
        rtf = cost_time / audio_duration if audio_duration > 0 else 0
        
        logger.info(f"[{chunk_idx}] 合成耗时: {cost_time:.3f}s | 音频时长: {audio_duration:.3f}s | RTF: {rtf:.3f}")
        
        # 保存切片音频进行人工评估
        os.makedirs("output_audio", exist_ok=True)
        out_path = f"output_audio/chunk_{chunk_idx}.wav"
        sf.write(out_path, audio_data, sr)
        
        return audio_data, sr, cost_time

def main():
    # 1. 准备测试文本（模拟 LLM 即将生成的长文本）
    test_text = "其实我真的有发现，我是一个特别善于观察别人情绪的人。每次朋友不开心，我都能第一时间察觉到。你觉得这是天生的吗？"
    
    # 2. 初始化各个组件
    llm_simulator = LLMStreamSimulator(test_text, tokens_per_second=15)
    chunker = TextChunker()
    tts_bench = QwenTTSBenchmarker(
        model_path="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/", 
        device="cuda:0"
    )
    
    # 3. 构建 Pipeline 并测试
    logger.info("\n" + "="*40)
    logger.info("🚀 开始 RAG 流式 TTS 管道测试")
    logger.info("="*40)
    
    # 将 LLM 流传入切块器
    sentence_stream = chunker.chunk_stream(llm_simulator.generate())
    
    total_cost_time = 0
    first_audio_latency = None
    
    for idx, sentence in enumerate(sentence_stream):
        # 记录首字/首句到达时间
        if idx == 0 and first_audio_latency is None:
            # 这里简化计算，实际中需要加上 LLM 吐出第一个完整句子的时间
            pass 
            
        # 触发 TTS
        _, _, cost = tts_bench.synthesize_chunk(
            text_chunk=sentence,
            speaker="Vivian",
            instruct="用温柔且带有一点思考的语气说",
            chunk_idx=idx
        )
        total_cost_time += cost

    logger.info("\n" + "="*40)
    logger.info(f"✅ 测试完成！总合成耗时: {total_cost_time:.3f}s")
    logger.info("请检查 `output_audio/` 目录下的音频，评估声音拟真度和质量。")

if __name__ == "__main__":
    main()

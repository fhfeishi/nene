# coding=utf-8
# kokoro tts 

import time
import torch
import numpy as np
import re
import os
import threading
import queue
import pyaudio
import warnings
from loguru import logger 

# 屏蔽底层库烦人的告警信息，保持控制台整洁
warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"

try:
    from kokoro import KPipeline
except ImportError:
    logger.info("❌ 请先安装依赖: pip install kokoro soundfile")
    exit()

class AudioPlayer:
    """音频流式播放器"""
    def __init__(self, sample_rate=24000):
        self.sample_rate = sample_rate
        self.p = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self.is_playing = True
        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()

    def _def_play_loop(self):
        stream = self.p.open(format=pyaudio.paFloat32,
                            channels=1,
                            rate=self.sample_rate,
                            output=True)
        while self.is_playing:
            try:
                data = self.queue.get(timeout=1)
                if data is not None:
                    # 关键修复：确保将 PyTorch Tensor 转换为 NumPy 数组
                    if isinstance(data, torch.Tensor):
                        data = data.detach().cpu().numpy()
                    stream.write(data.astype(np.float32).tobytes())
                self.queue.task_done()
            except queue.Empty:
                continue
        stream.stop_stream()
        stream.close()
        
    _play_loop = _def_play_loop 

    def add_to_queue(self, audio_data):
        self.queue.put(audio_data)

class TextChunker:
    """文本分块器"""
    def __init__(self):
        # 遇到逗号也进行切分，进一步压榨 TTFA (首字发声时间)
        self.split_pattern = re.compile(r'([。！？；，,!?;])')

    def chunk_stream(self, token_stream):
        buffer = ""
        for token in token_stream:
            buffer += token
            if self.split_pattern.search(token):
                yield buffer.strip()
                buffer = ""
        if buffer.strip():
            yield buffer.strip()

class KokoroTTSController:
    """Kokoro-82M 控制器"""
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[Kokoro Benchmark] 正在加载 Kokoro 模型到 {self.device.upper()}...")
        t0 = time.time()
        
        # 传入 repo_id 消除警告
        kwargs = {
            "lang_code": 'z', 
            "repo_id": 'hexgrad/Kokoro-82M'
        }
        
        self.pipeline = KPipeline(**kwargs)
        
        logger.info(f"[Kokoro Benchmark] 模型加载完成，耗时: {time.time() - t0:.2f}s")
        self._warmup()

    def _warmup(self):
        logger.info("[Kokoro Benchmark] 正在预热...")
        # 静默预热
        list(self.pipeline("测试", voice='zf_xiaoxiao', speed=1.0))
        if self.device == "cuda":
            torch.cuda.synchronize()
        logger.info("[Kokoro Benchmark] 预热完成。")

    def generate(self, text, chunk_idx, voice='zf_xiaoxiao'):
        logger.info(f"\n[推理中] Chunk {chunk_idx}: {text}")
        
        if self.device == "cuda":
            torch.cuda.synchronize()
        t0 = time.time()
        
        generator = self.pipeline(text, voice=voice, speed=1.0)
        
        audio_data = None
        for gs, ps, audio in generator:
            audio_data = audio
            break 
            
        if audio_data is None:
            return None, 24000
            
        if self.device == "cuda":
            torch.cuda.synchronize()
        cost_time = time.time() - t0
        
        sample_rate = 24000
        audio_duration = len(audio_data) / sample_rate
        rtf = cost_time / audio_duration if audio_duration > 0 else 0
        
        status = "🟢 实时" if rtf < 1 else "🔴 延迟 (RTF > 1)"
        logger.info(f"[推理完成] 耗时: {cost_time:.3f}s | 时长: {audio_duration:.2f}s | RTF: {rtf:.3f} [{status}]")
        
        return audio_data, sample_rate

def main():
    TEST_TEXT = "你好，我是 nene。这次我换上了全新的 Kokoro 引擎。你可以明显感觉到，我的响应速度有了质的飞跃。就算文本被切得非常碎，我也能快速连贯地发声。"
    
    try:
        tts_controller = KokoroTTSController()
    except Exception as e:
        logger.info(f"❌ 加载出错，请检查配置。\n详细报错: {e}")
        return

    player = AudioPlayer(sample_rate=24000)
    chunker = TextChunker()
    
    def mock_llm_stream():
        for char in TEST_TEXT:
            yield char
            time.sleep(0.05)
            
    logger.info("\n>>> 开始 Kokoro-82M 流式语音测试 (按 Ctrl+C 停止) <<<")
    
    sentences = chunker.chunk_stream(mock_llm_stream())
    
    for i, sentence in enumerate(sentences):
        # 官方可选中文音色：zf_xiaoxiao (女声), zf_xiaoyi (女声), zm_yunjian (男声)
        audio, sr = tts_controller.generate(sentence, i, voice='zf_xiaoxiao')
        if audio is not None:
            player.add_to_queue(audio)

    player.queue.join()
    logger.info("\n>>> 所有音频播放完毕 <<<")

if __name__ == "__main__":
    main()
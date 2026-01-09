# app/components/tts/component.py 

from app.components.base import TTSModel
# edge-tts MicroSoft
import edge_tts

import re 
import time 
import asyncio
import logging 
import threading
from typing import Optional, List, Any, Dict, AsyncGenerator 


logger = logging.getLogger(__name__)

class EdgeTTS(TTSModel):
    """
    Edge TTS 文本转语音类 - 使用微软Edge的在线TTS服务
    
    特性：
    - 支持同步/异步两种调用方式
    - 支持流式合成（按句子分割）
    - 支持单句快速合成（用于RAG流式输出）
    - 内置句子分割器，智能处理中英文标点
    
    性能说明：
    - Edge-TTS 是微软的云端TTS服务，延迟约200-500ms
    - 通过流式合成 + 预加载，可实现近乎实时的语音输出
    """
    # 中英文句子结束标点
    SENTENCE_ENDINGS = re.compile(r'(?<=[。！？.!?;；])\s*')
    
    # 可用的中文语音列表（常用）
    CHINESE_VOICES = {
        "晓晓（女）": "zh-CN-XiaoxiaoNeural",       # 默认，自然流畅
        "云希（男）": "zh-CN-YunxiNeural",          # 男声，新闻播报风格
        "晓依（女）": "zh-CN-XiaoyiNeural",         # 温柔女声
        "云健（男）": "zh-CN-YunjianNeural",        # 运动解说风格
        "晓辰（女）": "zh-CN-XiaochenNeural",       # 活泼女声
        "晓涵（女）": "zh-CN-XiaohanNeural",        # 情感丰富
        "晓墨（女）": "zh-CN-XiaomoNeural",         # 故事讲述风格
        "晓秋（女）": "zh-CN-XiaoqiuNeural",        # 客服风格
        "晓睿（女）": "zh-CN-XiaoruiNeural",        # 自信女声
        "晓双（女）": "zh-CN-XiaoshuangNeural",     # 儿童语音
        "晓萱（女）": "zh-CN-XiaoxuanNeural",       # 主持人风格
        "晓颜（女）": "zh-CN-XiaoyanNeural",        # 文静女声
        "晓悠（女）": "zh-CN-XiaoyouNeural",        # 儿童语音
        "云枫（男）": "zh-CN-YunfengNeural",        # 情感男声
        "云皓（男）": "zh-CN-YunhaoNeural",         # 广告风格
        "云夏（男）": "zh-CN-YunxiaNeural",         # 男童语音
        "云扬（男）": "zh-CN-YunyangNeural",        # 新闻播报
        "云泽（男）": "zh-CN-YunzeNeural",          # 纪录片风格
    }
    
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+10%", volume: str = "+0%"):
        """
        初始化 EdgeTTS
        
        Args:
            voice: 默认使用的语音。例如 "zh-CN-XiaoxiaoNeural" (中文女声)
            rate: 语速调整。例如 "+10%" (加快10%), "-10%" (减慢10%)
            volume: 音量调整。例如 "+10%" (增大10%), "-10%" (减小10%)
        """
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self._available_voices: Optional[List[Dict[str, Any]]] = None
        self._voices_lock = threading.Lock()
        self._loop = None
        
        logger.info(f"EdgeTTS 实例已创建，默认语音: {voice}, 语速: {rate}, 音量: {volume}")

    def _get_loop(self):
        """获取或创建事件循环，确保异步操作有执行环境"""
        try:
            # 尝试获取当前线程的运行中循环
            return asyncio.get_running_loop()
        except RuntimeError:
            # 如果没有运行中的循环，则创建一个新的
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop
        
    async def _synthesize_async(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        异步合成语音（核心方法）
        
        Args:
            text: 要合成的文本
            voice: 可选，指定语音
            
        Returns:
            bytes: 音频数据（MP3格式）
        """
        if not text or not text.strip():
            raise ValueError("输入文本不能为空")

        target_voice = voice or self.voice
        
        logger.info(f"[EdgeTTS] 开始合成: '{text[:50]}...', voice={target_voice}")
        start_time = time.time()

        try:
            communicate = edge_tts.Communicate(
                text, 
                voice=target_voice,
                rate=self.rate,
                volume=self.volume
            )
            
            # 收集音频数据
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if not audio_data:
                raise RuntimeError("EdgeTTS 未生成任何音频数据")

            elapsed = time.time() - start_time
            logger.info(f"[EdgeTTS] 合成完成: {len(audio_data)} bytes, 耗时: {elapsed:.2f}s")
            return audio_data

        except Exception as e:
            logger.error(f"[EdgeTTS] 合成失败: {e}", exc_info=True)
            if "No such voice" in str(e):
                raise ValueError(f"无效的语音名称: {target_voice}") from e
            raise RuntimeError(f"EdgeTTS 合成错误: {e}") from e
        
    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        将文本转换为语音并返回音频数据（同步接口）
        
        Args:
            text: 要转换的文本
            voice: 指定语音（可选，如果为None则使用实例默认语音）
        
        Returns:
            音频数据（通常是MP3或WEBM格式的字节流）
        """
        loop = self._get_loop()
        
        # 如果当前线程正在运行事件循环（例如在Jupyter Notebook或另一个异步环境中）
        # 我们需要将任务提交到该循环中执行
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._synthesize_async(text, voice), loop)
            return future.result(timeout=120) # 设置超时
        else:
            # 如果没有运行中的循环，直接运行直到完成
            return loop.run_until_complete(self._synthesize_async(text, voice))

    async def synthesize_sentence_async(self, sentence: str, voice: Optional[str] = None) -> bytes:
        """
        异步合成单个句子（用于流式TTS）
        
        这是流式TTS的核心方法，每个句子独立合成，实现边生成边播放
        
        Args:
            sentence: 单个句子文本
            voice: 可选，指定语音
            
        Returns:
            bytes: 音频数据
        """
        return await self._synthesize_async(sentence, voice)

    async def stream_sentences_async(
        self, 
        text_generator: AsyncGenerator[str, None],
        voice: Optional[str] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        流式合成语音（核心流式方法）
        
        从文本生成器读取文本，按句子分割后逐句合成语音
        实现真正的流式语音输出：文字一边生成，语音一边合成播放
        
        Args:
            text_generator: 异步文本生成器（来自LLM的流式输出）
            voice: 可选，指定语音
            
        Yields:
            bytes: 每个句子的音频数据
            
        使用示例:
            async for audio_chunk in tts.stream_sentences_async(llm_stream):
                await websocket.send(audio_chunk)
        """
        target_voice = voice or self.voice
        sentence_buffer = ""
        
        logger.info(f"[EdgeTTS] 开始流式合成, voice={target_voice}")

        try:
            async for text_chunk in text_generator:
                if not text_chunk:
                    continue
                
                sentence_buffer += text_chunk
                
                # 查找并提取完整的句子
                while True:
                    match = self.SENTENCE_ENDINGS.search(sentence_buffer)
                    if not match:
                        break
                    
                    # 提取完整句子
                    sentence = sentence_buffer[:match.end()].strip()
                    sentence_buffer = sentence_buffer[match.end():]
                    
                    if sentence:
                        logger.debug(f"[EdgeTTS] 合成句子: '{sentence[:30]}...'")
                        try:
                            audio_data = await self._synthesize_async(sentence, target_voice)
                            yield audio_data
                        except Exception as e:
                            logger.error(f"[EdgeTTS] 句子合成失败: {e}")
                            # 继续处理下一个句子，不中断整个流程
            
            # 处理缓冲区中剩余的文本
            if sentence_buffer.strip():
                logger.debug(f"[EdgeTTS] 合成末尾文本: '{sentence_buffer.strip()[:30]}...'")
                try:
                    audio_data = await self._synthesize_async(sentence_buffer.strip(), target_voice)
                    yield audio_data
                except Exception as e:
                    logger.error(f"[EdgeTTS] 末尾文本合成失败: {e}")
            
            logger.info("[EdgeTTS] 流式合成完成")

        except Exception as e:
            logger.error(f"[EdgeTTS] 流式合成错误: {e}", exc_info=True)
            raise

    def split_into_sentences(self, text: str) -> List[str]:
        """
        将文本分割为句子
        
        用于预处理文本，支持中英文混合标点
        
        Args:
            text: 待分割的文本
            
        Returns:
            List[str]: 句子列表
        """
        if not text:
            return []
        
        sentences = []
        last_end = 0
        
        for match in self.SENTENCE_ENDINGS.finditer(text):
            sentence = text[last_end:match.end()].strip()
            if sentence:
                sentences.append(sentence)
            last_end = match.end()
        
        # 添加剩余的文本
        remaining = text[last_end:].strip()
        if remaining:
            sentences.append(remaining)
        
        return sentences

    # =========================================================================
    # 配置和信息方法
    # =========================================================================

    def set_voice(self, voice: str):
        """设置默认语音"""
        self.voice = voice
        logger.info(f"EdgeTTS voice updated to: {voice}")

    def set_rate(self, rate: str):
        """设置默认语速"""
        self.rate = rate
        logger.info(f"EdgeTTS rate updated to: {rate}")

    def set_volume(self, volume: str):
        """设置默认音量"""
        self.volume = volume
        logger.info(f"EdgeTTS volume updated to: {volume}")

    async def _get_voices_async(self) -> List[Dict[str, Any]]:
        """异步获取所有可用语音列表"""
        try:
            voices = await edge_tts.list_voices()
            return voices
        except Exception as e:
            logger.error(f"获取语音列表失败: {e}")
            return []

    def get_available_voices(self) -> List[Dict[str, Any]]:
        """获取所有可用的语音列表"""
        if self._available_voices is None:
            with self._voices_lock:
                if self._available_voices is None:
                    loop = self._get_loop()
                    if loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            self._get_voices_async(), loop
                        )
                        self._available_voices = future.result(timeout=30)
                    else:
                        self._available_voices = loop.run_until_complete(
                            self._get_voices_async()
                        )
        return self._available_voices

    @classmethod
    def get_chinese_voices(cls) -> Dict[str, str]:
        """获取常用中文语音列表"""
        return cls.CHINESE_VOICES.copy()


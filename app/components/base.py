# app/components/base.py

from typing import Callable, Optional, AsyncGenerator, List, Dict 
from abc import ABC, abstractmethod 


# base class: RAG system
class BaseRAG(ABC):
    """RAG 系统基类"""
    @abstractmethod
    async def astream(self, query: str, history: List[Dict]) -> AsyncGenerator[str, None]:
        """流式输出文本"""
        pass


# base class: TTS system
class BaseSTT(ABC):
    """
    语音转文本 STT 基类
    设计原则：全异步接口，防止阻塞主事件循环。
    """
    
    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """
        一次性识别整段音频（适用于普通多轮对话的录音上传）。
        """
        pass

    @abstractmethod
    async def start_streaming(self) -> None:
        """
        初始化并启动流式识别上下文。
        """
        pass

    @abstractmethod
    async def send_audio_frame(self, audio_frame: bytes) -> tuple[str, bool]:
        """
        发送流式音频帧并获取即时结果（适用于语音通话模式）。
        :return: (text, is_final) 返回当前识别的文本，以及是否是最终结果。
        """
        pass

    @abstractmethod
    async def force_break_sentence(self) -> str:
        """
        VAD 静默触发：强制断句并返回该句最终文本，清空上下文准备下一句。
        """
        pass

    @abstractmethod
    async def stop_streaming(self) -> str:
        """
        结束流式识别，处理残留缓冲区音频，返回最终文本并销毁上下文。
        """
        pass


class BaseTTS(ABC):
    """
    文本转语音 TTS 基类
    """
    
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        一次性合成整段文本为音频（适用于普通多轮对话的完整回复）。
        """
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        流式合成文本，生成一段音频片段就 yield 出去一次（适用于实时语音通话）。
        :return: 异步生成器，产出音频字节流
        """
        pass

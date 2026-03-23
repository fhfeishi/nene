# app/components/base.py

from typing import Callable, Optional,AsyncGenerator, List, Dict 
from abc import ABC, abstractmethod 


# base class: RAG system
class BaseRAG(ABC):
    """RAG 系统基类"""
    @abstractmethod
    async def astream(self, query: str, history: List[Dict]) -> AsyncGenerator[str, None]:
        """流式输出文本"""
        pass


# base class: TTS system
class BaseTTS(ABC):
    """文本转语音 TTS 基类"""
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """音频转文字"""
        pass

# base class: STT system
class BaseSTT(ABC):
    """语音转文本 STT 基类"""
    
    @abstractmethod
    def transcribe(self, audio_data: bytes) -> str:
        """一次性识别整段音频"""
        pass

    def start_streaming(self, result_callback: Optional[Callable[[str, bool], None]] = None):
        """启动流式识别"""
        raise NotImplementedError("Streaming not implemented for this STT model")

    def send_audio_frame(self, audio_frame: bytes):
        """发送音频帧"""
        raise NotImplementedError("Streaming not implemented for this STT model")

    def stop_streaming(self) -> str:
        """停止流式识别"""
        raise NotImplementedError("Streaming not implemented for this STT model")



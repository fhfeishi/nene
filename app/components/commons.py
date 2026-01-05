# app/commons.py

from langchain_huggingface import HuggingFaceEmbeddings, ChatHuggingFace
from typing import Callable, Optional
from abc import ABC, abstractmethod 

# llm models 
def inst_llm():
    pass 


# embeding models 
def inst_embed():
    pass 

# 语音转文本基类
class STTModel(ABC):
    """语音转文本基类"""
    
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
    

# 文本转语音基类
class TTSModel(ABC):
    """文本转语音基类"""
    
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """将文本转换为语音"""
        pass




# app/base.py

from typing import Callable, Optional,AsyncGenerator, List, Dict 
from abc import ABC, abstractmethod 
import os 


class BaseRAG(ABC):
    @abstractmethod
    async def astream(self, query: str, history: List[Dict]) -> AsyncGenerator[str, None]:
        """流式输出文本"""
        pass

class BaseTTS(ABC):
    """文本转语音基类"""
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """音频转文字"""
        pass

class BaseSTT(ABC):
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


# llm models 
def inst_llm():
    pass 


# embeding models 
def inst_embed():
    pass 


# instance : huggingface cached model, modelscope cached model 
# ── 路径配置 ──────────────────────────────────────────────
MODELSCOPE_ROOT = r"E:\local_models\modelscope\models"
HUGGINGFACE_ROOT = r"E:\local_models\huggingface\cache\hub"

def get_modelscope_path(model_name: str) -> str:
    """modelscope 路径直接拼接即可，如 'Qwen/Qwen3.5-2B'"""
    return os.path.normpath(os.path.join(MODELSCOPE_ROOT, model_name))

def get_huggingface_path(model_name: str) -> str:
    """
    hf 缓存路径需要找到 snapshots 下最新的那个 hash 目录
    model_name 格式: 'Qwen/Qwen3.5-2B'  →  目录名: 'models--Qwen--Qwen3.5-2B'
    """
    dir_name = "models--" + model_name.replace("/", "--")
    snapshots_dir = os.path.join(HUGGINGFACE_ROOT, dir_name, "snapshots")
    
    # 取 snapshots 下第一个（通常只有一个）hash 目录
    hashes = os.listdir(snapshots_dir)
    if not hashes:
        raise FileNotFoundError(f"No snapshots found in {snapshots_dir}")
    
    return os.path.normpath(os.path.join(snapshots_dir, hashes[0]))



    




# 定义交互协议 (Schemas)
# app/schemas/protocol.py
# 前后端必须严格遵守同一套 JSON 结构。

from enum import Enum 
from typing import Optional, Any, Dict 
from pydantic import BaseModel, Field
import time 

# 消息类型枚举，防止前端拼写错误
class MessageType(str, Enum):
    # 前端发来的
    CHAT_TEXT = "chat.text"          # 文本对话
    CHAT_AUDIO_START = "chat.audio.start" 
    CHAT_AUDIO_CHUNK = "chat.audio.chunk"
    CHAT_AUDIO_END = "chat.audio.end"
    CONTROL_STOP = "control.stop"    # 打断/停止
    PING = "ping"

    # 后端发出的
    RAG_CHUNK = "rag.chunk"          # RAG 流式文字
    RAG_END = "rag.end"              # RAG 结束（带引用源）
    TTS_CHUNK = "tts.chunk"          # TTS 音频流
    ERROR = "system.error"
    PONG = "pong"

# 统一的 WebSocket 消息信封
class WSMessage(BaseModel):
    type: MessageType
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    request_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


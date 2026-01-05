"""
# app/server.py
WebSocket服务器 - 支持流式输出的RAG聊天服务

    - 流式TTS的架构：LLM流式输出 -> 句子分割 -> Edge-TTS合成 -> 发送音频
    - 中断机制：新请求会中断旧请求的TTS，但文字继续生成

LLM生成文本 → 后端句子分割 → EdgeTTS合成 → 发送音频 → 前端播放
              ↑ 统一在后端处理
              ↑ 异步队列机制
              ↑ 按序播放保证流畅
"""
import asyncio
import time
import json
import logging
import os
import uuid
import base64
import wave
import io
from typing import Dict, List, Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_rag_config
from components.rag.component import build_chain, load_retriever, answer_question
from components.api import VoiceInterface, IicRealtimeSTT, EdgeTTS


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================
class ChatMessage(BaseModel):
    question: str
    chat_history: Optional[List[Dict]] = []
    session_id: Optional[str] = None

class VoiceTranscribeRequest(BaseModel):
    audio_data: str
    session_id: Optional[str] = None

# =============================================================================
# FastAPI 应用初始化
# =============================================================================

app = FastAPI(title="博物馆RAG WebSocket服务", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# 全局变量
# =============================================================================

# RAG相关
rag_chain = None
retriever = None

# 语音相关
voice_interface: Optional[VoiceInterface] = None
edge_tts_instance: Optional[EdgeTTS] = None

# 会话管理
active_connections: Dict[str, WebSocket] = {}
user_sessions: Dict[str, Dict] = {}

# 会话状态：用于中断机制
# 结构: {session_id: {current_request_id, is_interrupted}}
session_states: Dict[str, Dict] = {}


# =============================================================================
# 初始化函数
# =============================================================================

def initialize_rag_system() -> bool:
    """初始化RAG系统"""
    global rag_chain, retriever, voice_interface, edge_tts_instance
    
    try:
        logger.info("正在初始化RAG系统...")
        rag_chain, retriever = build_chain()
        logger.info("✅ RAG系统初始化成功")
        
        # 初始化语音系统
        logger.info("正在初始化语音系统...")
        voice_interface = create_voice_interface()
        
        # 单独初始化全局EdgeTTS实例（用于流式TTS）
        edge_tts_instance = EdgeTTS()
        logger.info("✅ 全局EdgeTTS实例初始化成功")
        
        return True
    except Exception as e:
        logger.error(f"❌ RAG系统初始化失败: {e}")
        return False


def create_voice_interface() -> Optional[VoiceInterface]:
    """创建语音接口"""
    try:
        stt = IicRealtimeSTT()
        tts = EdgeTTS()
        
        voice_interface = VoiceInterface(
            stt_model=stt, 
            tts_model=tts, 
            voice="zh-CN-XiaoxiaoNeural"
        )
        
        logger.info(f"✅ 语音接口初始化成功")
        logger.info(f"   STT: {type(voice_interface.stt).__name__}")
        logger.info(f"   TTS: {type(voice_interface.tts).__name__}")
        
        return voice_interface
    except Exception as e:
        logger.error(f"❌ 语音接口创建失败: {e}", exc_info=True)
        return None


# =============================================================================
# 工具函数
# =============================================================================

def extract_pcm_from_wav(wav_data: bytes) -> bytes:
    """从WAV文件中提取PCM数据"""
    try:
        wav_buffer = io.BytesIO(wav_data)
        with wave.open(wav_buffer, 'rb') as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            
            logger.debug(f"WAV: {sample_rate}Hz, {channels}ch, {sample_width*8}bit")
            
            pcm_data = wav_file.readframes(wav_file.getnframes())
            return pcm_data
    except Exception as e:
        logger.error(f"提取PCM失败: {e}")
        return wav_data


def format_chat_history(chat_history: List[Dict]) -> str:
    """格式化聊天历史"""
    if not chat_history:
        return ""
    
    formatted = []
    for msg in chat_history[-10:]:  # 只保留最近10条
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        prefix = "用户: " if role == 'user' else "助手: "
        formatted.append(prefix + content)
    
    return "\n".join(formatted)


async def transcribe_audio_local(audio_data: str) -> str:
    """使用本地STT进行语音转文字"""
    try:
        if not voice_interface:
            return "语音系统未初始化"
        
        audio_bytes = base64.b64decode(audio_data)
        text = voice_interface.stt.transcribe(audio_bytes)
        
        return text if text else "未识别到语音内容"
    except Exception as e:
        logger.error(f"语音转写错误: {e}")
        return f"语音识别失败: {str(e)}"


# =============================================================================
# 流式响应核心函数（优化版）
# =============================================================================

async def stream_response(
    question: str,
    chat_history: List[Dict],
    websocket: WebSocket,
    auto_tts: bool = False,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None
):
    """
    流式响应生成 - 集成流式TTS（优化版）
    
    核心逻辑：
    1. LLM流式生成文本 -> 发送文本chunk到前端
    2. 同时将文本累积，按句子分割
    3. 每个完整句子立即发送到Edge-TTS合成
    4. 合成的音频实时发送到前端播放
    
    中断机制：
    - 如果 session_states[session_id]["is_interrupted"] 为 True，停止TTS
    - 文字生成不受影响，继续完成
    
    Args:
        question: 用户问题
        chat_history: 聊天历史
        websocket: WebSocket连接
        auto_tts: 是否自动TTS（语音输入时为True）
        request_id: 请求ID（用于中断检测）
        session_id: 会话ID
    """
    try:
        logger.info(f"[{session_id}] stream_response 开始, 接收到的 request_id: {request_id}")
        # 发送开始信号
        await websocket.send_text(json.dumps({
            "type": "response_start",
            "message": "开始生成回答...",
            "requestId": request_id
        }))
        logger.info(f"[{session_id}] 已发送 response_start, requestId: {request_id}")
        # 检查RAG系统
        if not rag_chain or not retriever:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "RAG系统未初始化"
            }))
            return
        
        # =====================================================================
        # 第1步：向量检索
        # =====================================================================
        docs = retriever.invoke(question)
        
        if not docs:
            await websocket.send_text(json.dumps({
                "type": "response_end",
                "fullResponse": "抱歉，我不确定，可能未在知识库中找到相关内容。",
                "timestamp": datetime.now().isoformat(),
                "sources": [],
                "requestId": request_id
            }))
            return
        
        # 准备来源信息
        sources = []
        for d in docs:
            source = d.metadata.get("source", "unknown")
            page = d.metadata.get("page")
            chunk_id = d.metadata.get("chunk_id")
            locator = f"page {page}" if page is not None else f"chunk {chunk_id}"
            sources.append({"source": source, "locator": locator})

        # =====================================================================
        # 第2步：初始化流式TTS状态
        # =====================================================================
        
        # 句子缓冲区：累积文本直到遇到句子结束符
        sentence_buffer = ""
        
        # TTS任务队列：存储待合成的句子
        tts_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        
        # TTS完成标志
        tts_done = asyncio.Event()
        
        # 检查是否应该中断TTS
        def should_interrupt_tts() -> bool:
            if not session_id:
                return False
            state = session_states.get(session_id, {})
            return state.get("is_interrupted", False)

        # =====================================================================
        # 第3步：定义TTS消费者任务
        # =====================================================================
        
        async def tts_consumer():
            """
            TTS消费者：从队列中取出句子，合成语音并发送到前端
            
            这是一个独立的协程，与LLM生成并行执行
            """
            if not auto_tts or not edge_tts_instance:
                tts_done.set()
                return
            
            logger.info(f"[{session_id}] TTS消费者启动")
            
            try:
                while True:
                    # 检查是否中断
                    if should_interrupt_tts():
                        logger.info(f"[{session_id}] TTS被中断，停止合成")
                        break
                    
                    # 从队列获取句子（带超时，避免死锁）
                    try:
                        sentence = await asyncio.wait_for(
                            tts_queue.get(), 
                            timeout=0.5
                        )
                    except asyncio.TimeoutError:
                        continue
                    
                    # None 表示结束信号
                    if sentence is None:
                        logger.info(f"[{session_id}] TTS收到结束信号")
                        break
                    
                    # 再次检查中断
                    if should_interrupt_tts():
                        logger.info(f"[{session_id}] TTS被中断（合成前）")
                        break
                    
                    # 合成语音
                    try:
                        logger.debug(f"[{session_id}] 合成句子: {sentence[:30]}...")
                        audio_data = await edge_tts_instance.synthesize_sentence_async(
                            sentence
                        )
                        
                        # 发送音频到前端
                        if audio_data and not should_interrupt_tts():
                            await websocket.send_text(json.dumps({
                                "type": "audio_chunk",
                                "audio": base64.b64encode(audio_data).decode('utf-8'),
                                "requestId": request_id
                            }))
                            logger.debug(f"[{session_id}] 音频已发送: {len(audio_data)} bytes")
                            
                    except Exception as e:
                        logger.error(f"[{session_id}] TTS合成失败: {e}")
                        # 继续处理下一个句子
                        
            except asyncio.CancelledError:
                logger.info(f"[{session_id}] TTS消费者被取消")
            except Exception as e:
                logger.error(f"[{session_id}] TTS消费者错误: {e}", exc_info=True)
            finally:
                tts_done.set()
                logger.info(f"[{session_id}] TTS消费者退出")

        # =====================================================================
        # 第4步：启动TTS消费者任务
        # =====================================================================
        
        tts_task = asyncio.create_task(tts_consumer())

        # =====================================================================
        # 第5步：LLM流式生成 + 句子分割 + 推送到TTS队列
        # =====================================================================
        
        response_text = ""
        
        # 句子结束符正则
        import re
        sentence_endings = re.compile(r'(?<=[。！？.!?;；])\s*')
        
        try:
            logger.info(f"[{session_id}] LLM开始生成...")
            
            for chunk in rag_chain.stream({
                "question": question,
                "chat_history": format_chat_history(chat_history)
            }):
                # 检查是否被中断（影响整个生成）
                if session_id and session_states.get(session_id, {}).get("is_interrupted"):
                    logger.info(f"[{session_id}] LLM生成被中断")
                    break
                
                if not chunk:
                    continue
                
                # 累积完整响应
                response_text += chunk
                
                # 发送文本chunk到前端（即时显示）
                await websocket.send_text(json.dumps({
                    "type": "response_chunk",
                    "content": chunk,
                    "requestId": request_id
                }))
                
                # 如果启用了自动TTS，进行句子分割
                if auto_tts:
                    sentence_buffer += chunk
                    
                    # 查找完整的句子
                    while True:
                        match = sentence_endings.search(sentence_buffer)
                        if not match:
                            break
                        
                        # 提取完整句子
                        sentence = sentence_buffer[:match.end()].strip()
                        sentence_buffer = sentence_buffer[match.end():]
                        
                        if sentence:
                            # 推送到TTS队列
                            await tts_queue.put(sentence)
                            logger.debug(f"[{session_id}] 句子入队: {sentence[:30]}...")
                            
        except Exception as e:
            logger.error(f"[{session_id}] LLM生成错误: {e}", exc_info=True)
        finally:
            # 处理剩余的缓冲区文本
            if auto_tts and sentence_buffer.strip():
                await tts_queue.put(sentence_buffer.strip())
            
            # 发送结束信号到TTS队列
            await tts_queue.put(None)
            logger.info(f"[{session_id}] LLM生成完成")

        # =====================================================================
        # 第6步：等待TTS完成
        # =====================================================================
        
        try:
            # 等待TTS完成，但设置超时
            await asyncio.wait_for(tts_done.wait(), timeout=60)
        except asyncio.TimeoutError:
            logger.warning(f"[{session_id}] 等待TTS超时")
            tts_task.cancel()

        # =====================================================================
        # 第7步：发送响应结束信号
        # =====================================================================
        
        is_interrupted = (
            session_id and 
            session_states.get(session_id, {}).get("is_interrupted", False)
        )
        
        await websocket.send_text(json.dumps({
            "type": "response_end",
            "fullResponse": response_text,
            "timestamp": datetime.now().isoformat(),
            "sources": sources,
            "requestId": request_id,
            "isInterrupted": is_interrupted
        }))
        
        logger.info(f"[{session_id}] 流式响应完成, 中断={is_interrupted}")

    except Exception as e:
        logger.error(f"流式响应错误: {e}", exc_info=True)
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"生成回答时发生错误: {str(e)}"
        }))


# =============================================================================
# 事件处理
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("正在启动WebSocket服务器...")
    if not initialize_rag_system():
        logger.error("RAG系统初始化失败，服务器可能无法正常工作")


# =============================================================================
# WebSocket端点：主聊天
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """主WebSocket端点：处理文本和语音消息"""
    await websocket.accept()
    
    session_id = str(uuid.uuid4())
    active_connections[session_id] = websocket
    user_sessions[session_id] = {
        "chat_history": [],
        "created_at": datetime.now()
    }
    session_states[session_id] = {
        "current_request_id": None,
        "is_interrupted": False
    }
    
    logger.info(f"新WebSocket连接: {session_id}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            print("Get message:", message)
            # -----------------------------------------------------------------
            # 处理文本消息
            # -----------------------------------------------------------------
            if message["type"] == "send_message":
                logger.info(f"[{session_id}] 收到 send_message, 原始数据: {message}")
                question = message.get("question", "") or message.get("message", "")
                request_id = message.get("requestId")
                logger.info(f"[{session_id}] 解析出的 request_id: {request_id}")
                if not request_id:
                    # 如果前端没有提供，则生成一个唯一的ID
                    request_id = str(uuid.uuid4())
                    logger.warning(f"[{session_id}] 前端未提供requestId，后端生成: {request_id}")
                logger.info(f"[{session_id}] 解析出的 request_id: {request_id}")
                
                # 中断旧请求的TTS
                old_request_id = session_states[session_id].get("current_request_id")
                if request_id and old_request_id and old_request_id != request_id:
                    logger.info(f"[{session_id}] 新请求{request_id}，取消旧请求{old_request_id}的TTS")
                    session_states[session_id]["is_interrupted"] = True
                
                # 更新会话状态
                session_states[session_id]["current_request_id"] = request_id
                session_states[session_id]["is_interrupted"] = False
                
                # 添加到历史
                user_sessions[session_id]["chat_history"].append({
                    "role": "user",
                    "content": question,
                    "timestamp": datetime.now().isoformat()
                })
                
                # 生成响应（默认启用TTS）
                await stream_response(
                    question,
                    user_sessions[session_id]["chat_history"],
                    websocket,
                    auto_tts=True,
                    request_id=request_id,
                    session_id=session_id
                )
                
            # -----------------------------------------------------------------
            # 处理语音消息
            # -----------------------------------------------------------------
            elif message["type"] == "send_audio":
                audio_data = message.get("audio_data", "")
                logger.info(f"收到语音消息: {len(audio_data)} 字符")
                
                if voice_interface:
                    try:
                        # 语音识别
                        transcribed_text = await transcribe_audio_local(audio_data)
                        
                        # 发送识别结果
                        await websocket.send_text(json.dumps({
                            "type": "transcription",
                            "text": transcribed_text
                        }))
                        
                        # 如果识别成功，自动处理
                        if transcribed_text and transcribed_text.strip():
                            user_sessions[session_id]["chat_history"].append({
                                "role": "user",
                                "content": transcribed_text,
                                "timestamp": datetime.now().isoformat(),
                                "isVoice": True
                            })
                            
                            # 生成响应（语音输入自动启用TTS）
                            await stream_response(
                                transcribed_text,
                                user_sessions[session_id]["chat_history"],
                                websocket,
                                auto_tts=True
                            )
                    except Exception as e:
                        logger.error(f"语音处理失败: {e}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"语音识别失败: {str(e)}"
                        }))
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "语音系统未初始化"
                    }))
                    
    except WebSocketDisconnect:
        logger.info(f"WebSocket连接断开: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket处理错误: {e}")
    finally:
        # 清理
        active_connections.pop(session_id, None)
        user_sessions.pop(session_id, None)
        session_states.pop(session_id, None)


# =============================================================================
# WebSocket端点：实时语音识别
# =============================================================================

@app.websocket("/ws/realtime-speech")
async def realtime_speech_endpoint(websocket: WebSocket):
    """实时语音识别WebSocket端点"""
    await websocket.accept()
    client_id = f"realtime_speech_{id(websocket)}"
    logger.info(f"[{client_id}] 实时语音识别客户端连接")
    
    stt_instance = None
    streaming_started = False
    result_queue = asyncio.Queue()

    try:
        while True:
            message = await websocket.receive_text()
            
            try:
                data = json.loads(message)
                message_type = data.get('type')
                
                # 开始流式识别
                if message_type == 'start':
                    if not voice_interface or not voice_interface.stt:
                        await websocket.send_text(json.dumps({
                            'type': 'error',
                            'error': '语音识别服务未初始化'
                        }))
                        continue

                    stt_instance = IicRealtimeSTT()
                    
                    # 状态维护
                    state = {
                        "full_text": "",
                        "last_text": "",
                        "last_recog_time": None
                    }
                    
                    main_loop = asyncio.get_event_loop()
                    
                    def merge_text(full_text: str, last_text: str, new_text: str):
                        """合并流式文本，避免重复"""
                        if not last_text:
                            return full_text + new_text, new_text
                        
                        # 计算公共前缀
                        prefix_len = 0
                        for a, b in zip(last_text, new_text):
                            if a == b:
                                prefix_len += 1
                            else:
                                break
                        
                        append_part = new_text[prefix_len:]
                        return full_text + append_part, new_text
                    
                    def result_callback(text: str, is_final: bool):
                        if not text or not text.strip():
                            return
                        asyncio.run_coroutine_threadsafe(
                            result_queue.put({
                                'type': 'final' if is_final else 'interim',
                                'text': text.strip()
                            }),
                            main_loop
                        )
                    
                    stt_instance.start_streaming(result_callback=result_callback)
                    streaming_started = True
                    
                    await websocket.send_text(json.dumps({
                        'type': 'status',
                        'message': '流式识别已启动'
                    }))
                    
                    # 结果处理任务
                    async def process_results():
                        SILENCE_TIMEOUT = 2.0
                        should_continue = True
                        
                        while should_continue:
                            try:
                                result = await asyncio.wait_for(
                                    result_queue.get(), 
                                    timeout=0.5
                                )
                                
                                new_text = result.get('text', '')
                                state['full_text'], state['last_text'] = merge_text(
                                    state['full_text'], state['last_text'], new_text
                                )
                                state['last_recog_time'] = time.time()
                                
                                await websocket.send_text(json.dumps({
                                    'type': 'interim',
                                    'text': state['full_text']
                                }))
                                
                            except asyncio.TimeoutError:
                                # VAD检测
                                if (streaming_started 
                                    and state['full_text'] 
                                    and state['last_recog_time']
                                    and (time.time() - state['last_recog_time']) >= SILENCE_TIMEOUT):
                                    
                                    if stt_instance:
                                        final_part = stt_instance.force_final_and_reset()
                                        if final_part:
                                            state['full_text'], state['last_text'] = merge_text(
                                                state['full_text'], state['last_text'], final_part
                                            )
                                    
                                    await websocket.send_text(json.dumps({
                                        'type': 'final',
                                        'text': state['full_text']
                                    }))
                                    
                                    state['full_text'] = ""
                                    state['last_text'] = ""
                                    state['last_recog_time'] = None
                                
                                if not streaming_started and result_queue.empty():
                                    should_continue = False
                                    
                            except Exception as e:
                                logger.error(f"[{client_id}] 处理结果失败: {e}")
                                if "websocket" in str(e).lower():
                                    should_continue = False
                    
                    result_task = asyncio.create_task(process_results())
                
                # 处理音频数据
                elif message_type == 'audio':
                    audio_base64 = data.get('audio', '')
                    if audio_base64 and streaming_started and stt_instance:
                        audio_bytes = base64.b64decode(audio_base64)
                        
                        # 检查是否是WAV格式
                        if len(audio_bytes) > 4 and audio_bytes[:4] == b'RIFF':
                            audio_bytes = extract_pcm_from_wav(audio_bytes)
                        
                        stt_instance.send_audio_frame(audio_bytes)
                
                # 结束识别
                elif message_type == 'end':
                    if streaming_started and stt_instance:
                        final_text = stt_instance.stop_streaming()
                        streaming_started = False
                        
                        if final_text and final_text.strip():
                            await websocket.send_text(json.dumps({
                                'type': 'final',
                                'text': final_text
                            }))
                    
                    await websocket.send_text(json.dumps({
                        'type': 'status',
                        'message': '语音识别已结束'
                    }))
                    
            except json.JSONDecodeError as e:
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'error': f'消息格式错误: {str(e)}'
                }))
                
    except WebSocketDisconnect:
        logger.info(f"[{client_id}] 实时语音识别客户端断开")
    except Exception as e:
        logger.error(f"[{client_id}] 实时语音识别错误: {e}")
    finally:
        if stt_instance:
            try:
                stt_instance.stop_streaming()
            except:
                pass


# =============================================================================
# WebSocket端点：单次TTS
# =============================================================================
@app.websocket("/ws/tts")
async def tts_endpoint(websocket: WebSocket):
    """
    TTS WebSocket端点 - 支持长连接模式
    
    协议：
    1. 客户端连接后可以发送多个请求
    2. 请求格式: {"text": "要合成的文本"} 或 {"type": "ping"}
    3. 响应格式: {"type": "audio", "audio": "base64"} 然后 {"type": "end"}
    4. 客户端发送 {"type": "close"} 或断开连接时结束
    """
    await websocket.accept()
    client_id = f"tts_{id(websocket)}"
    logger.info(f"[{client_id}] TTS客户端连接")
    
    try:
        while True:
            # 等待客户端消息
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
            except WebSocketDisconnect:
                logger.info(f"[{client_id}] 客户端主动断开")
                break
            except Exception as e:
                logger.error(f"[{client_id}] 接收消息失败: {e}")
                break
            
            msg_type = message.get('type', '')
            
            # ★ 处理ping消息（用于预热/保持连接）
            if msg_type == 'ping':
                await websocket.send_text(json.dumps({'type': 'pong'}))
                logger.debug(f"[{client_id}] 收到ping，回复pong")
                continue
            
            # ★ 处理关闭请求
            if msg_type == 'close':
                logger.info(f"[{client_id}] 收到关闭请求")
                break
            
            # ★ 处理TTS请求
            if message.get('text'):
                text = message['text']
                logger.info(f"[{client_id}] TTS请求: {len(text)} 字符")
                
                try:
                    # 使用Edge-TTS合成
                    if edge_tts_instance:
                        audio_data = await edge_tts_instance.synthesize_sentence_async(text)
                    elif voice_interface:
                        audio_data = voice_interface.tts.synthesize(text)
                    else:
                        raise RuntimeError("TTS实例未初始化")
                    if websocket.client_state.name == 'CONNECTED':
                        if audio_data:
                            await websocket.send_text(json.dumps({
                                'type': 'audio',
                                'audio': base64.b64encode(audio_data).decode('utf-8')
                            }))
                            logger.debug(f"[{client_id}] 音频已发送: {len(audio_data)} bytes")
                        
                        # 发送本次请求的结束标记
                        await websocket.send_text(json.dumps({'type': 'end'}))
                    else:
                        logger.warning(f"[{client_id}] 连接已断开，跳过发送音频")
                    
                except Exception as e:
                    logger.error(f"[{client_id}] TTS合成错误: {e}")
                    if websocket.client_state.name == 'CONNECTED':
                        await websocket.send_text(json.dumps({
                            'type': 'error',
                            'error': str(e)
                        }))
            else:
                logger.warning(f"[{client_id}] 无效请求: {message}")
                    
    except WebSocketDisconnect:
        logger.info(f"[{client_id}] TTS客户端断开")
    except Exception as e:
        logger.error(f"[{client_id}] TTS端点错误: {e}")
    finally:
        logger.info(f"[{client_id}] TTS连接关闭")


# =============================================================================
# HTTP端点
# =============================================================================
@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatMessage):
    """HTTP流式聊天端点（用于测试）"""
    async def generate():
        try:
            if not rag_chain or not retriever:
                yield f"data: {json.dumps({'error': 'RAG系统未初始化'})}\n\n"
                return
            
            docs = retriever.invoke(request.question)
            
            if not docs:
                yield f"data: {json.dumps({'content': '抱歉，我不确定。'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            for chunk in rag_chain.stream({
                "question": request.question,
                "chat_history": format_chat_history(request.chat_history)
            }):
                if chunk:
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"HTTP流式响应错误: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_connections": len(active_connections),
        "rag_ready": rag_chain is not None,
        "voice_ready": voice_interface is not None,
        "tts_ready": edge_tts_instance is not None
    }


# =============================================================================
# 启动
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
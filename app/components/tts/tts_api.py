# app/components/tts/tts_api.py

import logging
from config.config import settings
from app.components.tts.component import EdgeTTS, KokoroTTS, CosyVoiceTTS, CloudTTS

logger = logging.getLogger(__name__)

class TTSInterface:
    """ 
    TTS 统一入口（工厂类）。
    根据配置文件，动态实例化合适的 TTS 引擎。
    """
    
    @staticmethod
    def get_instance(cfg):
        """
        根据 cfg.tts 的配置参数选择具体实现类
        """
        infer_engine = cfg.tts.infer_engine.lower()
        model_name = cfg.tts.model_id_or_path.lower()
        
        logger.info(f"TTSInterface routing: engine={infer_engine}, model={model_name}")

        # 1. 优先检查是否使用了云端 API (OpenAI 等兼容协议)
        if infer_engine == "cloud-api":
            return CloudTTS(cfg)
            
        # 2. 如果是正常的 SDK/本地加载模式
        elif infer_engine == "normal":
            if "kokoro" in model_name:
                return KokoroTTS(cfg)
            elif "cosyvoice" in model_name:
                return CosyVoiceTTS(cfg)
            elif "edge" in model_name:
                return EdgeTTS()
            else:
                logger.warning(f"未知模型 {model_name}，回退使用免费的 EdgeTTS。")
                return EdgeTTS()
                
        else:
            logger.warning(f"不支持的 infer_engine: {infer_engine}，回退使用 EdgeTTS。")
            return EdgeTTS()

# ====================================================================
# 使用示例 
# ====================================================================
"""
async def rag_pipeline_demo():
    from app.components.llm.llm_api import LLMInterface
    
    # 1. 初始化模块
    llm = LLMInterface.get_instance(settings)
    tts = TTSInterface.get_instance(settings)
    
    # 2. LLM 流式输出 (生成器)
    llm_stream = llm.astream_chat("请介绍一下 nene 系统。")
    
    # 3. TTS 边听边读 (通过 stream_sentences_async 连接 LLM 的流)
    async for audio_chunk in tts.stream_sentences_async(llm_stream):
        # 此时已经获取到了单句的音频 bytes，可以通过 WebSocket 发送给前端播放
        # await websocket.send_bytes(audio_chunk)
        print(f"发送音频片段: {len(audio_chunk)} bytes")
"""




if __name__ == '__main__':
    
    tts_engine = "edge-tts"    #   edge-tts  kokoro-tts   qwen_tts
    
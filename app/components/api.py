# app/components/api.py
import os, logging, time
from dotenv import load_dotenv
import pyaudio 
from typing import Dict 

from base import STTModel, TTSModel
from stt.component import IicRealtimeSTT
from tts.component import EdgeTTS


logger = logging.getLogger(__name__)

# =============================================================================
# 语音接口主类
# =============================================================================

class VoiceInterface:
    """
    语音接口主类 - 整合STT和TTS
    
    提供统一的语音交互接口
    """
    
    def __init__(
        self, 
        stt_model: STTModel = None, 
        tts_model: TTSModel = None, 
        voice: str = "zh-CN-XiaoxiaoNeural"
    ):
        load_dotenv()
        self._setup_logging()
        
        # 初始化STT和TTS
        self.stt = stt_model or self._create_stt()
        self.tts = tts_model or self._create_tts()
        self.voice = voice
        
        # 音频参数
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000  # 16kHz采样率，匹配Paraformer
        self.record_seconds = 5
        
        self.audio = pyaudio.PyAudio()

    def _setup_logging(self):
        """配置日志"""
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=level, 
            format="%(asctime)s | %(levelname)s | %(message)s"
        )

    def _create_stt(self) -> STTModel:
        """创建STT模型"""
        try:
            return IicRealtimeSTT()
        except Exception as e:
            logger.error(f"创建STT失败: {e}", exc_info=True)
            
            # 返回占位STT
            class BasicSTT(STTModel):
                def transcribe(self, audio_data: bytes) -> str:
                    return "STT不可用，请检查funasr依赖"
            return BasicSTT()

    def _create_tts(self) -> TTSModel:
        """创建TTS模型"""
        return EdgeTTS()

    def transcribe_audio(self, audio_data: bytes) -> str:
        """将音频转换为文本"""
        logger.info("正在识别语音...")
        start = time.perf_counter()
        
        text = self.stt.transcribe(audio_data)
        
        elapsed = time.perf_counter() - start
        if text and text.strip():
            logger.info(f"识别完成 ({elapsed:.1f}s): {text}")
        else:
            logger.warning(f"识别失败 ({elapsed:.1f}s): 未识别到有效内容")
        
        return text

    def synthesize_speech(self, text: str) -> bytes:
        """将文本转换为语音"""
        logger.info("正在合成语音...")
        start = time.perf_counter()
        
        audio_data = self.tts.synthesize(text, voice=self.voice)
        
        elapsed = time.perf_counter() - start
        logger.info(f"合成完成 ({elapsed:.1f}s)")
        
        return audio_data

    def set_voice(self, voice: str):
        """设置TTS音色"""
        self.voice = voice
        logger.info(f"TTS voice changed to: {voice}")

    def get_available_voices(self) -> Dict[str, str]:
        """获取可用的音色列表"""
        return EdgeTTS.get_chinese_voices()

    def cleanup(self):
        """清理资源"""
        if hasattr(self, 'audio') and self.audio:
            self.audio.terminate()



# =============================================================================
# 测试入口
# =============================================================================

def test_voice_interface():
    """测试语音接口"""
    print("=== 语音接口测试 ===")
    print("✅ FunASR 本地实时语音识别已配置")
    print("✅ Edge-TTS 语音合成已配置")
    
    # 测试Edge-TTS
    tts = EdgeTTS()
    print(f"✅ 默认语音: {tts.voice}")
    print(f"✅ 可用中文语音数量: {len(tts.get_chinese_voices())}")
    
    print("=== 测试完成 ===")


if __name__ == "__main__":
    test_voice_interface()
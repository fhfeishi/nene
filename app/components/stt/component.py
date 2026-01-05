# app/components/stt/component.py

from app.components.commons import STTModel 
try:
    from funasr import AutoModel
    FUNASR_AVAILABLE = True 
except:
    FUNASR_AVAILABLE = False 
    
from typing import Callable, Optional, Dict, Any
import logging 
import numpy as np 


class IicRealtimeSTT(STTModel):
    """
    使用 FunASR Paraformer Online 模型实现的一次性 + 流式 STT。
    - 默认模型: iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online
    - 假定音频为: 16kHz, 16bit PCM, 单声道 (paInt16)
    - 支持实时流式识别
    - 支持VAD静默检测后强制断句
    """
    
    def __init__(
        self,
        model_id: str = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
        model_revision: str = "v2.0.4",
        device: str = "cuda:0",
        sample_rate: int = 16000,
        chunk_size=None,
        encoder_chunk_look_back: int = 2,
        decoder_chunk_look_back: int = 1,
    ):
        if not FUNASR_AVAILABLE:
            raise ImportError("funasr 未安装。请运行: pip install funasr modelscope huggingface_hub")

        self.sample_rate = sample_rate
        # 流式相关参数，默认 [0, 10, 5] -> 600ms chunk
        self.chunk_size = chunk_size or [0, 10, 5]
        self.encoder_chunk_look_back = encoder_chunk_look_back
        self.decoder_chunk_look_back = decoder_chunk_look_back

        # 对于16k采样率，60ms = 960个采样点；一块 = chunk_size[1] * 960
        self._model_chunk_stride = self.chunk_size[1] * 960

        logging.info(
            "Loading FunASR model: %s (rev=%s), device=%s, chunk_size=%s, stride_samples=%s",
            model_id,
            model_revision,
            device,
            self.chunk_size,
            self._model_chunk_stride,
        )

        # 加载 FunASR 模型
        self._model = AutoModel(
            model=model_id,
            model_revision=model_revision,
            device=device,
        )

        # 流式识别状态
        self._streaming_active = False
        self._cache = None
        self._audio_buffer = None
        self._result_callback: Optional[Callable[[str, bool], None]] = None
        self._last_text = ""

        logging.info("IicRealtimeSTT initialized.")

    # ========== 一次性识别接口（整段音频转文字） ==========
    def transcribe(self, audio_data: bytes) -> str:
        """
        同步识别整段音频数据。
        :param audio_data: 16kHz, 16-bit PCM, mono 的原始字节数据
        :return: 识别文本
        """
        try:
            if not audio_data:
                return ""

            # bytes -> int16 -> float32 [-1, 1]
            speech = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            if speech.size == 0:
                return ""

            # 对于一次性识别, 直接 is_final=True，把整段音频喂进去
            cache = {}
            rec_result = self._model.generate(
                input=speech,
                cache=cache,
                is_final=True,
                chunk_size=self.chunk_size,
                encoder_chunk_look_back=self.encoder_chunk_look_back,
                decoder_chunk_look_back=self.decoder_chunk_look_back,
            )

            if rec_result and "text" in rec_result[0]:
                text = (rec_result[0]["text"] or "").strip()
                return text
            return ""
        except Exception as e:
            logging.error("IicRealtimeSTT.transcribe failed: %s", e, exc_info=True)
            return ""
    
    # ========== 流式识别接口 ==========
    def start_streaming(self, result_callback: Optional[Callable[[str, bool], None]] = None):
        """
        启动流式识别，会重置内部缓存。
        :param result_callback: 回调函数 (text: str, is_final: bool) -> None
                                is_final = False -> 中间结果
                                is_final = True -> 最终结果
        """
        logging.info("IicRealtimeSTT.streaming: start_streaming called.")
        self._streaming_active = True
        self._cache = {}
        self._audio_buffer = np.array([], dtype=np.float32)
        self._result_callback = result_callback
        self._last_text = ""
    
    def send_audio_frame(self, audio_frame: bytes) -> bool:
        """
        发送一帧音频数据用于流式识别。
        :param audio_frame: 一段16kHz, 16bit, mono的PCM数据
        :return: bool 是否成功发送
        """
        if not self._streaming_active:
            logging.warning("IicRealtimeSTT.streaming: send_audio_frame called but streaming not active.")
            return False
        if not audio_frame:
            return True  # 空帧不视为错误

        try:
            # 转换音频格式
            frame = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32) / 32768.0
            if frame.size == 0:
                return True

            # 追加到缓冲区
            self._audio_buffer = np.concatenate([self._audio_buffer, frame])

            # 当缓冲区足够大时，取一块给模型
            while self._audio_buffer.size >= self._model_chunk_stride:
                input_chunk = self._audio_buffer[: self._model_chunk_stride]
                self._audio_buffer = self._audio_buffer[self._model_chunk_stride :]

                rec_result = self._model.generate(
                    input=input_chunk,
                    cache=self._cache,
                    is_final=False,  # 中间块
                    chunk_size=self.chunk_size,
                    encoder_chunk_look_back=self.encoder_chunk_look_back,
                    decoder_chunk_look_back=self.decoder_chunk_look_back,
                )

                if rec_result and "text" in rec_result[0]:
                    text = (rec_result[0]["text"] or "").strip()
                    self._last_text = text
                    if self._result_callback and text:
                        # 中间结果回调 is_final=False
                        self._result_callback(text, False)
            return True
        except Exception as e:
            logging.error("IicRealtimeSTT.send_audio_frame failed: %s", e, exc_info=True)
            return False

    def force_final_and_reset(self) -> str:
        """
        强制结束当前句子的识别（触发 is_final=True），返回剩余文本，并重置内部状态以便开始下一句。
        用于 VAD 静默检测超时后的断句。
        """
        if not self._streaming_active:
            return ""

        final_text = ""
        try:
            # 1. 发送空数据触发 is_final=True
            rec_result = self._model.generate(
                input=np.array([], dtype=np.float32),  # 空输入
                cache=self._cache,
                is_final=True,
                chunk_size=self.chunk_size,
                encoder_chunk_look_back=self.encoder_chunk_look_back,
                decoder_chunk_look_back=self.decoder_chunk_look_back,
            )
            if rec_result and "text" in rec_result[0]:
                final_text = (rec_result[0]["text"] or "").strip()

            return final_text
        except Exception as e:
            logging.error("IicRealtimeSTT.force_final_and_reset failed: %s", e, exc_info=True)
            return ""
        finally:
            # 2. 重置状态，准备下一句
            self._cache = {}
            self._last_text = ""
            # 注意：不清除 _audio_buffer，因为可能还有未处理的音频？
            # 通常 VAD 触发时 buffer 应该是空的或者只有静音。为了安全起见，可以不清空 buffer，
            # 但 cache 必须清空以重置解码器上下文。
            logging.info("IicRealtimeSTT: State reset for new sentence.")
    
    def stop_streaming(self) -> str:
        """停止流式识别，处理剩余缓冲区并返回最终文本。"""
        logging.info("IicRealtimeSTT.streaming: stop_streaming called.")
        final_text = ""

        try:
            if self._streaming_active:
                # 处理缓冲区里剩余的音频，做一次 is_final=True 的收尾
                if self._audio_buffer is not None and self._audio_buffer.size > 0:
                    rec_result = self._model.generate(
                        input=self._audio_buffer,
                        cache=self._cache,
                        is_final=True,
                        chunk_size=self.chunk_size,
                        encoder_chunk_look_back=self.encoder_chunk_look_back,
                        decoder_chunk_look_back=self.decoder_chunk_look_back,
                    )
                    if rec_result and "text" in rec_result[0]:
                        final_text = (rec_result[0]["text"] or "").strip()

                # 回调最终结果
                if self._result_callback and final_text:
                    self._result_callback(final_text, True)

                return final_text
        except Exception as e:
            logging.error("IicRealtimeSTT.stop_streaming failed: %s", e, exc_info=True)
            return final_text
        finally:
            # 清理流式状态
            self._streaming_active = False
            self._cache = None
            self._audio_buffer = None
            self._result_callback = None
    
    def transcribe_streaming(self, audio_chunk: bytes, callback=None) -> str:
        """
        兼容性方法：对单个 chunk 做一次性识别。
        如果现有代码把 streaming 当“一块一块调用这个函数”，
        那这里就直接走非流式的 transcribe。
        """
        if callback:
            text = self.transcribe(audio_chunk)
            callback(text, True)
            return text
        else:
            return self.transcribe(audio_chunk)


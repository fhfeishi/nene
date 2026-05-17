# app/components/tts/factory.py

import logging
from typing import Optional

from app.components.base import BaseTTS
from app.components.tts.component import EdgeTTS, KokoroTTS, QwenTTS, CosyVoiceTTS, CloudTTS
from config.config import NeneSettings, settings

logger = logging.getLogger(__name__)


class TTSFactory:
    """TTS 统一工厂"""

    @staticmethod
    def create(config: Optional[NeneSettings] = None) -> BaseTTS:
        cfg = (config or settings).tts
        engine = cfg.infer_engine

        if engine == "edge":
            return EdgeTTS(config.tts if config else cfg)
        elif engine == "kokoro":
            return KokoroTTS(config.tts if config else cfg)
        elif engine == "qwen":
            return QwenTTS(config.tts if config else cfg)
        elif engine == "cosyvoice":
            return CosyVoiceTTS(config.tts if config else cfg)
        elif engine == "cloud":
            return CloudTTS(config.tts if config else cfg)
        else:
            logger.warning("Unknown TTS engine '%s', falling back to EdgeTTS.", engine)
            return EdgeTTS(config.tts if config else cfg)

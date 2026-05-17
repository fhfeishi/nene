# app/components/stt/factory.py

import logging
from typing import Optional

from app.components.base import BaseSTT
from app.components.stt.component import FunASRSTT
from config.config import NeneSettings, settings

logger = logging.getLogger(__name__)


class STTFactory:
    """STT 统一工厂"""

    @staticmethod
    def create(config: Optional[NeneSettings] = None) -> BaseSTT:
        cfg = (config or settings).stt
        engine = cfg.infer_engine

        if engine in ("funasr", "normal"):
            return FunASRSTT(config.stt if config else cfg)
        else:
            logger.warning("Unknown STT engine '%s', falling back to FunASRSTT.", engine)
            return FunASRSTT(config.stt if config else cfg)

# app/components/embed/factory.py

import logging
from typing import Optional

from app.components.base import BaseEmbed
from app.components.embed.component import SentenceTransformerEmbed, CloudEmbed
from config.config import NeneSettings, settings

logger = logging.getLogger(__name__)


class EmbedFactory:
    """Embedding 统一工厂"""

    @staticmethod
    def create(config: Optional[NeneSettings] = None) -> BaseEmbed:
        cfg = (config or settings).embed
        engine = cfg.infer_engine

        if engine in ("sentence-transformers", "transformers"):
            return SentenceTransformerEmbed(config.embed if config else cfg)
        elif engine == "cloud-api":
            return CloudEmbed(config.embed if config else cfg)
        else:
            logger.warning(
                "Unknown embed engine '%s', falling back to SentenceTransformerEmbed.", engine
            )
            return SentenceTransformerEmbed(config.embed if config else cfg)

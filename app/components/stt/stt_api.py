# app/components/stt/service_stt.py

from app.components.base import BaseSTT
from app.components.stt.component import IicRealtimeSTT, iic_stt 
from config.config import settings


import logging 
logger = logging.getLogger(__name__)

class stt_interface:
    """ stt interface class """
    
    @staticmethod
    def get_instance(cfg: settings) -> BaseSTT:
        """ get stt instance """
        engine = cfg.stt.infer_engine
        if engine == "normal":
            return iic_stt(cfg)
        else:
            logger.warning(f"No specific wrapper found for {engine}, using default iic_stt fallback.")
    






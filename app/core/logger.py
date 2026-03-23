# app/core/logger.py 

import logging
import sys 
from config.config import settings 



def setup_logging():
    """全局日志初始化"""
    logging.basicConfig(
        level=settings.LogConfig.level,
        format=settings.LogConfig.format,
        datefmt=settings.LogConfig.datefmt,
        # 显式指定输出到标准输出，防止容器环境日志丢失
        handlers=[logging.StreamHandler(sys.stdout)],
        # filename = str(settings.LogConfig.file_path,
    )
    
    # 捕获 Python warnings (如 DeprecationWarning) 到日志
    logging.captureWarnings(True)
    
    # [可选] 压制一些过于啰嗦的第三方库日志
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # # 测试一下
    # logger = logging.getLogger(__name__)
    # logger.info(f"Logger initialized with level: {settings.LogConfig.level}")


# loguru 日志配置
import sys
from loguru import logger

def setup_logger(
    log_level: str = settings.LogConfig.level,
    log_file: str = str(settings.LogConfig.file_path),
    rotation: str = settings.LogConfig.file_max_size,      # 超过 10MB 自动切割
    retention: str = settings.LogConfig.file_retention,    # 保留 7 天
    serialize: bool = False,      # True 则输出 JSON 格式，适合生产环境采集
) -> None:
    """
    整个工程调用一次，在 main.py 或服务入口处调用。
    """
    # 移除 loguru 默认的 handler，避免重复输出
    logger.remove()

    # ── 控制台输出（带颜色）────────────────────────────────
    logger.add(
        sys.stdout,
        level=log_level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # ── 文件输出（自动切割 + 保留）────────────────────────
    logger.add(
        log_file,
        level=log_level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        serialize=serialize,       # True → 每行一个 JSON，方便日志平台采集
        enqueue=True,              # 异步写入，不阻塞主线程（多服务场景重要）
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level:<8} | "
            "{name}:{line} | "
            "{message}"
        ),
    )

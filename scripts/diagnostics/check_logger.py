# 导入 logger 模块，会自动完成日志配置
import logging

from knowledge_base.tool.logger import logger

logger.setLevel(logging.DEBUG)

# 默认的日志级别是info
logger.debug("这是一条 DEBUG 日志（默认级别为 INFO，不应显示）")
logger.info("这是一条 INFO 日志 - 绿色")
logger.warning("这是一条 WARNING 日志 - 黄色")
logger.error("这是一条 ERROR 日志 - 红色")
logger.critical("这是一条 CRITICAL 日志 - 加粗红色")

from loguru import logger
from ..config import openai_api_key
from ..lib.cache import BaseCache
from ..model.exception import AbortError
from .openai_summarise import openai_summarization


async def summarization(cache: BaseCache):
    logger.info(f"生成 {cache.id} 的内容总结")
    if not cache.content:
        raise AbortError("视频无有效字幕")

    if openai_api_key:
        return await openai_summarization(cache)  # type: ignore

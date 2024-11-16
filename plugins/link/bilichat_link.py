#  Copyright (c) 2024. Henry Yang
#
#  This program is licensed under the GNU General Public License v3.0.

import re
import contextlib
import httpx
import yaml
import asyncio
from loguru import logger
from openai import AsyncOpenAI,AzureOpenAI
from wcferry import client
import xml.etree.ElementTree as ET
from utils.database import BotDatabase
from utils.plugin_interface import PluginInterface
from wcferry_helper import XYBotWxMsg
from utils.bilichat.content import Video
# from utils.bilichat.summary import summarization
lock = asyncio.Lock()
hc = httpx.AsyncClient(
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.39"
        )
    },
    follow_redirects=True,
)
class bilichat_link(PluginInterface):
    def __init__(self):
        config_path = "plugins/link/bilichat_link.yml"

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f.read())

        self.enable_bilichat = config["enable_bilichat"]  # 是否开启私聊chatgpt
        self.bilichat_basic_info  = config["bilichat_basic_info"] 
        self.bilichat_official_summary = config["bilichat_official_summary"]
        self.bilichat_neterror_retry = config["bilichat_neterror_retry"]
        self.bilichat_dynamic = config["bilichat_dynamic"]
        main_config_path = "main_config.yml"
        with open(main_config_path, "r", encoding="utf-8") as f:  # 读取设置
            main_config = yaml.safe_load(f.read())

        self.admins = main_config["admins"]  # 管理员列表

        self.db = BotDatabase()
        
    async def _bili_check(self, bot: client.Wcf, message: str, type: int) -> str:
        logger.debug(f"待处理消息{message}")
        out_message = ""
        # if Reply in msg and (
        #     (plugin_config.bilichat_enable_self and str(event.get_user_id()) == str(bot.self_id)) or event.is_tome()
        # ):
        #     # 如果是回复消息
        #     # 1. 如果是自身消息且允许自身消息
        #     # 2. 如果被回复消息中包含对自身的at
        #     # 满足上述任一条件，则将被回复的消息的内容添加到待解析的内容中
        #     _msgs.append(Text(str(msg[Reply, 0].msg)))

        bililink = None
        if "b23" in message:
            match = re.search(r'<url>(.*?)</url>', message)
            if b23 := re.search(r"b23.(tv|wtf)[\\/]+(\w+)", str(match.group(1))):  # type: ignore
                logger.debug(f"待处理链接：{list(b23.groups())}")
                bililink = await self.b23_extract(list(b23.groups()))

        if not bililink:
            return False
        
        content: Video | None = None #  | Column |  | Dynamic
        options = None
        try:
            ## video handle
            if matched := re.search(r"(?i)av(\d{1,15})|bv(1[0-9a-z]{9})", bililink):
                _id = matched.group()
                logger.info(f"video id: {_id}")
                content = await Video.from_id(_id, options)

        #     ## column handle
        #     elif matched := re.search(r"cv(\d{1,16})", bililink):
        #         _id = matched.group()
        #         logger.info(f"column id: {_id}")
        #         content = await Column.from_id(_id, options)

        #     ## dynamic handle
        #     elif self.bilichat_dynamic and (
        #         matched := re.search(r"(dynamic|opus|t.bilibili.com)/(\d{1,128})", bililink)
        #     ):
        #         _id = matched.group()
        #         logger.info(f"dynamic id: {_id}")
        #         content = await Dynamic.from_id(_id)

        #     if content:
        #         # if options.force:
        #         #     BilichatCD.record_cd(state["_uid_"], str(content.id))
        #         # else:
        #         #     BilichatCD.check_cd(state["_uid_"], str(content.id))
        #         # state["_content_"] = content
        #         logger.debug(f"返回数据：{content}")
        #     else:
        #         raise AbortError(f"查询 {bililink} 返回内容为空")
            # logger.debug(f"返回内容：{content}")
            if isinstance(content, Video) :
                try:
                    logger.debug(f"视频标题:{content.title}")
                    # out_message = out_message.join(f"视频标题：{content.title}\n")
                    out_message += "🎞️视频标题:" + f"{content.title}" + "\n"
                except:
                    pass

                if self.bilichat_official_summary:
                    # 获取官方总结内容
                    try:
                        official_summary_response = await content.get_offical_summary()
                        official_summary = official_summary_response.result.markdown()
                        logger.debug(f"AI总结:{official_summary}")
                        if official_summary:
                            # out_message = out_message.join(f"官方AI总结:{official_summary}")
                            out_message += "🎉官方AI总结:" + f"{official_summary}"
                            # logger.debug(f"最终回复:{out_message}")

                    except Exception as e:
                        return None
                if not official_summary:
                    try:
                        async with lock:
                            if self.openai_api_key:
                                subtitle = await content.get_subtitle()
                                if not subtitle:
                                    raise AbortError("视频无有效字幕")
                                # summary
                                if summary := await summarization(cache=content.cache):
                                    # future_msg.append(Image(raw=summary))
                                    out_message += "🎉OpenAI总结:" + f"{summary}"
                                    # out_message = out_message.join(f"OpenAI总结:{official_summary}")
                                    logger.debug(f"{summary}")
                    except Exception as e:
                        logger.debug(f"{e}")
                if not official_summary and not summary:
                    return None
            return out_message
            # return None
        except Exception as e:
            return None

    async def b23_extract(self, b23: list[str]):
        try:
            url = f"https://b23.tv/{b23[1]}"
            for _ in range(self.bilichat_neterror_retry):
                with contextlib.suppress(Exception):
                    resp = await hc.get(url, follow_redirects=True)
                    break
            else:
                return None
            logger.debug(f"b23.tv url: {resp.url}")
            return str(resp.url)
        except TypeError:
            return None

    async def run(self, bot: client.Wcf, recv: XYBotWxMsg):
        if not self.enable_bilichat:
            return  # 如果不开启，不处理
        elif not recv.from_group():
            return  # 如果是私聊消息，不处理

        roomid = recv.roomid
        recv.content = re.split(" |\u2005", recv.content) # 拆分消息    
        message = " ".join(recv.content)
        logger.debug(f"bilichat 处理消息:{message}")
        out_message = await self._bili_check(bot, message, recv.type)
        if out_message:
            bot.send_text(out_message, roomid)

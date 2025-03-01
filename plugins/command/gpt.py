#  Copyright (c) 2024. Henry Yang
#
#  This program is licensed under the GNU General Public License v3.0.

import re
import asyncio
import yaml
from loguru import logger
from openai import AsyncOpenAI,AzureOpenAI
from wcferry import client

from utils.database import BotDatabase
from utils.plugin_interface import PluginInterface
import config.config as CONFIG
from wcferry_helper import XYBotWxMsg
from utils.openai import chatgpt, senstitive_word_check, clear_dialogue, update_config
from utils.xybot import send_friend_or_group

class gpt(PluginInterface):
    def __init__(self):
        config_path = "plugins/command/gpt.yml"
        with open(config_path, "r", encoding="utf-8") as f:  # 读取设置
            config = yaml.safe_load(f.read())

        self.gpt_point_price = config["gpt_point_price"]  # gpt使用价格（单次）

        main_config_path = "main_config.yml"
        with open(main_config_path, "r", encoding="utf-8") as f:  # 读取设置
            main_config = yaml.safe_load(f.read())

        self.admins = main_config["admins"]  # 获取管理员列表
        
        self.db = BotDatabase()

    async def run(self, bot: client.Wcf, recv: XYBotWxMsg):
        recv.content = re.split(" |\u2005", recv.content)  # 拆分消息

        user_wxid = recv.sender  # 获取发送者wxid

        error_message = ""

        if self.db.get_points(user_wxid) < self.gpt_point_price and self.db.get_whitelist(
                user_wxid) != 1 and user_wxid not in self.admins:  # 积分不足 不在白名单 不是管理员
            # error_message = f"积分不足,需要{self.gpt_point_price}点⚠️"
            pass
        elif len(recv.content) < 2:  # 指令格式正确
            error_message = "参数错误!❌"

        gpt_request_message = " ".join(recv.content[1:])  # 用户问题
        if not senstitive_word_check(gpt_request_message):  # 敏感词检查
            error_message = "内容包含敏感词!⚠️"

        if not error_message:
            if True: #self.db.get_whitelist(user_wxid) == 1 or user_wxid in self.admins:  # 如果用户在白名单内/是管理员
                if recv.content[1] == "清除对话" :
                    if user_wxid in self.admins or not recv.from_group:  # 如果是清除对话记录的关键词，清除数据库对话记录
                        if recv.from_group():
                            clear_dialogue(recv.roomid)  # 保存清除了的数据到数据库
                        else :
                            clear_dialogue(user_wxid)  # 保存清除了的数据到数据库
                        out_message = "对话记录已清除！✅"
                        await send_friend_or_group(self.db, bot, recv, out_message)
                        return
                if recv.content[1] == "修改模型" :
                    if user_wxid in self.admins and recv.content[2] in CONFIG.OPENAI_PROVIDER_LIST and recv.content[3] in CONFIG.GPT_VERSION_LIST[recv.content[2]]:  # 管理员修改模型
                        try:
                            update_config(recv.content[2],recv.content[3])
                            if recv.from_group():
                                clear_dialogue(recv.roomid)  # 保存清除了的数据到数据库
                            else :
                                clear_dialogue(user_wxid)  # 保存清除了的数据到数据库
                            out_message = "模型已修改，对话记录已清除"
                        except:
                            out_message = "修改出错"
                        await send_friend_or_group(self.db, bot, recv, out_message)
                        return
                if recv.from_group():
                    chatgpt_answer = await chatgpt(recv.roomid, gpt_request_message)   # 从chatgpt api 获取回答
                else :
                    chatgpt_answer = await chatgpt(recv.roomid, gpt_request_message)   # 从chatgpt api 获取回答
                if chatgpt_answer[0]:
                    # out_message = f"{chatgpt_answer[1]}\nChatGPT版本：{self.gpt_version}"  # 创建信息
                    out_message = f"{chatgpt_answer[1]}"  # 创建信息
                else:
                    out_message = f"出现错误！⚠️{chatgpt_answer}"
                await send_friend_or_group(self.db, bot, recv, out_message)

        else:
            await send_friend_or_group(self.db, bot, recv, error_message)



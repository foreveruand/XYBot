#  Copyright (c) 2024. Henry Yang
#
#  This program is licensed under the GNU General Public License v3.0.

import os
import re
import time
import random
import aiohttp
import yaml
from loguru import logger
from wcferry import client

from utils.plugin_interface import PluginInterface
from wcferry_helper import XYBotWxMsg
from utils.database import BotDatabase
from utils.eat import *
from typing import Dict, List, Optional, Tuple, Union

class eat_what(PluginInterface):
    def __init__(self):
        config_path = "plugins/command/eat_what.yml"
        with open(config_path, "r", encoding="utf-8") as f:  # 读取设置
            config = yaml.safe_load(f.read())
        self._eating: Dict[str, Union[List[str], Dict[str,
                                                      Union[Dict[str, List[int]], List[str]]]]] = {}
        self._greetings: Dict[str, Union[List[str], Dict[str, bool]]] = {}
        self._eating_json =  "resources/eat_what/eating.json"
        self._greetings_json =  "resources/eat_what/greetings.json"
        self._drinks_json =  "resources/eat_what/drinks.json"
        self.eating_limit = config["eating_limit"]
    def _init_data(self, gid: str,uid: str = None):
        '''
            初始化用户信息
        '''
        if gid not in self._eating["group_food"]:
            self._eating["group_food"][gid] = []
        if gid not in self._eating["count"]:
            self._eating["count"][gid] = {}
        if isinstance(uid, str):
            if uid not in self._eating["count"][gid]:
                self._eating["count"][gid][uid] = 0

    def get_eat(self,gid: str,uid: Optional[str] = None) -> str:
        food_list: List[str] = []

        self._eating = load_json(self._eating_json)
        self._init_data(gid,uid)

        # Check whether is full of stomach
        if self._eating["count"][gid][uid] >= self.eating_limit:
            save_json(self._eating_json, self._eating)
            # return bot.send_text(random.choice(EatingEnough_List), recv.roomid)  # 发送
            return random.choice(EatingEnough_List)  # 发送
        else:
            # basic_food and group_food both are EMPTY
            if len(self._eating["basic_food"]) == 0 and len(self._eating["group_food"][gid]) == 0:
                return "没东西吃，饿着吧"  # 发送

            food_list = self._eating["basic_food"].copy()

            # 取并集
            if len(self._eating["group_food"][gid]) > 0:
                food_list = list(set(food_list).union(
                    set(self._eating["group_food"][gid])))

            msg = f"建议{random.choice(food_list)}"
            self._eating["count"][gid][uid] += 1
            save_json(self._eating_json, self._eating)
            return msg
    def _is_food_exists(self, _food: str, _search: SearchLoc, gid: Optional[str] = None) -> Tuple[FoodLoc, str]:
        '''
            检查菜品是否存在于某个群组/全局，优先检测是否在群组，返回菜品所在区域及其全称；
            - gid = None, 搜索群组
            - _search: IN_BASIC, IN_GROUP or IN_GLOBAL（全局指本群与基础菜单）

            群组添加菜品: gid=str, _search=IN_GLOBAL
            优先检测群组是否匹配，返回：
            IN_BASIC, IN_GROUP, NOT_EXISTS

            基础添加菜品: gid=None, _search=IN_BASIC
            仅检测基础菜单是否存在，返回：
            IN_BASIC, NOT_EXISTS

            群组移除菜品: gid=str, _search=IN_GLOBAL
            全局检测，返回：IN_BASIC, IN_GROUP, NOT_EXISTS

            Notes:
            1. 添加时，文字与图片一一对应才认为是相同的菜品
            2. 移除时，移除文字匹配的第一个；若配图也被移除，同时移除配图相同的其余菜品（即使在基础菜单中）
        '''
        if _search == SearchLoc.IN_GROUP or _search == SearchLoc.IN_GLOBAL:
            if isinstance(gid, str):
                if gid in self._eating["group_food"]:
                    for food in self._eating["group_food"][gid]:
                        # food is the full name or _food matches the food name before CQ code
                        if _food == food : # or _food == food.split("[CQ:image")[0]:
                            return FoodLoc.IN_GROUP, food

                    if _search == SearchLoc.IN_GROUP:
                        return FoodLoc.NOT_EXISTS, ""

        if _search == SearchLoc.IN_BASIC or _search == SearchLoc.IN_GLOBAL:
            for food in self._eating["basic_food"]:
                if _food == food : # or _food == food.split("[CQ:image")[0]:
                    return FoodLoc.IN_BASIC, food

            return FoodLoc.NOT_EXISTS, ""

    def add_group_food(self,uid: str, gid: str, new_food: str):
        '''
            添加至群菜单
        '''
        msg = ""
        self._eating = load_json(self._eating_json)
        self._init_data(gid, uid)
        status, _ = self._is_food_exists(
            new_food, SearchLoc.IN_GLOBAL, gid)  # new food may include cq

        if status == FoodLoc.IN_BASIC:
            msg = f"已在基础菜单中~"
        elif status == FoodLoc.IN_GROUP:
            msg = f"已在群特色菜单中~"
        else:
            # If image included, save it, return the path in string
            self._eating["group_food"][gid].append(new_food)
            msg = f"已加入群特色菜单~"

        save_json(self._eating_json, self._eating)
        return msg

    def remove_group_food(self,uid: str, gid: str, new_food: str):
        '''
            从群菜单移除
        '''
        msg = ""
        self._eating = load_json(self._eating_json)
        self._init_data(gid, uid)
        status, _ = self._is_food_exists(
            new_food, SearchLoc.IN_GLOBAL, gid)  # new food may include cq

        if status == FoodLoc.IN_GROUP:
            self._eating["group_food"][gid].remove(new_food)
            msg = f"已从群特色菜单中移除~"
        else:
            # If image included, save it, return the path in string
            # self._eating["group_food"][gid].append(new_food)
            msg = f"{new_food}不在群特色菜单~"

        save_json(self._eating_json, self._eating)
        return msg

    async def run(self, bot: client.Wcf, recv: XYBotWxMsg):
        recv.content = re.split(" |\u2005", recv.content)  # 拆分消息
        uid  = recv.sender
        gid = recv.roomid
        command = " ".join(recv.content)
        logger.debug(f"处理指令：{recv.content}")
        if recv.from_group():  # 判断是群还是私聊
            if recv.content[0] == "添加群菜单":
                if len(recv.content) < 2:
                    msg ="还没输入你要添加的菜品呢~"
                    logger.info("还没输入你要添加的菜品呢")
                elif len(recv.content) > 2:
                    msg ="添加菜品参数错误~"
                    logger.info(f"添加菜品参数错误，处理指令：{command}")
                else:
                    msg = self.add_group_food(uid,gid,recv.content[1])
                    logger.info("添加群菜单")
            elif recv.content[0] == "删除群菜单":
                if len(recv.content) < 2:
                    msg ="还没输入你要删除的菜品呢~"
                    logger.info("还没输入你要删除的菜品呢")
                elif len(recv.content) > 2:
                    msg ="删除菜品参数错误~"
                    logger.info(f"删除菜品参数错误，处理指令：{command}")
                else:
                    msg = self.remove_group_food(uid,gid,recv.content[1])
                    logger.info("删除群菜单")
            else :
                msg = self.get_eat(gid,uid)
        else:
            logger.info(f'[发送信息]请在群聊中使用| [发送到] {recv.roomid}')
            msg = "请在群聊中使用"

        bot.send_text(msg, recv.roomid)  # 发送

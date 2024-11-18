#  Copyright (c) 2024. Henry Yang
#
#  This program is licensed under the GNU General Public License v3.0.

import re
import os
import yaml
import time
import asyncio
import glob
from asyncio import TimerHandle
from typing import Annotated, Any, TypeVar, Callable
from typing_extensions import ParamSpec
from collections.abc import Coroutine
from loguru import logger
from wcferry import client
from functools import wraps, partial
import anyio
import anyio.to_thread
from utils.database import BotDatabase
from config.config import handle_color_enhance,handle_strict_mode
from utils.handle_data import GuessResult, Handle
from utils.handle import random_idiom

from utils.plugin_interface import PluginInterface
from wcferry_helper import XYBotWxMsg

games: dict[str, Handle] = {}
timers: dict[str, TimerHandle] = {}

class handle(PluginInterface):
    def __init__(self):
        config_path = "plugins/text/handle.yml"
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f.read())
        self.enable_private_handle = config["enable_private_handle"]
        self.command = config["command_keywords"]
        self.db = BotDatabase()
    def stop_game(self, room_id: str):
        if timer := timers.pop(room_id, None):
            timer.cancel()
        games.pop(room_id, None)


    async def stop_game_timeout(self, bot: client.Wcf, room_id: str):
        logger.debug(f"handle :超时")
        game = games.get(room_id, None)
        self.stop_game(room_id)
        if game:
            msg = "猜成语超时，游戏结束。"
            if len(game.guessed_idiom) >= 1:
                msg += f"\n{str(game.result)}"
            await bot.send_text(f"{msg}", room_id)


    def set_timeout(self, bot: client.Wcf, room_id: str, timeout: float = 300):
        logger.debug(f"handle :设置超时时间")
        if timer := timers.get(room_id, None):
            timer.cancel()
        loop = asyncio.get_running_loop()
        logger.debug(f"handle :开始计时")
        timer = loop.call_later(
            timeout, lambda: asyncio.ensure_future(self.stop_game_timeout(bot, room_id))
        )
        timers[room_id] = timer

    async def run(self, bot: client.Wcf, recv: XYBotWxMsg):
        if not self.enable_private_handle:
            return  # 如果不开启私聊，不处理
        elif not recv.from_group():
            return  # 如果是群聊消息，不处理
        logger.debug(f"handle 处理消息:{recv.content}")
        try:
            recv.content = re.split(" |\u2005", recv.content)  # 拆分消息
        except:
            pass
        room_id = recv.roomid
        game = games.get(room_id, None)
        if not game and recv.content[0]=='handle':
            # logger.debug("handle: 开始游戏")
            if len(recv.content) >1 :
                if recv.content[1] == "-s":
                    is_strict = True
                else:
                    bot.send_text("参数错误",recv.roomid)
                    return
            else :
                is_strict = handle_strict_mode
            idiom, explanation = random_idiom()
            # logger.debug("handle: 创建游戏")
            game = Handle(idiom, explanation, strict=is_strict)
            # logger.debug("handle: 保存游戏")
            games[room_id] = game
            self.set_timeout(bot, room_id, 300.0)

            # logger.debug("handle: 发送消息")
            msg = f"你有{game.times}次机会猜一个四字成语，"+ ("发送有效成语以参与游戏。" if is_strict else "发送任意四字词语以参与游戏。")
            raw=await run_sync(game.draw)()
            save_path = os.path.abspath(f"resources/cache/handle_{time.time_ns()}.png")
            with open(save_path, 'wb') as f:
                f.write(raw.getvalue())
            await self.send_friend_or_group(bot, recv, msg)
            await self.send_friend_or_group_image(bot, recv, save_path)
        elif game:
            if recv.content[0]=='结束':
                self.stop_game(room_id)
                await self.send_friend_or_group(bot, recv, "猜成语结束")
                return
            if recv.content[0]=='提示':
                save_path = get_latest_file("resources/cache/handle_*")
                await self.send_friend_or_group_image(bot, recv, save_path)
                return
            if not (re.fullmatch(r'^[\u4e00-\u9fa5]{4}$', recv.content[0])):
                logger.debug("非四字词语，跳过")
                return

            self.set_timeout(bot, room_id, 300.0)

            # idiom = str(matched["idiom"])
            idiom = "".join(recv.content[0])
            result = game.guess(idiom)

            if result in [GuessResult.WIN, GuessResult.LOSS]:
                self.stop_game(room_id)
                msg =("恭喜你猜出了成语！"if result == GuessResult.WIN else "很遗憾，没有人猜出来呢")+ f"\n{game.result}"
                #+ Image(raw=await run_sync(game.draw)())
                raw=await run_sync(game.draw)()
                save_path = os.path.abspath(f"resources/cache/handle_{time.time_ns()}.png")
                with open(save_path, 'wb') as f:
                    f.write(raw.getvalue())
                await self.send_friend_or_group( bot, recv, msg)
                await self.send_friend_or_group_image(bot, recv, save_path)

            elif result == GuessResult.DUPLICATE:
                await self.send_friend_or_group( bot, recv, "你已经猜过这个成语了呢")

            elif result == GuessResult.ILLEGAL:
                await self.send_friend_or_group( bot, recv, f"你确定“{idiom}”是个成语吗？")

            else:
                raw=await run_sync(game.draw)()
                save_path = os.path.abspath(f"resources/cache/handle_{time.time_ns()}.png")
                with open(save_path, 'wb') as f:
                    f.write(raw.getvalue())
                await self.send_friend_or_group_image(bot, recv, save_path)

    async def send_friend_or_group(self, bot: client.Wcf, recv: XYBotWxMsg, out_message="null"):
        if recv.from_group():  # 判断是群还是私聊
            out_message = f"@{self.db.get_nickname(recv.sender)}\n{out_message}"
            logger.info(f'[发送@信息]{out_message}| [发送到] {recv.roomid}')
            bot.send_text(out_message, recv.roomid, recv.sender)  # 发送@信息

        else:
            logger.info(f'[发送信息]{out_message}| [发送到] {recv.roomid}')
            bot.send_text(out_message, recv.roomid)  # 发送

    async def send_friend_or_group_image(self, bot: client.Wcf, recv: XYBotWxMsg, image_path: str):
        bot.send_image(image_path, recv.roomid)
P = ParamSpec("P")
R = TypeVar("R")

def run_sync(call: Callable[P, R]) -> Callable[P, Coroutine[None, None, R]]:
    """一个用于包装 sync function 为 async function 的装饰器

    参数:
        call: 被装饰的同步函数
    """

    @wraps(call)
    async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return await anyio.to_thread.run_sync(
            partial(call, *args, **kwargs), abandon_on_cancel=True
        )

    return _wrapper

def get_latest_file(filename: str):
    # 获取所有匹配的文件
    files = glob.glob(filename)
    
    # 如果没有文件，返回 None
    if not files:
        return None
    
    # 找到最新的文件
    latest_file = max(files, key=os.path.getmtime)
    return latest_file
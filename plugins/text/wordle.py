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
from utils.wordle_data import GuessResult, Wordle
from utils.wordle import dic_list, random_word

from utils.plugin_interface import PluginInterface
from wcferry_helper import XYBotWxMsg

games: dict[str, Wordle] = {}
timers: dict[str, TimerHandle] = {}

# def game_is_running(room_id: UserId) -> bool:
#     return room_id in games

# def game_not_running(room_id: UserId) -> bool:
#     return room_id not in games

def same_user(game_room_id: str):
    def _same_user(room_id: UserId) -> bool:
        return room_id in games and room_id == game_room_id
    return _same_user

def stop_game(room_id: str):
    if timer := timers.pop(room_id, None):
        timer.cancel()
    games.pop(room_id, None)

async def stop_game_timeout(bot: client.Wcf, room_id: str):
    logger.debug(f"wordle :超时")
    game = games.get(room_id, None)
    stop_game(room_id)
    if game:
        msg = "猜成语超时，游戏结束。"
        if len(game.guessed_idiom) >= 1:
            msg += f"\n{str(game.result)}"
        await bot.send_text(f"{msg}", room_id)

def set_timeout(bot: client.Wcf, room_id: str, timeout: float = 300):
    logger.debug(f"wordle :设置超时时间")
    if timer := timers.get(room_id, None):
        timer.cancel()
    loop = asyncio.get_running_loop()
    logger.debug(f"wordle :开始计时")
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game_timeout(bot, room_id))
    )
    timers[room_id] = timer

class wordle(PluginInterface):
    def __init__(self):
        config_path = "plugins/text/wordle.yml"
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f.read())
        self.enable_private_wordle = config["enable_private_wordle"]
        self.command = config["command_keywords"]

    async def run(self, bot: client.Wcf, recv: XYBotWxMsg):
        if not self.enable_private_wordle:
            return  # 如果不开启私聊，不处理
        elif not recv.from_group():
            return  # 如果是群聊消息，不处理
        logger.debug(f"wordle 处理消息:{recv.content}")
        try:
            recv.content = re.split(" |\u2005", recv.content)  # 拆分消息
        except:
            pass
        room_id = recv.roomid
        game = games.get(room_id, None)
        length = 5
        dictionary = "GRE"
        if not game and recv.content[0]=='wordle':
            # logger.debug("wordle: 开始游戏")
            if len(recv.content) >4 :
                try:
                    if recv.content[1] == "-l":
                        length = int(recv.content[2])
                    elif recv.content[3] == "-l":
                        length = int(recv.content[4])
                    if recv.content[1] == "-d":
                        dictionary = recv.content[2]
                    elif recv.content[3] == "-d":
                        dictionary = recv.content[4]
                except:
                    bot.send_text("参数错误",recv.roomid)
                    return
            elif len(recv.content) >2 :
                try:
                    if recv.content[1] == "-l":
                        length = int(recv.content[2])
                    if recv.content[1] == "-d":
                        dictionary = recv.content[2]
                except:
                    bot.send_text("参数错误",recv.roomid)
                    return
            if length<3 or length>8:
                bot.send_text("单词长度应在3-8之间",recv.roomid)
                return 
            if dictionary not in dic_list:
                bot.send_text("支持的词典：" + ", ".join(dic_list),recv.roomid)
                return 
            # logger.debug("wordle: 创建游戏")
            word, meaning = random_word(dictionary, length)
            game = Wordle(word, meaning)

            # logger.debug("wordle: 保存游戏")
            games[room_id] = game
            set_timeout(bot, room_id)

            # logger.debug("wordle: 发送消息")
            msg = f"你有{game.rows}次机会猜出单词，单词长度为{game.length}，请发送单词"
            raw=await run_sync(game.draw)()
            save_path = os.path.abspath(f"resources/cache/wordle_{time.time_ns()}.png")
            with open(save_path, 'wb') as f:
                f.write(raw.getvalue())
            await send_friend_or_group(bot, recv, msg)
            # await send_friend_or_group_image(bot, recv, save_path)
        elif game:
            if recv.content[0]=='不猜了':
                stop_game(room_id)
                await send_friend_or_group(bot, recv, "猜单词结束")
                return
            if recv.content[0]=='单词':
                save_path = get_latest_file("resources/cache/wordle_*")
                logger.debug(f"wordle:最新文件地址:{save_path}")
                await send_friend_or_group_image(bot, recv, save_path)
                return
            if not (re.fullmatch(f'^[a-zA-Z]{{{game.length}}}', recv.content[0])):
                logger.debug("非给定长度单词，跳过")
                return

            set_timeout(bot, room_id)

            word = "".join(recv.content[0])
            result = game.guess(word)

            if result in [GuessResult.WIN, GuessResult.LOSS]:
                stop_game(room_id)
                msg =("恭喜你猜出了单词！"if result == GuessResult.WIN else "很遗憾，没有人猜出来呢")+ f"\n{game.result}"
                #+ Image(raw=await run_sync(game.draw)())
                raw=await run_sync(game.draw)()
                save_path = os.path.abspath(f"resources/cache/wordle_{time.time_ns()}.png")
                with open(save_path, 'wb') as f:
                    f.write(raw.getvalue())
                await send_friend_or_group( bot, recv, msg)
                await send_friend_or_group_image(bot, recv, save_path)

            elif result == GuessResult.DUPLICATE:
                return
                # await send_friend_or_group( bot, recv, "你已经猜过这个单词了呢")
                # save_path = get_latest_file("resources/cache/wordle_*")
                # await send_friend_or_group_image(bot, recv, save_path)

            elif result == GuessResult.ILLEGAL:
                await send_friend_or_group( bot, recv, f"你确定“{word}”是个单词吗？")

            else:
                raw=await run_sync(game.draw)()
                save_path = os.path.abspath(f"resources/cache/wordle_{time.time_ns()}.png")
                with open(save_path, 'wb') as f:
                    f.write(raw.getvalue())
                await send_friend_or_group_image(bot, recv, save_path)

async def send_friend_or_group(bot: client.Wcf, recv: XYBotWxMsg, out_message="null"):
    db = BotDatabase()
    if recv.from_group():  # 判断是群还是私聊
        out_message = f"@{db.get_nickname(recv.sender)}\n{out_message}"
        logger.info(f'[发送@信息]{out_message}| [发送到] {recv.roomid}')
        bot.send_text(out_message, recv.roomid, recv.sender)  # 发送@信息

    else:
        logger.info(f'[发送信息]{out_message}| [发送到] {recv.roomid}')
        bot.send_text(out_message, recv.roomid)  # 发送

async def send_friend_or_group_image(bot: client.Wcf, recv: XYBotWxMsg, image_path: str):
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
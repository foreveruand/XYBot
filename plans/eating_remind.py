#  Copyright (c) 2024. Henry Yang
#
#  This program is licensed under the GNU General Public License v3.0.
import random
import yaml
from loguru import logger
from wcferry import client
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Union
import asyncio
import schedule
from utils.plans_interface import PlansInterface
try:
    import ujson as json
except ModuleNotFoundError:
    import json
    
class Meals(Enum):
    BREAKFAST = ["breakfast", "早餐", "早饭"]
    LUNCH = ["lunch", "午餐", "午饭", "中餐"]
    SNACK = ["snack", "摸鱼", "下午茶", "饮茶"]
    DINNER = ["dinner", "晚餐", "晚饭"]
    MIDNIGHT = ["midnight", "夜宵", "宵夜"]

class SearchLoc(Enum):
    IN_BASIC = "In basic"
    IN_GROUP = "In group"
    IN_GLOBAL = "In global"

def save_json(_file: Path, _data: Any) -> None:
    with open(_file, 'w', encoding='utf-8') as f:
        json.dump(_data, f, ensure_ascii=False, indent=4)


def load_json(_file: Path) -> Any:
    with open(_file, 'r', encoding='utf-8') as f:
        return json.load(f)

class eating_remind(PlansInterface):
    def __init__(self):
        main_config_path = "main_config.yml"
        with open(main_config_path, "r", encoding="utf-8") as f:  # 读取设置
            main_config = yaml.safe_load(f.read())
        self._eating: Dict[str, Union[List[str], Dict[str,
                                                      Union[Dict[str, List[int]], List[str]]]]] = {}
        self.timezone = main_config["timezone"]  # 时区
        self._greetings: Dict[str, Union[List[str], Dict[str, bool]]] = {}
        self._greetings_json =  "resources/eat_what/greetings.json"
        self._eating_json =  "resources/eat_what/eating.json"

    async def do_greeting(self, bot: client.Wcf, meal: Meals) -> None:
        self._greetings = load_json(self._greetings_json)
        msg = self._get_greeting(meal)

        if bool(self._greetings["groups_id"]) > 0:
            for gid in self._greetings["groups_id"]:
                try:
                    bot.send_text(msg, gid)
                    logger.info(f"已群发{meal.value[1]}提醒")
                except Exception as e:
                    logger.warning(f"发送群 {gid} 失败：{e}")

    def _get_greeting(self, meal: Meals) -> str:
        '''
            Get a greeting, return None if empty
        '''
        if meal.value[0] in self._greetings:
            if len(self._greetings.get(meal.value[0])) > 0:
                greetings: List[str] = self._greetings.get(meal.value[0])
                return random.choice(greetings)

        return None
    def reset_count(self):
        '''
            Reset eating times in every eating time
        '''
        self._eating = load_json(self._eating_json)

        for gid in self._eating["count"]:
            for uid in self._eating["count"][gid]:
                self._eating["count"][gid][uid] = 0

        save_json(self._eating_json, self._eating)
        logger.info("今天吃什么次数已刷新")

    def job_async(self, bot: client.Wcf, meal: Meals):
        loop = asyncio.get_running_loop()
        loop.create_task(self.do_greeting(bot,meal))

    def run(self, bot: client.Wcf):
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            getattr(schedule.every(), day).at("08:00", tz=self.timezone).do(self.job_async, bot,Meals.BREAKFAST)
            getattr(schedule.every(), day).at("12:00", tz=self.timezone).do(self.job_async, bot,Meals.LUNCH)
            getattr(schedule.every(), day).at("18:00", tz=self.timezone).do(self.job_async, bot,Meals.DINNER)
            # schedule.every().day.at("08:00", tz=self.timezone).do(self.job_async, bot,Meals.BREAKFAST)
            # schedule.every().day.at("12:00", tz=self.timezone).do(self.job_async, bot,Meals.LUNCH)
            # schedule.every().day.at("18:00", tz=self.timezone).do(self.job_async, bot,Meals.DINNER)
        schedule.every().day.at("03:00", tz=self.timezone).do(self.reset_count)
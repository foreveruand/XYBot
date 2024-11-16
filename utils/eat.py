from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

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


class FoodLoc(Enum):
    IN_BASIC = "In basic"
    IN_GROUP = "In group"
    NOT_EXISTS = "Not exists"


class SearchLoc(Enum):
    IN_BASIC = "In basic"
    IN_GROUP = "In group"
    IN_GLOBAL = "In global"

EatingEnough_List: List[str] = [
    "你今天已经吃得够多了！",
    "吃这么多的吗？",
    "害搁这吃呢？不工作的吗？",
    "再吃肚子就要爆炸咯~",
    "你是米虫吗？今天碳水要爆炸啦！",
    "去码头整点薯条吧🍟"
]

DrinkingEnough_List: List[str] = [
    "你今天已经喝得够多了！",
    "喝这么多的吗？",
    "害搁这喝呢？不工作的吗？",
    "再喝肚子就要爆炸咯~",
    "你是水桶吗？今天糖分要超标啦！"
]


def save_json(_file: Path, _data: Any) -> None:
    with open(_file, 'w', encoding='utf-8') as f:
        json.dump(_data, f, ensure_ascii=False, indent=4)


def load_json(_file: Path) -> Any:
    with open(_file, 'r', encoding='utf-8') as f:
        return json.load(f)


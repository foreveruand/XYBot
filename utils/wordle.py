import json
import random
from io import BytesIO
from pathlib import Path

from PIL import ImageFont
from PIL.Image import Image as IMG
from PIL.ImageFont import FreeTypeFont
from pypinyin import Style, pinyin
from spellchecker import SpellChecker
resource_dir = Path(__file__).parents[1] / "resources" / "wordle"
if not resource_dir.exists():
    # 创建必要的目录结构
    resource_dir.mkdir(parents=True, exist_ok=True)
fonts_dir = resource_dir / "fonts"
words_dir = resource_dir / "words"

dic_list = [f.stem for f in words_dir.iterdir() if f.suffix == ".json"]

spell = SpellChecker()


def legal_word(word: str) -> bool:
    return not spell.unknown((word,))


def random_word(dic_name: str = "CET4", word_length: int = 5) -> tuple[str, str]:
    with (words_dir / f"{dic_name}.json").open("r", encoding="utf-8") as f:
        data: dict = json.load(f)
        data = {k: v for k, v in data.items() if len(k) == word_length}
        word = random.choice(list(data.keys()))
        meaning = data[word]["中释"]
        return word, meaning


def save_png(frame: IMG) -> BytesIO:
    output = BytesIO()
    frame = frame.convert("RGBA")
    frame.save(output, format="png")
    return output


def load_font(name: str, fontsize: int) -> FreeTypeFont:
    return ImageFont.truetype(str(fonts_dir / name), fontsize, encoding="utf-8")
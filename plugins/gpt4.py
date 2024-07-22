import yaml
from loguru import logger
from openai import AsyncOpenAI

import pywxdll
from utils.database import BotDatabase
from utils.plugin_interface import PluginInterface


class gpt4(PluginInterface):
    def __init__(self):
        config_path = "plugins/gpt4.yml"
        with open(config_path, "r", encoding="utf-8") as f:  # 读取设置
            config = yaml.safe_load(f.read())

        self.gpt_version = config["gpt_version"]  # gpt版本
        self.gpt_point_price = config["gpt_point_price"]  # gpt使用价格（单次）
        self.gpt_max_token = config["gpt_max_token"]  # gpt 最大token
        self.gpt_temperature = config["gpt_temperature"]  # gpt 温度

        main_config_path = "main_config.yml"
        with open(main_config_path, "r", encoding="utf-8") as f:  # 读取设置
            main_config = yaml.safe_load(f.read())

        self.ip = main_config["ip"]  # 机器人ip
        self.port = main_config["port"]  # 机器人端口
        self.admins = main_config["admins"]  # 管理员列表

        self.openai_api_base = main_config["openai_api_base"]  # openai api 链接
        self.openai_api_key = main_config["openai_api_key"]  # openai api 密钥

        sensitive_words_path = "sensitive_words.yml"  # 加载敏感词yml
        with open(sensitive_words_path, "r", encoding="utf-8") as f:  # 读取设置
            sensitive_words_config = yaml.safe_load(f.read())
        self.sensitive_words = sensitive_words_config["sensitive_words"]  # 敏感词列表

        self.bot = pywxdll.Pywxdll(self.ip, self.port)  # 机器人

        self.db = BotDatabase()

    async def run(self, recv):
        user_wxid = recv["sender"]
        gpt_request_message = " ".join(recv["content"][1:])  # 用户问题

        error_message = ""

        if not (
                self.db.get_points(user_wxid) >= self.gpt_point_price
                or self.db.get_whitelist(user_wxid) == 1
                or user_wxid in self.admins
        ):  # 积分足够或在白名单或在管理员
            error_message = f"-----XYBot-----\n积分不足,需要{self.gpt_point_price}点⚠️"
        elif len(recv["content"]) < 2:  # 指令格式正确
            error_message = "-----XYBot-----\n参数错误!❌"
        elif not self.senstitive_word_check(gpt_request_message):  # 敏感词检查
            error_message = "-----XYBot-----\n内容包含敏感词!⚠️"

        if not error_message:
            out_message = "-----XYBot-----\n已收到指令，处理中，请勿重复发送指令！👍"  # 发送已收到信息，防止用户反复发送命令
            self.send_friend_or_group(recv, out_message)

            if self.db.get_whitelist(user_wxid) == 1 or user_wxid in self.admins:  # 如果用户在白名单内/是管理员
                chatgpt_answer = await self.chatgpt(gpt_request_message)
                if chatgpt_answer[0]:
                    out_message = f"-----XYBot-----\n因为你在白名单内，所以没扣除积分！👍\nChatGPT回答：\n{chatgpt_answer[1]}\n\n⚙️ChatGPT版本：{self.gpt_version}"
                else:
                    out_message = f"-----XYBot-----\n出现错误！⚠️{chatgpt_answer}"
                self.send_friend_or_group(recv, out_message)

            elif self.db.get_points(user_wxid) >= self.gpt_point_price:
                self.db.add_points(user_wxid, self.gpt_point_price * -1)  # 减掉积分
                chatgpt_answer = await self.chatgpt(gpt_request_message)  # 从chatgpt api 获取回答
                if chatgpt_answer[0]:
                    out_message = f"-----XYBot-----\n已扣除{self.gpt_point_price}点积分，还剩{self.db.get_points(user_wxid)}点积分👍\nChatGPT回答：\n{chatgpt_answer[1]}\n\n⚙️ChatGPT版本：{self.gpt_version}"  # 创建信息
                else:
                    self.db.add_points(user_wxid, self.gpt_point_price)  # 补回积分
                    out_message = f"-----XYBot-----\n出现错误，已补回积分！⚠️{chatgpt_answer}"
                self.send_friend_or_group(recv, out_message)
        else:
            self.send_friend_or_group(recv, error_message)

    async def chatgpt(self, gpt_request_message):
        client = AsyncOpenAI(api_key=self.openai_api_key, base_url=self.openai_api_base)
        try:
            chat_completion = await client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": gpt_request_message,
                    }
                ],
                model=self.gpt_version,
                temperature=self.gpt_temperature,
                max_tokens=self.gpt_max_token,
            )
            return True, chat_completion.choices[0].message.content
        except Exception as error:
            return False, error

    def senstitive_word_check(self, message):  # 检查敏感词
        for word in self.sensitive_words:
            if word in message:
                return False
        return True

    def send_friend_or_group(self, recv, out_message="null"):
        if recv["fromType"] == "chatroom":  # 判断是群还是私聊
            logger.info(f'[发送@信息]{out_message}| [发送到] {recv["from"]}')
            self.bot.send_at_msg(recv["from"], "\n" + out_message, [recv["sender"]])

        else:
            logger.info(f'[发送信息]{out_message}| [发送到] {recv["from"]}')
            self.bot.send_text_msg(recv["from"], out_message)  # 发送

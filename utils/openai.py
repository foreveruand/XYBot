from openai import AsyncOpenAI,AsyncAzureOpenAI
import config.config as CONFIG
from utils.database import BotDatabase
from typing import Dict
import yaml
import base64
from mimetypes import guess_type
from loguru import logger
from .openai_plugin_manager import plugin_manager as openai_function_manager
import tiktoken
import json

_openai_provider = CONFIG.OPENAI_PROVIDER
_model = CONFIG.GPT_VERSION
_max_tokens = CONFIG.MAX_TOKENS
def update_config(provider, model):
    global _openai_provider, _model
    _openai_provider = provider
    _model = model
    file_path = 'config/config.py'
    CONFIG.OPENAI_PROVIDER=provider
    CONFIG.GPT_VERSION=model
    with open(file_path, 'r') as file:
        lines = file.readlines()
    for i, line in enumerate(lines):
        if line.startswith('OPENAI_PROVIDER='):
            lines[i] = f'OPENAI_PROVIDER=\"{provider}\"\n'
        elif line.startswith('GPT_VERSION='):
            lines[i] = f'GPT_VERSION=\"{model}\"\n'
    with open(file_path, 'w') as file:    
        file.writelines(lines)

async def compose_gpt_dialogue_request_content(wxid: str, new_message: str) -> list:
    db = BotDatabase()
    json_data = db.get_private_gpt_data(wxid)  # 从数据库获得到之前的对话
    request_content = []
    if not json_data or "data" not in json_data.keys():  # 如果没有对话数据，则初始化
        init_data = {"data": []}
        json_data = init_data
        request_content = [{"role": "system", "content": "Please try to keep your response concise, ideally within 50 words."}]

    previous_dialogue = json_data['data']  # 获取指定轮数的对话，乘-2是因为一轮对话包含了1个请求和1个答复
    token_count= count_tokens(previous_dialogue)
    if token_count > _max_tokens:
        logger.info("Token count exceeds the limit, summarizing the conversation")
        summary = await summarise(previous_dialogue)
        request_content = [{"role": "system", "content": "Please try to keep your response concise, ideally within 50 words."}]
        request_content.append({"role": "assistant", "content": summary})
        json_data = {"data": request_content}  # 构成保存需要的json数据
        db=BotDatabase()
        db.save_private_gpt_data(wxid, json_data)
    else:
        request_content += previous_dialogue  # 将之前的对话加入到api请求内容中

    request_content.append({"role": "user", "content": new_message})  # 将用户新的问题加入api请求内容

    return request_content
    
async def chatgpt(wxid: str, message: str):  # 这个函数请求了openai的api
    request_content = [] 
    if _openai_provider == "azure" :
        client = AsyncAzureOpenAI(
            api_key=CONFIG.OPENAI_API_KEY,
            azure_endpoint=CONFIG.OPENAI_API_BASE,
            api_version="2024-07-01-preview",
        )
    elif _openai_provider == "workers":
        client = AsyncOpenAI(
            api_key= CONFIG.CLOUDFLARE_API_KEY,
            base_url= f"https://api.cloudflare.com/client/v4/accounts/{CONFIG.CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        )
    else :
        client = AsyncOpenAI(api_key=CONFIG.DEEPSEEK_API_KEY, base_url=CONFIG.DEEPSEEK_API_BASE)
    try:
        if _openai_provider == "azure":
            response = await client.chat.completions.create(
                model=_model,
                messages=[{"role":"user","content":message}],
                tools=openai_function_manager.get_functions_specs('azure'),
                tool_choice="auto",
            )
            # logger.info(f"send request with tool:{openai_function_manager.get_functions_specs('azure')}")
            # Process the model's response
            response_message = response.choices[0].message
            request_content = await compose_gpt_dialogue_request_content(wxid, message)
            # Handle function calls
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    if tool_call.function.name :
                        function_args = tool_call.function.arguments
                        function_response = await openai_function_manager.call_function(tool_call.function.name, function_args)
                        # logger.info(f"get function {tool_call.function.name} response message:{function_response}")
                        request_content = add_function_call_to_request(request_content=request_content, 
                            function_name=tool_call.function.name,content=function_response,tool_call_id=tool_call.id,arguments=function_args)
        elif _openai_provider == "openai":
            response = await client.chat.completions.create(
                model=_model,
                messages=[{"role":"user","content":message}],
                functions=openai_function_manager.get_functions_specs(),
                function_call="auto",
            )
            # Process the model's response
            response_message = response.choices[0].message
            request_content = await compose_gpt_dialogue_request_content(wxid, message)
            # Handle function calls
            if response_message.function_call:
                for tool_call in response_message.function_call:
                    if tool_call.name:
                        function_args = tool_call.arguments
                        function_response = await openai_function_manager.call_function(tool_call.name, function_args)
                        # logger.info(f"get web response:{web_response}")
                        request_content = add_function_call_to_request(request_content=request_content, 
                            function_name=tool_call.name,content=function_response,arguments=function_args)
        else:
            request_content = await compose_gpt_dialogue_request_content(wxid, message)
        logger.info(f"final requests:{request_content}")
        chat_completion = await client.chat.completions.create(
            messages=request_content,
            model=_model,
            temperature=CONFIG.TEMPERATURE,
            max_tokens=CONFIG.MAX_TOKENS,
            timeout=5.0,
            stream=False
        )  # 调用openai api
        logger.info(f"final response:{chat_completion.choices[0]}")
        save_gpt_dialogue_request_content(wxid, request_content,
                                            chat_completion.choices[0].message.content)  # 保存对话请求与回答内容
        return True, chat_completion.choices[0].message.content  # 返回对话回答内容
    except Exception as error:
        return False, error

async def chatgpt_img(wxid:str, image_path: str, message: str = "Describe this picture:"):
    # Function to encode a local image into data URL 
    # Guess the MIME type of the image based on the file extension
    mime_type, _ = guess_type(image_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'  # Default MIME type if none is found

    # Read and encode the image file
    with open(image_path, "rb") as image_file:
        base64_encoded_data = base64.b64encode(image_file.read()).decode('utf-8')
    # Construct the data URL
    # return f"data:{mime_type};base64,{base64_encoded_data}"

    request_content = await compose_gpt_dialogue_request_content(wxid, message)  # 构成对话请求内容，返回一个包含之前对话的列表
    request_content.append({"type": "image_url","image_url": {"url": "data:image/jpeg;base64,{base64_encoded_data}"}})

    if _openai_provider == "azure" :
        client = AsyncAzureOpenAI(
            api_key=CONFIG.OPENAI_API_KEY,
            azure_endpoint=CONFIG.OPENAI_API_BASE,
            api_version="2024-07-01-preview",
        )
    else:
        client = AsyncOpenAI(api_key=CONFIG.OPENAI_API_KEY, base_url=CONFIG.OPENAI_API_BASE)
    try:
        chat_completion = client.chat.completions.create(
            messages=request_content,
            model=CONFIG.GPT_VISION_VERSION,
            temperature=CONFIG.TEMPERATURE,
            max_tokens=CONFIG.MAX_TOKENS,
        )  # 调用openai api

        save_gpt_dialogue_request_content(wxid, request_content,
                                                chat_completion.choices[0].message.content)  # 保存对话请求与回答内容
        return True, chat_completion.choices[0].message.content  # 返回对话回答内容
    except Exception as error:
        return False, error

def save_gpt_dialogue_request_content(wxid: str, request_content: list, gpt_response: str) -> None:
    request_content = [msg for msg in request_content if isinstance(msg, dict) ]
    # logger.debug(f"save request:{str(request_content)};\nresponse:{gpt_response}")
    request_content.append({"role": "assistant", "content": gpt_response})  # 将gpt回答加入到api请求内容
    # request_content = request_content[CONFIG.DIALOGUE_COUNT * -2:]  # 将列表切片以符合指定的对话轮数，乘-2是因为一轮对话包含了1个请求和1个答复

    json_data = {"data": request_content}  # 构成保存需要的json数据
    db=BotDatabase()
    db.save_private_gpt_data(wxid, json_data)  # 保存到数据库中

def add_function_call_to_request(request_content, function_name, content,tool_call_id=None,arguments=None):
    """
    Adds a function call to the request
    """
    if _openai_provider == "azure":
        request_content.append({"role": "assistant", 'tool_calls': [{'id': tool_call_id, 'function': {'arguments': arguments, 'name':  function_name}, 'type': 'function'}]})
        request_content.append({
            "tool_call_id": tool_call_id,
            "role": "tool",
            "name": function_name,
            "content": content,
        })
    else:
        request_content.append({
            "role": "function",
            "name": function_name,
            "content": content,
        })
    return request_content

def senstitive_word_check(message):  # 检查敏感词
    sensitive_words_path = "sensitive_words.yml"  # 加载敏感词yml
    with open(sensitive_words_path, "r", encoding="utf-8") as f:  # 读取设置
        sensitive_words_config = yaml.safe_load(f.read())
    sensitive_words = sensitive_words_config["sensitive_words"]  # 敏感词列表
    for word in sensitive_words:
        if word in message:
            return False
    return True

async def summarise(conversation) -> str:
    """
    Summarises the conversation history.
    :param conversation: The conversation history
    :return: The summary
    """
    messages = [
        {"role": "system", "content": "Summarize this conversation in 700 characters or less"}
    ] + conversation
    if _openai_provider == "azure" :
        client = AsyncAzureOpenAI(
            api_key=CONFIG.OPENAI_API_KEY,
            azure_endpoint=CONFIG.OPENAI_API_BASE,
            api_version="2024-07-01-preview",
        )
    elif _openai_provider == "workers":
        client = AsyncOpenAI(
            api_key= CONFIG.CLOUDFLARE_API_KEY,
            base_url= f"https://api.cloudflare.com/client/v4/accounts/{CONFIG.CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        )
    else :
        client = AsyncOpenAI(api_key=CONFIG.DEEPSEEK_API_KEY, base_url=CONFIG.DEEPSEEK_API_BASE)
    response = await client.chat.completions.create(
        model=_model,
        messages=messages,
        temperature=0.4,
    )
    return response.choices[0].message.content
def count_tokens(messages) -> int:
    """
    Counts the number of tokens required to send the given messages.
    :param messages: the messages to send
    :return: the number of tokens required
    """
    model = _model
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")

    tokens_per_message = 3
    tokens_per_name = 1
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            if key == 'content':
                if isinstance(value, str):
                    num_tokens += len(encoding.encode(value))
                else:
                    for message1 in value:
                        if message1['type'] == 'image_url':
                            pass
                        else:
                            num_tokens += len(encoding.encode(message1['text']))
            else:
                try:
                    num_tokens += len(encoding.encode(value))
                except:
                    value_str = json.dumps(value)
                    try:
                        num_tokens += len(encoding.encode(value_str))
                    except:
                        pass
                if key == "name":
                    num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens
def clear_dialogue(wxid):  # 清除对话记录
    db=BotDatabase()
    db.save_private_gpt_data(wxid, {"data": []})
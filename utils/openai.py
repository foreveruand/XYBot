from openai import AsyncOpenAI,AsyncAzureOpenAI
import config.config as CONFIG
from utils.database import BotDatabase
from typing import Dict
import yaml
import base64
from mimetypes import guess_type
from loguru import logger
import requests
import json

_openai_provider = CONFIG.OPENAI_PROVIDER
_model = CONFIG.GPT_VERSION

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

def bing_search(query):
    subscription_key = CONFIG.BING_API_KEY
    # search_url = 
    # headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    # params = {"q": query, "textDecorations": True, "textFormat": "HTML"}
    # response = requests.get(search_url, headers=headers, params=params)
    # response.raise_for_status()

    endpoint = "https://api.bing.microsoft.com" + "/v7.0/search"
    # Construct a request
    mkt = 'zh-CN'
    params = { 'q': query, 'mkt': mkt }
    headers = { 'Ocp-Apim-Subscription-Key': subscription_key }
    # Call the API
    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        results = response.json()
        results = results['webPages']['value'][:2]
        if results is None or len(results) == 0:
            return {"Result": "No good Bing Search Result was found"}

        def to_metadata(result: Dict) -> Dict[str, str]:
            return {
                "snippet": result["snippet"],
                "link": result["url"],
            }  
        # return {"Result": "No good Bing Search Result was found"}
        return {"result": [to_metadata(result) for result in results]}
    except Exception as ex:
        raise ex
    

def compose_gpt_dialogue_request_content(wxid: str, new_message: str) -> list:
    db = BotDatabase()
    json_data = db.get_private_gpt_data(wxid)  # 从数据库获得到之前的对话

    if not json_data or "data" not in json_data.keys():  # 如果没有对话数据，则初始化
        init_data = {"data": []}
        json_data = init_data

    previous_dialogue = json_data['data'][CONFIG.DIALOGUE_COUNT * -2:]  # 获取指定轮数的对话，乘-2是因为一轮对话包含了1个请求和1个答复
    request_content = [{"role": "system", "content": "Please try to keep your response concise, ideally within 50 words."}]
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
        logger.info(f"send request to azure: {_openai_provider} with model {_model}")
    elif _openai_provider == "workers":
        client = AsyncOpenAI(
            api_key= CONFIG.CLOUDFLARE_API_KEY,
            base_url= f"https://api.cloudflare.com/client/v4/accounts/{CONFIG.CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        )
    else :
        client = AsyncOpenAI(api_key=CONFIG.DEEPSEEK_API_KEY, base_url=CONFIG.DEEPSEEK_API_BASE)
        logger.info(f"send request to deepseek: {_openai_provider} with model {_model} to {CONFIG.DEEPSEEK_API_BASE}")
    try:
        if _openai_provider == "azure" :
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Execute a web search for the given query and return a list of results",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "the user query",
                                },
                            },
                            "required": ["query"],
                        },
                    }
                }
            ]
            response = await client.chat.completions.create(
                model=_model,
                messages=[{"role":"user","content":message}],
                tools=tools,
                tool_choice="auto",
            )
            # Process the model's response
            response_message = response.choices[0].message
            request_content = compose_gpt_dialogue_request_content(wxid, message)
            # Handle function calls
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    if tool_call.function.name == "web_search":
                        function_args = json.loads(tool_call.function.arguments)
                        web_response = bing_search(function_args["query"])
                        # logger.info(f"get web response:{web_response}")
                        request_content.append({"role": "assistant", 'tool_calls': [{'id': tool_call.id, 'function': {'arguments': function_args["query"], 'name':  "web_search"}, 'type': 'function'}]})
                        request_content.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": "web_search",
                            "content": json.dumps(web_response),
                        })
        else:
            function = {
                        "name": "web_search",
                        "description": "Execute a web search for the given query and return a list of results",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "the user query",
                                },
                            },
                            "required": ["query"],
                        },
                    }
            response = await client.chat.completions.create(
                model=_model,
                messages=[{"role":"user","content":message}],
                functions=function,
                function_call="auto",
            )
            # Process the model's response
            response_message = response.choices[0].message
            request_content = compose_gpt_dialogue_request_content(wxid, message)
            # Handle function calls
            if response_message.function_call:
                for tool_call in response_message.function_call:
                    if tool_call.name == "web_search":
                        function_args = json.loads(tool_call.arguments)
                        web_response = bing_search(function_args["query"])
                        # logger.info(f"get web response:{web_response}")
                        request_content.append({
                            "role": "function",
                            "name": "web_search",
                            "content": json.dumps(web_response),
                        })
            # request_content = compose_gpt_dialogue_request_content(wxid, message)
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

    request_content = compose_gpt_dialogue_request_content(wxid, message)  # 构成对话请求内容，返回一个包含之前对话的列表
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
    logger.debug(f"save request:{str(request_content)};\nresponse:{gpt_response}")
    request_content.append({"role": "assistant", "content": gpt_response})  # 将gpt回答加入到api请求内容
    request_content = request_content[CONFIG.DIALOGUE_COUNT * -2:]  # 将列表切片以符合指定的对话轮数，乘-2是因为一轮对话包含了1个请求和1个答复

    json_data = {"data": request_content}  # 构成保存需要的json数据
    db=BotDatabase()
    db.save_private_gpt_data(wxid, json_data)  # 保存到数据库中

def senstitive_word_check(message):  # 检查敏感词
    sensitive_words_path = "sensitive_words.yml"  # 加载敏感词yml
    with open(sensitive_words_path, "r", encoding="utf-8") as f:  # 读取设置
        sensitive_words_config = yaml.safe_load(f.read())
    sensitive_words = sensitive_words_config["sensitive_words"]  # 敏感词列表
    for word in sensitive_words:
        if word in message:
            return False
    return True


def clear_dialogue(wxid):  # 清除对话记录
    db=BotDatabase()
    db.save_private_gpt_data(wxid, {"data": []})
import json
import yaml
# from openai_plugin.gtts_text_to_speech import GTTSTextToSpeech
# from openai_plugin.auto_tts import AutoTextToSpeech
# from openai_plugin.dice import DicePlugin
# from openai_plugin.youtube_audio_extractor import YouTubeAudioExtractorPlugin
# from openai_plugin.ddg_image_search import DDGImageSearchPlugin
# from openai_plugin.spotify import SpotifyPlugin
# from openai_plugin.crypto import CryptoPlugin
# from openai_plugin.weather import WeatherPlugin
# from openai_plugin.ddg_web_search import DDGWebSearchPlugin
from .openai_plugin.bing_web_search import BINGWebSearchPlugin
# from openai_plugin.wolfram_alpha import WolframAlphaPlugin
# from openai_plugin.deepl import DeeplTranslatePlugin
# from openai_plugin.worldtimeapi import WorldTimeApiPlugin
# from openai_plugin.whois_ import WhoisPlugin
# from openai_plugin.webshot import WebshotPlugin
# from openai_plugin.iplocation import IpLocationPlugin


class OpenAIPluginManager:
    """
    A class to manage the plugins and call the correct functions
    """

    def __init__(self):
        with open("main_config.yml", "r", encoding="utf-8") as f:  # 读取设置
            config = yaml.safe_load(f.read())
        enabled_plugins = config["openai_functions"]
        plugin_mapping = {
            # 'wolfram': WolframAlphaPlugin,
            # 'weather': WeatherPlugin,
            # 'crypto': CryptoPlugin,
            # 'ddg_web_search': DDGWebSearchPlugin,
            # 'ddg_image_search': DDGImageSearchPlugin,
            # 'spotify': SpotifyPlugin,
            # 'worldtimeapi': WorldTimeApiPlugin,
            # 'youtube_audio_extractor': YouTubeAudioExtractorPlugin,
            # 'dice': DicePlugin,
            # 'deepl_translate': DeeplTranslatePlugin,
            # 'gtts_text_to_speech': GTTSTextToSpeech,
            # 'auto_tts': AutoTextToSpeech,
            # 'whois': WhoisPlugin,
            # 'webshot': WebshotPlugin,
            # 'iplocation': IpLocationPlugin,
            'bing_web_search': BINGWebSearchPlugin,
        }
        self.plugins = [plugin_mapping[plugin]() for plugin in enabled_plugins if plugin in plugin_mapping]

    def get_functions_specs(self,provider='openai'):
        """
        Return the list of function specs that can be called by the model
        """
        if provider=='azure':
            return [{"type":"function","function": spec} for specs in map(lambda plugin: plugin.get_spec(), self.plugins) for spec in specs]
        else:
            return [spec for specs in map(lambda plugin: plugin.get_spec(), self.plugins) for spec in specs]

    async def call_function(self, function_name, arguments):
        """
        Call a function based on the name and parameters provided
        """
        plugin = self.__get_plugin_by_function_name(function_name)
        if not plugin:
            return json.dumps({'error': f'Function {function_name} not found'})
        return json.dumps(await plugin.execute(function_name, **json.loads(arguments)), default=str)

    def get_plugin_source_name(self, function_name) -> str:
        """
        Return the source name of the plugin
        """
        plugin = self.__get_plugin_by_function_name(function_name)
        if not plugin:
            return ''
        return plugin.get_source_name()

    def __get_plugin_by_function_name(self, function_name):
        return next((plugin for plugin in self.plugins
                    if function_name in map(lambda spec: spec.get('name'), plugin.get_spec())), None)

plugin_manager = OpenAIPluginManager()
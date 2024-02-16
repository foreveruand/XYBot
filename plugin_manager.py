import importlib
import os

import yaml
from loguru import logger

from plugin_interface import PluginInterface
from singleton import singleton


@singleton
class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.keywords = {}

        with open('main_config.yml', 'r', encoding='utf-8') as f:  # 读取设置
            config = yaml.safe_load(f.read())

        self.excluded_plugins = config['excluded_plugins']

    def refresh_keywords(self):
        self.keywords.clear()
        plugins_folder = './plugins'
        plugin_config_path = []

        # 遍历文件夹中的所有文件
        for root, dirs, files in os.walk(plugins_folder):
            for file in files:
                if file.endswith('.yml') and not file.startswith('_'):
                    # 处理符合条件的文件
                    file_path = os.path.join(root, file)
                    plugin_config_path.append(file_path)

        for path in plugin_config_path:
            with open(path, 'r', encoding='utf-8') as f:  # 读取设置
                config = yaml.safe_load(f.read())

            keywords_list = config['keywords']
            plugin_name = config['plugin_name']

            if plugin_name in self.plugins.keys():
                for keyword in keywords_list:
                    self.keywords[keyword] = plugin_name

        logger.info('已刷新指令关键词')

    def get_keywords(self):
        return self.keywords

    def load_plugin(self, plugin_name, launchload=False):
        if plugin_name not in self.plugins and plugin_name not in self.excluded_plugins and plugin_name != [
            'manage_plugins']:
            module = importlib.import_module(f'plugins.{plugin_name}')
            plugin_class = getattr(module, plugin_name)
            if issubclass(plugin_class, PluginInterface):
                plugin_instance = plugin_class()
                self.plugins[plugin_name] = plugin_instance
                logger.info(f'+ 已加载插件：{plugin_name}')
                if not launchload:
                    self.refresh_keywords()
                return True

            return False
        return False

    def load_plugins(self, plugin_dir, launchload=False):
        logger.info('开始加载所有插件')
        for plugin_file in os.listdir(plugin_dir):
            if plugin_file.endswith(".py") and plugin_file != "__init__.py" and not plugin_file.startswith('_'):
                plugin_name = os.path.splitext(plugin_file)[0]
                self.load_plugin(plugin_name, launchload=launchload)
        self.refresh_keywords()

    def unload_plugin(self, plugin_name):
        if plugin_name in self.plugins and plugin_name != ['manage_plugins']:
            del self.plugins[plugin_name]
            self.refresh_keywords()
            logger.info(f'- 已卸载插件：{plugin_name}')
            self.refresh_keywords()
            return True
        else:
            return False

    def reload_plugin(self, plugin_name):
        if self.unload_plugin(plugin_name) and plugin_name != ['manage_plugins']:
            if self.load_plugin(plugin_name):
                logger.info(f'! 已重载插件：{plugin_name}')
                self.refresh_keywords()
                return True
            else:
                logger.info(f'! 重载插件失败：{plugin_name}')
                return False
        else:
            logger.info(f'! 重载插件失败：{plugin_name}')
            return False


# 实例化插件管理器
plugin_manager = PluginManager()

from typing import Dict, List, Optional, Any
from playwright.sync_api import Page
import allure

from .base_plugin import FlowPlugin


class PluginManager:
    """Менеджер для управления плагинами"""
    
    def __init__(self, browser_type: str):
        self.browser_type = browser_type
        self.plugins: List[FlowPlugin] = []
        self.enabled_hooks: Dict[str, List[FlowPlugin]] = {}
    
    def register_plugin(self, plugin: FlowPlugin):
        """Регистрация плагина"""
        self.plugins.append(plugin)
        
        # Регистрируем хуки плагина
        for hook_name in plugin.get_supported_hooks().keys():
            if hook_name not in self.enabled_hooks:
                self.enabled_hooks[hook_name] = []
            self.enabled_hooks[hook_name].append(plugin)
        
        print(f"[PLUGIN MANAGER] Зарегистрирован плагин: {plugin.PLUGIN_NAME}")
    
    def register_default_plugins(self, config: Optional[Dict] = None):
        """Регистрация плагинов по умолчанию на основе браузера"""
        
        # Всегда регистрируем плагин видео метрик
        from .video_metrics_plugin import VideoMetricsPlugin
        self.register_plugin(VideoMetricsPlugin(self.browser_type))
        
        # Для Chromium регистрируем дополнительные плагины
        if self.browser_type == "chromium":
            from .lighthouse_plugin import LighthousePlugin
            from .cdp_plugin import CDPPlugin
            
            # Lighthouse плагин
            lighthouse_path = (config or {}).get('lighthouse_path', 'lighthouse')
            self.register_plugin(LighthousePlugin(self.browser_type, lighthouse_path))
            
            # CDP плагин
            self.register_plugin(CDPPlugin(self.browser_type))
        
        print(f"[PLUGIN MANAGER] Зарегистрировано {len(self.plugins)} плагинов для {self.browser_type}")
    
    def execute_hooks(self, hook_name: str, page: Page, context: Dict, **kwargs) -> List[Any]:
        """Выполнение всех зарегистрированных хуков"""
        results = []
        
        if hook_name not in self.enabled_hooks:
            print(f"[PLUGIN MANAGER] Нет плагинов для хука: {hook_name}")
            return results
        
        with allure.step(f"Выполнение хука: {hook_name}"):
            for plugin in self.enabled_hooks[hook_name]:
                try:
                    print(f"[PLUGIN MANAGER] Запуск {plugin.PLUGIN_NAME} для хука {hook_name}")
                    result = plugin.execute_hook(hook_name, page, context, **kwargs)
                    if result is not None:
                        results.append({
                            "plugin": plugin.PLUGIN_NAME,
                            "result": result
                        })
                except Exception as e:
                    error_msg = f"Plugin {plugin.PLUGIN_NAME} failed in hook {hook_name}: {str(e)}"
                    context.setdefault("errors", []).append(error_msg)
                    print(f"[PLUGIN MANAGER] Ошибка: {error_msg}")
        
        return results
    
    def get_plugin(self, plugin_name: str) -> Optional[FlowPlugin]:
        """Получение плагина по имени"""
        for plugin in self.plugins:
            if plugin.PLUGIN_NAME == plugin_name:
                return plugin
        return None
    
    def get_active_plugins(self) -> List[str]:
        """Получение списка активных плагинов"""
        return [p.PLUGIN_NAME for p in self.plugins]
    
    def shutdown(self):
        """Завершение работы всех плагинов"""
        for plugin in self.plugins:
            try:
                # Если плагин поддерживает хук after_test, выполняем его
                if "after_test" in plugin.get_supported_hooks():
                    print(f"[PLUGIN MANAGER] Завершение плагина: {plugin.PLUGIN_NAME}")
            except:
                pass
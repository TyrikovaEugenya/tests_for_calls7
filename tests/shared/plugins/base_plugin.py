from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from playwright.sync_api import Page
import allure
import config


class FlowPlugin(ABC):
    """Базовый класс плагина для расширения флоу"""
    
    PLUGIN_NAME: str = "base_plugin"
    SUPPORTED_BROWSERS: List[str] = config.BROWSERS  # Все браузеры по умолчанию
    
    def __init__(self, browser_type: str):
        self.browser_type = browser_type
        self.is_supported = browser_type in self.SUPPORTED_BROWSERS
    
    @abstractmethod
    def get_supported_hooks(self) -> Dict[str, List[str]]:
        """
        Возвращает поддерживаемые хуки и их описание
        Формат: {"hook_name": ["description", "required_params"]}
        """
        pass
    
    @abstractmethod
    def execute_hook(self, hook_name: str, page: Page, context: Dict, **kwargs) -> Optional[Any]:
        """Выполнение хука"""
        pass
    
    def is_browser_supported(self) -> bool:
        """Проверка поддержки текущего браузера"""
        return self.is_supported
    
    def _log_unsupported(self, hook_name: str):
        """Логирование для неподдерживаемых браузеров"""
        if not self.is_supported:
            print(f"[INFO] Plugin '{self.PLUGIN_NAME}' skipped for {self.browser_type} in hook '{hook_name}'")
            return True
        return False
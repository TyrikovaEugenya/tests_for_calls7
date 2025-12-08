import pytest
import allure
from tests.shared.base_user_flow_improwed_test import BaseUserFlowTest, FlowBranch, UserFlowBuilder, HandlePhonePopupStep, NavigateToFilmPageStep
from config import SELECTORS, DEVICES, THROTTLING_MODES, GEO_LOCATIONS, PAY_METHODS
from typing import Dict, List, Optional, Any, Callable

class TestGoodmovieUserFlowImproved(BaseUserFlowTest):
    BASE_URL = "https://tests.goodmovie.net"
    SELECTORS = SELECTORS
    DOMAIN_NAME = "tests.goodmovie"
    
    def get_test_context(self, **kwargs) -> Dict:
        """Получение контекста теста"""
        return {
            "base_url": self.BASE_URL,
            "film_url": kwargs.get("film_url"),
            "device": kwargs.get("device"),
            "throttling": kwargs.get("throttling"),
            "geo": kwargs.get("geo"),
            "browser_type": kwargs.get("browser_type"),
            "pay_method": kwargs.get("pay_method"),
            "test_name": kwargs.get("test_name", "unknown"),
            "selectors": self.SELECTORS
        }
    
    @pytest.mark.parametrize("device", DEVICES)
    @pytest.mark.parametrize("throttling", THROTTLING_MODES)
    @pytest.mark.parametrize("geo", GEO_LOCATIONS)
    @pytest.mark.parametrize("pay_method", PAY_METHODS)
    @allure.story("User Flow: Главная → Фильм → Телефон → Оплата")
    @allure.title("Полный user flow с новой архитектурой")
    def test_user_flow_improved(self, page, get_film_url, device, throttling, 
                                geo, browser_type, pay_method, request):
        # Подготовка контекста
        test_context = self.get_test_context(
            film_url=get_film_url,
            device=device,
            throttling=throttling,
            geo=geo,
            browser_type=browser_type,
            pay_method=pay_method,
            test_name=request.node.name
        )
        
        # Запуск флоу
        metrics = self.run_flow(page, **test_context)
        
        # Проверка результатов
        if metrics.is_problematic:
            pytest.fail(f"Test completed with problems. Errors: {len(metrics.errors)}")
        
        # Дополнительные проверки
        assert metrics.flow_branch in [b.value for b in FlowBranch], f"Invalid flow branch: {metrics.flow_branch}"
        
        # Проверка ключевых метрик
        film_page_metrics = metrics.step_metrics.get("Переход на страницу фильма", {})
        if film_page_metrics.get("videoStartTime"):
            assert film_page_metrics["videoStartTime"] < 15000, "Video start time too high"
        
        # Добавление информации в Allure
        allure.dynamic.description(
            f"**Домен**: {self.DOMAIN_NAME}\n"
            f"**Устройство**: {device}\n"
            f"**Сеть**: {throttling}\n"
            f"**ГЕО**: {geo}\n"
            f"**Браузер**: {browser_type}\n"
            f"**Способ оплаты**: {pay_method}\n"
            f"**Ветка флоу**: {metrics.flow_branch}\n"
            f"**Проблемы**: {'Да' if metrics.is_problematic else 'Нет'}"
        )



class TestGoodmovieFlowBranches(BaseUserFlowTest):
    """Тестирование разных веток флоу"""
    BASE_URL = "https://tests.goodmovie.net"
    SELECTORS = SELECTORS
    DOMAIN_NAME = "tests.goodmovie"
    
    @pytest.mark.parametrize("phone_type", ["valid", "invalid", "error"])
    @allure.story("Тестирование разных веток флоу (валидный/невалидный номер)")
    @allure.title("Ветки флоу для типа телефона: {phone_type}")
    def test_flow_branches(self, page, get_film_url, device, throttling, 
                                geo, browser_type, pay_method, request, phone_type):
        # Настройка кастомного флоу
        self.flow_builder = UserFlowBuilder()
        self.flow_builder.add_step(NavigateToFilmPageStep("Переход на страницу фильма"))
        
        # Специальный шаг с указанным типом телефона
        self.flow_builder.add_step(
            HandlePhonePopupStep("Обработка попапа с телефоном", phone_type=phone_type)
        )
        
        # Контекст теста
        context = {
            "film_url": get_film_url,
            "test_name": request.node.name,
            "selectors": self.SELECTORS,
            "phone_type": phone_type,
            "base_url": self.BASE_URL
        }
        
        # Запуск теста
        metrics = self.run_flow(page, **context)
        
        # Валидация ветки флоу
        expected_branch = {
            "valid": FlowBranch.CARD.value,  # или SMS
            "invalid": FlowBranch.ERROR.value,
            "error": FlowBranch.ERROR.value
        }.get(phone_type, FlowBranch.ERROR.value)
        
        assert metrics.flow_branch == expected_branch, \
            f"Expected branch {expected_branch}, got {metrics.flow_branch}"
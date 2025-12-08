from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import time
import json
from pathlib import Path
import allure
import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from enum import Enum

class FlowStep(Enum):
    """Шаги пользовательского флоу"""
    MAIN_PAGE = "main_page"
    FILM_PAGE = "film_page"
    VIDEO_PLAYBACK = "video_playback"
    PHONE_POPUP = "phone_popup"
    PAYMENT_PAGE = "payment_page"
    SMS_VERIFICATION = "sms_verification"
    AFTER_PAYMENT = "after_payment"


@dataclass
class TestMetrics:
    """Контейнер для метрик теста"""
    step_metrics: Dict[str, Dict] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    flow_branch: Optional[str] = None  # error/card/sms
    is_problematic: bool = False
    
    def add_metric(self, step: str, metric_name: str, value: Any):
        """Добавление метрики для шага"""
        if step not in self.step_metrics:
            self.step_metrics[step] = {}
        self.step_metrics[step][metric_name] = value
    
    def add_error(self, error: str):
        """Добавление ошибки"""
        self.errors.append(f"{datetime.now().isoformat()}: {error}")
        self.is_problematic = True
        

class BaseTestStep(ABC):
    """Базовый класс для шага теста"""
    
    def __init__(self, name: str, timeout: int = 30000):
        self.name = name
        self.timeout = timeout
    
    @abstractmethod
    def execute(self, page: Page, context: Dict) -> Dict:
        """Выполнение шага"""
        pass
    
    def safe_execute(self, page: Page, context: Dict) -> Dict:
        """Безопасное выполнение с обработкой ошибок"""
        try:
            with allure.step(self.name):
                return self.execute(page, context)
        except Exception as e:
            error_msg = f"Step '{self.name}' failed: {str(e)}"
            context['metrics'].add_error(error_msg)
            return {"success": False, "error": error_msg}
        

class VideoMetricsCollector:
    """Класс для сбора метрик видеоплеера"""
    
    @staticmethod
    def collect_video_start_time(page: Page, timeout: int = 30) -> Optional[float]:
        """Сбор времени старта видео с использованием Performance API"""
        try:
            # Используем Performance API для точного измерения
            video_start = page.evaluate("""
                () => {
                    // Ищем первый video элемент
                    const video = document.querySelector('video');
                    if (!video) return null;
                    
                    // Используем Performance API для точного времени
                    const entries = performance.getEntriesByType('resource');
                    const videoEntries = entries.filter(e => 
                        e.initiatorType === 'video' || 
                        e.name.includes('.mp4') || 
                        e.name.includes('.m3u8')
                    );
                    
                    if (videoEntries.length > 0) {
                        return videoEntries[0].responseStart || videoEntries[0].startTime;
                    }
                    
                    // Альтернатива: слушаем события video
                    return new Promise(resolve => {
                        const onCanPlay = () => {
                            video.removeEventListener('canplay', onCanPlay);
                            resolve(performance.now());
                        };
                        
                        if (video.readyState >= 3) {
                            resolve(performance.now());
                        } else {
                            video.addEventListener('canplay', onCanPlay);
                            setTimeout(() => resolve(null), 5000);
                        }
                    });
                }
            """)
            
            if video_start:
                return float(video_start)
        except Exception as e:
            print(f"[WARNING] Video metrics collection failed: {e}")
        
        return None
    
    @staticmethod
    def collect_buffering_metrics(page: Page) -> Dict:
        """Сбор метрик буферизации"""
        try:
            metrics = page.evaluate("""
                () => {
                    const video = document.querySelector('video');
                    if (!video) return { rebufferCount: 0, rebufferDuration: 0 };
                    
                    // Собираем статистику через API видеоплеера
                    const buffered = video.buffered;
                    let totalBuffered = 0;
                    for (let i = 0; i < buffered.length; i++) {
                        totalBuffered += buffered.end(i) - buffered.start(i);
                    }
                    
                    return {
                        rebufferCount: window.__rebufferCount || 0,
                        rebufferDuration: window.__rebufferDuration || 0,
                        bufferedDuration: totalBuffered,
                        readyState: video.readyState,
                        networkState: video.networkState
                    };
                }
            """)
            return metrics
        except:
            return {"rebufferCount": 0, "rebufferDuration": 0}
        

class PhonePopupHandler:
    """Обработчик попапа с телефоном"""
    
    @staticmethod
    def generate_phone_number(operator_type: str = "valid") -> str:
        """Генерация номеров телефона"""
        import random
        
        operators = {
            "valid": ["79", "79"],  # МТС, Мегафон
            "invalid": ["73", "74"],  # Несуществующие операторы
            "error": ["77", "78"]  # Другие операторы
        }
        
        prefix = random.choice(operators.get(operator_type, ["79"]))
        number = ''.join([str(random.randint(0, 9)) for _ in range(9)])
        return f"{prefix}{number}"
    
    @staticmethod
    def handle_phone_popup(page: Page, selectors: Dict, phone_type: str = "valid") -> Dict:
        """Обработка попапа с телефоном"""
        try:
            # Генерация номера
            phone_number = PhonePopupHandler.generate_phone_number(phone_type)
            
            # Ввод номера
            phone_input = page.locator(selectors.get("phone_input", "#dialog-phone"))
            phone_input.wait_for(state="visible", timeout=10000)
            phone_input.fill(phone_number)
            
            # Нажатие кнопки
            submit_btn = page.locator(selectors.get("phone_submit", "button[type='submit']"))
            submit_btn.click()
            
            # Ожидание результата и определение ветки
            time.sleep(2)  # Даем время для обработки
            
            # Определяем ветку по наличию элементов
            if page.locator(selectors.get("phone_error", ".error-message")).is_visible():
                return {"branch": "error", "phone": phone_number, "success": False}
            elif page.locator(selectors.get("sms_form", "[data-testid='sms-form']")).is_visible():
                return {"branch": "sms", "phone": phone_number, "success": True}
            else:
                return {"branch": "card", "phone": phone_number, "success": True}
                
        except Exception as e:
            return {"branch": "error", "error": str(e), "success": False}


class FlowBranch(Enum):
    """Ветки пользовательского флоу"""
    ERROR = "error"
    CARD = "card"
    SMS = "sms"


class UserFlowBuilder:
    """Строитель пользовательского флоу"""
    
    def __init__(self):
        self.steps = []
    
    def add_step(self, step: BaseTestStep):
        """Добавление шага"""
        self.steps.append(step)
        return self
    
    def build(self) -> List[BaseTestStep]:
        """Построение флоу"""
        return self.steps


# Конкретные шаги теста
class NavigateToMainPageStep(BaseTestStep):
    def execute(self, page: Page, context: Dict) -> Dict:
        base_url = context.get('base_url')
        page.goto(base_url, timeout=self.timeout)
        page.wait_for_load_state("networkidle")
        return {"success": True, "url": base_url}


class NavigateToFilmPageStep(BaseTestStep):
    def execute(self, page: Page, context: Dict) -> Dict:
        film_url = context.get('film_url')
        
        # Включаем логирование Vidu
        page.evaluate("() => { localStorage.setItem('vidu_log', '1'); }")
        
        page.goto(film_url)
        
        # Ожидание плеера с улучшенной диагностикой
        player_ready_time = self._wait_for_player_improved(page, 30)
        
        # Сбор метрик
        video_metrics = VideoMetricsCollector.collect_video_start_time(page)
        buffering_metrics = VideoMetricsCollector.collect_buffering_metrics(page)
        
        return {
            "success": True,
            "videoStartTime": round(player_ready_time * 1000) if player_ready_time else None,
            "buffering": buffering_metrics,
            "videoMetrics": video_metrics
        }
    
    def _wait_for_player_improved(self, page: Page, timeout: int) -> Optional[float]:
        """Улучшенное ожидание плеера"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Проверяем множественные признаки готовности
                status = page.evaluate("""
                    () => {
                        const checks = {
                            playerReady: window.__playerReadyDetected || false,
                            videoElements: document.querySelectorAll('video').length,
                            videoWithSrc: document.querySelectorAll('video[src]').length,
                            videoPlaying: Array.from(document.querySelectorAll('video'))
                                .filter(v => !v.paused && v.readyState >= 2).length,
                            viduLoaded: window.__consoleMessages ? 
                                window.__consoleMessages.some(m => m.message.includes('[Dc] loaded')) : false,
                            performanceEntries: performance.getEntriesByType('resource')
                                .filter(e => e.initiatorType === 'video').length
                        };
                        
                        // Комбинированный критерий готовности
                        checks.isReady = checks.playerReady || 
                                        checks.videoPlaying > 0 ||
                                        (checks.videoWithSrc > 0 && checks.viduLoaded);
                        
                        return checks;
                    }
                """)
                
                if status.get("isReady"):
                    ready_time = time.time() - start_time
                    print(f"[SUCCESS] Player ready after {ready_time:.2f}s")
                    return ready_time
                
                time.sleep(1)
                
            except Exception as e:
                print(f"[DEBUG] Player check error: {e}")
                time.sleep(1)
        
        return None


class HandlePhonePopupStep(BaseTestStep):
    def __init__(self, name: str, phone_type: str = "valid", timeout: int = 30000):
        super().__init__(name, timeout)
        self.phone_type = phone_type
    
    def execute(self, page: Page, context: Dict) -> Dict:
        selectors = context.get('selectors', {})
        
        # Ждем попап
        popup_start = time.time()
        popup = page.locator(selectors.get("popup", "[data-testid='phone-popup']"))
        popup.wait_for(state="visible", timeout=90000)
        popup_time = round((time.time() - popup_start) * 1000)
        
        # Обрабатываем попап
        result = PhonePopupHandler.handle_phone_popup(page, selectors, self.phone_type)
        result["popupAppearTime"] = popup_time
        
        # Сохраняем ветку флоу
        context['metrics'].flow_branch = result["branch"]
        
        return result


class ProcessPaymentStep(BaseTestStep):
    def __init__(self, name: str, payment_method: str, timeout: int = 30000):
        super().__init__(name, timeout)
        self.payment_method = payment_method
    
    def execute(self, page: Page, context: Dict) -> Dict:
        selectors = context.get('selectors', {})
        
        # Определяем селекторы в зависимости от метода оплаты
        if self.payment_method == "card":
            button_selector = selectors.get("pay_button_bank_card")
            form_selector = selectors.get("pay_form_bank_card")
        elif self.payment_method == "sbp":
            button_selector = selectors.get("pay_button_sbp")
            form_selector = selectors.get("pay_form_sbp")
        else:
            button_selector = selectors.get("pay_button_tpay")
            form_selector = None
        
        # Ждем iframe оплаты
        iframe_start = time.time()
        iframe = page.frame_locator(selectors.get("payment_iframe", "iframe"))
        iframe_load_time = round((time.time() - iframe_start) * 1000)
        
        # Кликаем на кнопку оплаты
        try:
            button = iframe.locator(button_selector)
            button.wait_for(state="visible", timeout=15000)
            button.click(timeout=5000)
            
            # Ждем форму оплаты
            if form_selector:
                iframe.locator(form_selector).wait_for(state="visible", timeout=10000)
            
            return {
                "success": True,
                "iframeLoadTime": iframe_load_time,
                "buttonClicked": True,
                "formVisible": True if form_selector else None
            }
        except Exception as e:
            return {
                "success": False,
                "iframeLoadTime": iframe_load_time,
                "error": str(e)
            }


class BaseUserFlowTest(ABC):
    """Улучшенный базовый класс для пользовательских флоу"""
    
    BASE_URL: str = None
    SELECTORS: Dict = None
    DOMAIN_NAME: str = "unknown"
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Метод, который вызывается перед каждым тестом в pytest"""
        self.metrics = TestMetrics()
        self.flow_builder = UserFlowBuilder()
        self._setup_default_flow()
        yield
    
    def _setup_default_flow(self):
        """Настройка стандартного флоу"""
        self.flow_builder.add_step(NavigateToMainPageStep("Переход на главную страницу"))
        self.flow_builder.add_step(NavigateToFilmPageStep("Переход на страницу фильма"))
        self.flow_builder.add_step(HandlePhonePopupStep("Обработка попапа с телефоном"))
        self.flow_builder.add_step(ProcessPaymentStep("Обработка оплаты", "card"))
    
    @abstractmethod
    def get_test_context(self, **kwargs) -> Dict:
        """Получение контекста теста"""
        pass
    
    def run_flow(self, page: Page, **kwargs) -> TestMetrics:
        """
        Основной метод запуска флоу
        """
        if not hasattr(self, 'metrics'):
            self.setup_method()
            
        # Подготовка контекста
        context = self.get_test_context(**kwargs)
        context['page'] = page
        context['metrics'] = self.metrics
        
        # Получение шагов флоу
        steps = self.flow_builder.build()
        
        # Выполнение шагов
        for step in steps:
            result = step.safe_execute(page, context)
            
            # Сохранение результатов
            if step.name not in self.metrics.step_metrics:
                self.metrics.step_metrics[step.name] = {}
            
            self.metrics.step_metrics[step.name].update(result)
            
            # Если шаг неудачен, можно решить продолжать ли выполнение
            if not result.get("success", True) and step.name != "Обработка попапа с телефоном":
                self.metrics.add_error(f"Step {step.name} failed")
        
        # Сохранение отчета
        self._save_report(context)
        
        return self.metrics
    
    def _save_report(self, context: Dict):
        """Сохранение отчета"""
        report_data = {
            "test_name": context.get("test_name", "unknown"),
            "domain": self.DOMAIN_NAME,
            "timestamp": datetime.now().isoformat(),
            "flow_branch": self.metrics.flow_branch,
            "metrics": self.metrics.step_metrics,
            "errors": self.metrics.errors,
            "warnings": self.metrics.warnings,
            "is_problematic": self.metrics.is_problematic,
            "context": {k: v for k, v in context.items() if k != 'page' and k != 'metrics'}
        }
        
        # Сохранение в файл
        Path("reports").mkdir(exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in context.get("test_name", ""))
        filename = f"report_{self.DOMAIN_NAME}_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(Path("reports") / filename, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        # Прикрепление к Allure
        allure.attach.file(
            str(Path("reports") / filename),
            name="Test Report",
            extension="json"
        )
import pytest
import allure
import time
import json
from pathlib import Path
from typing import Dict
from playwright.sync_api import Page

from tests.shared.plugins.plugin_manager import PluginManager
from config import SELECTORS, DEVICES, THROTTLING_MODES, GEO_LOCATIONS, PAY_METHODS


class PluginBasedUserFlowTest:
    """Тестовый класс с плагинной системой"""
    
    BASE_URL = "https://tests.goodmovie.net"
    DOMAIN_NAME = "tests.goodmovie"
    
    @pytest.fixture(autouse=True)
    def setup_test(self, browser_type: str):
        """Настройка теста с плагинами"""
        self.test_start_time = time.time()
        
        # Инициализируем менеджер плагинов
        self.plugin_manager = PluginManager(browser_type)
        
        # Регистрируем плагины по умолчанию
        self.plugin_manager.register_default_plugins({
            'lighthouse_path': 'lighthouse'  # Путь к Lighthouse CLI
        })
        
        print(f"[TEST SETUP] Плагины зарегистрированы: {self.plugin_manager.get_active_plugins()}")
    
    def run_plugin_based_flow(self, page: Page, get_film_url: str, device: str,
                              throttling: str, geo: str, browser_type: str,
                              pay_method: str, request) -> Dict:
        """Основной метод запуска флоу с плагинами"""
        
        # Настройка плагинов
        # self.setup_test(browser_type)
        
        report = {
            "test_name": request.node.name,
            "domain": self.DOMAIN_NAME,
            "film_url": get_film_url,
            "device": device,
            "throttling": throttling,
            "geoposition": geo,
            "browser_type": browser_type,
            "pay_method": pay_method,
            "timestamp": time.time(),
            "plugins": self.plugin_manager.get_active_plugins(),
            "steps": {},
            "metrics": {},
            "errors": [],
            "warnings": [],
            "success": False
        }
        
        try:
            # Хук: before_test
            self.plugin_manager.execute_hooks("before_test", page, report)
            
            # 1. Переход на страницу фильма
            with allure.step("Переход на страницу фильма"):
                print("[FLOW] Шаг 1: Переход на страницу фильма")
                page.goto(get_film_url, timeout=30000)
                page.wait_for_load_state("networkidle")
                report["steps"]["page_load"] = {"success": True}
            
            # Хук: after_page_load (Lighthouse здесь)
            self.plugin_manager.execute_hooks(
                "after_page_load", 
                page, 
                report,
                url=get_film_url,
                device=device,
                throttling=throttling
            )
            
            # 2. Подготовка к проверке видео
            with allure.step("Подготовка к проверке видео"):
                print("[FLOW] Шаг 2: Подготовка видео")
                self.plugin_manager.execute_hooks("before_video_check", page, report)
            
            # 3. Проверка состояния видео
            with allure.step("Проверка видео"):
                print("[FLOW] Шаг 3: Проверка видео")
                video_result = self.plugin_manager.execute_hooks("video_check", page, report)
                if video_result:
                    report["steps"]["video_check"] = video_result
            
            # Хук: before_video_playback (CDP настройка здесь)
            self.plugin_manager.execute_hooks("before_video_playback", page, report)
            
            # 4. Запуск видео
            with allure.step("Запуск видео"):
                print("[FLOW] Шаг 4: Запуск видео")
                try:
                    # Пробуем кликнуть на видео
                    video_element = page.locator("video").first
                    if video_element.count() > 0:
                        video_element.click()
                        report["steps"]["video_play"] = {"clicked": True}
                        
                        # Ждем начала воспроизведения
                        page.wait_for_timeout(2000)
                    else:
                        report["warnings"].append("Video element not found for playback")
                except Exception as e:
                    report["errors"].append(f"Video play error: {str(e)}")
            
            # Хук: during_video_playback (сбор rebuffer метрик)
            print("[FLOW] Сбор метрик во время воспроизведения")
            self.plugin_manager.execute_hooks("during_video_playback", page, report)
            
            # Даем видео воспроизвестись немного
            page.wait_for_timeout(3000)
            
            # Хук: after_video_ready
            print("[FLOW] Видео готово, сбор финальных метрик")
            self.plugin_manager.execute_hooks("after_video_ready", page, report)
            
            # Хук: after_video_playback (финализация метрик видео)
            self.plugin_manager.execute_hooks("after_video_playback", page, report)
            
            # 5. Ожидание попапа (новый флоу с телефоном)
            with allure.step("Ожидание попапа с телефоном"):
                print("[FLOW] Шаг 5: Ожидание попапа")
                # ... ваш код для попапа с телефоном ...
                pass
            
            # 6. Обработка попапа
            with allure.step("Обработка попапа"):
                print("[FLOW] Шаг 6: Обработка попапа")
                # ... ваш код для обработки телефона ...
                pass
            
            # Хук: after_popup
            self.plugin_manager.execute_hooks("after_popup", page, report)
            
            # 7. Определение ветки и обработка
            with allure.step("Определение ветки флоу"):
                print("[FLOW] Шаг 7: Определение ветки")
                branch = self._determine_flow_branch(page)
                report["flow_branch"] = branch
                
                if branch == "error":
                    # Обработка ошибки
                    pass
                elif branch == "card":
                    # Переход на форму оплаты картой
                    pass
                elif branch == "sms":
                    # Переход на форму SMS
                    pass
            
            # Хук: after_payment_page (второй Lighthouse замер)
            if branch in ["card", "sms"]:
                self.plugin_manager.execute_hooks(
                    "after_payment_page",
                    page,
                    report,
                    url=page.url,
                    branch=branch
                )
            
            # Проверяем успешность
            report["success"] = len(report["errors"]) == 0
            
            # Расчет общего времени теста
            report["total_duration"] = round((time.time() - self.test_start_time) * 1000)
            
            print(f"[FLOW] Тест завершен: {'УСПЕХ' if report['success'] else 'ОШИБКИ'}")
            
        except Exception as e:
            report["errors"].append(f"Test flow error: {str(e)}")
            report["success"] = False
            print(f"[FLOW] Критическая ошибка: {e}")
            raise
        finally:
            # Хук: after_test (закрытие CDP сессии и т.д.)
            self.plugin_manager.execute_hooks("after_test", page, report)
            
            # Сохранение отчета
            self._save_report(report)
        
        return report
    
    def _determine_flow_branch(self, page: Page) -> str:
        """Определение ветки флоу на основе элементов на странице"""
        try:
            # Проверяем наличие элементов для разных веток
            error_elements = page.locator(".error-message, [data-error]")
            sms_elements = page.locator("input[type='text'][name='code'], [data-form='sms']")
            card_elements = page.locator("iframe[src*='pay'], [data-payment='card']")
            
            if error_elements.count() > 0:
                return "error"
            elif sms_elements.count() > 0:
                return "sms"
            elif card_elements.count() > 0:
                return "card"
            else:
                return "unknown"
        except:
            return "unknown"
    
    def _save_report(self, report: Dict):
        """Сохранение отчета"""
        Path("reports").mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        safe_url = report['film_url'].split("/")[-2] if "/" in report['film_url'] else "unknown"
        
        filename = f"plugin_report_{self.DOMAIN_NAME}_{report['device']}_{report['browser_type']}_{safe_url}_{timestamp}.json"
        filepath = Path("reports") / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Прикрепляем к Allure
        allure.attach.file(
            str(filepath),
            name="Plugin Based Test Report",
            extension="json"
        )
        
        print(f"[REPORT] Отчет сохранен: {filepath}")


class TestGoodmoviePluginBased(PluginBasedUserFlowTest):
    """Тесты на основе плагинной системы"""
    
    @pytest.mark.single_run
    @allure.story("Plugin-based User Flow")
    @allure.title("Полный user flow с плагинами (браузер: {browser_type})")
    def test_plugin_based_flow_single(self, page, get_film_url, device, throttling,
                               geo, browser_type, pay_method, request):
        """Основной тест с плагинной системой"""
        
        print(f"\n{'='*60}")
        print(f"Запуск теста с плагинами")
        print(f"Браузер: {browser_type}")
        print(f"Устройство: {device}")
        print(f"Сеть: {throttling}")
        print(f"ГЕО: {geo}")
        print(f"Оплата: {pay_method}")
        print(f"URL: {get_film_url}")
        print(f"{'='*60}\n")
        
        # Запускаем флоу с плагинами
        report = self.run_plugin_based_flow(
            page=page,
            get_film_url=get_film_url,
            device=device,
            throttling=throttling,
            geo=geo,
            browser_type=browser_type,
            pay_method=pay_method,
            request=request
        )
        
        # Формируем описание для Allure
        description = f"""
        **Тест с плагинной системой**

        **Домен**: {self.DOMAIN_NAME}
        **Устройство**: {device}
        **Сеть**: {throttling}
        **ГЕО**: {geo}
        **Браузер**: {browser_type}
        **Способ оплаты**: {pay_method}
        **Ветка флоу**: {report.get('flow_branch', 'unknown')}
        **Плагины**: {', '.join(report.get('plugins', []))}
        **Успех**: {'✅ Да' if report['success'] else '❌ Нет'}
        **Ошибки**: {len(report['errors'])}
        **Предупреждения**: {len(report['warnings'])}
        **Длительность**: {report.get('total_duration', 0)}мс

        **Собранные метрики**:
        - Lighthouse: {'✅' if 'lighthouse' in report.get('plugins', []) else '❌'}
        - CDP (rebuffer): {'✅' if 'cdp' in report.get('plugins', []) else '❌'}
        - Видео метрики: {'✅' if 'video_metrics' in report.get('plugins', []) else '❌'}
        """
        
        allure.dynamic.description(description)
        
        # Проверяем результаты
        assert report["success"], f"Test failed with errors: {report['errors'][:3]}"
        
        # Проверяем, что для Chromium собраны дополнительные метрики
        if browser_type == "chromium":
            assert "lighthouse" in report.get("plugins", []), "Lighthouse plugin should be active for Chromium"
            assert "cdp" in report.get("plugins", []), "CDP plugin should be active for Chromium"
            
            # Проверяем наличие метрик
            if "lighthouse" in report.get("metrics", {}):
                lh_metrics = report["metrics"]["lighthouse"]
                assert lh_metrics.get("after_page_load", {}).get("performance_score", 0) > 0, \
                    "Lighthouse should return performance score"
            
            if "video_metrics" in report.get("metrics", {}):
                video_metrics = report["metrics"]["video_metrics"]
                assert "cdp" in video_metrics, "CDP video metrics should be present"
        
        print(f"\n{'='*60}")
        print(f"Тест завершен: {'УСПЕХ' if report['success'] else 'ОШИБКИ'}")
        print(f"{'='*60}\n")
    
    @pytest.mark.parametrize("browser_type", ["chromium"], scope="session")
    @pytest.mark.parametrize("device", DEVICES)
    @pytest.mark.parametrize("throttling", THROTTLING_MODES)
    @pytest.mark.parametrize("geo", GEO_LOCATIONS)
    @pytest.mark.parametrize("pay_method", PAY_METHODS)
    @allure.story("Plugin-based User Flow")
    @allure.title("Полный user flow с плагинами (браузер: {browser_type})")
    def test_plugin_based_flow_chromium(self, page, get_film_url, device, throttling,
                               geo, browser_type, pay_method, request):
        """Основной тест с плагинной системой"""
        
        print(f"\n{'='*60}")
        print(f"Запуск теста с плагинами")
        print(f"Браузер: {browser_type}")
        print(f"Устройство: {device}")
        print(f"Сеть: {throttling}")
        print(f"ГЕО: {geo}")
        print(f"Оплата: {pay_method}")
        print(f"URL: {get_film_url}")
        print(f"{'='*60}\n")
        
        # Запускаем флоу с плагинами
        report = self.run_plugin_based_flow(
            page=page,
            get_film_url=get_film_url,
            device=device,
            throttling=throttling,
            geo=geo,
            browser_type=browser_type,
            pay_method=pay_method,
            request=request
        )
        
        # Формируем описание для Allure
        description = f"""
        **Тест с плагинной системой**

        **Домен**: {self.DOMAIN_NAME}
        **Устройство**: {device}
        **Сеть**: {throttling}
        **ГЕО**: {geo}
        **Браузер**: {browser_type}
        **Способ оплаты**: {pay_method}
        **Ветка флоу**: {report.get('flow_branch', 'unknown')}
        **Плагины**: {', '.join(report.get('plugins', []))}
        **Успех**: {'✅ Да' if report['success'] else '❌ Нет'}
        **Ошибки**: {len(report['errors'])}
        **Предупреждения**: {len(report['warnings'])}
        **Длительность**: {report.get('total_duration', 0)}мс

        **Собранные метрики**:
        - Lighthouse: {'✅' if 'lighthouse' in report.get('plugins', []) else '❌'}
        - CDP (rebuffer): {'✅' if 'cdp' in report.get('plugins', []) else '❌'}
        - Видео метрики: {'✅' if 'video_metrics' in report.get('plugins', []) else '❌'}
        """
        
        allure.dynamic.description(description)
        
        # Проверяем результаты
        assert report["success"], f"Test failed with errors: {report['errors'][:3]}"
        
        # Проверяем, что для Chromium собраны дополнительные метрики
        if browser_type == "chromium":
            assert "lighthouse" in report.get("plugins", []), "Lighthouse plugin should be active for Chromium"
            assert "cdp" in report.get("plugins", []), "CDP plugin should be active for Chromium"
            
            # Проверяем наличие метрик
            if "lighthouse" in report.get("metrics", {}):
                lh_metrics = report["metrics"]["lighthouse"]
                assert lh_metrics.get("after_page_load", {}).get("performance_score", 0) > 0, \
                    "Lighthouse should return performance score"
            
            if "video_metrics" in report.get("metrics", {}):
                video_metrics = report["metrics"]["video_metrics"]
                assert "cdp" in video_metrics, "CDP video metrics should be present"
        
        print(f"\n{'='*60}")
        print(f"Тест завершен: {'УСПЕХ' if report['success'] else 'ОШИБКИ'}")
        print(f"{'='*60}\n")
        
    @pytest.mark.parametrize("browser_type", ["firefox", "webkit"], scope="session")
    @pytest.mark.parametrize("device", ["Desktop"])
    @pytest.mark.parametrize("throttling", ["No_throttling"])
    @pytest.mark.parametrize("geo", GEO_LOCATIONS)
    @pytest.mark.parametrize("pay_method", PAY_METHODS)
    @allure.story("Plugin-based User Flow")
    @allure.title("Полный user flow с плагинами (браузер: {browser_type})")
    def test_plugin_based_flow_non_chromium(self, page, get_film_url, device, throttling,
                               geo, browser_type, pay_method, request):
        """Основной тест с плагинной системой"""
        
        print(f"\n{'='*60}")
        print(f"Запуск теста с плагинами")
        print(f"Браузер: {browser_type}")
        print(f"Устройство: {device}")
        print(f"Сеть: {throttling}")
        print(f"ГЕО: {geo}")
        print(f"Оплата: {pay_method}")
        print(f"URL: {get_film_url}")
        print(f"{'='*60}\n")
        
        # Запускаем флоу с плагинами
        report = self.run_plugin_based_flow(
            page=page,
            get_film_url=get_film_url,
            device=device,
            throttling=throttling,
            geo=geo,
            browser_type=browser_type,
            pay_method=pay_method,
            request=request
        )
        
        # Формируем описание для Allure
        description = f"""
        **Тест с плагинной системой**

        **Домен**: {self.DOMAIN_NAME}
        **Устройство**: {device}
        **Сеть**: {throttling}
        **ГЕО**: {geo}
        **Браузер**: {browser_type}
        **Способ оплаты**: {pay_method}
        **Ветка флоу**: {report.get('flow_branch', 'unknown')}
        **Плагины**: {', '.join(report.get('plugins', []))}
        **Успех**: {'✅ Да' if report['success'] else '❌ Нет'}
        **Ошибки**: {len(report['errors'])}
        **Предупреждения**: {len(report['warnings'])}
        **Длительность**: {report.get('total_duration', 0)}мс

        **Собранные метрики**:
        - Lighthouse: {'✅' if 'lighthouse' in report.get('plugins', []) else '❌'}
        - CDP (rebuffer): {'✅' if 'cdp' in report.get('plugins', []) else '❌'}
        - Видео метрики: {'✅' if 'video_metrics' in report.get('plugins', []) else '❌'}
        """
        
        allure.dynamic.description(description)
        
        # Проверяем результаты
        assert report["success"], f"Test failed with errors: {report['errors'][:3]}"
        
        # Проверяем, что для Chromium собраны дополнительные метрики
        if browser_type == "chromium":
            assert "lighthouse" in report.get("plugins", []), "Lighthouse plugin should be active for Chromium"
            assert "cdp" in report.get("plugins", []), "CDP plugin should be active for Chromium"
            
            # Проверяем наличие метрик
            if "lighthouse" in report.get("metrics", {}):
                lh_metrics = report["metrics"]["lighthouse"]
                assert lh_metrics.get("after_page_load", {}).get("performance_score", 0) > 0, \
                    "Lighthouse should return performance score"
            
            if "video_metrics" in report.get("metrics", {}):
                video_metrics = report["metrics"]["video_metrics"]
                assert "cdp" in video_metrics, "CDP video metrics should be present"
        
        print(f"\n{'='*60}")
        print(f"Тест завершен: {'УСПЕХ' if report['success'] else 'ОШИБКИ'}")
        print(f"{'='*60}\n")
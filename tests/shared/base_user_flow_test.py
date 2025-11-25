import json
import time
from pathlib import Path
import pytest
import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import config
from utils import metrics
from utils.report_explainer import sanitize_filename
from utils.report_aggregator import log_issues_if_any
from utils.lighthouse_runner import run_lighthouse_for_url, extract_metrics_from_lighthouse

class BaseUserFlowTest:
    BASE_URL = None
    SELECTORS = None
    DOMAIN_NAME = "unknown"

    def _goto_main_page(self, page, request, report):
        with allure.step(f"Переходим на главную страницу {self.BASE_URL}"):
            try:
                page.goto(self.BASE_URL, timeout=30000)
                page.wait_for_load_state("networkidle")
            except PlaywrightTimeoutError as e:
                raise
                # pytest.fail(f"Не удалось загрузить {self.BASE_URL}", pytrace=False)

    def _goto_film_page_and_init_player(self, page, film_url, request, report):
        with allure.step(f"Переходим на страницу фильма и инициализируем плеер для {film_url}"):
            try:
                page.goto(film_url)
                player_ready_time = round(self._wait_for_player_simple(page, timeout=30) * 1000)
                print(f"[DEBUG] After wait_for_player_simple: {player_ready_time} (type: {type(player_ready_time)})")
                player_start = time.time()
                page.wait_for_selector("video", timeout=15000)
                player_init_ms = round((time.time() - player_start) * 1000)
                
                page.wait_for_load_state("networkidle")
                result = {
                    "playerInitTime": player_init_ms,
                    "videoStartTime": player_ready_time
                }
                print(f"[DEBUG] _goto_film_page_and_init_player returning: {result}")
                return result
            except PlaywrightTimeoutError:
                raise
                
    def _start_video_and_collect_metrics(self, page, request, report):
        with allure.step("Нажать Play и замерить videoStartTime"):
            try:
                page.wait_for_selector(".plyr", timeout=10000)
                page.click(self.SELECTORS["play_button"])
            except Exception as e:
                raise
                # pytest.fail(f"Ошибка при запуске видео: {e}", pytrace=False)
                
    def _collect_buffering_metrics(self, page):
        with allure.step("Собрать метрики буферизации"):
            rebuffer_count = page.evaluate("window.__rebufferCount || 0")
            rebuffer_duration = page.evaluate("window.__rebufferDuration || 0")
            return {
                "rebufferCount": rebuffer_count,
                "rebufferDuration": round(rebuffer_duration)
            }
        
    def _wait_for_popup_and_click(self, page, request, report):
        with allure.step("Дождаться появления попапа оплаты и кликнуть"):
            try:
                popup_start = time.time()
                popup_locator = page.locator(self.SELECTORS["popup"])
                popup_locator.wait_for(state="visible", timeout=90000)
                popup_time_ms = round((time.time() - popup_start) * 1000)

                if popup_locator.is_visible() and popup_locator.is_enabled():
                    
                    popup_locator.click(timeout=5000)
                    return {
                        "popupAppearTime": popup_time_ms,
                        "popupAvailable": True,
                        "popupClickSuccess": True
                    }
                else:
                    return {
                        "popupAppearTime": popup_time_ms,
                        "popupAvailable": False,
                        "popupClickSuccess": False
                    }
            except PlaywrightTimeoutError:
                raise
                # pytest.fail("Попап оплаты не появился за 90 секунд", pytrace=False)
                
    def _collect_payment_metrics(self, page, iframe_start_time, request, report):
        with allure.step("На странице оплаты собрать метрики"):
            try:
                page.wait_for_selector(self.SELECTORS["payment_iframe"], timeout=15000)
                iframe_load_time_ms = round((time.time() - iframe_start_time) * 1000)
                return {
                    "iframeCpLoadTime": iframe_load_time_ms
                }
            except Exception as e:
                raise
                # pytest.fail(f"Ошибка на странице оплаты: {e}", pytrace=False)
                
    def _check_payment_button_click(self, page, iframe, request, report):
        with allure.step("Проверить кликабельность кнопок на странице оплаты"):
            try:
                bank_card_button = iframe.locator(self.SELECTORS["pay_button_bank_card"])
                bank_card_button.wait_for(state="visible", timeout=30000)
                if bank_card_button.is_visible() and bank_card_button.is_enabled():
                    page.wait_for_load_state("networkidle")
                    bank_card_button.locator("tui-loader:not([aria-busy='true'])").first.wait_for(
                        state="attached", timeout=10000
                    )
                    bank_card_button.click(timeout=5000)
                    return {"buttonsCpAvailable": True, "buttonsClickSuccess": True}
                else:
                    return {"buttonsCpAvailable": False, "buttonsClickSuccess": False}
            except PlaywrightTimeoutError:
                raise
                # pytest.fail("Клик по кнопке оплаты не удался", pytrace=False)
                
    def _wait_for_payment_form(self, page, iframe, request, report):
        with allure.step("Проверить появление формы оплаты"):
            try:
                page.wait_for_load_state("networkidle")
                iframe.locator(self.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")
            except Exception as e:
                raise
                # pytest.fail(f"Форма оплаты не появилась: {e}", pytrace=False)

                
                
    def _collect_lighthouse_metrics(self, url, request, report):
        try:
            lh_report = run_lighthouse_for_url(url)
        except Exception as e:
            raise
            # if "timed out" in str(e) or "Timeout" in str(e):
            #     pytest.fail(f"Lighthouse не ответил для {url}", pytrace=False)
            # else:
            #     raise
        lh_metrics = extract_metrics_from_lighthouse(lh_report)
            
        ppi = config.calculate_page_performance_index(
            lcp=lh_metrics.get("lcp"),
            cls=lh_metrics.get("cls"),
            tbt=lh_metrics.get("tbt"),
            ttfb=lh_metrics.get("ttfb"),
            fid=lh_metrics.get("inp")  # используем INP как замену FID
        )
            
        return {
            **lh_metrics,
            "pagePerformanceIndex": ppi,
            "is_problematic_page": ppi < config.TARGET_PAGE_PERFORMANCE_INDEX
        }
    
    def _wait_for_player_simple(self, page, timeout=30):
        """Простое ожидание готовности плеера через JS мониторинг"""
        print(f"[INFO] Waiting for player ready (timeout: {timeout}s)")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Проверяем статус через JS
                result = page.evaluate("""
                    () => {
                        return {
                            playerReady: window.__playerReadyDetected || false,
                            playerReadyTime: window.__playerReadyTimestamp || null,
                            messageCount: window.__consoleMessages ? window.__consoleMessages.length : 0,
                            recentMessages: window.__consoleMessages ? 
                                window.__consoleMessages.slice(-5).map(m => m.type + ': ' + m.message) : []
                        };
                    }
                """)
                
                if result["playerReady"]:
                    ready_time = time.time()
                    print(f"[SUCCESS] Player ready detected at {ready_time}")
                    return ready_time - start_time
                
                # Диагностика каждые 5 секунд
                if int(time.time() - start_time) % 5 == 0:
                    print(f"[DEBUG] Waiting... {int(time.time() - start_time)}s elapsed")
                    print(f"[DEBUG] Messages: {result['messageCount']}")
                    if result['recentMessages']:
                        print("[DEBUG] Recent messages:")
                        for msg in result['recentMessages']:
                            print(f"  - {msg}")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"[ERROR] Check failed: {e}")
                time.sleep(1)
        
        # Таймаут
        print(f"[ERROR] Timeout after {timeout} seconds")
        
        # Финальная диагностика
        try:
            final = page.evaluate("""
                () => {
                    return {
                        playerReady: window.__playerReadyDetected || false,
                        allMessages: window.__consoleMessages ? 
                            window.__consoleMessages.map(m => m.type + ': ' + m.message) : []
                    };
                }
            """)
            print(f"[DEBUG] Final state: playerReady={final['playerReady']}, messages={len(final['allMessages'])}")
            for msg in final['allMessages'][-10:]:
                print(f"  - {msg}")
        except Exception as e:
            print(f"[DEBUG] Final check failed: {e}")
        
        raise TimeoutError(f"Player not ready within {timeout}s")
                
    # Основной метод — шаблонный метод (template method)
    def run_user_flow(self, page, get_film_url, device, throttling, geo, browser_type, request, extra_steps=None):
        """
        Общий сценарий. extra_steps — словарь с кастомными шагами: 
        {"main_page": func, "film_page_before_video": func}
        """
        report = {
            "test_name": request.node.name,
            "domain": self.DOMAIN_NAME,
            "film_url": get_film_url,
            "device": device,
            "throttling": throttling,
            "geoposition": geo,
            "browser_type": browser_type,
            "steps": {},
            "is_problematic_flow": False,
            "error": None
        }

        allure.dynamic.description(
            f"**Домен**: {self.DOMAIN_NAME}\n"
            f"**Устройство**: {device}\n"
            f"**Сеть**: {throttling}\n"
            f"**ГЕО**: {geo}\n"
            f"**Браузер**: {browser_type}"
        )
        
        request.node._report_data = report
        
        try:
            
            if self.DOMAIN_NAME == "calls7":
                # --- Шаг 1: Главная страница
                if extra_steps and "main_page" in extra_steps:
                    extra_steps["main_page"](page, request, report)
                else:
                    self._goto_main_page(page, request, report)

            # --- Шаг 2: Страница фильма
            film_metrics = self._goto_film_page_and_init_player(page, get_film_url, request, report)
            report["steps"]["film_page"] = film_metrics

            if extra_steps and "film_page_before_video" in extra_steps:
                extra_steps["film_page_before_video"](page, request, report)

            # --- Шаг 3: Видео
            self._start_video_and_collect_metrics(page, request, report)
            

            # --- Шаг 4: Буферизация
            buffer_metrics = self._collect_buffering_metrics(page)
            report["steps"]["film_page"].update(buffer_metrics)

            # --- Шаг 5: Попап
            popup_metrics = self._wait_for_popup_and_click(page, request, report)
            report["steps"]["film_page"].update(popup_metrics)
            iframe_start = time.time()

            # --- Шаг 6: Оплата
            iframe = page.frame_locator(self.SELECTORS["payment_iframe"])
            payment_meta = self._collect_payment_metrics(page, iframe_start, request, report)
            report["steps"]["pay_page"] = payment_meta

            if extra_steps and "pay_page_before_click" in extra_steps:
                extra_steps["pay_page_before_click"](page, request, report)

            button_metrics = self._check_payment_button_click(page, iframe, request, report)
            report["steps"]["pay_page"].update(button_metrics)

            self._wait_for_payment_form(page, iframe, request, report)

            # --- Завершение
            if log_issues_if_any(report):
                report["is_problematic_flow"] = True
            request.node._report_data = report
            if report.get("is_problematic_flow"):
                pytest.fail("Проблемный запуск", pytrace=False)
        except Exception as e:
            report["error"] = str(e)
            report["is_problematic_flow"] = True
            raise
        finally:
            # Сохранение отчёта
            self._save_report(report, get_film_url, device, throttling, geo, browser_type, request)
        return report
    
    def _save_report(self, report, film_url, device, throttling, geo, browser_type, request):
        Path("reports").mkdir(exist_ok=True)
        safe_url = sanitize_filename(film_url)
        test_name = report["test_name"].split("[")[0]
        report_path = f"reports/report_{self.DOMAIN_NAME}_{test_name}_{safe_url}_{device}_{throttling}_{geo}_{browser_type}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        allure.attach.file(report_path, name="JSON-отчёт", extension="json")
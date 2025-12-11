import json
import time
import random
from pathlib import Path
import pytest
import allure
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import config
from utils import metrics
from utils.scenario_detector import detect_video_scenario
from utils.report_explainer import sanitize_filename
from utils.log_issues import log_issues_if_any
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

    def _goto_film_page_and_init_player(self, page, film_url):
        with allure.step(f"Переходим на страницу фильма и инициализируем плеер для {film_url}"):
            try:
                page.evaluate("() => { localStorage.setItem('vidu_log', '1'); }")
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
                
    def _start_video_and_collect_metrics(self, page, scenario: str) -> int:
        with allure.step("Нажать Play и замерить firstFrameTime"):
            try:
                metrics.inject_plyr_playing_listener(page)
                page.wait_for_selector(".plyr", timeout=10000)
                page.click(self.SELECTORS["video_element"])
            except Exception as e:
                raise
                
    def _collect_buffering_metrics(self, page):
        with allure.step("Собрать метрики буферизации"):
            rebuffer_count = page.evaluate("window.__rebufferCount || 0")
            rebuffer_duration = page.evaluate("window.__rebufferDuration || 0")
            return {
                "rebufferCount": rebuffer_count,
                "rebufferDuration": round(rebuffer_duration)
            }
        
    def _wait_for_phone_popup_and_fill(self, page, phone_branch: str):
        try:
            popup_start = time.time()
            phone_popup = page.locator(self.SELECTORS["phone_popup_form"])
            phone_popup.wait_for(state="visible", timeout=90000)
            popup_time_ms = round((time.time() - popup_start) * 1000)
            popup_input = page.locator(self.SELECTORS["phone_input"])
            if popup_input:
                try:
                    # В зависимости от ветки заполняем номер телефона
                    if phone_branch != "paid":
                        phone_number = self._generate_phone_number(phone_branch)
                    else:
                        phone_number = config.TEST_PHONE_NUMBER
                    popup_input.fill(phone_number)
                    phone_submit_button = page.locator(self.SELECTORS["phone_submit"])
                    phone_submit_button.wait_for(state="attached", timeout=10000)
                    phone_submit_button.click(force=True)
                    return {
                            "popupAppearTime": popup_time_ms,
                            "popupAvailable": True,
                            "popupClickSuccess": True
                        }
                except:
                    return {
                            "popupAppearTime": popup_time_ms,
                            "popupAvailable": True,
                            "popupClickSuccess": False
                        }
            else:
                return {
                            "popupAppearTime": None,
                            "popupAvailable": False,
                            "popupClickSuccess": False
                        }
        except PlaywrightTimeoutError:
            raise
        
    def _generate_phone_number(self, phone_branch: str = "valid") -> str:
        """Генерация номеров телефона"""
        
        operators = {
            "valid": ["79", "79"],  # МТС, Мегафон
            "invalid": ["73", "74"]  # Несуществующие операторы
        }
        
        prefix = random.choice(operators.get(phone_branch, ["79"]))
        number = ''.join([str(random.randint(0, 9)) for _ in range(9)])
        return f"{prefix}{number}"
        
    def _wait_for_popup_and_click(self, page, request, report):
        with allure.step("Дождаться появления попапа оплаты и кликнуть"):
            try:
                popup_start = time.time()
                popup = page.locator(self.SELECTORS["popup"])
                popup.wait_for(state="visible", timeout=90000)
                popup_time_ms = round((time.time() - popup_start) * 1000)
                popup_locator = page.locator(self.SELECTORS["popup_cta"])
                
                if popup_locator:
                    try:
                        popup_locator.click(timeout=5000)
                        return {
                            "popupAppearTime": popup_time_ms,
                            "popupAvailable": True,
                            "popupClickSuccess": True
                        }
                    except:
                        return {
                            "popupAppearTime": popup_time_ms,
                            "popupAvailable": True,
                            "popupClickSuccess": False
                        }
                else:
                    return {
                        "popupAppearTime": popup_time_ms,
                        "popupAvailable": False,
                        "popupClickSuccess": False
                    }
            except PlaywrightTimeoutError:
                raise
                
    def _collect_payment_metrics(self, page, iframe_start_time, request, report):
        with allure.step("На странице оплаты собрать метрики"):
            try:
                iframe = page.frame_locator(self.SELECTORS["payment_iframe"])
                iframe_load_time_ms = round((time.time() - iframe_start_time) * 1000)
                return {
                    "iframeCpLoadTime": iframe_load_time_ms
                }
            except Exception as e:
                raise

                
    def _check_payment_button_click(self, page, iframe, pay_method):
        with allure.step("Проверить кликабельность кнопок на странице оплаты"):
            try:
                page.wait_for_load_state("networkidle")
                match pay_method:
                    case "card":
                        bank_card_button = iframe.locator(self.SELECTORS["pay_button_bank_card"])
                    case "sbp":
                        bank_card_button = iframe.locator(self.SELECTORS["pay_button_sbp"])
                    case "tpay":
                        bank_card_button = iframe.locator(self.SELECTORS["pay_button_tpay"])
                # bank_card_button.wait_for(state="visible", timeout=30000)
                if bank_card_button.is_visible() and bank_card_button.is_enabled():
                    bank_card_button.locator("tui-loader:not([aria-busy='true'])").first.wait_for(
                        state="attached", timeout=10000
                    )
                    bank_card_button.click(timeout=5000)
                    return {"buttonsCpAvailable": True, "buttonsClickSuccess": True}
                else:
                    return {"buttonsCpAvailable": False, "buttonsClickSuccess": False}
            except PlaywrightTimeoutError:
                raise
                
    def _wait_for_payment_form(self, page, iframe, pay_method):
        with allure.step("Проверить появление формы оплаты"):
            try:
                page.wait_for_load_state("networkidle")
                match pay_method:
                    case "card":
                        iframe.locator(self.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")
                        return {"payFormAppear": True}
                    case "sbp":
                        iframe.locator(self.SELECTORS["pay_form_sbp"]).wait_for(state="visible")
                        return {"payFormAppear": True}
            except Exception as e:
                return {"payFormAppear": False}

    def _load_popup_after_closing_pay_form(self, page, iframe):
        with allure.step("Закрыть форму оплаты и замерить время появления формы vidu"):
            try:
                start_time = time.time()
                iframe.locator(self.SELECTORS["close_button"]).click(timeout=10000)
                page.locator(self.SELECTORS["vidu_popup"]).wait_for(state="visible", timeout=30000)
                popup_load_time_ms = round((time.time() - start_time) * 1000)
                return {
                    "popupReloadTime": popup_load_time_ms,
                    "popupIsVisibleAfterReload": True
                }
            except Exception as e:
                return {
                    "popupReloadTime": None,
                    "popupIsVisibleAfterReload": False,
                    "error": str(e)
                }
            
    def _retry_payment_from_vidu_popup(self, page, iframe) -> dict:
        """
        Нажимает «Оплатить доступ сейчас» и ждёт новую форму оплаты.
        Возвращает: {"loadTime": int, "success": bool}
        """
        with allure.step("Повторная загрузка формы оплаты из попапа Vidu"):
            try:
                # Кликаем по кнопке в попапе
                retry_btn = page.locator(self.SELECTORS["pay_button_in_iframe"])
                retry_btn.wait_for(state="visible", timeout=5000)
                iframe_start = time.time()
                retry_btn.click(timeout=30000)

                # Ждём iframe
                page.wait_for_selector(self.SELECTORS["payment_iframe"], timeout=15000)

                return {
                    "loadTime": round((time.time() - iframe_start) * 1000),
                    "success": True
                }
            except Exception as e:
                return {
                    "loadTime": None,
                    "success": False,
                    "error": str(e)
                }
                
    def _collect_lighthouse_metrics(self, url, request, report):
        try:
            lh_report = run_lighthouse_for_url(url)
        except Exception as e:
            raise
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
    
    def _enable_vidu_logging(self, page):
        """
        Включает расширенное логирование Vidu через localStorage.
        """
        try:
            # Устанавливаем флаг логирования в localStorage
            page.evaluate("() => { localStorage.setItem('vidu_log', '1'); }")
            
            # Также можно установить другие флаги для максимальной детализации
            page.evaluate("""
                () => {
                    // Основной флаг логирования Vidu
                    localStorage.setItem('vidu_log', '1');
                    
                    // Дополнительные флаги (если известны)
                    localStorage.setItem('vidu_debug', '1');
                    localStorage.setItem('player_debug', '1');
                    localStorage.setItem('debug', 'true');
                    
                    // Флаги для различных компонентов
                    localStorage.setItem('debug_player', '1');
                    localStorage.setItem('debug_ads', '1');
                    localStorage.setItem('debug_analytics', '1');
                    
                    console.log('[Vidu Logging] Расширенное логирование включено');
                }
            """)
            
            print("[INFO] Расширенное логирование Vidu включено")
            return True
            
        except Exception as e:
            print(f"[WARNING] Не удалось включить логирование Vidu: {e}")
            return False
                
    # Основной метод — шаблонный метод (template method)
    def run_user_flow(self, page, get_film_url, device, throttling, geo, browser_type, pay_method, request,  phone_branch, extra_steps=None):
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
            "phone_branch": phone_branch,
            "steps": {},
            "is_problematic_flow": False,
            "error": None
        }

        allure.dynamic.description(
            f"**Домен**: {self.DOMAIN_NAME}\n"
            f"**Устройство**: {device}\n"
            f"**Сеть**: {throttling}\n"
            f"**ГЕО**: {geo}\n"
            f"**Браузер**: {browser_type}\n"
            f"**Способ оплаты**: {pay_method}\n"
            f"**Вариант телефона**: {phone_branch}\n"
        )
        
        request.node._report_data = report
        
        try:
            
            if self.DOMAIN_NAME == "calls7" or self.DOMAIN_NAME == "tests.goodmovie":
                # 1. Главная страница
                if extra_steps and "main_page" in extra_steps:
                    extra_steps["main_page"](page, request, report)
                else:
                    self._goto_main_page(page, request, report)

            # 2. Страница фильма
            if browser_type == "chromium":
                try:
                    film_metrics = self._goto_film_page_and_init_player(page, get_film_url)
                    report["steps"]["film_page"] = film_metrics
                except Exception as e:
                    print(f"Не удалось собрать метрики видеоплеера: {e}")
                    report["steps"]["film_page"] = {
                        "playerInitTime": None,
                        "videoStartTime": None  
                    }
            else:
                page.goto(get_film_url)
                

            if extra_steps and "film_page_before_video" in extra_steps:
                extra_steps["film_page_before_video"](page, request, report)
                
            # 3. Определяем сценарий
            scenario = detect_video_scenario(page)
            report["video_scenario"] = scenario

            # 4. Буферизация
            buffer_metrics = self._collect_buffering_metrics(page)
            if "film_page" in report["steps"]:
                report["steps"]["film_page"].update(buffer_metrics)
            else:
                report["steps"]["film_page"] = buffer_metrics
            
            self._start_video_and_collect_metrics(page, scenario)
            # Подключаем обработчик дилогового окна до клика
            message = page.on("dialog", lambda dialog: dialog.message)
            # 5. Попап
            popup_metrics = self._wait_for_phone_popup_and_fill(page, phone_branch)
            sms_code_time_start = time.time()
            report["steps"]["film_page"].update(popup_metrics)
            
            

            # 6. Оплата или смс
            if phone_branch == "paid":
                sms_code_form = page.locator(config.SELECTORS[""])
                sms_code_form_metric = {
                    "smsFormTime": round((time.time() - sms_code_time_start) * 100)
                }
                report["steps"]["film_page"].update(sms_code_form_metric)
                assert sms_code_form, "Не появилась форма ввода смс кода"
            elif phone_branch == "invalid":
                assert message is not None, "Не появилось диалоговое окно"
            else:
                iframe_start = time.time()
                iframe = page.frame_locator(self.SELECTORS["payment_iframe"])
                payment_meta = self._collect_payment_metrics(page, iframe_start, request, report)
                report["steps"]["pay_page"] = payment_meta

                if extra_steps and "pay_page_before_click" in extra_steps:
                    extra_steps["pay_page_before_click"](page, request, report)

                button_metrics = self._check_payment_button_click(page, iframe, pay_method)
                report["steps"]["pay_page"].update(button_metrics)

                payment_form_appear = self._wait_for_payment_form(page, iframe, pay_method)
                report["steps"]["pay_page"].update(payment_form_appear)
                
                # 7. Повторная загрузка попапа
                vidu_popup = self._load_popup_after_closing_pay_form(page, iframe)
                retry_payment = self._retry_payment_from_vidu_popup(page, iframe)
                report["steps"]["after_payment_popup"] = {
                    "viduPopupAppearTime": vidu_popup.get("popupReloadTime"),
                    "viduPopupSuccess": vidu_popup.get("popupIsVisibleAfterReload"),
                    "retryPaymentLoadTime": retry_payment.get("loadTime"),
                    "retryPaymentSuccess": retry_payment.get("success"),
                }
                report["error"] = vidu_popup.get("error")
                
                # 8. Повторная загрузка видео
                if browser_type == "chromium":
                    try:
                        film_metrics_after_return = self._goto_film_page_and_init_player(page, get_film_url)
                        report["steps"]["after_return_without_payment"] = {
                            "playerInitTime": film_metrics_after_return.get("playerInitTime"),
                            "videoStartTime": film_metrics_after_return.get("videoStartTime"),
                        }
                    except Exception as e:
                        print(f"Не удалось собрать метрики видеоплеера: {e}")
                        report["steps"]["film_page"] = {
                            "playerInitTime": None,
                            "videoStartTime": None  
                        }
            
            
            # Завершение
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
            self._save_report(report, get_film_url, device, throttling, geo, browser_type, pay_method)
        return report
    
    def _save_report(self, report, film_url, device, throttling, geo, browser_type, pay_method):
        Path("reports").mkdir(exist_ok=True)
        safe_url = sanitize_filename(film_url)
        test_name = report["test_name"].split("[")[0]
        report_path = f"reports/report_{self.DOMAIN_NAME}_{test_name}_{safe_url}_{device}_{throttling}_{geo}_{browser_type}_{pay_method}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        allure.attach.file(report_path, name="JSON-отчёт", extension="json")
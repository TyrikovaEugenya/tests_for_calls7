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

    def _goto_main_page(self, page):
        with allure.step(f"Переходим на главную страницу {self.BASE_URL}"):
            try:
                page.goto(self.BASE_URL, timeout=30000)
                page.wait_for_load_state("networkidle")
            except PlaywrightTimeoutError as e:
                pytest.fail(f"Не удалось загрузить {self.BASE_URL}", pytrace=False)

    def _goto_film_page_and_init_player(self, page, film_url):
        with allure.step(f"Переходим на страницу фильма и инициализируем плеер для {film_url}"):
            try:
                page.goto(film_url)
                player_start = time.time()
                page.wait_for_selector("video", timeout=15000)
                player_init_ms = round((time.time() - player_start) * 1000)
                page.wait_for_load_state("networkidle")
                return {"playerInitTime": player_init_ms}
            except PlaywrightTimeoutError:
                pytest.fail(f"Видео не появилось на {film_url} за 15 сек", pytrace=False)
                
    def _start_video_and_collect_metrics(self, page):
        with allure.step("Нажать Play и замерить videoStartTime"):
            try:
                page.wait_for_selector(".plyr", timeout=10000)
                metrics.inject_plyr_playing_listener(page)
                page.click(self.SELECTORS["play_button"])
                page.wait_for_function(
                    "() => window.__videoStartTime !== null",
                    timeout=30000
                )
                return page.evaluate("window.__videoStartTime")
            except Exception as e:
                pytest.fail(f"Ошибка при запуске видео: {e}", pytrace=False)
                
    def _collect_buffering_metrics(self, page):
        with allure.step("Собрать метрики буферизации"):
            rebuffer_count = page.evaluate("window.__rebufferCount || 0")
            rebuffer_duration = page.evaluate("window.__rebufferDuration || 0")
            return {
                "rebufferCount": rebuffer_count,
                "rebufferDuration": round(rebuffer_duration)
            }
        
    def _wait_for_popup_and_click(self, page):
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
                pytest.fail("Попап оплаты не появился за 90 секунд", pytrace=False)
                
    def _collect_payment_metrics(self, page, iframe_start_time):
        with allure.step("На странице оплаты собрать метрики"):
            try:
                page.wait_for_selector(self.SELECTORS["payment_iframe"], timeout=15000)
                iframe_load_time_ms = round((time.time() - iframe_start_time) * 1000)
                iframe = page.frame_locator(self.SELECTORS["payment_iframe"])
                return {
                    "iframeCpLoadTime": iframe_load_time_ms,
                    "iframe": iframe
                }
            except Exception as e:
                pytest.fail(f"Ошибка на странице оплаты: {e}", pytrace=False)
                
    def _check_payment_button_click(self, iframe):
        with allure.step("Проверить кликабельность кнопок на странице оплаты"):
            try:
                bank_card_button = iframe.locator(self.SELECTORS["pay_button_bank_card"])
                bank_card_button.wait_for(state="visible", timeout=15000)
                if bank_card_button.is_visible() and bank_card_button.is_enabled():
                    bank_card_button.click(timeout=5000)
                    return {"buttonsCpAvailable": True, "buttonsClickSuccess": True}
                else:
                    return {"buttonsCpAvailable": False, "buttonsClickSuccess": False}
            except PlaywrightTimeoutError:
                pytest.fail("Клик по кнопке оплаты не удался", pytrace=False)
                
    def _wait_for_payment_form(self, iframe):
        with allure.step("Проверить появление формы оплаты"):
            try:
                iframe.locator(self.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")
            except Exception as e:
                pytest.fail(f"Форма оплаты не появилась: {e}", pytrace=False)
                
                
    def _collect_lighthouse_metrics(self, url):
        try:
            lh_report = run_lighthouse_for_url(url)
        except Exception as e:
            if "timed out" in str(e) or "Timeout" in str(e):
                pytest.fail(f"Lighthouse не ответил для {url}", pytrace=False)
            else:
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
                
    # Основной метод — шаблонный метод (template method)
    def run_user_flow(self, page, get_film_url, device, throttling, geo, browser_type, request, extra_steps=None):
        """
        Общий сценарий. extra_steps — словарь с кастомными шагами: 
        {"main_page": func, "film_page_before_video": func}
        """
        report = {
            "test_name": request.node.name,
            "film_url": get_film_url,
            "device": device,
            "throttling": throttling,
            "geoposition": geo,
            "browser_type": browser_type,
            "steps": {},
            "is_problematic_flow": False,
        }

        # Динамические теги и описание
        allure.dynamic.tag(f"device:{device}")
        allure.dynamic.tag(f"throttling:{throttling}")
        allure.dynamic.tag(f"geo:{geo}")
        allure.dynamic.tag(f"browser:{browser_type}")
        allure.dynamic.tag(f"domain:{self.DOMAIN_NAME}")
        allure.dynamic.description(
            f"**Домен**: {self.DOMAIN_NAME}\n"
            f"**Устройство**: {device}\n"
            f"**Сеть**: {throttling}\n"
            f"**ГЕО**: {geo}\n"
            f"**Браузер**: {browser_type}"
        )

        if self.DOMAIN_NAME == "calls7":
            # --- Шаг 1: Главная страница
            if extra_steps and "main_page" in extra_steps:
                extra_steps["main_page"](page, report)
            else:
                self._goto_main_page(page)

        # --- Шаг 2: Страница фильма
        film_metrics = self._goto_film_page_and_init_player(page, get_film_url)
        report["steps"]["film_page"] = film_metrics

        if extra_steps and "film_page_before_video" in extra_steps:
            extra_steps["film_page_before_video"](page, report)

        # --- Шаг 3: Видео
        video_start_ms = self._start_video_and_collect_metrics(page)
        report["steps"]["film_page"]["videoStartTime"] = video_start_ms

        # --- Шаг 4: Буферизация
        buffer_metrics = self._collect_buffering_metrics(page)
        report["steps"]["film_page"].update(buffer_metrics)

        # --- Шаг 5: Попап
        popup_metrics = self._wait_for_popup_and_click(page)
        report["steps"]["film_page"].update(popup_metrics)
        iframe_start = time.time()

        # --- Шаг 6: Оплата
        payment_meta = self._collect_payment_metrics(page, iframe_start)
        report["steps"]["pay_page"] = payment_meta

        if extra_steps and "pay_page_before_click" in extra_steps:
            extra_steps["pay_page_before_click"](page, report)

        button_metrics = self._check_payment_button_click(payment_meta["iframe"])
        report["steps"]["pay_page"].update(button_metrics)

        self._wait_for_payment_form(payment_meta["iframe"])

        # --- Завершение
        log_issues_if_any(report)
        if report.get("is_problematic_flow"):
            pytest.fail("Проблемный запуск", pytrace=False)

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
        request.node._report_data = report
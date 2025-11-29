import allure
import json
import logging
from pathlib import Path
import time
import pytest
import os
import config
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import utils.metrics as metrics
from utils.report_explainer import sanitize_filename
from utils.lighthouse_runner import run_lighthouse_for_url, extract_metrics_from_lighthouse
from utils.log_issues import log_issues_if_any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@pytest.mark.parametrize("device", config.DEVICES)
@pytest.mark.parametrize("throttling", config.THROTTLING_MODES)
@pytest.mark.parametrize("geo", config.GEO_LOCATIONS)
@pytest.mark.parametrize("browser_type", ["chromium"], scope="session")
@allure.story("User Flow: Главная → Фильм → Плеер → Попап → Оплата")
@allure.title("Полный user flow: от главной до формы оплаты  только в chromium")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_flow_parametrized_only_chromium(page, get_film_url, device, throttling, geo, browser_type, request):
    report = {
        "test_name": "test_user_flow_with_metrics_only_chromium",
        "film_url": get_film_url,
        "device": device,
        "throttling": throttling,
        "geoposition": geo,
        "browser_type": browser_type,
        "steps": {},
        "is_problematic_flow": False,
    }
    allure.dynamic.tag(f"device:{device}")
    allure.dynamic.tag(f"throttling:{throttling}")
    allure.dynamic.tag(f"geo:{geo}")
    allure.dynamic.tag(f"browser:{browser_type}")
    
    allure.dynamic.description(
        f"**Устройство**: {device}\n"
        f"**Сеть**: {throttling}\n"
        f"**ГЕО**: {geo}\n"
        f"**Браузер**: {browser_type}"
    )
    
    with allure.step(f"Переходим на главную страницу {config.BASE_URL}"):
        try:
            dns_metrics = metrics.collect_network_metrics(page)
            page.goto(config.BASE_URL)
            page.wait_for_load_state("networkidle")
            try:
                lh_report = run_lighthouse_for_url(config.BASE_URL)
            except Exception as e:
                if "timed out" in str(e) or "Timeout" in str(e):
                    pytest.fail(f"Lighthouse не ответил для {config.BASE_URL}", pytrace=False)
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
            
            report["steps"]["main_page"] = {
                **lh_metrics,
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"],
                "pagePerformanceIndex": ppi,
                "is_problematic_page": ppi < config.TARGET_PAGE_PERFORMANCE_INDEX
            }
            
            if report["steps"]["main_page"]["is_problematic_page"] is True:
                report["is_problematic_flow"] = True

            allure.attach(json.dumps(report["steps"]["main_page"], indent=2), name="MainPage Metrics", attachment_type=allure.attachment_type.JSON)
            allure.attach(f"pagePerformanceIndex: {ppi}\nTarget: {config.TARGET_PAGE_PERFORMANCE_INDEX}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)
        except PlaywrightTimeoutError:
            pytest.fail(f"Не удалось загрузить {config.BASE_URL}", pytrace=False)
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик главной странице: {e}")
            allure.attach(str(e), name="Mainpage Error", attachment_type=allure.attachment_type.TEXT)
            raise
        
    with allure.step(f"Переходим на страницу фильма и собираем метрики для {get_film_url}"):
        try:
            dns_metrics = metrics.collect_network_metrics(page)
            page.goto(get_film_url)
            player_start = time.time()
            page.wait_for_selector("video", timeout=15000)
            player_init_ms = round((time.time() - player_start) * 1000)
            
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            metrics.inject_hls_buffering_listener(page)
            try:
                lh_report = run_lighthouse_for_url(get_film_url)
            except Exception as e:
                if "timed out" in str(e) or "Timeout" in str(e):
                    pytest.fail(f"Lighthouse не ответил для {get_film_url}", pytrace=False)
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
            
            report["steps"]["film_page"] = {
                **lh_metrics,
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"],
                "playerInitTime": player_init_ms,
                "pagePerformanceIndex": ppi,
                "is_problematic_page": ppi < config.TARGET_PAGE_PERFORMANCE_INDEX
            }
            
            if report["steps"]["film_page"]["is_problematic_page"] is True:
                report["is_problematic_flow"] = True

            allure.attach(json.dumps(report["steps"]["film_page"], indent=2), name="FilmPage Metrics", attachment_type=allure.attachment_type.JSON)
            allure.attach(f"pagePerformanceIndex: {ppi}\nTarget: {config.TARGET_PAGE_PERFORMANCE_INDEX}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)
            
        except PlaywrightTimeoutError:
            pytest.fail(f"Не удалось загрузить {get_film_url}", pytrace=False)
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик на странице фильма: {e}")
            allure.attach(str(e), name="FilmPage Error", attachment_type=allure.attachment_type.TEXT)
            raise
        
    with allure.step("Нажать Play и замерить videoStartTime"):
        try:
            page.wait_for_selector(".plyr", timeout=10000)
            metrics.inject_plyr_playing_listener(page)
            page.click(config.SELECTORS["play_button"])
            
            page.wait_for_function(
                "() => window.__videoStartTime !== null",
                timeout=30000
            )
            video_start_ms = page.evaluate("window.__videoStartTime")
            report["steps"]["film_page"]["videoStartTime"] = video_start_ms
            
            allure.attach(f"videoStartTime: {video_start_ms}", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик плеера на странице фильма: {e}")
            allure.attach(str(e), name="FilmPage player Error", attachment_type=allure.attachment_type.TEXT)
            raise

    with allure.step("Собрать метрики буферизации"):
        try:
            rebuffer_count = page.evaluate("window.__rebufferCount || 0")
            rebuffer_duration = page.evaluate("window.__rebufferDuration || 0")
            report["steps"]["film_page"]["rebufferCount"] = rebuffer_count
            report["steps"]["film_page"]["rebufferDuration"] = round(rebuffer_duration)
            
            allure.attach(f"rebufferCount: {rebuffer_count}", name="rebufferCount", attachment_type=allure.attachment_type.TEXT)
            allure.attach(f"rebufferDuration: {round(rebuffer_duration)}", name="rebufferDuration", attachment_type=allure.attachment_type.TEXT)
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик буферизации на странице фильма: {e}")
            allure.attach(str(e), name="FilmPage buffer Error", attachment_type=allure.attachment_type.TEXT)
            raise

    with allure.step("Дождаться появления попапа оплаты"):
        try:
            popup_start = time.time()
            popup_locator = page.locator(config.SELECTORS["popup"])
            popup_locator.wait_for(state="visible", timeout=90000)
            popup_time_ms = round((time.time() - popup_start) * 1000)
            report["steps"]["film_page"]["popupAppearTime"] = popup_time_ms
            
            allure.attach(f"popupAppearTime: {popup_time_ms}", name="popupAppearTime", attachment_type=allure.attachment_type.TEXT)
        except PlaywrightTimeoutError:
            report["steps"]["film_page"]["popupAvailable"] = False
            pytest.fail("Попап оплаты не появился за 90 секунд", pytrace=False)
        except Exception as e:
            logger.error(f"Ошибка при появления попапа оплаты на странице фильма: {e}")
            allure.attach(str(e), name="FilmPage popup Error", attachment_type=allure.attachment_type.TEXT)
            raise
        
    with allure.step("Проверить кликабельность попапа"):
        try:
            if popup_locator.is_visible() and popup_locator.is_enabled():
                popup_available = True
                try:
                    dns_metrics = metrics.collect_network_metrics(page, "vidu.my") # HERE OR EARLIER?
                    popup_locator.click(timeout=5000)
                    iframe_start = time.time() # iframe start here!
                    popup_click_success = True
                except PlaywrightTimeoutError as e:
                    logger.warning("Попап виден, но клик не прошёл (возможно, перекрыт или не интерактивен)")
                    allure.attach(str(e), name="FilmPage popup click Error", attachment_type=allure.attachment_type.TEXT)
                    popup_click_success = False
                    pytest.fail("Клик по попапу не удался (элемент не интерактивен)", pytrace=False)
            else:
                popup_available = False
        except Exception as e:
            logger.error(f"Ошибка кликабельности попапа оплаты на странице фильма: {e}")
            allure.attach(str(e), name="FilmPage popup click Error", attachment_type=allure.attachment_type.TEXT)
            popup_available = False
            popup_click_success = False
            raise
        finally:
            report["steps"]["film_page"]["popupAvailable"] = popup_available
            report["steps"]["film_page"]["popupClickSuccess"] = popup_click_success
            allure.attach(f"popupAvailable: {popup_available}", name="popupAvailable", attachment_type=allure.attachment_type.TEXT)
            allure.attach(f"popupClickSuccess: {popup_click_success}", name="popupClickSuccess", attachment_type=allure.attachment_type.TEXT)
            
    with allure.step("На странице оплаты собрать метрики"):
        try:
            page.wait_for_selector(config.SELECTORS["payment_iframe"], timeout=15000)
            iframe_load_time_ms = round((time.time() - iframe_start) * 1000)
            iframe = page.frame_locator(config.SELECTORS["payment_iframe"])
            
            page.wait_for_load_state("networkidle")
            
            report["steps"]["pay_page"] = {
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"],
                "iframeCpLoadTime": iframe_load_time_ms
            }
            
            allure.attach(f"{iframe_load_time_ms} ms", name="iframeCpLoadTime", attachment_type=allure.attachment_type.TEXT)
            allure.attach(json.dumps(report["steps"]["pay_page"], indent=2), name="PayPage Metrics", attachment_type=allure.attachment_type.JSON)

        except Exception as e:
            logger.error(f"Ошибка на странице оплаты: {e}")
            allure.attach(str(e), name="PaymentPage Error", attachment_type=allure.attachment_type.TEXT)
            raise
            

    with allure.step("Проверить кликабельность кнопок на странице оплаты"):
        try:
            bank_card_button = iframe.locator(config.SELECTORS["pay_button_bank_card"])
            bank_card_button.wait_for(state="visible", timeout=15000)
            if bank_card_button.is_visible() and bank_card_button.is_enabled():
                buttons_cp_available = True
                try:
                    bank_card_button.click(timeout=5000)
                    buttons_click_success = True
                except PlaywrightTimeoutError as e:
                    logger.warning("Кнопка видна, но клик не прошёл (возможно, перекрыта или не интерактивена)")
                    buttons_click_success = False
                    allure.attach(str(e), name="PayPage button click Error", attachment_type=allure.attachment_type.TEXT)
                    pytest.fail("Клик по кнопке оплаты не удался", pytrace=False)
            else:
                buttons_cp_available = False
        except Exception as e:
            logger.error(f"Ошибка кликабельности на странице оплаты: {e}")
            allure.attach(str(e), name="PaymentPage click Error", attachment_type=allure.attachment_type.TEXT)
            buttons_cp_available = False
        finally:
            report["steps"]["pay_page"]["buttonsCpAvailable"] = buttons_cp_available
            report["steps"]["pay_page"]["buttonsClickSuccess"] = buttons_click_success
            allure.attach(f"buttonsCpAvailable: {buttons_cp_available}", name="buttonsCpAvailable", attachment_type=allure.attachment_type.TEXT)
            allure.attach(f"buttonsClickSuccess: {buttons_click_success}", name="buttonsClickSuccess", attachment_type=allure.attachment_type.TEXT)
            
    with allure.step("Проверить появление формы оплаты"):
        try:
            iframe.locator(config.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")
        except Exception as e:
            logger.error(f"Ошибка появления формы на странице оплаты: {e}")
            allure.attach(str(e), name="PaymentPage form visibility Error", attachment_type=allure.attachment_type.TEXT)
            

    if log_issues_if_any(report):
        report["is_problematic_flow"] = True
            

    # === Сохранение финального отчёта ===
    with allure.step("Сохранить сводный отчёт"):
        Path("reports").mkdir(exist_ok=True)
        safe_url = sanitize_filename(get_film_url)
        report_path = f"reports/report_{__name__}_{safe_url}_{device}_{throttling}_{geo}_{browser_type}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        allure.attach.file(report_path, name="JSON-отчёт по конкретному запуску", extension="json")
        
        request.node._report_data = report

    
    assert report["is_problematic_flow"] == False, "Проблемный запуск"
    
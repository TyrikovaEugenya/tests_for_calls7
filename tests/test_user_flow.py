import allure
import time
import pytest
import json
import logging
import os
import config
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import utils.metrics as metrics
from utils.report_builder import build_enriched_report
from utils.lighthouse_runner import run_lighthouse_for_url, extract_metrics_from_lighthouse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def save_json_report(data, filename="user_flow_report.json"):
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@allure.title("Полный user flow: от главной до формы оплаты")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_flow_with_metrics(page, get_film_url):
    report = {
        "url": get_film_url,
        "steps": {},
        "metrics": {},
        "pagePerformanceIndex": None,
        "playerInitTime": None,
        "videoStartTime": None,
        "popupAppearTime": None,
        "popupAvailable": True,
        "popupClickSuccess": True,
        "buttonsCpAvailable": True
    }
    
    # with allure.step("Собрать Lighthouse-метрики для главной страницы"):
    #     try:
    #         lh_report = run_lighthouse_for_url(config.BASE_URL)
    #         lh_metrics = extract_metrics_from_lighthouse(lh_report)

    #         # Сохраняем в общий отчёт
    #         report["metrics"] = lh_metrics

    #         # Вычисляем индекс
    #         ppi = config.calculate_page_performance_index(
    #             lcp=lh_metrics.get("lcp"),
    #             cls=lh_metrics.get("cls"),
    #             tbt=lh_metrics.get("tbt"),
    #             ttfb=lh_metrics.get("ttfb"),
    #             fid=lh_metrics.get("inp")  # используем INP как замену FID
    #         )
    #         report["pagePerformanceIndex"] = ppi
    #         report["is_problematic"] = ppi < config.TARGET_PAGE_PERFORMANCE_INDEX

    #         # Прикрепляем к Allure
    #         allure.attach(json.dumps(lh_metrics, indent=2, ensure_ascii=False), name="Lighthouse Metrics", attachment_type=allure.attachment_type.JSON)
    #         allure.attach(f"pagePerformanceIndex: {ppi}\nTarget: {config.TARGET_PAGE_PERFORMANCE_INDEX}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)

    #         logger.info(f"Lighthouse метрики собраны. PPI: {ppi}")

    #     except Exception as e:
    #         logger.error(f"Ошибка при сборе Lighthouse-метрик: {e}")
    #         allure.attach(str(e), name="Lighthouse Error", attachment_type=allure.attachment_type.TEXT)
    #         raise

    with allure.step("Открыть главную и собрать метрики"):
        dns_metrics = metrics.collect_network_metrics(page)
        page.goto(config.BASE_URL)
        page.wait_for_load_state("networkidle")
        perf_main = metrics.collect_performance_metrics(page)
        report["steps"]["main_page"] = {
            **perf_main,
            "dnsResolveTime": dns_metrics["dnsResolveTime"],
            "connectTime": dns_metrics["connectTime"]
        }
        allure.attach(json.dumps(report["metrics"], indent=2), name="MainPage Metrics", attachment_type=allure.attachment_type.JSON)
        
    with allure.step("Перейти на страницу фильма и дождаться появления плеера"):
        dns_metrics = metrics.collect_network_metrics(page)
        page.goto(get_film_url)
        player_start = time.time()
        page.wait_for_selector("video", timeout=15000)
        player_end = round((time.time() - player_start) * 1000)
        report["playerInitTime"] = player_end


    with allure.step("Инжектировать слушатель буферизации"):
        page.wait_for_load_state("networkidle")
        metrics.inject_hls_buffering_listener(page)
        

    with allure.step("Собрать метрики страницы фильма"):
        
        perf_film = metrics.collect_performance_metrics(page)
        report["steps"]["film_page"] = {
            **perf_film,
            "dnsResolveTime": dns_metrics["dnsResolveTime"],
            "connectTime": dns_metrics["connectTime"]
        }
        report["metrics"] = report["steps"]["film_page"]

        ppi = config.calculate_page_performance_index(
            lcp=perf_film["lcp"],
            fid=perf_film["fid"],
            cls=perf_film["cls"],
            tbt=perf_film["tbt"],
            ttfb=perf_film["ttfb"]
        )
        report["pagePerformanceIndex"] = ppi

        allure.attach(json.dumps(report["metrics"], indent=2), name="Page Metrics", attachment_type=allure.attachment_type.JSON)
        allure.attach(f"pagePerformanceIndex: {ppi}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)

    with allure.step("Нажать Play и замерить videoStartTime"):
        page.on("console", lambda msg: 
            logger.warning(f"Console: {msg.text}") if "ERR_FILE_NOT_FOUND" in msg.text else None
        )
        page.wait_for_selector(".plyr", timeout=10000)
        metrics.inject_plyr_playing_listener(page)
        page.click(config.SELECTORS["play_button"])

        try:
            page.wait_for_function(
                "() => window.__videoStartTime !== null",
                timeout=30000
            )
            video_start_ms = page.evaluate("window.__videoStartTime")
            report["videoStartTime"] = round(video_start_ms)
            allure.attach(f"{video_start_ms:.0f} ms", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)
        except Exception as e:
            report["videoStartTime"] = "Не удалось измерить"
            logger.warning(f"Не удалось измерить videoStartTime: {e}")
            allure.attach("Не удалось измерить", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)
            
    with allure.step("Собрать метрики буферизации"):
        rebuffer_count = page.evaluate("window.__rebufferCount || 0")
        rebuffer_duration = page.evaluate("window.__rebufferDuration || 0")
        report["rebufferCount"] = rebuffer_count
        report["rebufferDuration"] = round(rebuffer_duration)

    with allure.step("Дождаться появления попапа оплаты и проверить кликабельность"):
        try:
            popup_start = time.time()
            popup_locator = page.locator(config.SELECTORS["popup"])
            popup_locator.wait_for(state="visible", timeout=90000)
            popup_time = time.time() - popup_start
            report["popupAppearTime"] = round(popup_time * 1000)
            if popup_locator.is_visible() and popup_locator.is_enabled():
                popup_available = True
                try:
                    popup_locator.click(timeout=5000)
                    popup_click_success = True
                except PlaywrightTimeoutError:
                    logger.warning("Попап виден, но клик не прошёл (возможно, перекрыт или не интерактивен)")
                    popup_click_success = False
            else:
                popup_available = False
        
        except PlaywrightTimeoutError:
            logger.error("Попап не появился в течение 90 секунд")
            popup_available = False
            popup_click_success = False
            
        report["popupAvailable"] = popup_available
        report["popupClickSuccess"] = popup_click_success
                    
        
    with allure.step("Дождаться появления iframe и замерить время"):
        iframe_start = time.time()
        page.wait_for_selector(config.SELECTORS["payment_iframe"], timeout=15000)
        iframe = page.frame_locator(config.SELECTORS["payment_iframe"])
        iframe_load_time_ms = round((time.time() - iframe_start) * 1000)
        report["iframeCpLoadTime"] = iframe_load_time_ms
        allure.attach(f"{iframe_load_time_ms} ms", name="iframeCpLoadTime", attachment_type=allure.attachment_type.TEXT)

    with allure.step("Нажать на кнопку оплаты и дождаться появления формы, измерить доступность кнопок"):
        try:
            bank_card_button = iframe.locator(config.SELECTORS["pay_button_bank_card"])
            bank_card_button.wait_for(state="visible", timeout=15000)
            if bank_card_button.is_visible() and bank_card_button.is_enabled():
                buttons_cp_available = True
            else:
                buttons_cp_available = False
        except Exception as e:
            logger.error(f"Ошибка при проверке кнопок оплаты: {e}")
            buttons_cp_available = False
            
        report["buttonsCpAvailable"] = buttons_cp_available
        iframe.locator(config.SELECTORS["pay_button_bank_card"]).click()
        iframe.locator(config.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")

    geo = "Moscow"          # или из фикстуры --geo
    device = "Desktop"      # или из --device
    network = "Slow 4G"     # или из --throttling

    enriched = build_enriched_report(
        raw_data=report,
        geo=geo,
        device=device,
        network=network,
        target_ppi=config.TARGET_PAGE_PERFORMANCE_INDEX
    )

    # === Сохранение отчёта ===
    with open("reports/user_flow_report_raw.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open("reports/user_flow_report.json", "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
        
    allure.attach.file("reports/user_flow_report_raw.json", name="JSON Report", extension=".json")
    allure.attach.file("reports/user_flow_report.json", name="Full JSON Report", extension=".json")
    

    # === Проверка порога производительности ===
    assert report["pagePerformanceIndex"] >= config.TARGET_PAGE_PERFORMANCE_INDEX, \
        f"pagePerformanceIndex ({report['pagePerformanceIndex']}) < {config.TARGET_PAGE_PERFORMANCE_INDEX}"
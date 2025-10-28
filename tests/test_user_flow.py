import allure
import time
import pytest
import json
import logging
import os
import config
import utils.metrics as metrics

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
        "videoStartTime": None,
        "popupAppearTime": None
    }

    with allure.step("Открыть главную и собрать метрики"):
        dns_metrics = metrics.collect_network_metrics(page)
        page.goto(config.BASE_URL)
        perf_main = metrics.collect_performance_metrics(page)
        report["steps"]["main_page"] = {
            **perf_main,
            "dnsResolveTime": dns_metrics["dnsResolveTime"],
            "connectTime": dns_metrics["connectTime"]
        }
        
    with allure.step("Перейти на страницу фильма"):
        dns_metrics = metrics.collect_network_metrics(page)
        page.goto(get_film_url)
        page.wait_for_load_state("networkidle")

    with allure.step("Инжектировать слушатель буферизации"):
        metrics.inject_hls_buffering_listener(page)
        
    with allure.step("Дождаться появления элемента <video>"):
        page.wait_for_selector("video", timeout=15000)

    with allure.step("Собрать метрики страницы фильма"):
        
        perf_film = metrics.collect_performance_metrics_after_video(page)
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

    with allure.step("Дождаться появления попапа оплаты (до 90 сек)"):
        popup_start = time.time()
        page.wait_for_selector(config.SELECTORS["popup"], timeout=90000)
        popup_time = time.time() - popup_start
        report["popupAppearTime"] = round(popup_time * 1000)
        logger.info(f"✅ Попап появился через {popup_time:.1f} сек")

    with allure.step("Перейти на страницу оплаты и открыть форму карты"):
        with page.expect_navigation():
            page.click(config.SELECTORS["popup_cta"])

        page.wait_for_selector(config.SELECTORS["payment_iframe"], timeout=15000)
        iframe = page.frame_locator(config.SELECTORS["payment_iframe"])
        iframe.locator(config.SELECTORS["pay_button_bank_card"]).wait_for(state="visible")
        iframe.locator(config.SELECTORS["pay_button_bank_card"]).click()
        iframe.locator(config.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")

    # === Сохранение отчёта ===
    save_json_report(report)
    allure.attach.file("reports/user_flow_report.json", name="Full JSON Report", extension=".json")

    # === Проверка порога производительности ===
    assert report["pagePerformanceIndex"] >= config.TARGET_PAGE_PERFORMANCE_INDEX, \
        f"pagePerformanceIndex ({report['pagePerformanceIndex']}) < {config.TARGET_PAGE_PERFORMANCE_INDEX}"
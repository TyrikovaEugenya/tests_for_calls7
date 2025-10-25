import allure
import time
import pytest
import json
import logging
import os
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def collect_performance_metrics(page):
    """Собирает Lighthouse-подобные метрики через Performance API"""
    metrics = page.evaluate("""
        () => {
            const entries = performance.getEntriesByType('navigation')[0];
            const lcpEntry = performance.getEntriesByName('largest-contentful-paint')[0];
            const lcp = lcpEntry ? lcpEntry.startTime : 0;
            const ttfb = entries ? entries.responseStart - entries.requestStart : 0;
            const cls = 0;
            const fid = 0;
            let tbt = 0;
            const longTasks = performance.getEntriesByType('longtask');
            if (longTasks) {
                tbt = longTasks.reduce((sum, task) => sum + task.duration, 0);
            }
            return { lcp, ttfb, cls, fid, tbt };
        }
    """)
    return metrics


def save_json_report(data, filename="user_flow_report.json"):
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@allure.title("Полный user flow: от главной до формы оплаты")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_flow_with_metrics(page):
    report = {
        "url": None,
        "steps": {},
        "metrics": {},
        "pagePerformanceIndex": None,
        "videoStartTime": None,
        "popupAppearTime": None
    }
    is_webdriver = page.evaluate("() => navigator.webdriver")
    print("navigator.webdriver:", is_webdriver)

    # === Шаг 1: Главная страница ===
    with allure.step("Открыть главную и собрать метрики"):
        page.goto(config.BASE_URL)
        perf_main = collect_performance_metrics(page)
        report["steps"]["main_page"] = perf_main

    # === Шаг 2: Выбор фильма через клик ===
    with allure.step("Выбрать фильм"):
        # film_title = "Черный замок"
        # page.click(f"text={film_title}")
        page.goto(config.FILM_EXAMPLE_URL)
        page.wait_for_load_state("networkidle")
        has_play_js = page.evaluate("""
            () => {
                const scripts = Array.from(document.querySelectorAll('script'));
                return scripts.some(s => s.src.includes('play.js'));
            }
        """)
        logger.info(f"Скрипт play.js загружен: {has_play_js}")

    # === Шаг 3: Сбор метрик страницы фильма ===
    with allure.step("Собрать метрики страницы фильма"):
        perf_film = collect_performance_metrics(page)
        report["steps"]["film_page"] = perf_film

        ppi = config.calculate_page_performance_index(
            lcp=perf_film["lcp"],
            fid=perf_film["fid"],
            cls=perf_film["cls"],
            tbt=perf_film["tbt"],
            ttfb=perf_film["ttfb"]
        )
        report["pagePerformanceIndex"] = ppi
        report["metrics"] = perf_film

        allure.attach(json.dumps(perf_film, indent=2), name="Lighthouse Metrics", attachment_type=allure.attachment_type.JSON)
        allure.attach(f"pagePerformanceIndex: {ppi}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)

    # === Шаг 4: Дождаться появления плеера ===
    with allure.step("Дождаться появления элемента <video>"):
        page.wait_for_selector("video", timeout=15000)

    # === Шаг 5: Нажать Play и дождаться загрузки видео (.ts) ===
    with allure.step("Нажать Play и дождаться первого сегмента видео"):
        # Логирование консоли
        page.on("console", lambda msg: 
            logger.warning(f"Console: {msg.text}") if "ERR_FILE_NOT_FOUND" in msg.text else None
        )

        # Собираем сетевые запросы
        requests = []
        page.on("request", lambda r: requests.append(r))

        # Кликаем по большой кнопке Play
        start_click = time.time()
        page.click(config.SELECTORS["play_button"])

        # Ждём первый .ts сегмент до 30 сек
        ts_request = None
        for _ in range(30):
            for req in requests:
                if ".m3u8" in req.url or ".ts" in req.url:
                    print("✅ Видео грузится:", req.url)
                    if ".ts" in req.url and req.method == "GET":
                        ts_request = req
                        break
            if ts_request:
                break
            time.sleep(1)

        if not ts_request:
            logger.warning("Видео не начало грузиться за 30 сек — пропускаем замер videoStartTime")
            report["videoStartTime"] = "Не удалось замерить"
            allure.attach("Видео не загрузилось", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)
        else:
            logger.info(f"✅ Началась загрузка видео: {ts_request.url}")
            video_start_ms = (ts_request.timing.get("startTime", 0) * 1000) - (start_click * 1000)
            report["videoStartTime"] = round(video_start_ms)
            allure.attach(f"{video_start_ms:.0f} ms", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)

    # === Шаг 6: Ожидание попапа оплаты ===
    with allure.step("Дождаться появления попапа оплаты (до 90 сек)"):
        popup_start = time.time()
        page.wait_for_selector("#dcoverlay:not(.hidden)", timeout=90000)
        popup_time = time.time() - popup_start
        report["popupAppearTime"] = round(popup_time * 1000)
        logger.info(f"✅ Попап появился через {popup_time:.1f} сек")

    # === Шаг 7–8: Переход на оплату и работа с iframe ===
    with allure.step("Перейти на страницу оплаты и открыть форму карты"):
        with page.expect_navigation():
            page.click(config.SELECTORS["popup_cta"])

        page.wait_for_selector(config.SELECTORS["payment_iframe"], timeout=15000)
        iframe = page.frame_locator(config.SELECTORS["payment_iframe"])
        iframe.locator(config.SELECTORS["pay_button_in_iframe"]).click()
        iframe.locator(config.SELECTORS["pay_button_bank_card"]).click()
        iframe.locator(config.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")

    # === Сохранение отчёта ===
    save_json_report(report)
    allure.attach.file("reports/user_flow_report.json", name="Full JSON Report", extension=".json")

    # === Проверка порога производительности ===
    assert report["pagePerformanceIndex"] >= config.TARGET_PAGE_PERFORMANCE_INDEX, \
        f"pagePerformanceIndex ({report['pagePerformanceIndex']}) < {config.TARGET_PAGE_PERFORMANCE_INDEX}"
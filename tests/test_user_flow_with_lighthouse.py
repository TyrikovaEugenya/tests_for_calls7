# tests/test_user_flow.py
import allure
import json
import logging
from pathlib import Path
from utils.lighthouse_runner import run_lighthouse_for_url, extract_metrics_from_lighthouse
from config import calculate_page_performance_index, TARGET_PAGE_PERFORMANCE_INDEX

logger = logging.getLogger(__name__)

@allure.title("Полный user flow: от главной до формы оплаты")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_flow_with_metrics(page, get_film_url):
    report = {
        "film_url": get_film_url,
        "metrics": {},
        "pagePerformanceIndex": None,
        "is_problematic": False,
    }

    # === Шаг 1: Сбор Lighthouse-метрик для страницы фильма ===
    with allure.step(f"Собрать Lighthouse-метрики для {get_film_url}"):
        try:
            page.goto(get_film_url)
            page.wait_for_load_state("networkidle")
            lh_report = run_lighthouse_for_url(get_film_url)
            lh_metrics = extract_metrics_from_lighthouse(lh_report)

            # Сохраняем в общий отчёт
            report["metrics"] = lh_metrics

            # Вычисляем индекс
            ppi = calculate_page_performance_index(
                lcp=lh_metrics.get("lcp"),
                cls=lh_metrics.get("cls"),
                tbt=lh_metrics.get("tbt"),
                ttfb=lh_metrics.get("ttfb"),
                fid=lh_metrics.get("inp")  # используем INP как замену FID
            )
            report["pagePerformanceIndex"] = ppi
            report["is_problematic"] = ppi < TARGET_PAGE_PERFORMANCE_INDEX

            # Прикрепляем к Allure
            allure.attach(json.dumps(lh_metrics, indent=2, ensure_ascii=False), name="Lighthouse Metrics", attachment_type=allure.attachment_type.JSON)
            allure.attach(f"pagePerformanceIndex: {ppi}\nTarget: {TARGET_PAGE_PERFORMANCE_INDEX}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)

            logger.info(f"Lighthouse метрики собраны. PPI: {ppi}")

        except Exception as e:
            logger.error(f"Ошибка при сборе Lighthouse-метрик: {e}")
            allure.attach(str(e), name="Lighthouse Error", attachment_type=allure.attachment_type.TEXT)
            raise

    # === Шаг 2: Открыть страницу фильма в Playwright (для дальнейших действий) ===
    with allure.step("Открыть страницу фильма в браузере"):
        page.goto(get_film_url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

    # === Шаг 3: Работа с плеером (твоя логика) ===
    with allure.step("Дождаться появления плеера"):
        page.wait_for_selector("video", timeout=15000)

    with allure.step("Нажать Play и замерить videoStartTime"):
        # ... твоя существующая логика ...
        pass  # замени на свой код

    # === Шаг 4: Попап и оплата (твоя логика) ===
    # ... продолжи свой сценарий ...

    # === Сохранение финального отчёта ===
    with allure.step("Сохранить сводный отчёт"):
        Path("reports").mkdir(exist_ok=True)
        report_path = f"reports/report_{hash(get_film_url) % 10000}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        allure.attach.file(report_path, name="Сводный JSON-отчёт", extension="json")
import config
import os
from pathlib import Path

def log_issues_if_any(report: dict, log_path: str = "reports/issues.log"):
    """
    Анализирует report и дописывает проблемные метрики в лог-файл.
    Вызывать внутри теста после заполнения report.
    """
    issues = []
    has_issues = False

    test_name = report.get("test_name", "unknown_test")
    device = report.get("device", "N/A")
    throttling = report.get("throttling", "N/A")
    geo = report.get("geoposition", "N/A")
    browser = report.get("browser_type", "N/A")
    film_url = report.get("film_url", "").strip()
    test_display = f"{test_name}[{device}, {throttling}, {geo}, {browser}]"
    
    # 2. Проверяем Page Performance Index по шагам
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        ppi = metrics.get("pagePerformanceIndex")
        if ppi is not None and ppi < config.TARGET_PAGE_PERFORMANCE_INDEX:
            issues.append(f"{test_display} | {film_url} | {step_name}.pagePerformanceIndex = {ppi}")
            
    # 3. Проверяем индивидуальные метрики из METRIC_THRESHOLDS
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        for metric_name, (good, poor) in config.METRIC_THRESHOLDS.items():
            value = metrics.get(metric_name)
            # Пропускаем None и 0 (если 0 — ок, например, rebufferCount)
            if value is None or value == 0:
                continue
            if value > poor:
                issues.append(f"{test_display} | {film_url} | {step_name}.{metric_name} = {value}")
                
    # 4. Дополнительные бинарные проверки
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        # popupAvailable == False
        popup_ok = metrics.get("popupAvailable")
        if popup_ok is False:
            issues.append(f"{test_display} | {film_url} | {step_name}.popupAvailable = False")

        # buttonsCpAvailable == False
        buttons_ok = metrics.get("buttonsCpAvailable")
        if buttons_ok is False:
            issues.append(f"{test_display} | {film_url} | {step_name}.buttonsCpAvailable = False")
            
    # 5. Запись в файл (дозапись)
    if issues:
        has_issues = True
        Path("reports").mkdir(exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for issue in issues:
                f.write(issue + "\n")

    return has_issues
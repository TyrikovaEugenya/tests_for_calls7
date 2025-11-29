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
    
    # Проверяем Page Performance Index по шагам
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        ppi = metrics.get("pagePerformanceIndex")
        if ppi is not None and ppi < config.TARGET_PAGE_PERFORMANCE_INDEX:
            issues.append(f"{test_display} | {film_url} | {step_name}.pagePerformanceIndex = {ppi}")
            
    # Проверяем ВСЕ индивидуальные метрики из METRIC_THRESHOLDS
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        for metric_name, (good, poor) in config.METRIC_THRESHOLDS.items():
            value = metrics.get(metric_name)
            # Пропускаем None и 0 (если 0 — ок, например, rebufferCount)
            if value is None:
                continue
                
            # Для rebufferCount 0 - это хорошо, поэтому проверяем только > 0
            if metric_name == "rebufferCount" and value == 0:
                continue
                
            if value > poor:
                issues.append(f"{test_display} | {film_url} | {step_name}.{metric_name} = {value}")
                
    # Проверяем ВСЕ бинарные метрики
    binary_metrics = [
        "popupAvailable", "buttonsCpAvailable", "popupClickSuccess", 
        "buttonsClickSuccess", "payFormAppear", "viduPopupSuccess", "retryPaymentSuccess"
    ]
    
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        for metric_name in binary_metrics:
            value = metrics.get(metric_name)
            if value is False:
                issues.append(f"{test_display} | {film_url} | {step_name}.{metric_name} = False")

    # Дополнительные проверки для специфичных метрик
    for step_name, metrics in report.get("steps", {}).items():
        if not isinstance(metrics, dict):
            continue

        # Проверяем performance_score
        perf_score = metrics.get("performance_score")
        if perf_score is not None and perf_score < 0.7:  # Порог для performance_score
            issues.append(f"{test_display} | {film_url} | {step_name}.performance_score = {perf_score}")

        # Проверяем CLS (Cumulative Layout Shift)
        cls = metrics.get("cls")
        if cls is not None and cls > 0.1:  # Рекомендуемый порог CLS
            issues.append(f"{test_display} | {film_url} | {step_name}.cls = {cls}")

        # Проверяем TBT (Total Blocking Time)
        tbt = metrics.get("tbt")
        if tbt is not None and tbt > 200:  # Рекомендуемый порог TBT
            issues.append(f"{test_display} | {film_url} | {step_name}.tbt = {tbt}")
            
    if report.get("error"):
        issues.append(f"{test_display} | {film_url} | error = {report['error']}")
            
    # Запись в файл (дозапись)
    if issues:
        has_issues = True
        Path("reports").mkdir(exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for issue in issues:
                f.write(issue + "\n")

    return has_issues
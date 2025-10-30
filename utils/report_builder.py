import json
import time
import config

def enrich_metric(metric_name: str, value, page_type: str = "film_page"):
    """Обогащает метрику статусом и пояснением"""
    base = {"value": value}

    if metric_name == "lcp":
        if value == 0:
            base.update({
                "status": "Не измерено",
                "reason": "Кастомный плеер не роспознан как LCP элемент" if page_type == "film_page" else "Не зафиксировано больших элементов контента"
            })
        elif value < 2500:
            base["status"] = "good"
        elif value < 4000:
            base["status"] = "needs_improvement"
        else:
            base["status"] = "poor"
        base["unit"] = "ms"

    elif metric_name == "fid":
        if value == 0:
            base.update({
                "status": "not_applicable",
                "reason": "Нет реальных пользовательских взаимодействий во время теста"
            })
        else:
            base["status"] = "good" if value < 100 else "poor"
        base["unit"] = "ms"

    elif metric_name == "cls":
        if value == 0:
            base["status"] = "good"
        elif value < 0.1:
            base["status"] = "good"
        elif value < 0.25:
            base["status"] = "needs_improvement"
        else:
            base["status"] = "poor"
        base["unit"] = "score"

    elif metric_name in ("tbt", "ttfb"):
        threshold = 200 if metric_name == "tbt" else 600
        if value == 0:
            base["status"] = "good"  # возможно, страница очень быстрая
        else:
            base["status"] = "good" if value < threshold else "needs_improvement"
        base["unit"] = "ms"

    else:
        base["status"] = "unknown"

    return base

def build_enriched_report(
    raw_data: dict,
    geo: str = "Moscow",
    device: str = "Desktop",
    network: str = "Slow 4G",
    target_ppi: float = config.TARGET_PAGE_PERFORMANCE_INDEX
):
    film_url = raw_data["url"].strip()

    # Определяем, проблемная ли страница
    film_ppi = raw_data.get("pagePerformanceIndex", 100)
    is_problematic = film_ppi < target_ppi

    # Обогащаем метрики для страниц
    enriched_pages = {}
    for page_key in ["main_page", "film_page"]:
        if page_key in raw_data["steps"]:
            raw_metrics = raw_data["steps"][page_key]
            enriched_metrics = {}

            for metric_name in ["lcp", "ttfb", "cls", "fid", "tbt"]:
                val = raw_metrics.get(metric_name)
                if val is not None:
                    enriched_metrics[metric_name.upper()] = enrich_metric(metric_name, val, page_key)

            # Сетевые метрики
            dns = raw_metrics.get("dnsResolveTime")
            connect = raw_metrics.get("connectTime")

            # Преобразуем строки в null, числа — оставляем
            def clean_net(val):
                return None if isinstance(val, str) else round(val, 1) if isinstance(val, (int, float)) else None

            network_data = {
                "dnsResolveTime_ms": clean_net(dns),
                "connectTime_ms": clean_net(connect)
            }
            if isinstance(dns, str):
                network_data["note"] = dns  # переносим пояснение

            enriched_pages[page_key] = {
                "url": raw_data["steps"][page_key].get("url", film_url if page_key == "film_page" else "https://calls7.com/"),
                "metrics": enriched_metrics,
                "network": network_data
            }

    # Формируем итоговый отчёт
    report = {
        "test_run": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "film": film_url,
            "context": {
                "geo": geo,
                "device": device,
                "network": network
            }
        },
        "user_flow": {
            "video_started": raw_data.get("videoStartTime") not in (None, "Не удалось измерить"),
            "popup_appeared": raw_data.get("popupAppearTime") is not None,
            "payment_iframe_loaded": raw_data.get("iframeCpLoadTime") is not None
        },
        "performance": {
            "target_page_performance_index": target_ppi,
            "film_page_index": film_ppi,
            "status": "warning" if is_problematic else "good",
            "summary": "LCP не измерен из-за особенностей плеера. Рекомендуется явно помечать видео как hero-элемент." if film_ppi < 100 else "Все метрики в пределах нормы."
        },
        "pages": enriched_pages,
        "player": {
            "playerInitTime_ms": raw_data.get("playerInitTime"),
            "videoStartTime_ms": raw_data.get("videoStartTime"),
            "popupAppearTime_ms": raw_data.get("popupAppearTime"),
            "popupAvailable": raw_data.get("popupAvailable"),
            "rebufferCount": raw_data.get("rebufferCount", 0),
            "rebufferDuration_ms": raw_data.get("rebufferDuration", 0)
        },
        "payment": {
            "iframeCpLoadTime_ms": raw_data.get("iframeCpLoadTime"),
            "buttonsAvailable": raw_data.get("buttonsCpAvailable")
        }
    }

    return report
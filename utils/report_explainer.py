
def _get_metric_rating(value, metric_name):
    """Возвращает оценку (✅/⚠️/❌) и текстовую метку."""
    if value is None:
        return "❓", "не измерено"
    if value == 0:
        if metric_name in ("rebufferCount", "rebufferDuration", "cls"):
            return "✅", "отлично"
        # для dns/connect — нейтрально
        if metric_name in ("dnsResolveTime", "connectTime"):
            return "ℹ️", "кэшировано"

    thresholds = {
        "lcp": (2500, 4000),
        "fcp": (1800, 3000),
        "tbt": (200, 600),
        "ttfb": (600, 1000),
        "inp": (200, 500),
        "videoStartTime": (3000, 10000),
        "iframeCpLoadTime": (2000, 4000),
    }

    if metric_name in thresholds:
        good, poor = thresholds[metric_name]
        if value <= good:
            return "✅", "хорошо"
        elif value <= poor:
            return "⚠️", "удовлетворительно"
        else:
            return "❌", "плохо"

    if metric_name == "cls":
        if value <= 0.1:
            return "✅", "хорошо"
        elif value <= 0.25:
            return "⚠️", "удовлетворительно"
        else:
            return "❌", "плохо"

    return "ℹ️", "без оценки"


def explain_metric_value(value: Any, metric_name: str) -> str:
    """Пояснение + оценка."""
    if value is None:
        if metric_name == "inp":
            return "не измерено (INP требует реального взаимодействия)"
        return "не измерено"
    if value == 0:
        if metric_name in ("dnsResolveTime", "connectTime"):
            return "0 — использовано кэшированное соединение"
        if metric_name in ("rebufferCount", "rebufferDuration"):
            return "0 — без буферизации (отлично!)"
        if metric_name == "cls":
            return "0 — нет сдвигов макета (идеально)"
        return "0 — значение не зафиксировано"
    return str(value)


def generate_human_readable_report(report: dict) -> str:
    film_url = report.get("film_url", "").strip()
    is_problematic_flow = report.get("is_problematic_flow", False)

    lines = []
    lines.append("🔍 **Сводный отчёт по пользовательскому сценарию**")
    lines.append(f"🎬 Фильм: {film_url}")
    lines.append(f"⚠️ Проблемный сценарий: {'Да' if is_problematic_flow else 'Нет'}")
    lines.append("")

    steps = report.get("steps", {})
    for step_name, metrics in steps.items():
        if not metrics:
            continue

        title_map = {
            "main_page": "Главная страница",
            "film_page": "Страница фильма",
            "pay_page": "Страница оплаты"
        }
        title = title_map.get(step_name, step_name.replace("_", " ").title())
        lines.append(f"### 📄 {title}")
        lines.append("")

        # Performance Score и PagePerformanceIndex
        if "performance_score" in metrics:
            score = metrics["performance_score"]
            score_val = int(score * 100) if isinstance(score, (int, float)) else "N/A"
            lines.append(f"- **Lighthouse Performance Score**: {score_val}/100")

        if "pagePerformanceIndex" in metrics:
            ppi = metrics["pagePerformanceIndex"]
            problematic = metrics.get("is_problematic_page", False)
            status = "⚠️ (ниже целевого)" if problematic else "✅"
            lines.append(f"- **Page Performance Index**: {ppi} {status}")
        lines.append("")

        # Сетевые и CWV метрики
        core_metrics = ["ttfb", "lcp", "fcp", "tbt", "cls", "inp"]
        network_metrics = ["dnsResolveTime", "connectTime"]

        for key in network_metrics + core_metrics:
            if key in metrics:
                val = metrics[key]
                explanation = explain_metric_value(val, key)
                rating_icon, rating_text = _get_metric_rating(val, key)

                label = {
                    "dnsResolveTime": "DNS Resolve Time",
                    "connectTime": "TCP Connect Time",
                    "ttfb": "TTFB",
                    "lcp": "LCP",
                    "fcp": "FCP",
                    "tbt": "TBT",
                    "cls": "CLS",
                    "inp": "INP"
                }[key]

                unit = " мс" if key != "cls" else ""
                lines.append(f"- **{label}**: {explanation}{unit} → {rating_icon} {rating_text}")

        lines.append("")

        # Метрики плеера
        if step_name == "film_page":
            lines.append("#### 🎞️ Метрики видеоплеера")
            player_metrics = ["playerInitTime", "videoStartTime", "rebufferCount", "rebufferDuration", "popupAppearTime"]
            for key in player_metrics:
                if key in metrics:
                    val = metrics[key]
                    explanation = explain_metric_value(val, key)
                    rating_icon, rating_text = _get_metric_rating(val, key)

                    label = {
                        "playerInitTime": "Инициализация плеера",
                        "videoStartTime": "До первого кадра",
                        "rebufferCount": "Буферизации (кол-во)",
                        "rebufferDuration": "Буферизация (длительность)",
                        "popupAppearTime": "Появление попапа"
                    }[key]

                    unit = " мс" if key in ("playerInitTime", "videoStartTime", "rebufferDuration", "popupAppearTime") else ""
                    if key == "popupAppearTime":
                        # Для попапа — только пояснение, без оценки
                        lines.append(f"- **{label}**: {explanation}{unit}")
                    else:
                        lines.append(f"- **{label}**: {explanation}{unit} → {rating_icon} {rating_text}")

            for key in ["popupAvailable", "popupClickSuccess"]:
                if key in metrics:
                    status = "✅ Да" if metrics[key] else "❌ Нет"
                    label = "Попап доступен" if key == "popupAvailable" else "Клик успешен"
                    lines.append(f"- **{label}**: {status}")
            lines.append("")

        # Метрики оплаты
        if step_name == "pay_page":
            lines.append("#### 💳 Метрики оплаты")
            if "iframeCpLoadTime" in metrics:
                val = metrics["iframeCpLoadTime"]
                explanation = f"{val} мс"
                rating_icon, rating_text = _get_metric_rating(val, "iframeCpLoadTime")
                lines.append(f"- **Загрузка iframe CloudPayments**: {explanation} → {rating_icon} {rating_text}")

            for key in ["buttonsCpAvailable", "buttonsClickSuccess"]:
                if key in metrics:
                    status = "✅ Да" if metrics[key] else "❌ Нет"
                    label = "Кнопки доступны" if key == "buttonsCpAvailable" else "Клик успешен"
                    lines.append(f"- **{label}**: {status}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
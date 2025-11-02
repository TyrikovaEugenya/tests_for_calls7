# === Основные URL ===
BASE_URL = "https://calls7.com"

CHROMIUM_PATH = "/home/eugene/.cache/ms-playwright/chromium-1187/chrome-linux/chrome"

SELECTORS = {
    "film_card": "a[href*='/chernyy-zamok/']",
    "play_button": ".plyr__control--overlaid",
    "video_element": ".plyr--video",
    "popup": "#dcoverlay",
    "popup_cta": "#dcoverlay a.dialog",
    "payment_iframe": "iframe[src*='cloudpayments']",
    "pay_button_in_iframe": "#cta-button",
    "pay_button_bank_card": "button[data-test='cardpay-page-button']",
    "pay_form_bank_card": "input[automation-id='tui-input-card-group__card']",
}

# === Метрики и пороги ===
TARGET_PAGE_PERFORMANCE_INDEX = 70  # если ниже — страница "проблемная"

# Веса для pagePerformanceIndex
METRIC_WEIGHTS = {
    "lcp": 0.25,
    "fid": 0.15,
    "cls": 0.15,
    "tbt": 0.25,
    "ttfb": 0.20,
}

# === Сетевые профили ===
THROTTLING_PROFILES = {
    "No throttling": None,
    "Slow 4G": {
        "download": 1.5 * 1024 * 1024,   # 1.5 Mbps
        "upload": 750 * 1024,            # 750 Kbps
        "latency": 150,                  # ms
    }
}

# === Геолокации (пример) ===
GEO_LOCATIONS = {
    "Moscow": {"latitude": 55.75, "longitude": 37.62},
    "Yekaterinburg": {"latitude": 56.85, "longitude": 60.61},
    "Novosibirsk": {"latitude": 55.01, "longitude": 82.93},
}

# === Устройства ===
DEVICES = {
    "desktop": {"width": 1920, "height": 1080, "is_mobile": False},
    "mobile": {"width": 390, "height": 844, "is_mobile": True},  # iPhone 12
}

# === Отчёт ===
REPORT_OUTPUT = "report.json"
ENRICHED_REPORT_OUTPUT = "enriched_report.json"

# === Рассчет по формуле ===
def calculate_page_performance_index(
    lcp: float = None,
    fid: float = None,
    cls: float = None,
    tbt: float = None,
    ttfb: float = None,
    target_weights: dict = METRIC_WEIGHTS
) -> float:
    """
    Рассчитывает pagePerformanceIndex от 0 до 100.
    Все входные метрики — в миллисекундах (кроме CLS — безразмерный).
    None означает "метрика не измерена" → исключается из расчёта.
    """
    # Пороги: (good, poor) в мс (CLS — в долях)
    thresholds = {
        "lcp": (1250, 4000),
        "fid": (100, 300),
        "cls": (0.1, 0.25),
        "tbt": (200, 600),
        "ttfb": (200, 600)
    }

    def score(value, good, poor):
        if value is None or value <= 0:
            return None
        if value <= good:
            return 100.0
        if value >= poor:
            return 0.0
        return 100.0 - (value - good) * 100.0 / (poor - good)

    raw_scores = {
        "lcp": score(lcp, *thresholds["lcp"]) if lcp is not None else None,
        "fid": score(fid, *thresholds["fid"]) if fid is not None else None,
        "cls": score(cls, *thresholds["cls"]) if cls is not None else None,
        "tbt": score(tbt, *thresholds["tbt"]) if tbt is not None else None,
        "ttfb": score(ttfb, *thresholds["ttfb"]) if ttfb is not None else None,
    }

    # Убираем None-значения
    available_scores = {k: v for k, v in raw_scores.items() if v is not None}

    if not available_scores:
        return 100.0  # или raise ValueError?

    # Базовые веса
    if target_weights is None:
        target_weights = {
            "lcp": 0.25,
            "fid": 0.15,
            "cls": 0.15,
            "tbt": 0.25,
            "ttfb": 0.20
        }

    # Фильтруем веса по доступным метрикам
    active_weights = {k: v for k, v in target_weights.items() if k in available_scores}
    total_weight = sum(active_weights.values())

    if total_weight == 0:
        return 100.0

    # Нормализуем веса
    normalized_weights = {k: v / total_weight for k, v in active_weights.items()}

    index = sum(
        normalized_weights[k] * available_scores[k]
        for k in available_scores
    )

    return round(index, 1)
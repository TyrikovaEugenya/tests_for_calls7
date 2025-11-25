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
    "pay_form_bank_card": "tui-input-card-group[data-test='input-card-groupped']", # button[data-test=cardpay-button]
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

METRIC_THRESHOLDS = {
    "lcp": (2500, 4000),
    "fcp": (1800, 3000),
    "tbt": (200, 600),
    "ttfb": (600, 1000),
    "inp": (200, 500),
    "videoStartTime": (3000, 10000),
    "iframeCpLoadTime": (2000, 4000),
}

def grade_metric(value_ms: float, metric_name: str) -> str:
    thresholds = {
        "videoStartTime": {"good": 3000, "ok": 6000, "poor": 15000},
        "playerInitTime": {"good": 1000, "ok": 2000, "poor": 4000},
        "popupAppearTime": {"good": 5000, "ok": 10000, "poor": 20000},
        "iframeCpLoadTime": {"good": 2000, "ok": 4000, "poor": 8000},
        
        "main_page_load": {"good": 1500, "ok": 3000, "poor": 5000},
        "film_cards_load": {"good": 2000, "ok": 4000, "poor": 8000},
        
        # Страница фильма
        "film_page_load": {"good": 2000, "ok": 4000, "poor": 8000},
        "player_init": {"good": 1000, "ok": 2000, "poor": 4000},
        "player_ready": {"good": 2000, "ok": 4000, "poor": 8000},  # loadPlayer finished
        "video_first_frame_A": {"good": 3000, "ok": 6000, "poor": 15000},  # заставка
        "video_first_frame_B": {"good": 2000, "ok": 4000, "poor": 10000},  # без заставки
        
        # Попап блокировки
        "lock_popup_appear": {"good": 3000, "ok": 6000, "poor": 12000},
        
        # Оплата
        "payment_iframe_load": {"good": 2000, "ok": 4000, "poor": 8000},
        "payment_form_card": {"good": 1500, "ok": 3000, "poor": 6000},
        "payment_form_tpay": {"good": 1500, "ok": 3000, "poor": 6000},
        "payment_form_sbp": {"good": 2000, "ok": 4000, "poor": 8000},
        
        # Повторные загрузки
        "player_reload": {"good": 2000, "ok": 4000, "poor": 8000},
        "video_reload_A": {"good": 4000, "ok": 8000, "poor": 20000},
        "video_reload_B": {"good": 3000, "ok": 6000, "poor": 12000},
    }.get(metric_name, {"good": 1000, "ok": 3000, "poor": 10000})
    
    if value_ms <= thresholds["good"]:
        return "отлично"
    elif value_ms <= thresholds["ok"]:
        return "хорошо"
    elif value_ms <= thresholds["poor"]:
        return "удовлетворительно"
    else:
        return "плохо"

DEVICES = ["Desktop", "Mobile"]
THROTTLING_MODES = ["No_throttling", "Slow_4G"]
GEO_LOCATIONS = ["Moscow", "SPb", "Kazan", "Novosibirsk", "Yekaterinburg"]
BROWSERS = ["chromium", "firefox", "webkit"]

# === Отчёт ===
REPORT_OUTPUT = "report.json"

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
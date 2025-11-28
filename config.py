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
    "pay_button_sbp": "button[data-test='sbppay-button']",
    "pay_button_tpay": "[data-testid='tpay-form'], .tpay-input",
    "pay_form_bank_card": "tui-input-card-group[data-test='input-card-groupped']",
    "pay_form_sbp": "img.qr-box",
    "close_button": "img[data-test='close-button']"
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
    "videoStartTime": (5000, 15000),
    "popupAppearTime": (30000, 90000),     
    "iframeCpLoadTime": (1000, 5000),     
    "playerInitTime": (1000, 5000),      
    "lcp": (2500, 4000),
    "ttfb": (800, 1200),                 
    "fcp": (1000, 3000),                  
    "cls": (0.1, 0.25),  
    "tbt": (200, 600),                    
    "performance_score": (0.8, 0.6),      
    "pagePerformanceIndex": (85, 70),     
    "rebufferCount": (0, 3),              
    "rebufferDuration": (0, 5000),
}

def grade_metric(value: float, metric_name: str) -> str:
    """Оценивает метрику по порогам"""
    if metric_name not in METRIC_THRESHOLDS:
        return "неизвестно"
        
    good, poor = METRIC_THRESHOLDS[metric_name]
    
    # Для метрик, где больше = лучше (performance_score, pagePerformanceIndex)
    if metric_name in ["performance_score", "pagePerformanceIndex"]:
        if value >= good:
            return "отлично"
        elif value >= poor:
            return "хорошо"
        else:
            return "плохо"
    # Для метрик, где меньше = лучше (все остальные)
    else:
        if value <= good:
            return "отлично"
        elif value <= poor:
            return "удовлетворительно"
        else:
            return "плохо"

DEVICES = ["Desktop", "Mobile"]
THROTTLING_MODES = ["No_throttling", "Slow_4G"]
GEO_LOCATIONS = ["Moscow", "SPb", "Kazan", "Novosibirsk", "Yekaterinburg"]
BROWSERS = ["chromium", "firefox", "webkit"]
PAY_METHODS = ["card", 'sbp']

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
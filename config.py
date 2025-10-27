# === Основные URL ===
BASE_URL = "https://calls7.com"
FILM_EXAMPLE_URL = "https://calls7.com/movie/370"  # актуальный рабочий URL

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

# === Рассчет по формуле ===
def calculate_page_performance_index(lcp, fid, cls, tbt, ttfb):
    """Рассчитывает сводный индекс производительности от 0 до 100"""
    def norm(val, good, poor, reverse=False):
        if reverse:  # чем меньше, тем лучше (например, CLS)
            if val <= good:
                return 100
            elif val >= poor:
                return 0
            return 100 - (val - good) * 100 / (poor - good)
        else:  # чем больше, тем хуже (например, LCP)
            if val <= good:
                return 100
            elif val >= poor:
                return 0
            return 100 - (val - good) * 100 / (poor - good)

    lcp_score = norm(lcp, 1250, 4000)
    fid_score = norm(fid, 100, 300)
    cls_score = norm(cls, 0.1, 0.25, reverse=True)
    tbt_score = norm(tbt, 200, 600)
    ttfb_score = norm(ttfb, 200, 600)

    if lcp == 0:
        weights = {"lcp": 0, "fid": 0.2, "cls": 0.2, "tbt": 0.4, "ttfb": 0.2}
    else:
        weights = {"lcp": 0.25, "fid": 0.15, "cls": 0.15, "tbt": 0.25, "ttfb": 0.20}
        
    index = (
        weights["lcp"] * lcp_score +
        weights["fid"] * fid_score +
        weights["cls"] * cls_score +
        weights["tbt"] * tbt_score +
        weights["ttfb"] * ttfb_score
    )
    return round(index, 1)
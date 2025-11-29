"""
CONFTEST.PY - КОНФИГУРАЦИЯ PYTEST ДЛЯ АВТОМАТИЗИРОВАННОГО ТЕСТИРОВАНИЯ

Этот файл содержит фикстуры и хуки для настройки тестового окружения,
параметризации тестов и управления браузером через Playwright.
"""

import pytest
import re
from playwright.sync_api import sync_playwright, Playwright
import allure
import time
from collections import Counter, defaultdict, deque
import statistics
from typing import Dict, Any, Tuple, List, Optional
import json
from pathlib import Path
import requests
import config
from config import (
    DEVICES, THROTTLING_MODES, GEO_LOCATIONS, BROWSERS, PAY_METHODS, CHROMIUM_PATH
)
import aggregator

# CHROMIUM_PATH = "/opt/chromium/chrome"

# === КОНФИГУРАЦИЯ ГЕОЛОКАЦИЙ ===
geo_map: Dict[str, Tuple[str, str]] = {
    "Moscow": ("ru-RU", "Europe/Moscow"),
    "SPb": ("ru-RU", "Europe/Moscow"),
    "Kazan": ("ru-RU", "Europe/Moscow"),
    "Novosibirsk": ("ru-RU", "Asia/Novosibirsk"),
    "Yekaterinburg": ("ru-RU", "Asia/Yekaterinburg"),
}
"""Соответствие городов настройкам локали и часового пояса"""

def pytest_addoption(parser: pytest.Parser) -> None:
    """
    Добавляет пользовательские опции командной строки для pytest.
    
    Аргументы:
        parser: парсер pytest для добавления опций
    """
    parser.addoption(
        '--film-url',
        action='store',
        default="https://calls7.com/movie/370",
        help="URL фильма для тестирования (по умолчанию: демо фильм)"
    )
    parser.addoption(
        "--film-list",
        action="store",
        default=None,
        help="Путь к films.json или films.txt со списком URL"
    )
    parser.addoption(
        "--film-limit",
        action="store",
        type=int,
        default=None,
        help="Ограничение количества URL из списка для тестирования"
    )
    parser.addoption(
        '--device',
        action='store',
        default="Desktop",
        choices=DEVICES,
        help="Тип устройства для тестирования"
    )
    parser.addoption(
        "--throttling",
        action="store",
        default="No_throttling",
        choices=THROTTLING_MODES,
        help="Режим ограничения скорости сети"
    )
    parser.addoption(
        "--geo",
        action="store",
        default="Moscow",
        choices=GEO_LOCATIONS,
        help="Геолокация для тестирования"
    )
    parser.addoption(
        "--browser",
        action="store",
        default="chromium",
        choices=BROWSERS,
        help="Браузер для тестирования"
    )
    parser.addoption(
        "--pay-method",
        action="store",
        default="card",
        choices=PAY_METHODS,
        help="Метод оплаты для тестирования"    
    )

# === ФИКСТУРЫ ДЛЯ ПАРАМЕТРОВ ТЕСТИРОВАНИЯ ===
@pytest.fixture()
def get_film_url(request: pytest.FixtureRequest) -> str:
    """Возвращает URL фильма для тестирования."""
    return request.config.getoption("--film-url")

@pytest.fixture
def device(request: pytest.FixtureRequest) -> str:
    """Возвращает тип устройства для тестирования."""
    return request.config.getoption("--device")

@pytest.fixture
def throttling(request: pytest.FixtureRequest) -> str:
    """Возвращает режим ограничения скорости сети."""
    return request.config.getoption("--throttling")

@pytest.fixture
def geo(request: pytest.FixtureRequest) -> str:
    """Возвращает геолокацию для тестирования."""
    return request.config.getoption("--geo")

@pytest.fixture(scope="session")
def browser_type(request: pytest.FixtureRequest) -> str:
    """Возвращает тип браузера для тестирования."""
    return request.config.getoption("--browser")

@pytest.fixture
def film_list(request: pytest.FixtureRequest) -> str:
    """Возвращает путь к файлу со списком фильмов."""
    return request.config.getoption("--film-list")

@pytest.fixture
def film_limit(request: pytest.FixtureRequest) -> str:
    """Возвращает ограничение количества фильмов для тестирования."""
    return request.config.getoption("--film-limit")

@pytest.fixture
def pay_method(request: pytest.FixtureRequest) -> str:
    """Возвращает метод оплаты для тестирования."""
    return request.config.getoption("--pay-method")

# === УТИЛИТЫ ДЛЯ РАБОТЫ С ФАЙЛАМИ ===
def load_film_urls(film_list_path: str, limit: Optional[int] = None) -> List[str]:
    """
    Загружает список URL фильмов из JSON или TXT файла.
    
    Аргументы:
        film_list_path: путь к файлу со списком URL
        limit: ограничение количества URL (опционально)
        
    Возвращает:
        List[str]: список URL фильмов
        
    Исключения:
        FileNotFoundError: если файл не существует
        ValueError: если формат файла не поддерживается
    """
    path = Path(film_list_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {film_list_path}")

    if path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            urls = data.get("urls", data) if isinstance(data, dict) else data
    elif path.suffix == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        raise ValueError(f"Поддерживаются только .json и .txt, получено: {path.suffix}")
    
    if limit is not None:
        urls = urls[:limit]

    return urls

# === ДИНАМИЧЕСКАЯ ПАРАМЕТРИЗАЦИЯ ТЕСТОВ ===
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """
    Автоматически параметризует тесты на основе опций командной строки.
    
    Логика:
    1. Если указаны CLI опции - использует их значения
    2. Если CLI опции не указаны - использует полную параметризацию
    3. Обрабатывает как одиночные URL, так и списки фильмов
    """
    device = metafunc.config.getoption("--device")
    throttling = metafunc.config.getoption("--throttling")
    geo = metafunc.config.getoption("--geo")
    browser = metafunc.config.getoption("--browser")
    payment_method = metafunc.config.getoption("--pay-method")
    # Проверяем, используются ли CLI опции
    use_cli = any([device, throttling, geo, browser, payment_method])
    # Параметризация если не используются CLI опции
    if not use_cli:
        if "device" in metafunc.fixturenames:
            metafunc.parametrize("device", DEVICES, scope="function")
        if "throttling" in metafunc.fixturenames:
            metafunc.parametrize("throttling", THROTTLING_MODES, scope="function")
        if "geo" in metafunc.fixturenames:
            metafunc.parametrize("geo", GEO_LOCATIONS, scope="function")
        if "browser_type" in metafunc.fixturenames:
            metafunc.parametrize("browser_type", BROWSERS, scope="session")
        if "pay_method" in metafunc.fixturenames:
            metafunc.parametrize("pay_method", PAY_METHODS, scope="function")

    # Обработка URL фильмов
    film_url = metafunc.config.getoption("--film-url")
    film_list = metafunc.config.getoption("--film-list")
    film_limit = metafunc.config.getoption("--film-limit")
    
    if "get_film_url" in metafunc.fixturenames:
        if film_list:
            urls = load_film_urls(film_list, limit=film_limit)
            metafunc.parametrize(
                "get_film_url",
                urls,
                scope="function",
                ids=lambda x: x.split("/")[-2]  # человекочитаемые ID
            )
        elif film_url:
            metafunc.parametrize("get_film_url", [film_url], scope="function")
        else:
            # Нет входных данных — один пропущенный тест
            metafunc.parametrize("get_film_url", [None], scope="function")


# === ФИКСТУРЫ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ ===
@pytest.fixture(scope="session")
def playwright_instance():
    """Создает экземпляр Playwright для сессии тестирования."""
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser_instance(playwright_instance, browser_type):
    """
    Запускает браузер указанного типа для сессии тестирования.
    
    Аргументы:
        playwright_instance: экземпляр Playwright
        browser_type: тип браузера (chromium/firefox/webkit)
        
    Возвращает:
        запущенный экземпляр браузера
    """
    p = playwright_instance
    if browser_type == "chromium":
            browser = p.chromium.launch(
                headless=True,
                executable_path=CHROMIUM_PATH,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage"
                ],
            )
    elif browser_type == "firefox":
        browser = p.firefox.launch(headless=True)
    elif browser_type == "webkit":
        browser = p.webkit.launch(headless=True)
    else:
        raise ValueError(f"Неподдерживаемый браузер: {browser}")
    yield browser
    browser.close()
    
# === ФИКСТУРА СТРАНИЦЫ С НАСТРОЙКОЙ ОКРУЖЕНИЯ ===
@pytest.fixture(scope='function')
def page(browser_type, device, geo, throttling, browser_instance, playwright_instance):
    """
    Создает новую страницу с настройками окружения для каждого теста.
    
    Настройки включают:
    - Размер viewport (Desktop/Mobile)
    - Локаль и часовой пояс
    - User Agent и разрешения
    - Защита от обнаружения автоматизации
    - Мониторинг консоли браузера
    - Ограничение скорости сети (при необходимости)
    """
    p = playwright_instance
    context_args = {}
        
    if device == "Mobile":
        p_config = dict(p.devices["Pixel 5"])
        if browser_type != "chromium":
            # Убираем mobile-специфичные настройки для не-Chromium браузеров
            p_config.pop("is_mobile", None)
            p_config.pop("has_touch", None)
        context_args = p_config
    else:
        context_args["viewport"] = {"width": 1920, "height": 1080}

    # Настройка геолокации
    locale, timezone = geo_map.get(geo, ("ru-RU", "UTC"))
    context_args.update({
        "locale": locale,
        "timezone_id": timezone,
    })

    # Общие настройки контекста
    context_args.update({
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "permissions": ["geolocation", "notifications"],
        "java_script_enabled": True,
    })
        
    try:
        context = browser_instance.new_context(**context_args)
    except Exception as e:
        pytest.fail(f"Не удалось создать контекст браузера: {e}")
    # Скрипт для защиты от обнаружения и мониторинга
    context.add_init_script("""
            // Скрытие navigator.webdriver для обхода защиты
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            // Мониторинг консоли
            (function() {
                const originalConsole = {
                    log: console.log,
                    info: console.info,
                    debug: console.debug,
                    warn: console.warn,
                    error: console.error
                };
            
                function interceptConsole(method, args) {
                    try {
                        const message = args.map(arg => {
                            if (arg === null) return 'null';
                            if (arg === undefined) return 'undefined';
                            if (typeof arg === 'object') {
                                try {
                                    return JSON.stringify(arg);
                                } catch(e) {
                                    return String(arg);
                                }
                            }
                            return String(arg);
                        }).join(' ');
                        
                        // Сохраняем сообщения
                        if (!window.__consoleMessages) {
                            window.__consoleMessages = [];
                        }
                        window.__consoleMessages.push({
                            type: method,
                            message: message,
                            timestamp: Date.now()
                        });
                        
                        // Отмечаем готовность плеера
                        if (message.includes('loadPlayer finished')) {
                            window.__playerReadyDetected = true;
                            window.__playerReadyTimestamp = Date.now();
                            console.log('[MONITOR] 🎯 Player ready detected!');
                        }
                        
                        // Вызываем оригинальный метод
                        originalConsole[method].apply(console, args);
                    } catch(e) {
                        originalConsole[method].apply(console, args);
                    }
                }
            
                // Перехватываем все методы console
                ['log', 'info', 'debug', 'warn', 'error'].forEach(method => {
                    console[method] = function(...args) {
                        interceptConsole(method, args);
                    };
                });
            })();
        """)
    # Очистка cookies перед тестом
    context.clear_cookies()
    page = context.new_page()
    
    # Настройки специфичные для Chromium
    if browser_type == "chromium":
        client = context.new_cdp_session(page)
        client.send("Runtime.enable")
        client.send("Log.enable")
        
        def on_log_entry(params):
            """Обработчик логов Chrome DevTools Protocol."""
            text = params.get("entry", {}).get("text", "")
            args = params.get("entry", {}).get("args", [])
            # Если текст пустой, пытаемся извлечь из args
            if not text and args:
                text = " ".join(str(arg.get("value", "")) for arg in args)
                
            # Детектор готовности плеера через CDP
            if "[Dc] loadPlayer finished" in text:
                page.evaluate("""
                    window.__playerReadyDetected = true;
                    window.__playerReadyTimestamp = Date.now();
                    window.__cdpDetected = true;
                """)
                print(f"[PLAYER] ✅ [Dc] loadPlayer finished: {text}")
                
        client.on("Log.entryAdded", on_log_entry)
        time.sleep(0.1) # Даем время для инициализации
        
        # Применение ограничения скорости сети
        if throttling == "Slow_4G":
            try:
                client.send("Network.enable")
                client.send("Network.emulateNetworkConditions", {
                    "offline": False,
                    "latency": 400,
                    "downloadThroughput": 700 * 1024,
                    "uploadThroughput": 700 * 1024,
                    "connectionType": "cellular4g"
                })
                # Даём сети примениться
                time.sleep(0.5)
            except Exception as e:
                print(f"[WARN] Не удалось применить троттлинг: {e}")

                
    yield page
    context.close()
    
# === ХУКИ ДЛЯ ОБРАБОТКИ РЕЗУЛЬТАТОВ ТЕСТОВ ===
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """
    Обрабатывает результаты выполнения тестов.
    
    Функциональность:
    - Создает скриншоты при падении тестов
    - Сохраняет данные отчетов в агрегатор
    """
    outcome = yield
    rep = outcome.get_result()
    
    # Скриншот при падении
    if rep.when == "call" and rep.failed:
        page = item.funcargs.get("page")
        if page:
            try:
                allure.attach(
                    page.screenshot(),
                    name="screenshot",
                    attachment_type=allure.attachment_type.PNG
                )
            except Exception as e:
                print(f"[WARN] Скриншот не сохранён: {e}")
    
    # Сохранение report даже если тест упал
    if rep.when == "call":
        if hasattr(item, "_report_data") and isinstance(item._report_data, dict):
            test_name = item.nodeid.split("::")[-1].split("[")[0]
            _aggregator.add_report(test_name, item._report_data)
            
    

# Глобальный агрегатор (на сессию)
_aggregator = aggregator.MultiTestRunAggregator()


@pytest.fixture(scope="session")
def aggregate_run_summary():
    """Возвращает агрегированный отчёт после всех тестов."""
    yield _aggregator

# Переменные для подсчета количества пройденных тестов
_test_run_counts = defaultdict(int)
_test_total_expected = {}

def pytest_collection_finish(session):
    """Считаем, сколько раз будет вызван каждый тест (из-за параметризации)."""
    global _test_total_expected
    for item in session.items:
        test_name = item.originalname or item.name.split("[")[0]
        _test_total_expected[test_name] = _test_total_expected.get(test_name, 0) + 1
        
_start_time = None

def pytest_sessionstart(session):
    global _start_time
    _start_time = time.time()
    
def aggregate_reports() -> dict:
    """Собирает сводку и сохраняет в environment.properties для Allure."""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return

    # Собираем ВСЕ JSON-отчёты
    reports = []
    for report_file in reports_dir.glob("report_*.json"):
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                reports.append(json.load(f))
        except Exception as e:
            print(f"[WARN] Не удалось загрузить {report_file}: {e}")

    if not reports:
        return

    total = len(reports)
    problematic = sum(1 for r in reports if r.get("is_problematic_flow"))
    failed = sum(1 for r in reports if r.get("error"))

    # Оценка качества: чем меньше проблем — тем выше оценка
    quality_score = max(0, int((1 - problematic / total) * 100))

    # Счётчик ключевых проблем
    video_slow = 0
    lcp_bad = 0
    iframe_slow = 0
    for r in reports:
        steps = r.get("steps", {})
        # film_page.videoStartTime > 15 сек
        vst = steps.get("film_page", {}).get("videoStartTime")
        if vst and vst > 15000:
            video_slow += 1
        # main_page.LCP > 2500 мс
        lcp = steps.get("main_page", {}).get("lcp")
        if lcp and lcp > 2500:
            lcp_bad += 1
        # pay_page.iframeCpLoadTime > 3 сек
        iframe = steps.get("pay_page", {}).get("iframeCpLoadTime")
        if iframe and iframe > 3000:
            iframe_slow += 1

    # Формируем environment.properties
    env = {
        "Start time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_start_time)),
        "End time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "Duration": f"{(time.time() - _start_time):.1f} sec",
        "Pages": f"{total} / 19975",
        "Problematic pages": f"{problematic} ({problematic/total*100:.1f}%)",
        "Failed by errors": f"{failed} ({failed/total*100:.1f}%)",
        "Quality score": f"{quality_score}%",
        # Ключевые проблемы — кратко, в одну строку
        "film_page.videoStartTime > 15 sec": f"{video_slow} ({video_slow/total*100:.1f}%)",
        "main_page.LCP > 2500 ms": f"{lcp_bad} ({lcp_bad/total*100:.1f}%)",
        "pay_page.iframeCpLoadTime > 3 sec": f"{iframe_slow} ({iframe_slow/total*100:.1f}%)",
    }
    return env
    

def pytest_sessionfinish(session, exitstatus):
    
    # Сохраняем в environment.properties для Allure
    env_path = Path("allure-results")
    env_path.mkdir(exist_ok=True)
        
    env = aggregate_reports()
    with open(env_path / "environment.properties", "w", encoding="utf-8") as f:
        for key, value in env.items():
            # Экранируем знаки = и \ в значениях (Allure требует)
            value = str(value).replace("\\", "\\\\").replace("=", "\\=")
            f.write(f"{key} = {value}\n")
            
    print(f"\n✅ Environment для Allure обновлён: {env_path}")


def pytest_runtest_logfinish(nodeid, location):
    """Вызывается после КАЖДОГО параметризованного запуска теста."""
    global _test_run_counts

    test_name = nodeid.split("::")[-1].split("[")[0]
    _test_run_counts[test_name] += 1

    # Если все запуски теста завершены — сохраняем его агрегат
    if _test_run_counts[test_name] == _test_total_expected.get(test_name, 1):
        _aggregator.save_summary(test_name)
        
    _aggregator.save_clustered_summaries(test_name, ["device", "throttling"])
    _aggregator.save_clustered_summaries(test_name, ["geo", "browser_type"])
    _aggregator.save_clustered_summaries(test_name, ["device"])

def send_telegram_report(summary_text: str, chat_id: str, bot_token: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": f"🎬 Тесты завершены\n\n{summary_text}",
        "parse_mode": "Markdown"
    }
    requests.post(url, data=data)
import pytest
import re
from playwright.sync_api import sync_playwright, Playwright
import allure
import time
from collections import defaultdict, deque
import statistics
from typing import Dict, Any
import json
from pathlib import Path
import requests

CHROMIUM_PATH = "/opt/chromium/chrome"

DEVICES = ["Desktop", "Mobile"]
THROTTLING_MODES = ["No_throttling", "Slow_4G"]
GEO_LOCATIONS = ["Moscow", "SPb", "Kazan", "Novosibirsk", "Yekaterinburg"]
BROWSERS = ["chromium", "firefox", "webkit"]


geo_map = {
    "Moscow": ("ru-RU", "Europe/Moscow"),
    "SPb": ("ru-RU", "Europe/Moscow"),
    "Kazan": ("ru-RU", "Europe/Moscow"),
    "Novosibirsk": ("ru-RU", "Asia/Novosibirsk"),
    "Yekaterinburg": ("ru-RU", "Asia/Yekaterinburg"),
}

def pytest_addoption(parser):
    parser.addoption(
        '--film_url',
        action='store',
        default="https://calls7.com/movie/370",
        help="Choose url for film which page you want to test"
    )
    parser.addoption(
        "--film_list",
        action="store",
        default=None,
        help="Путь к films.json или films.txt со списком URL"
    )
    parser.addoption(
        "--film_limit",
        action="store",
        type=int,
        default=None,
        help="Number of urls from list"
    )
    parser.addoption(
        '--device',
        action='store',
        default="Desktop",
        choices=DEVICES
    )
    parser.addoption(
        "--throttling",
        action="store",
        default="No_throttling",
        choices=THROTTLING_MODES
    )
    parser.addoption(
        "--geo",
        action="store",
        default="Moscow",
        choices=GEO_LOCATIONS
    )
    parser.addoption(
        "--browser",
        action="store",
        default="chromium",
        choices=BROWSERS
    )

    
@pytest.fixture()
def get_film_url(request):
    return request.config.getoption("--film_url")

@pytest.fixture
def device(request):
    return request.config.getoption("--device")

@pytest.fixture
def throttling(request):
    return request.config.getoption("--throttling")

@pytest.fixture
def geo(request):
    return request.config.getoption("--geo")

@pytest.fixture(scope="session")
def browser_type(request):
    return request.config.getoption("--browser")

@pytest.fixture
def film_list(request):
    return request.config.getoption("--film_list")

@pytest.fixture
def film_limit(request):
    return request.config.getoption("--film_limit")

def load_film_urls(film_list_path: str, limit: int = None) -> list:
    """Загружает список URL из JSON или TXT."""
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

def pytest_generate_tests(metafunc):
    """Автоматически параметризует тесты, если запрошены фикстуры."""
    device = metafunc.config.getoption("--device")
    throttling = metafunc.config.getoption("--throttling")
    geo = metafunc.config.getoption("--geo")
    browser = metafunc.config.getoption("--browser")
    use_cli = any([device, throttling, geo, browser])
    if not use_cli:
        if "device" in metafunc.fixturenames:
            metafunc.parametrize("device", DEVICES, scope="function")
        if "throttling" in metafunc.fixturenames:
            metafunc.parametrize("throttling", THROTTLING_MODES, scope="function")
        if "geo" in metafunc.fixturenames:
            metafunc.parametrize("geo", GEO_LOCATIONS, scope="function")
        if "browser_type" in metafunc.fixturenames:
            metafunc.parametrize("browser_type", BROWSERS, scope="session")
            
    film_url = metafunc.config.getoption("--film_url")
    film_list = metafunc.config.getoption("--film_list")
    film_limit = metafunc.config.getoption("--film_limit")
    
    if "get_film_url" in metafunc.fixturenames:
        if film_list:
            urls = load_film_urls(film_list, limit=film_limit)
            metafunc.parametrize(
                "get_film_url",
                urls,
                scope="function",
                ids=lambda x: x.split("/")[-2]  # человекочитаемые ID: kvest, chernyy-zamok
            )
        elif film_url:
            metafunc.parametrize("get_film_url", [film_url], scope="function")
        else:
            # Нет входных данных — один пропущенный тест
            metafunc.parametrize("get_film_url", [None], scope="function")


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser_instance(playwright_instance, browser_type):
    p = playwright_instance
    if browser_type == "chromium":
            browser = p.chromium.launch(
                headless=True,
                executable_path=CHROMIUM_PATH,
                args=[
                    "--no-sandbox",
                    #"--remote-debugging-port=9222",
                    "--disable-gpu",
                    "--disable-dev-shm-usage"
                ],
            )
    elif browser_type == "firefox":
        browser = p.firefox.launch(headless=True)
    elif browser_type == "webkit":
        browser = p.webkit.launch(headless=True)
    else:
        raise ValueError(f"Unsupported: {browser}")
    yield browser
    browser.close()

@pytest.fixture(scope='function')
def page(browser_type, device, geo, throttling, browser_instance, playwright_instance):
    p = playwright_instance
    context_args = {}
        
    if device == "Mobile":
        p_config = dict(p.devices["Pixel 5"])
        if browser_type != "chromium":
            p_config.pop("is_mobile", None)
            p_config.pop("has_touch", None)
        context_args = p_config
    else:
        context_args["viewport"] = {"width": 1920, "height": 1080}
            
        # ГЕО: локаль и часовой пояс
    locale, timezone = geo_map.get(geo, ("ru-RU", "UTC"))
    context_args.update({
        "locale": locale,
        "timezone_id": timezone,
    })

    context_args.update({
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "permissions": ["geolocation", "notifications"],
        "java_script_enabled": True,
    })
        
    context = browser_instance.new_context(**context_args)
    # скрываем navigator.webdriver
    context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
    context.clear_cookies()
    page = context.new_page()
        
    # троттлинг (только для Chromium) ===
    if throttling == "Slow_4G" and browser_type == "chromium":
        try:
            client = context.new_cdp_session(page)
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
    

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    
    # 1. Скриншот при падении
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
    
    # 2. Сохранение report — даже если тест упал
    if rep.when == "call":
        if hasattr(item, "_report_data") and isinstance(item._report_data, dict):
            test_name = item.nodeid.split("::")[-1].split("[")[0]
            _aggregator.add_report(test_name, item._report_data)
            

class MultiTestRunAggregator:
    def __init__(self):
        self.reports_by_test = defaultdict(list)
    
    def add_report(self, test_name: str, report: dict):
        self.reports_by_test[test_name].append(report)
    
    def get_summary(self, test_name: str) -> dict:
        reports = self.reports_by_test[test_name]
        if not reports:
            return {"error": f"No reports for {test_name}"}
        
        summary = {
            "test_name": test_name,
            "total_runs": len(reports),
            "problematic_runs": sum(1 for r in reports if r.get("is_problematic_flow", False)),
            "failed_runs": sum(1 for r in reports if r.get("error")),
            "steps": defaultdict(lambda: {"ppi": [], "metrics": defaultdict(list)}),
            "distribution": {
                "device": defaultdict(int),
                "throttling": defaultdict(int),
                "geo": defaultdict(int),
                "browser": defaultdict(int),
            },
            "film_urls": set(),
            "errors": defaultdict(list),
        }

        # Сбор данных
        for r in reports:
            # Распределение параметров
            summary["distribution"]["device"][r.get("device", "N/A")] += 1
            summary["distribution"]["throttling"][r.get("throttling", "N/A")] += 1
            summary["distribution"]["geo"][r.get("geoposition", "N/A")] += 1
            summary["distribution"]["browser"][r.get("browser_type", "N/A")] += 1
            summary["film_urls"].add(r.get("film_url", "").strip())
            
            error_msg = r.get("error")
            if error_msg:
                # Упрощаем сообщение: берём только тип и первые 50 символов
                simplified = re.sub(r"Call log:.*", "", error_msg).strip()
                simplified = re.sub(r"\s+", " ", simplified)[:100]
                summary["errors"][simplified].append(r)

            # Метрики по шагам
            for step_name, metrics in r.get("steps", {}).items():
                if not isinstance(metrics, dict):
                    continue
                ppi = metrics.get("pagePerformanceIndex")
                if ppi is not None:
                    summary["steps"][step_name]["ppi"].append(ppi)
                
                # Временные метрики (можно расширить)
                for metric in [
                    "videoStartTime",
                    "popupAppearTime",
                    "iframeCpLoadTime",
                    "playerInitTime",
                    "lcp",
                    "ttfb"
                ]:
                    val = metrics.get(metric)
                    if isinstance(val, (int, float)) and val > 0:
                        summary["steps"][step_name]["metrics"][metric].append(val)

        # Агрегация
        for step in summary["steps"].values():
            ppi_list = step["ppi"]
            if ppi_list:
                step["ppi_stats"] = {
                    "mean": round(statistics.mean(ppi_list), 1),
                    "median": round(statistics.median(ppi_list), 1),
                    "min": min(ppi_list),
                    "max": max(ppi_list),
                    "stdev": round(statistics.stdev(ppi_list), 1) if len(ppi_list) > 1 else 0.0,
                }
            for metric, values in step["metrics"].items():
                if values:
                    step["metrics"][metric] = {
                        "mean": round(statistics.mean(values), 1),
                        "median": round(statistics.median(values), 1),
                        "min": min(values),
                        "max": max(values),
                        "count": len(values),
                    }

        summary["film_urls"] = list(summary["film_urls"])
        return summary
    
    def save_summary(self, test_name: str):
        summary = self.get_summary(test_name)
        print(f"[DEBUG] save_summary({test_name}) → keys: {list(summary.keys())}")
        if "error" in summary:
            print(f"[INFO] Пропущен агрегат для '{test_name}': {summary['error']}")
            return
    
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        # Уникальные имена файлов
        safe_name = re.sub(r'[<>:"/\\|?*\s]', '_', test_name)[:30]
        json_path = reports_dir / f"RUN_SUMMARY_{safe_name}.json"
        md_path = reports_dir / f"RUN_SUMMARY_{safe_name}.md"
        
        # Сохраняем JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        # Сохраняем MD (аналогично предыдущей реализации)
        self._save_markdown(summary, md_path)

    def _save_markdown(self, summary: dict, path: Path):
        md_lines = []
        test_name = summary.get("test_name", "unknown")
        total = summary.get("total_runs", 0)
        problematic = summary.get("problematic_runs", 0)
        failed = summary["failed_runs"]
        
        md_lines.append(f"# 📊 Итог по тесту: `{test_name}`\n")
        md_lines.append(f"**Дата**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`")
        md_lines.append(f"**Всего запусков**: `{total}`")
        md_lines.append(f"**Проблемных (по метрикам)**: `{problematic}` (`{problematic/total*100:.1f}%`)")
        md_lines.append(f"**Упавших (по ошибкам)**: `{failed}` (`{failed/total*100:.1f}%`)")
        md_lines.append("")
        
        if summary["errors"]:
            md_lines.append("## 🚨 Критические ошибки")
            md_lines.append("| Ошибка | Частота | Пример URL |")
            md_lines.append("|--------|---------|------------|")
            for error_msg, reports in sorted(summary["errors"].items(), key=lambda x: len(x[1]), reverse=True):
                count = len(reports)
                pct = count / total * 100
                example_url = reports[0].get("film_url", "N/A").split("?")[0]
                md_lines.append(f"| `{error_msg}` | `{count}` (`{pct:.1f}%`) | `{example_url}` |")
            md_lines.append("")

        # Фильмы
        films = summary["film_urls"]
        md_lines.append("### 🎬 Протестированные фильмы")
        for url in films[:5]:
            md_lines.append(f"- `{url}`")
        if len(films) > 5:
            md_lines.append(f"- ... и ещё {len(films) - 5}")
        md_lines.append("")

        # Сводка по шагам
        md_lines.append("### 📈 Производительность по шагам")
        md_lines.append("| Шаг | Средний PPI | Вариация (σ) | Время загрузки (среднее) |")
        md_lines.append("|-----|-------------|--------------|--------------------------|")

        for step_name, data in summary["steps"].items():
            ppi_stats = data.get("ppi_stats", {})
            ppi_mean = ppi_stats.get("mean", "—")
            ppi_stdev = ppi_stats.get("stdev", "—")
            
            # Берём основную временную метрику для шага
            time_metric = ""
            if step_name == "main_page":
                time_metric = f"LCP: {data['metrics'].get('lcp', {}).get('mean', '—')} мс"
            elif step_name == "film_page":
                vs = data['metrics'].get('videoStartTime', {}).get('mean', '—')
                time_metric = f"Video Start: {vs} мс"
            elif step_name == "pay_page":
                iframe = data['metrics'].get('iframeCpLoadTime', {}).get('mean', '—')
                time_metric = f"IFrame Load: {iframe} мс"
            
            md_lines.append(f"| `{step_name}` | `{ppi_mean}` | `{ppi_stdev}` | `{time_metric}` |")
        md_lines.append("")

        # Распределение
        md_lines.append("### 🌍 Распределение по параметрам")
        for dim, counts in summary["distribution"].items():
            md_lines.append(f"#### `{dim}`")
            md_lines.append("| Значение | Количество |")
            md_lines.append("|----------|------------|")
            for val, cnt in sorted(counts.items()):
                md_lines.append(f"| `{val}` | `{cnt}` |")
            md_lines.append("")

        # Проблемные показатели (если есть)
        problematic_metrics = []
        for step_name, data in summary["steps"].items():
            ppi_stats = data.get("ppi_stats", {})
            if ppi_stats.get("mean", 100) < 85:
                problematic_metrics.append(f"- `{step_name}.pagePerformanceIndex`: {ppi_stats['mean']:.1f} < 85")
            for metric, stats in data.get("metrics", {}).items():
                if isinstance(stats, dict):
                    mean = stats.get("mean", 0)
                    if metric == "videoStartTime" and mean > 15000:
                        problematic_metrics.append(f"- `{step_name}.{metric}`: {mean:.0f} мс > 15 сек")
                    if metric == "iframeCpLoadTime" and mean > 3000:
                        problematic_metrics.append(f"- `{step_name}.{metric}`: {mean:.0f} мс > 3 сек")

        if problematic_metrics:
            md_lines.append("### ⚠️ Выявленные проблемы")
            md_lines.extend(problematic_metrics)
            md_lines.append("")
        else:
            md_lines.append("### ✅ Проблем не выявлено\n")
            
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

# Глобальный агрегатор (на сессию)
_aggregator = MultiTestRunAggregator()


@pytest.fixture(scope="session")
def aggregate_run_summary():
    """Возвращает агрегированный отчёт после всех тестов."""
    yield _aggregator


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
    
def pytest_sessionfinish(session, exitstatus):
    duration = time.time() - _start_time
    start_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_start_time))
    end_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    # Сохраняем в environment.properties для Allure
    with open("allure-results/environment.properties", "a") as f:
        f.write(f"Start {start_iso}\n")
        f.write(f"End {end_iso}\n")
        f.write(f"Duration={duration:.1f} sec\n")


def pytest_runtest_logfinish(nodeid, location):
    """Вызывается после КАЖДОГО параметризованного запуска теста."""
    global _test_run_counts

    test_name = nodeid.split("::")[-1].split("[")[0]
    _test_run_counts[test_name] += 1

    # Если все запуски теста завершены — сохраняем его агрегат
    if _test_run_counts[test_name] == _test_total_expected.get(test_name, 1):
        _aggregator.save_summary(test_name)

def send_telegram_report(summary_text: str, chat_id: str, bot_token: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": f"🎬 Тесты завершены\n\n{summary_text}",
        "parse_mode": "Markdown"
    }
    requests.post(url, data=data)
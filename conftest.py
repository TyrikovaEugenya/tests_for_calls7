import pytest
import re
from playwright.sync_api import sync_playwright, Playwright
import allure
import time
from collections import Counter, defaultdict, deque
import statistics
from typing import Dict, Any
import json
from pathlib import Path
import requests
import config

CHROMIUM_PATH = "/opt/chromium/chrome"

DEVICES = ["Desktop", "Mobile"]
THROTTLING_MODES = ["No_throttling", "Slow_4G"]
GEO_LOCATIONS = ["Moscow", "SPb", "Kazan", "Novosibirsk", "Yekaterinburg"]
BROWSERS = ["chromium", "firefox", "webkit"]
PAY_METHODS = ["card", 'sbp']


geo_map = {
    "Moscow": ("ru-RU", "Europe/Moscow"),
    "SPb": ("ru-RU", "Europe/Moscow"),
    "Kazan": ("ru-RU", "Europe/Moscow"),
    "Novosibirsk": ("ru-RU", "Asia/Novosibirsk"),
    "Yekaterinburg": ("ru-RU", "Asia/Yekaterinburg"),
}

def pytest_addoption(parser):
    parser.addoption(
        '--film-url',
        action='store',
        default="https://calls7.com/movie/370",
        help="Choose url for film which page you want to test"
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
    parser.addoption(
        "--pay-method",
        action="store",
        default="card",
        choices=PAY_METHODS    
    )

    
@pytest.fixture()
def get_film_url(request):
    return request.config.getoption("--film-url")

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
    return request.config.getoption("--film-list")

@pytest.fixture
def film_limit(request):
    return request.config.getoption("--film-limit")

@pytest.fixture
def pay_method(request):
    return request.config.getoption("--pay-method")

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
    payment_method = metafunc.config.getoption("--pay-method")
    use_cli = any([device, throttling, geo, browser, payment_method])
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
    context.clear_cookies()
    page = context.new_page()
    
    if browser_type == "chromium":
        client = context.new_cdp_session(page)
        client.send("Runtime.enable")
        client.send("Log.enable")
        
        def on_log_entry(params):
            text = params.get("entry", {}).get("text", "")
                # Или из args, если text пустой:
            args = params.get("entry", {}).get("args", [])
            if not text and args:
                text = " ".join(str(arg.get("value", "")) for arg in args)
                
            if "[Dc] loadPlayer finished" in text:
                page.evaluate("""
                    window.__playerReadyDetected = true;
                    window.__playerReadyTimestamp = Date.now();
                    window.__cdpDetected = true;
                """)
                print(f"[PLAYER] ✅ [Dc] loadPlayer finished: {text}")
                
        client.on("Log.entryAdded", on_log_entry)
        time.sleep(0.1)
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
        self.cluster_cache = {}
    
    def add_report(self, test_name: str, report: dict):
        self.reports_by_test[test_name].append(report)
        if test_name in self.cluster_cache:
            del self.cluster_cache[test_name]
        
    def step_factory(self):
        return {"metrics": defaultdict(list), "booleans": defaultdict(list)}
    
    def get_summary(self, test_name: str) -> dict:
        reports = self.reports_by_test[test_name]
        if not reports:
            return {"error": f"No reports for {test_name}"}
        
        summary = {
            "test_name": test_name,
            "domain": reports[0]["domain"],
            "total_runs": len(reports),
            "problematic_runs": sum(1 for r in reports if r.get("is_problematic_flow", False)),
            "failed_runs": sum(1 for r in reports if r.get("error")),
            "steps": defaultdict(self.step_factory),
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

            # Сбор ВСЕХ метрик по шагам
            for step_name, metrics in r.get("steps", {}).items():
                if not isinstance(metrics, dict):
                    continue
                
                if step_name not in summary["steps"]:
                    summary["steps"][step_name] = self.step_factory()
                
                for metric_name, value in metrics.items():
                    if value is None:
                        continue
                
                    if isinstance(value, bool):
                        # Булевы метрики - сохраняем как есть для подсчета процентов
                        summary["steps"][step_name]["booleans"][metric_name].append(value)
                    elif isinstance(value, (int, float)):
                        # Числовые метрики
                        summary["steps"][step_name]["metrics"][metric_name].append(value)

        # Агрегация числовых метрик
        for step_name, step_data in summary["steps"].items():
            # Агрегация числовых метрик
            for metric_name, values in step_data["metrics"].items():
                if values:
                    try:
                        step_data["metrics"][metric_name] = {
                            "mean": round(statistics.mean(values), 1),
                            "median": round(statistics.median(values), 1),
                            "min": min(values),
                            "max": max(values),
                            "count": len(values),
                            "stdev": round(statistics.stdev(values), 1) if len(values) > 1 else 0.0,
                        }
                    except statistics.StatisticsError:
                        step_data["metrics"][metric_name] = {"values": values}

            # Агрегация булевых метрик
            for metric_name, values in step_data["booleans"].items():
                if values:
                    true_count = sum(values)
                    total = len(values)
                    step_data["booleans"][metric_name] = {
                        "true_count": true_count,
                        "false_count": total - true_count,
                        "true_percentage": round(true_count / total * 100, 1) if total > 0 else 0,
                        "total": total
                    }


        # Отдельная агрегация для PPI
        for step_name, step_data in summary["steps"].items():
            ppi_values = []
            for r in reports:
                step_metrics = r.get("steps", {}).get(step_name, {})
                if isinstance(step_metrics, dict):
                    ppi = step_metrics.get("pagePerformanceIndex")
                    if isinstance(ppi, (int, float)) and ppi is not None:
                        ppi_values.append(ppi)
            
            if ppi_values:
                step_data["ppi_stats"] = {
                    "mean": round(statistics.mean(ppi_values), 1),
                    "median": round(statistics.median(ppi_values), 1),
                    "min": min(ppi_values),
                    "max": max(ppi_values),
                    "stdev": round(statistics.stdev(ppi_values), 1) if len(ppi_values) > 1 else 0.0,
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
        json_path = reports_dir / f"RUN_SUMMARY_{safe_name}_{summary['domain']}.json"
        md_path = reports_dir / f"RUN_SUMMARY_{safe_name}_{summary['domain']}.md"
        
        # Сохраняем JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        # Сохраняем MD
        self._save_markdown(summary, md_path)
        # Сохраняем кластеризованные отчеты
        try:
            self.save_clustered_summaries(test_name)
        except Exception as e:
            print(f"[WARNING] Failed to save clustered summaries: {e}")
        # Создаем отчет сравнения кластеров
        try:
            self.create_cluster_comparison_report(test_name)
        except Exception as e:
            print(f"[WARNING] Failed to create cluster comparison: {e}")

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
        md_lines.append("| Шаг | Средний PPI | Вариация (σ) | Ключевые метрики |")
        md_lines.append("|-----|-------------|--------------|-------------------|")

        for step_name, data in summary["steps"].items():
            ppi_stats = data.get("ppi_stats", {})
            ppi_mean = ppi_stats.get("mean", "—")
            ppi_stdev = ppi_stats.get("stdev", "—")
            
            # Формируем ключевые метрики для шага
            key_metrics = []
            metrics_data = data.get("metrics", {})
            
            # Выбираем наиболее важные метрики для каждого типа шага
            if step_name == "main_page":
                for metric in ["lcp", "fcp", "cls"]:
                    if metric in metrics_data:
                        val = metrics_data[metric].get("mean", "—")
                        key_metrics.append(f"{metric.upper()}: {val}")
            elif step_name == "film_page":
                for metric in ["videoStartTime", "playerInitTime", "lcp"]:
                    if metric in metrics_data:
                        val = metrics_data[metric].get("mean", "—")
                        key_metrics.append(f"{metric}: {val}")
            elif step_name == "pay_page":
                for metric in ["iframeCpLoadTime"]:
                    if metric in metrics_data:
                        val = metrics_data[metric].get("mean", "—")
                        key_metrics.append(f"{metric}: {val}")
            
            # Если нет специфичных метрик, берем первые 3 доступные
            if not key_metrics:
                available_metrics = list(metrics_data.keys())[:3]
                for metric in available_metrics:
                    if not metric.endswith('_count'):
                        val = metrics_data[metric].get("mean", "—")
                        unit = self._get_metric_unit(metric)
                        key_metrics.append(f"{metric}: {val}{unit}")
            
            key_metrics_str = ", ".join(key_metrics) if key_metrics else "—"
            md_lines.append(f"| `{step_name}` | `{ppi_mean}` | `{ppi_stdev}` | `{key_metrics_str}` |")
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

        # Проблемные показатели (расширенная версия)
        problematic_metrics = self._analyze_problematic_metrics(summary)

        if problematic_metrics:
            md_lines.append("### ⚠️ Выявленные проблемы")
            md_lines.extend(problematic_metrics)
            md_lines.append("")
            
        if failed > 0:
            md_lines.append("### 🚨 Упавшие тесты (ошибки)")
            md_lines.append(f"- Обнаружено `{failed}` падений (см. раздел «Критические ошибки» выше)")
            md_lines.append("")
            
        if not (problematic_metrics or failed):
            md_lines.append("### ✅ Проблем не выявлено\n")
            
        # Детализация по шагам
        md_lines.append("## 📋 Детализация по шагам")
        for step_name, step_data in summary["steps"].items():
            if not step_data.get("metrics"):
                continue

            title_map = {
                "main_page": "Главная страница",
                "film_page": "Страница с конкретным фильмом",
                "pay_page": "Оплата",
                "after_payment_popup": "Попап после оплаты",
                "after_return_without_payment": "Возврат без оплаты"
            }
            md_lines.append(f"\n### > {title_map.get(step_name, step_name)}:")

            # Сортируем метрики: сначала числовые, потом булевы
            metrics_data = step_data.get("metrics", {})
            for metric_name, stats in metrics_data.items():
                if not isinstance(stats, dict) or "mean" not in stats:
                    continue

                mean_val = stats["mean"]
                unit = self._get_metric_unit(metric_name)
                
                # Оценка метрики
                grade = config.grade_metric(mean_val, metric_name)
                icon = {"отлично": "✅", "хорошо": "🟢", "удовлетворительно": "🟡", "плохо": "🔴"}.get(grade, "❓")

                # Человекочитаемое имя
                nice_name = self._get_metric_display_name(metric_name)

                # Форматируем значение в зависимости от типа метрики
                if unit == "мс":
                    value_str = f"{int(mean_val)} {unit}"
                    range_str = f"(min: {int(stats.get('min', 0))}, max: {int(stats.get('max', 0))})"
                elif unit == "":
                    value_str = f"{mean_val}"
                    range_str = f"(min: {stats.get('min', 0)}, max: {stats.get('max', 0)})"
                else:
                    value_str = f"{mean_val} {unit}"
                    range_str = f"(min: {stats.get('min', 0)}, max: {stats.get('max', 0)})"

                md_lines.append(f"{icon} **{nice_name}**: {value_str} {range_str} — **{grade}**")

            # Выводим булевы метрики (только те, что имеют низкий процент успеха)
            booleans_data = step_data.get("booleans", {})
            for metric_name, stats in booleans_data.items():
                if not isinstance(stats, dict):
                    continue
                    
                true_percentage = stats.get('true_percentage', 0)
                total = stats.get('total', 0)
                
                # Выводим только проблемные булевы метрики
                if true_percentage < 90:  # Порог для вывода проблемных метрик
                    nice_name = self._get_metric_display_name(metric_name)
                    status_icon = "🔴" if true_percentage < 70 else "🟡"
                    md_lines.append(
                        f"{status_icon} **{nice_name}**: {true_percentage}% успешно "
                        f"({stats.get('true_count', 0)}/{total})"
                    )
                
        md_lines.append("")
            
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
            
        allure.attach.file(
            path,
            name="Детализация по шагам",
            extension="md"
        )

    def _analyze_problematic_metrics(self, summary: dict) -> list:
        """Анализирует все метрики и возвращает список проблем"""
        problematic = []
        
        for step_name, data in summary["steps"].items():
            metrics_data = data.get("metrics", {})
            booleans_data = data.get("booleans", {})
            
            # Проверяем PPI
            ppi_stats = data.get("ppi_stats", {})
            if ppi_stats.get("mean", 100) < config.TARGET_PAGE_PERFORMANCE_INDEX:
                problematic.append(f"- `{step_name}.pagePerformanceIndex`: {ppi_stats['mean']:.1f} < {config.TARGET_PAGE_PERFORMANCE_INDEX}")
            
            # Проверяем временные метрики по порогам из конфига
            for metric_name in config.METRIC_THRESHOLDS.keys():
                if metric_name in metrics_data:
                    mean_val = metrics_data[metric_name].get("mean", 0)
                    poor_threshold = config.METRIC_THRESHOLDS[metric_name][1]
                    if mean_val > poor_threshold:
                        unit = self._get_metric_unit(metric_name)
                        problematic.append(f"- `{step_name}.{metric_name}`: {mean_val:.0f}{unit} > {poor_threshold}{unit}")
            
            # Проверяем булевы метрики
            for metric_name, stats in booleans_data.items():
                if not isinstance(stats, dict):
                    continue
                    
                true_percentage = stats.get('true_percentage', 100)
                if true_percentage < 90:  # Порог для булевых метрик
                    problematic.append(f"- `{step_name}.{metric_name}`: {true_percentage}% успешных выполнений < 90%")
        
        return problematic
    
    def _get_metric_unit(self, metric_name: str) -> str:
        """Возвращает единицу измерения для метрики"""
        units = {
            # Временные метрики (миллисекунды)
            "videoStartTime": "мс",
            "playerInitTime": "мс",
            "popupAppearTime": "мс",
            "iframeCpLoadTime": "мс",
            "lcp": "мс",
            "ttfb": "мс",
            "fcp": "мс",
            "tbt": "мс",
            "inp": "мс",
            "dnsResolveTime": "мс",
            "connectTime": "мс",
            "rebufferDuration": "мс",
            "viduPopupAppearTime": "мс",
            "retryPaymentLoadTime": "мс",
            
            # Безразмерные метрики
            "cls": "",
            "performance_score": "",
            "pagePerformanceIndex": "",
            "rebufferCount": "",
            
            # Процентные метрики
            "true_percentage": "%",
        }
        return units.get(metric_name, "мс")
    
    def _get_metric_display_name(self, metric_name: str) -> str:
        """Возвращает человекочитаемое имя для метрики"""
        names = {
            "videoStartTime": "Загрузка первого кадра видео",
            "playerInitTime": "Загрузка плеера",
            "popupAppearTime": "Появление формы блокировки",
            "iframeCpLoadTime": "Загрузка формы оплаты",
            "lcp": "Largest Contentful Paint",
            "ttfb": "Time to First Byte",
            "fcp": "First Contentful Paint",
            "cls": "Cumulative Layout Shift",
            "tbt": "Total Blocking Time",
            "performance_score": "Performance Score",
            "pagePerformanceIndex": "Page Performance Index",
            "dnsResolveTime": "DNS Resolve Time",
            "connectTime": "Connect Time",
            "rebufferCount": "Rebuffer Count",
            "rebufferDuration": "Rebuffer Duration",
            "popupAvailable": "Доступность попапа",
            "popupClickSuccess": "Успешность клика по попапу",
            "buttonsCpAvailable": "Доступность кнопок оплаты",
            "buttonsClickSuccess": "Успешность клика по кнопкам",
            "payFormAppear": "Появление формы оплаты",
            "viduPopupSuccess": "Успешность попапа Vidu",
            "retryPaymentSuccess": "Успешность повторной оплаты",
            "is_problematic_page": "Проблемная страница",
        }
        return names.get(metric_name, metric_name)
    
    def get_clustered_summaries(self, test_name: str, cluster_by: list = None) -> dict:
        """Возвращает сводки, сгруппированные по указанным параметрам"""
        if cluster_by is None:
            cluster_by = ["device", "throttling", "geoposition", "browser_type"]
        
        cache_key = f"{test_name}_{'_'.join(sorted(cluster_by))}"
        if cache_key in self.cluster_cache:
            return self.cluster_cache[cache_key]
        
        reports = self.reports_by_test[test_name]
        if not reports:
            return {"error": f"No reports for {test_name}"}
        
        # Группируем отчеты по кластерам
        clusters = defaultdict(list)
        for report in reports:
            cluster_key = tuple(report.get(param, "N/A") for param in cluster_by)
            clusters[cluster_key].append(report)
        
        # Создаем сводки для каждого кластера
        clustered_summaries = {}
        for cluster_key, cluster_reports in clusters.items():
            cluster_name_parts = []
            for param, value in zip(cluster_by, cluster_key):
                cluster_name_parts.append(f"{param}: {value}")
            cluster_name = "; ".join(cluster_name_parts)
            
            # Создаем временный агрегатор для этого кластера
            temp_aggregator = MultiTestRunAggregator()
            for report in cluster_reports:
                temp_aggregator.add_report(test_name, report)
            
            clustered_summaries[cluster_name] = temp_aggregator.get_summary(test_name)
        
        self.cluster_cache[cache_key] = clustered_summaries
        return clustered_summaries
    
    def save_clustered_summaries(self, test_name: str, cluster_by: list = None):
        """Сохраняет кластеризованные отчеты"""
        clustered_summaries = self.get_clustered_summaries(test_name, cluster_by)
        
        if "error" in clustered_summaries:
            print(f"[INFO] Пропущена кластеризация для '{test_name}': {clustered_summaries['error']}")
            return
        
        reports_dir = Path("reports") / "clustered"
        reports_dir.mkdir(exist_ok=True, parents=True)
        
        safe_name = re.sub(r'[<>:"/\\|?*\s]', '_', test_name)[:30]
        
        # Сохраняем каждый кластер
        for cluster_name, summary in clustered_summaries.items():
            safe_cluster_name = re.sub(r'[<>:"/\\|?*\s]', '_', cluster_name)[:50]
            
            json_path = reports_dir / f"CLUSTER_{safe_name}_{safe_cluster_name}.json"
            md_path = reports_dir / f"CLUSTER_{safe_name}_{safe_cluster_name}.md"
            
            # Сохраняем JSON
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            # Сохраняем MD с улучшенным форматированием для кластеров
            self._save_clustered_markdown(summary, cluster_name, md_path)
    
    def _save_clustered_markdown(self, summary: dict, cluster_name: str, path: Path):
        """Сохраняет Markdown отчет для конкретного кластера"""
        md_lines = []
        short_cluster_name = self._shorten_cluster_name(cluster_name)
        
        md_lines.append(f"# 🎯 Кластер: `{cluster_name}`\n")
        md_lines.append(f"**Тест**: `{summary.get('test_name', 'unknown')}`")
        md_lines.append(f"**Домен**: `{summary.get('domain', 'unknown')}`")
        md_lines.append(f"**Дата**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`")
        md_lines.append(f"**Запусков в кластере**: `{summary.get('total_runs', 0)}`\n")
        
        # Остальная часть аналогична обычному отчету, но сфокусированная на одном кластере
        self._add_common_markdown_content(summary, md_lines)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
    
    def _shorten_cluster_name(self, cluster_name: str) -> str:
        """Сокращает имя кластера для лучшего отображения в таблицах"""
        # Заменяем длинные названия параметров на короткие
        """Компактное представление кластера (только значения)"""
        parts = cluster_name.split("; ")
        
        # Извлекаем только значения
        values = []
        for part in parts:
            if ": " in part:
                value = part.split(": ")[1]
                # Сокращаем значения
                short_value = {
                    "Desktop": "DT",
                    "No_throttling": "NoThrot",
                    "firefox": "FF",
                    "webkit": "WK",
                    "chromium": "CH", 
                    "Moscow": "MSK",
                    "Novosibirsk": "NSK",
                    "N/A": "NA"
                }.get(value, value[:3])
                values.append(short_value)
        
        return "-".join(values)

    def _add_common_markdown_content(self, summary: dict, md_lines: list):
        """Добавляет общее содержимое Markdown (переиспользуется в обычных и кластеризованных отчетах)"""
        total = summary.get("total_runs", 0)
        problematic = summary.get("problematic_runs", 0)
        failed = summary.get("failed_runs", 0)
        
        md_lines.append(f"**Проблемных запусков**: `{problematic}` (`{problematic/total*100:.1f}%`)")
        md_lines.append(f"**Упавших запусков**: `{failed}` (`{failed/total*100:.1f}%`)\n")
        
        if summary.get("errors"):
            md_lines.append("## 🚨 Критические ошибки")
            md_lines.append("| Ошибка | Частота | Пример URL |")
            md_lines.append("|--------|---------|------------|")
            for error_msg, reports in sorted(summary["errors"].items(), key=lambda x: len(x[1]), reverse=True):
                count = len(reports)
                pct = count / total * 100
                example_url = reports[0].get("film_url", "N/A").split("?")[0]
                md_lines.append(f"| `{error_msg}` | `{count}` (`{pct:.1f}%`) | `{example_url}` |")
            md_lines.append("")

        # Сводка по шагам
        md_lines.append("### 📈 Производительность по шагам")
        md_lines.append("| Шаг | Средний PPI | Медиана PPI | Вариация (σ) |")
        md_lines.append("|-----|-------------|-------------|--------------|")

        for step_name, data in summary["steps"].items():
            ppi_stats = data.get("ppi_stats", {})
            ppi_mean = ppi_stats.get("mean", "—")
            ppi_median = ppi_stats.get("median", "—")
            ppi_stdev = ppi_stats.get("stdev", "—")
            
            md_lines.append(f"| `{step_name}` | `{ppi_mean}` | `{ppi_median}` | `{ppi_stdev}` |")
        md_lines.append("")

        # Проблемные показатели
        problematic_metrics = self._analyze_problematic_metrics(summary)
        if problematic_metrics:
            md_lines.append("### ⚠️ Выявленные проблемы")
            md_lines.extend(problematic_metrics)
            md_lines.append("")
            
    def create_cluster_comparison_report(self, test_name: str, cluster_by: list = None):
        """Создает сводный отчет с сравнением всех кластеров"""
        try:
            clustered_summaries = self.get_clustered_summaries(test_name, cluster_by)
            
            if "error" in clustered_summaries:
                print(f"[INFO] Cannot create cluster comparison: {clustered_summaries['error']}")
                return
            
            reports_dir = Path("reports")
            safe_name = re.sub(r'[<>:"/\\|?*\s]', '_', test_name)[:30]
            md_path = reports_dir / f"CLUSTER_COMPARISON_{safe_name}.md"
            
            md_lines = []
            md_lines.append(f"# 📊 Сравнение кластеров: `{test_name}`\n")
            md_lines.append(f"**Дата**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`")
            md_lines.append(f"**Параметры кластеризации**: `{', '.join(cluster_by) if cluster_by else 'device, throttling, geo, browser_type'}`")
            md_lines.append(f"**Всего кластеров**: `{len(clustered_summaries)}`\n")
            
            # Сводная таблица по кластерам - улучшенная версия
            md_lines.append("## 📈 Сводка по кластерам")
            md_lines.append("| Кластер | Зап. | Пробл. | Упало | PPI |")
            md_lines.append("|---------|------|---------|-------|-----|")
            
            for cluster_name, summary in clustered_summaries.items():
                total = summary.get("total_runs", 0)
                problematic = summary.get("problematic_runs", 0)
                failed = summary.get("failed_runs", 0)
                
                # Вычисляем средний PPI по всем шагам
                avg_ppi = self._calculate_average_ppi(summary)
                
                short_name = self._shorten_cluster_name(cluster_name)
                
                md_lines.append(
                    f"| `{short_name}` | `{total}` | `{problematic}` | `{failed}` | `{avg_ppi:.1f}` |"
                )
            
            md_lines.append("\n")
            
            # Детальное сравнение метрик по кластерам - улучшенная версия
            md_lines.append("## 🔍 Детальное сравнение метрик")
            
            # Для каждой важной метрики создаем таблицу сравнения
            important_metrics = [
                ("film_page", "videoStartTime", "Загрузка видео"),
                ("film_page", "popupAppearTime", "Появление попапа"), 
                ("pay_page", "iframeCpLoadTime", "Загрузка формы оплаты"),
                ("film_page", "lcp", "LCP"),
                ("film_page", "pagePerformanceIndex", "PPI")
            ]
            
            for step, metric_name, display_name in important_metrics:
                md_lines.append(f"### 📊 {display_name}")
                md_lines.append("| Кластер | Среднее | Медиана | Min | Max | Статус |")
                md_lines.append("|---------|---------|---------|-----|-----|--------|")
                
                for cluster_name, summary in clustered_summaries.items():
                    step_data = summary.get("steps", {}).get(step, {})
                    metrics_data = step_data.get("metrics", {}).get(metric_name, {})
                    
                    if not metrics_data or "mean" not in metrics_data:
                        short_name = self._shorten_cluster_name(cluster_name)
                        md_lines.append(f"| `{short_name}` | — | — | — | — | ❓ |")
                        continue
                    
                    mean_val = metrics_data["mean"]
                    median_val = metrics_data["median"]
                    min_val = metrics_data["min"]
                    max_val = metrics_data["max"]
                    
                    # Оценка метрики
                    grade = config.grade_metric(mean_val, metric_name)
                    icon = {"отлично": "✅", "хорошо": "🟢", "удовлетворительно": "🟡", "плохо": "🔴"}.get(grade, "❓")
                    
                    # Получаем единицу измерения ДО ее использования
                    unit = self._get_metric_unit(metric_name)
                    
                    # Форматируем значения
                    if unit == "мс":
                        mean_str = f"{int(mean_val)}"
                        median_str = f"{int(median_val)}"
                        min_str = f"{int(min_val)}"
                        max_str = f"{int(max_val)}"
                    else:
                        mean_str = f"{mean_val:.1f}"
                        median_str = f"{median_val:.1f}"
                        min_str = f"{min_val:.1f}"
                        max_str = f"{max_val:.1f}"
                    
                    short_name = self._shorten_cluster_name(cluster_name)
                    md_lines.append(
                        f"| `{short_name}` | `{mean_str}{unit}` | `{median_str}{unit}` | "
                        f"`{min_str}{unit}` | `{max_str}{unit}` | {icon} |"
                    )
                
                md_lines.append("")
            
            # Улучшенный статистический анализ
            md_lines.append("## 📊 Статистический анализ")
            analysis_results = self._analyze_clusters_statistically(clustered_summaries)
            
            if analysis_results["anomalies"]:
                md_lines.append("### ⚠️ Выявленные аномалии")
                for anomaly in analysis_results["anomalies"]:
                    md_lines.append(f"- {anomaly}")
                md_lines.append("")
            
            if analysis_results["recommendations"]:
                md_lines.append("### 💡 Рекомендации")
                for recommendation in analysis_results["recommendations"]:
                    md_lines.append(f"- {recommendation}")
                md_lines.append("")
            
            if analysis_results["best_performing"]:
                md_lines.append("### 🏆 Лучшие кластеры")
                for best in analysis_results["best_performing"]:
                    md_lines.append(f"- {best}")
                md_lines.append("")
            
            if not any([analysis_results["anomalies"], analysis_results["recommendations"], analysis_results["best_performing"]]):
                md_lines.append("### ℹ️ Особых аномалий не выявлено\n")
            
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))
            
            allure.attach.file(
                md_path,
                name="Сравнение кластеров",
                extension="md"
            )
        except Exception as e:
            print(f"[ERROR] Failed to create cluster comparison report: {e}")
            import traceback
            traceback.print_exc()
    
    def _calculate_average_ppi(self, summary: dict) -> float:
        """Вычисляет средний PPI по всем шагам"""
        try:
            ppi_values = []
            for step_name, step_data in summary.get("steps", {}).items():
                ppi_stats = step_data.get("ppi_stats", {})
                if "mean" in ppi_stats:
                    ppi_mean = ppi_stats["mean"]
                    if isinstance(ppi_mean, (int, float)) and ppi_mean > 0:
                        ppi_values.append(ppi_mean)
        
            if ppi_values:
                return statistics.mean(ppi_values)
            else:
                return 0.0
        except Exception as e:
            print(f"[ERROR] Error calculating average PPI: {e}")
            return 0.0
    
    def _find_cluster_anomalies(self, clustered_summaries: dict) -> list:
        """Находит аномалии в данных кластеров"""
        anomalies = []
        
        # Анализ PPI между кластерами
        ppi_values = []
        for cluster_name, summary in clustered_summaries.items():
            avg_ppi = self._calculate_average_ppi(summary)
            ppi_values.append((cluster_name, avg_ppi))
        
        if ppi_values:
            avg_ppi_all = statistics.mean(ppi for _, ppi in ppi_values)
            std_ppi_all = statistics.stdev(ppi for _, ppi in ppi_values) if len(ppi_values) > 1 else 0
            
            for cluster_name, ppi in ppi_values:
                if std_ppi_all > 0 and abs(ppi - avg_ppi_all) > 2 * std_ppi_all:
                    anomalies.append(
                        f"Кластер `{cluster_name}` имеет аномальный PPI: {ppi:.1f} "
                        f"(среднее по всем кластерам: {avg_ppi_all:.1f})"
                    )
        
        return anomalies
    
    def _analyze_clusters_statistically(self, clustered_summaries: dict) -> dict:
        """Проводит статистический анализ кластеров"""
        results = {
            "anomalies": [],
            "recommendations": [],
            "best_performing": []
        }
        
        if len(clustered_summaries) < 2:
            results["anomalies"].append("Недостаточно кластеров для статистического анализа")
            return results
        
        # Анализ PPI между кластерами
        ppi_data = []
        for cluster_name, summary in clustered_summaries.items():
            avg_ppi = self._calculate_average_ppi(summary)
            ppi_data.append((cluster_name, avg_ppi, summary.get("total_runs", 0)))
        
        if ppi_data:
            ppi_values = [ppi for _, ppi, _ in ppi_data]
            avg_ppi_all = statistics.mean(ppi_values)
            
            if len(ppi_values) > 1:
                std_ppi_all = statistics.stdev(ppi_values)
                
                # Находим аномалии (более 2 стандартных отклонений)
                for cluster_name, ppi, runs in ppi_data:
                    if std_ppi_all > 0 and abs(ppi - avg_ppi_all) > 2 * std_ppi_all:
                        short_name = self._shorten_cluster_name(cluster_name)
                        results["anomalies"].append(
                            f"Кластер `{short_name}` имеет аномальный PPI: {ppi:.1f} "
                            f"(среднее: {avg_ppi_all:.1f} ± {std_ppi_all:.1f})"
                        )
            
            # Находим лучшие и худшие кластеры
            best_ppi = max(ppi_values)
            worst_ppi = min(ppi_values)
            
            for cluster_name, ppi, runs in ppi_data:
                short_name = self._shorten_cluster_name(cluster_name)
                if ppi == best_ppi and runs >= 3:  # Только если достаточно данных
                    results["best_performing"].append(
                        f"`{short_name}` - лучший PPI: {ppi:.1f} (запусков: {runs})"
                    )
                elif ppi == worst_ppi and runs >= 3:
                    results["anomalies"].append(
                        f"`{short_name}` - худший PPI: {ppi:.1f} (запусков: {runs})"
                    )
        
        # Анализ времени загрузки видео
        video_times = []
        for cluster_name, summary in clustered_summaries.items():
            film_metrics = summary.get("steps", {}).get("film_page", {})
            video_time = film_metrics.get("metrics", {}).get("videoStartTime", {}).get("mean", 0)
            if video_time > 0:
                video_times.append((cluster_name, video_time))
        
        if video_times:
            avg_video_time = statistics.mean(time for _, time in video_times)
            best_video = min(video_times, key=lambda x: x[1])
            worst_video = max(video_times, key=lambda x: x[1])
            
            short_best = self._shorten_cluster_name(best_video[0])
            short_worst = self._shorten_cluster_name(worst_video[0])
            
            results["recommendations"].append(
                f"Лучшее время загрузки видео: `{short_best}` ({best_video[1]:.0f}мс), "
                f"худшее: `{short_worst}` ({worst_video[1]:.0f}мс)"
            )
        
        # Анализ успешности
        success_rates = []
        for cluster_name, summary in clustered_summaries.items():
            total = summary.get("total_runs", 0)
            failed = summary.get("failed_runs", 0)
            if total > 0:
                success_rate = (total - failed) / total * 100
                success_rates.append((cluster_name, success_rate, total))
        
        if success_rates:
            worst_success = min(success_rates, key=lambda x: x[1])
            if worst_success[1] < 80 and worst_success[2] >= 3:  # Низкая успешность
                short_name = self._shorten_cluster_name(worst_success[0])
                results["anomalies"].append(
                    f"Низкая успешность в кластере `{short_name}`: {worst_success[1]:.1f}% "
                    f"({worst_success[2]-failed} из {worst_success[2]})"
                )
        
        return results

            

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
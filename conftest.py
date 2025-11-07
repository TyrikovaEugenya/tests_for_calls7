import pytest
from playwright.sync_api import sync_playwright, Playwright
import allure
import time

CHROMIUM_PATH = "/opt/chromium/chrome"

DEVICES = ["Desktop", "Mobile"]
THROTTLING_MODES = ["No throttling", "Slow 4G"]
GEO_LOCATIONS = ["Moscow", "SPb", "Kazan", "Novosibirsk", "Yekaterinburg"]
BROWSERS = ["chromium", "firefox", "webkit"]

geo_map = {
    "Moscow": ("ru-RU", "Europe/Moscow"),
    "SPb": ("ru-RU", "Europe/Moscow"),
    "Kazan": ("ru-RU", "Europe/Moscow"),
    "Novosibirsk": ("ru-RU", "Asia/Novosibirsk"),
    "Yekaterinburg": ("ru-RU", "Asia/Yekaterinburg"),
}

def pytest_generate_tests(metafunc):
    """Автоматически параметризует тесты, если запрошены фикстуры."""
    use_cli = any([device, throttling, geo, browser_type])
    if not use_cli:
        if "device" in metafunc.fixturenames:
            metafunc.parametrize("device", DEVICES, scope="function")
        if "throttling" in metafunc.fixturenames:
            metafunc.parametrize("throttling", THROTTLING_MODES, scope="function")
        if "geo" in metafunc.fixturenames:
            metafunc.parametrize("geo", GEO_LOCATIONS, scope="function")
        if "browser_type" in metafunc.fixturenames:
            metafunc.parametrize("browser_type", BROWSERS, scope="session")

def pytest_addoption(parser):
    parser.addoption('--film_url', action='store', default="https://calls7.com/movie/370",
                     help="Choose url for film which page you want to test")
    parser.addoption('--device', action='store', default="Desktop", choices=DEVICES)
    parser.addoption("--throttling", action="store", default="No throttling", choices=THROTTLING_MODES)
    parser.addoption("--geo", action="store", default="Moscow", choices=GEO_LOCATIONS)
    parser.addoption("--browser", action="store", default="chromium", choices=BROWSERS)
    
    
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
    
@pytest.fixture(scope="session")
def browser_instance(browser_type):
    with sync_playwright() as p:
        if browser_type == "chromium":
            browser = p.chromium.launch(
                headless=True,
                executable_path=CHROMIUM_PATH,
                args=[
                    "--no-sandbox",
                    "--remote-debugging-port=9222",
                    "--disable-gpu",
                    "--disable-dev-shm-usage"
                ],
            )
        elif browser_type == "firefox":
            browser = p.firefox.launch(headless=True)
        elif browser_type == "webkit":
            browser = p.webkit.launch(headless=True)
        else:
            raise ValueError(f"Unsupported: {browser_type}")
        yield browser
        browser.close()

@pytest.fixture(scope='function')
def page(browser_type, device, geo, throttling, browser_instance):
    with sync_playwright() as p:
        context_args = {}
        
        if device == "Mobile":
            context_args.update(p.devices["Pixel 5"])
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
        if throttling == "Slow 4G" and browser_type == "chromium":
            try:
                client = context.new_cdp_session(page)
                client.send("Network.enable")
                client.send("Network.emulateNetworkConditions", {
                    "offline": False,
                    "downloadThroughputKbps": 400,
                    "uploadThroughputKbps": 400,
                    "latency": 400
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
    if rep.when == "call" and rep.failed:
        page = item.funcargs.get("page")
        if page:
            allure.attach(
                page.screenshot(),
                name="screenshot",
                attachment_type=allure.attachment_type.PNG
            )
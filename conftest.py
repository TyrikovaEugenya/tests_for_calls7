import pytest
from playwright.sync_api import sync_playwright
import allure

CHROMIUM_PATH = "/opt/chromium/chrome"

def pytest_addoption(parser):
    parser.addoption('--film_url', action='store', default="https://calls7.com/movie/370",
                     help="Choose url for film which page you want to test")
    
@pytest.fixture()
def get_film_url(request):
    return request.config.getoption("--film_url")

@pytest.fixture(scope='function')
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # обязательно False для user gesture
            executable_path=CHROMIUM_PATH,
            args=[
                "--remote-debugging-port=9222",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage"
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            # Отключаем свойства, выдающие автоматизацию
            permissions=["geolocation", "notifications"],
            java_script_enabled=True,
        )

        # 🛡️ Главное: скрываем navigator.webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        context.clear_cookies()
        page = context.new_page()
        yield page
        context.close()
        browser.close()
        
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
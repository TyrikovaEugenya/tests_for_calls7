import allure
import time
import pytest
import json
import logging
import os
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def collect_performance_metrics(page):
    """Собирает Lighthouse-подобные метрики через Performance API"""
    metrics = page.evaluate("""
        () => {
            const entries = performance.getEntriesByType('navigation')[0];
            const lcpEntry = performance.getEntriesByName('largest-contentful-paint')[0];
            const lcp = lcpEntry ? lcpEntry.startTime : 0;
            const ttfb = entries ? entries.responseStart - entries.requestStart : 0;
            const cls = 0;
            const fid = 0;
            let tbt = 0;
            const longTasks = performance.getEntriesByType('longtask');
            if (longTasks) {
                tbt = longTasks.reduce((sum, task) => sum + task.duration, 0);
            }
            return { lcp, ttfb, cls, fid, tbt };
        }
    """)
    return metrics

def collect_performance_metrics_after_video(page):
    """
    Ждёт появления <video>, затем измеряет LCP и другие метрики.
    Используется для страниц фильмов.
    """

    return page.evaluate("""
        () => {
            const start = performance.now();
            let lcpEntry = performance.getEntriesByName('largest-contentful-paint')[0];
            while (!lcpEntry && (performance.now() - start) < 5000) {
                lcpEntry = performance.getEntriesByName('largest-contentful-paint')[0];
            }

            const nav = performance.getEntriesByType('navigation')[0];
            const lcp = lcpEntry ? lcpEntry.startTime : 0;
            const ttfb = nav ? nav.responseStart - nav.requestStart : 0;
            const cls = 0;
            const fid = 0;
            let tbt = 0;
            const longTasks = performance.getEntriesByType('longtask');
            if (longTasks) {
                tbt = longTasks.reduce((sum, task) => sum + task.duration, 0);
            }
            return { lcp, ttfb, cls, fid, tbt };
        }
    """)


def collect_dns_and_connect_time(page, target_domain: str = "calls7.com"):
    """
    Собирает dnsResolveTime и connectTime для первого запроса к target_domain.
    """
    timings = {"dnsResolveTime": None, "connectTime": None}
    recorded = False

    def on_request(request):
        nonlocal recorded
        if recorded:
            return
        url = request.url
        if url is None:
            return
        if target_domain in url:
            timing = request.timing
            if timing:
                dns_start = timing.get("domainLookupStart", -1)
                dns_end = timing.get("domainLookupEnd", -1)
                connect_start = timing.get("connectStart", -1)
                connect_end = timing.get("connectEnd", -1)

                if dns_start >= 0 and dns_end >= 0:
                    dns_time = dns_end - dns_start
                    if dns_time >= 0:
                        timings["dnsResolveTime"] = round(dns_time, 2)

                if connect_start >= 0 and connect_end >= 0:
                    connect_time = connect_end - connect_start
                    if connect_time >= 0:
                        timings["connectTime"] = round(connect_time, 2)

                recorded = True

    page.on("request", on_request)
    return timings


def inject_plyr_playing_listener(page):
    page.evaluate("""
        window.__videoStartTime = null;
        const target = document.querySelector('.plyr');
        if (target) {
            const observer = new MutationObserver((mutations) => {
                for (const mutation of mutations) {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        if (target.classList.contains('plyr--playing')) {
                            window.__videoStartTime = performance.now();
                            observer.disconnect();
                            break;
                        }
                    }
                }
            });
            observer.observe(target, { attributes: true, attributeFilter: ['class'] });
        }
    """)
    
# def measure_player_init_time(page):
#     # Инжектируем до загрузки play.js
#     page.evaluate("""
#         window.__playerInitStart = performance.now();
#         const originalPlayerInit = window.PlayerClass?.prototype?.playerInit;
#         if (originalPlayerInit) {
#             window.PlayerClass.prototype.playerInit = function(...args) {
#                 window.__playerInitTime = performance.now() - window.__playerInitStart;
#                 return originalPlayerInit.apply(this, args);
#             };
#         }
#     """)

#     # Загружаем страницу фильма
#     page.goto(config.FILM_EXAMPLE_URL)
#     page.wait_for_load_state("networkidle")

#     # Ждём, пока __playerInitTime появится (до 10 сек)
#     page.wait_for_function(
#         "() => window.__playerInitTime !== undefined",
#         timeout=10000
#     )

#     return page.evaluate("window.__playerInitTime")

def inject_hls_buffering_listener(page):
    page.evaluate("""
        window.__rebufferCount = 0;
        window.__rebufferStart = null;
        window.__rebufferDuration = 0;

        // Ждём загрузки hls.js
        const waitForHls = () => {
            if (window.Hls) {
                const originalAttachMedia = window.Hls.prototype.attachMedia;
                window.Hls.prototype.attachMedia = function(video) {
                    // Слушаем события буферизации
                    video.addEventListener('waiting', () => {
                        if (!window.__rebufferStart) {
                            window.__rebufferStart = performance.now();
                        }
                    });
                    video.addEventListener('playing', () => {
                        if (window.__rebufferStart) {
                            window.__rebufferCount += 1;
                            window.__rebufferDuration += performance.now() - window.__rebufferStart;
                            window.__rebufferStart = null;
                        }
                    });
                    return originalAttachMedia.call(this, video);
                };
            } else {
                setTimeout(waitForHls, 100);
            }
        };
        waitForHls();
    """)


def save_json_report(data, filename="user_flow_report.json"):
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@allure.title("Полный user flow: от главной до формы оплаты")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_flow_with_metrics(page, get_film_url):
    report = {
        "url": get_film_url,
        "steps": {},
        "metrics": {},
        "pagePerformanceIndex": None,
        "videoStartTime": None,
        "popupAppearTime": None
    }

    with allure.step("Открыть главную и собрать метрики"):
        dns_metrics = collect_dns_and_connect_time(page, "calls7.com")
        page.goto(config.BASE_URL)
        perf_main = collect_performance_metrics(page)
        report["steps"]["main_page"] = {
            **perf_main,
            "dnsResolveTime": dns_metrics["dnsResolveTime"],
            "connectTime": dns_metrics["connectTime"]
        }
        
    with allure.step("Перейти на страницу фильма и измерить playerInitTime"):
        page.goto(get_film_url)
        page.wait_for_load_state("networkidle")

    with allure.step("Инжектировать слушатель буферизации"):
        inject_hls_buffering_listener(page)
        
    with allure.step("Дождаться появления элемента <video>"):
        page.wait_for_selector("video", timeout=15000)

    with allure.step("Собрать метрики страницы фильма"):
        dns_metrics = collect_dns_and_connect_time(page, "calls7.com")
        perf_film = collect_performance_metrics_after_video(page)
        report["steps"]["film_page"] = {
            **perf_film,
            "dnsResolveTime": dns_metrics["dnsResolveTime"],
            "connectTime": dns_metrics["connectTime"]
        }
        report["metrics"] = report["steps"]["film_page"]

        ppi = config.calculate_page_performance_index(
            lcp=perf_film["lcp"],
            fid=perf_film["fid"],
            cls=perf_film["cls"],
            tbt=perf_film["tbt"],
            ttfb=perf_film["ttfb"]
        )
        report["pagePerformanceIndex"] = ppi

        allure.attach(json.dumps(report["metrics"], indent=2), name="Page Metrics", attachment_type=allure.attachment_type.JSON)
        allure.attach(f"pagePerformanceIndex: {ppi}", name="Performance Index", attachment_type=allure.attachment_type.TEXT)

    with allure.step("Нажать Play и замерить videoStartTime"):
        page.on("console", lambda msg: 
            logger.warning(f"Console: {msg.text}") if "ERR_FILE_NOT_FOUND" in msg.text else None
        )
        page.wait_for_selector(".plyr", timeout=10000)
        inject_plyr_playing_listener(page)
        page.click(config.SELECTORS["play_button"])

        try:
            page.wait_for_function(
                "() => window.__videoStartTime !== null",
                timeout=30000
            )
            video_start_ms = page.evaluate("window.__videoStartTime")
            report["videoStartTime"] = round(video_start_ms)
            allure.attach(f"{video_start_ms:.0f} ms", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)
        except Exception as e:
            report["videoStartTime"] = "Не удалось измерить"
            logger.warning(f"Не удалось измерить videoStartTime: {e}")
            allure.attach("Не удалось измерить", name="videoStartTime", attachment_type=allure.attachment_type.TEXT)
            
    with allure.step("Собрать метрики буферизации"):
        rebuffer_count = page.evaluate("window.__rebufferCount || 0")
        rebuffer_duration = page.evaluate("window.__rebufferDuration || 0")
        report["rebufferCount"] = rebuffer_count
        report["rebufferDuration"] = round(rebuffer_duration)

    with allure.step("Дождаться появления попапа оплаты (до 90 сек)"):
        popup_start = time.time()
        page.wait_for_selector(config.SELECTORS["popup"], timeout=90000)
        popup_time = time.time() - popup_start
        report["popupAppearTime"] = round(popup_time * 1000)
        logger.info(f"✅ Попап появился через {popup_time:.1f} сек")

    with allure.step("Перейти на страницу оплаты и открыть форму карты"):
        with page.expect_navigation():
            page.click(config.SELECTORS["popup_cta"])

        page.wait_for_selector(config.SELECTORS["payment_iframe"], timeout=15000)
        iframe = page.frame_locator(config.SELECTORS["payment_iframe"])
        iframe.locator(config.SELECTORS["pay_button_bank_card"]).wait_for(state="visible")
        iframe.locator(config.SELECTORS["pay_button_bank_card"]).click()
        iframe.locator(config.SELECTORS["pay_form_bank_card"]).wait_for(state="visible")

    # === Сохранение отчёта ===
    save_json_report(report)
    allure.attach.file("reports/user_flow_report.json", name="Full JSON Report", extension=".json")

    # === Проверка порога производительности ===
    assert report["pagePerformanceIndex"] >= config.TARGET_PAGE_PERFORMANCE_INDEX, \
        f"pagePerformanceIndex ({report['pagePerformanceIndex']}) < {config.TARGET_PAGE_PERFORMANCE_INDEX}"
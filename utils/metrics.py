from playwright.sync_api import sync_playwright
import time

# ДНС метрики

def collect_network_metrics(page):
    target_domain = "calls7.com"
    client = page.context.new_cdp_session(page)
    client.send("Network.enable")

    result = {
        "dnsResolveTime": 0.0,
        "connectTime": 0.0,
        "ttfb": 0.0,
        "found": False
    }

    def on_response_received(event):
        request_id = event["requestId"]
        resp = event.get("response", {})
        url_requested = resp.get("url", "")
        if target_domain in url_requested and not result["found"]:
            timing = resp.get("timing")
            if timing:
                dns = max(0, timing.get("dnsEnd", 0) - timing.get("dnsStart", 0))
                connect = max(0, timing.get("connectEnd", 0) - timing.get("connectStart", 0))
                # if dns == 0:
                #     dns = "Не измеряется, возможно закешировано"
                # if connect == 0:
                #     connect = "Не измеряется, возможно закешировано"
                ttfb = max(0, timing.get("sendEnd", 0) - (timing.get("requestTime", 0) * 1000))
                result.update({
                    "dnsResolveTime": dns,
                    "connectTime": connect,
                    "ttfb": ttfb,
                    "found": True
                })
            client.send("Network.disable")  # останавливаем после первого совпадения

    client.on("Network.responseReceived", on_response_received)

    return result


# Lighthouse метрики

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

# Замер метрик плеера

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
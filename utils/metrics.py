from playwright.sync_api import sync_playwright
import time



def wait_for_player_ready(page, timeout=30):
    """Ожидает готовность плеера с улучшенной диагностикой"""
    start_time = time.time()
    last_check_time = start_time
    checked_messages = 0
    
    print(f"[INFO] Starting to wait for player ready (timeout: {timeout}s)")
    
    while time.time() - start_time < timeout:
        try:
            result = page.evaluate("""
                () => {
                    if (!window.__consoleMessages) {
                        return { error: "Monitor not initialized" };
                    }
                    return {
                        playerReady: window.__playerReady || false,
                        playerReadyTime: window.__playerReadyTime || null,
                        playerReadyMessage: window.__playerReadyMessage || null,
                        messageCount: window.__consoleMessages.length,
                        recentMessages: window.__consoleMessages.slice(-20).map(m => ({
                            type: m.type,
                            message: m.message,
                            timestamp: m.timestamp
                        })),
                        allDcMessages: window.__consoleMessages
                            .filter(m => m.message.includes('[Dc]'))
                            .map(m => m.type + ': ' + m.message)
                    };
                }
            """)
            
            if "error" in result:
                print(f"[ERROR] Monitor error: {result['error']}")
                # Попробуем перезапустить мониторинг
                inject_console_monitor(page)
                time.sleep(1)
                continue
            
            if result["playerReady"]:
                ready_time = result["playerReadyTime"] / 1000  # Convert from JS timestamp
                print(f"[SUCCESS] Player ready detected!")
                print(f"[SUCCESS] Message: {result['playerReadyMessage']}")
                print(f"[SUCCESS] JS Timestamp: {result['playerReadyTime']}")
                print(f"[SUCCESS] Python Timestamp: {time.time()}")
                return ready_time
            
            # Логируем прогресс каждые 3 секунды
            current_time = time.time()
            if current_time - last_check_time >= 3:
                print(f"[DEBUG] Still waiting... {int(current_time - start_time)}s elapsed")
                print(f"[DEBUG] Total messages: {result['messageCount']}")
                print(f"[DEBUG] [Dc] messages: {len(result['allDcMessages'])}")
                
                if result["allDcMessages"]:
                    print(f"[DEBUG] Recent [Dc] messages:")
                    for msg in result["allDcMessages"][-5:]:
                        print(f"  - {msg}")
                
                last_check_time = current_time
            
            # Проверяем новые сообщения
            if result["messageCount"] > checked_messages:
                new_messages = result["messageCount"] - checked_messages
                if new_messages > 0:
                    recent = result["recentMessages"][-new_messages:]
                    for msg in recent:
                        if 'loadPlayer' in msg['message'] or 'player' in msg['message'].lower():
                            print(f"[MONITOR] Player-related: {msg['type']}: {msg['message']}")
                    checked_messages = result["messageCount"]
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"[ERROR] JS evaluation failed: {e}")
            time.sleep(1)
    
    # Таймаут - детальная диагностика
    print(f"[ERROR] TIMEOUT after {timeout} seconds")
    try:
        final_result = page.evaluate("""
            () => {
                if (!window.__consoleMessages) {
                    return { error: "No monitor data" };
                }
                return {
                    playerReady: window.__playerReady || false,
                    allMessages: window.__consoleMessages.map(m => m.type + ': ' + m.message),
                    dcMessages: window.__consoleMessages
                        .filter(m => m.message.includes('[Dc]'))
                        .map(m => m.type + ': ' + m.message),
                    playerMessages: window.__consoleMessages
                        .filter(m => m.message.toLowerCase().includes('player'))
                        .map(m => m.type + ': ' + m.message)
                };
            }
        """)
        
        if "error" in final_result:
            print(f"[DEBUG] {final_result['error']}")
        else:
            print(f"[DEBUG] Final status - Player ready: {final_result['playerReady']}")
            print(f"[DEBUG] Total messages: {len(final_result['allMessages'])}")
            print(f"[DEBUG] [Dc] messages ({len(final_result['dcMessages'])}")
            for msg in final_result['dcMessages']:
                print(f"  - {msg}")
            print(f"[DEBUG] Player-related messages ({len(final_result['playerMessages'])}):")
            for msg in final_result['playerMessages']:
                print(f"  - {msg}")
                
    except Exception as e:
        print(f"[ERROR] Final diagnosis failed: {e}")
    
    raise TimeoutError(f"Player ready not detected within {timeout} seconds")

def collect_network_metrics(page, target_domain = "calls7.com"):
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
                const cls = performance.getEntriesByType('layout-shift').reduce(
                        (sum, entry) => sum + (entry.hadRecentInput ? 0 : entry.value), 0
                );
                const fid = null;
                let tbt = null;
                const longTasks = performance.getEntriesByType('longtask');
                if (longTasks) {
                    tbt = longTasks.reduce((sum, task) => sum + task.duration, 0);
                }
                return {
                        ttfb: entries ? ttfb : null,
                        lcp: lcp ? lcp.renderTime || lcp.loadTime : null,
                        cls: cls || 0,
                        fid: null,  // FID требует реального взаимодействия
                        tbt: tbt > 0 ? tbt : null
                };
            }
        """)
    return metrics


# def collect_performance_metrics_after_video(page):
#     """
#     Ждёт появления <video>, затем измеряет LCP и другие метрики.
#     Используется для страниц фильмов.
#     """

#     return page.evaluate("""
#         () => {
#             const start = performance.now();
#             let lcpEntry = performance.getEntriesByName('largest-contentful-paint')[0];
#             while (!lcpEntry && (performance.now() - start) < 5000) {
#                 lcpEntry = performance.getEntriesByName('largest-contentful-paint')[0];
#             }

#             const nav = performance.getEntriesByType('navigation')[0];
#             const lcp = lcpEntry ? lcpEntry.startTime : 0;
#             const ttfb = nav ? nav.responseStart - nav.requestStart : 0;
#             const cls = 0;
#             const fid = 0;
#             let tbt = 0;
#             const longTasks = performance.getEntriesByType('longtask');
#             if (longTasks) {
#                 tbt = longTasks.reduce((sum, task) => sum + task.duration, 0);
#             }
#             return { lcp, ttfb, cls, fid, tbt };
#         }
#     """)

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
    
def inject_player_ready_listener(page):
    """
    Инжектирует слушатель console.log, чтобы поймать 'loadPlayer finished'
    и записать timestamp в window.__playerReadyTime.
    """
    page.evaluate("""
        // Сохраняем оригинальный console.log
        const originalLog = console.log;
        console.log = function (...args) {
            try {
                // Ищем строку "loadPlayer finished"
                const msg = args.map(String).join(' ');
                if (msg.includes('loadPlayer finished')) {
                    window.__playerReadyTime = performance.now();
                    console.info('[TEST] playerReadyTime:', window.__playerReadyTime);
                }
            } catch (e) {
                // Молча игнорируем — не ломаем сайт
            }
            return originalLog.apply(console, args);
        };
    """)
    
def wait_for_load_player_finished(page):
    """Ожидает сообщение [Dc] loadPlayer finished в консоли."""
    player_ready_time = None

    def on_console(msg):
        nonlocal player_ready_time
        try:
            text = msg.text
            print(f"[DEBUG] {text}\n")
            if "[Dc] loadPlayer finished" in text:
                # Записываем время (можно использовать performance.now() или time.time())
                player_ready_time = time.time()
                print(f"[PLAYER] loadPlayer finished зафиксировано: {text}")
        except Exception as e:
            pass  # молча игнорируем

    page.on("console", on_console)

    # Ждём 30 секунд — пока не появится сообщение
    start = time.time()
    while time.time() - start < 30:
        if player_ready_time is not None:
            return player_ready_time
        time.sleep(0.1)

        
    raise TimeoutError("[Dc] loadPlayer finished не обнаружено за 30 сек")

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
import time
from typing import Dict, List, Optional, Any
from playwright.sync_api import Page
import allure

from .base_plugin import FlowPlugin


class VideoMetricsPlugin(FlowPlugin):
    """Плагин для сбора метрик видео (все браузеры)"""
    
    PLUGIN_NAME = "video_metrics"
    SUPPORTED_BROWSERS = ["chromium", "firefox", "webkit"]  # Все браузеры
    
    def __init__(self, browser_type: str):
        super().__init__(browser_type)
        self.metrics = {
            "videoLoadTime": None,
            "timeToFirstFrame": None,
            "videoReadyState": None,
            "videoFound": False
        }
    
    def get_supported_hooks(self) -> Dict[str, List[str]]:
        return {
            "before_video_check": ["Подготовка к проверке видео", []],
            "video_check": ["Проверка наличия и состояния видео", []],
            "after_video_ready": ["Сбор метрик после готовности видео", []],
            "video_error": ["Обработка ошибок видео", ["error"]],
        }
    
    def execute_hook(self, hook_name: str, page: Page, context: Dict, **kwargs) -> Optional[Any]:
        """Сбор метрик видео"""
        
        try:
            if hook_name == "before_video_check":
                return self._prepare_video_check(page)
            
            elif hook_name == "video_check":
                return self._check_video_state(page, context)
            
            elif hook_name == "after_video_ready":
                return self._collect_video_metrics(page, context)
            
            elif hook_name == "video_error":
                return self._handle_video_error(page, context, kwargs.get('error'))
            
        except Exception as e:
            error_msg = f"Video Metrics Plugin error in {hook_name}: {str(e)}"
            context.setdefault("errors", []).append(error_msg)
            print(f"[VIDEO METRICS] Ошибка: {e}")
            return None
    
    def _prepare_video_check(self, page: Page) -> bool:
        """Подготовка к проверке видео - внедряем мониторинг"""
        try:
            # Внедряем универсальный мониторинг видео
            page.evaluate("""
                // Глобальные переменные для видео метрик
                window.__universalVideoMetrics = {
                    videoElements: 0,
                    videoWithSrc: 0,
                    videoReadyState: 0,
                    videoEvents: [],
                    videoLoadStart: null,
                    firstFrameTime: null
                };
                
                // Отслеживаем события видео
                function trackVideoEvents() {
                    const videos = document.querySelectorAll('video');
                    window.__universalVideoMetrics.videoElements = videos.length;
                    
                    videos.forEach((video, index) => {
                        if (video.src) {
                            window.__universalVideoMetrics.videoWithSrc++;
                        }
                        
                        // Отслеживаем загрузку
                        video.addEventListener('loadstart', () => {
                            window.__universalVideoMetrics.videoLoadStart = performance.now();
                            window.__universalVideoMetrics.videoEvents.push({
                                type: 'loadstart',
                                time: performance.now(),
                                videoIndex: index
                            });
                        });
                        
                        // Отслеживаем первый кадр
                        video.addEventListener('loadeddata', () => {
                            if (!window.__universalVideoMetrics.firstFrameTime) {
                                window.__universalVideoMetrics.firstFrameTime = performance.now();
                                window.__universalVideoMetrics.videoReadyState = video.readyState;
                            }
                            window.__universalVideoMetrics.videoEvents.push({
                                type: 'loadeddata',
                                time: performance.now(),
                                videoIndex: index,
                                readyState: video.readyState
                            });
                        });
                        
                        // Отслеживаем возможность воспроизведения
                        video.addEventListener('canplay', () => {
                            window.__universalVideoMetrics.videoEvents.push({
                                type: 'canplay',
                                time: performance.now(),
                                videoIndex: index
                            });
                        });
                        
                        // Отслеживаем начало воспроизведения
                        video.addEventListener('play', () => {
                            window.__universalVideoMetrics.videoEvents.push({
                                type: 'play',
                                time: performance.now(),
                                videoIndex: index
                            });
                        });
                    });
                }
                
                // Запускаем отслеживание
                if (document.readyState === 'complete') {
                    trackVideoEvents();
                } else {
                    window.addEventListener('load', trackVideoEvents);
                }
                
                // Периодическая проверка появления видео
                setInterval(() => {
                    const videos = document.querySelectorAll('video');
                    if (videos.length > window.__universalVideoMetrics.videoElements) {
                        trackVideoEvents();
                    }
                }, 1000);
            """)
            
            print("[VIDEO METRICS] Мониторинг видео инициализирован")
            return True
            
        except Exception as e:
            print(f"[VIDEO METRICS] Ошибка подготовки: {e}")
            return False
    
    def _check_video_state(self, page: Page, context: Dict) -> Dict:
        """Проверка состояния видео"""
        try:
            # Пробуем разные селекторы для видео
            video_selectors = [
                "video",
                ".plyr video",
                "[data-video] video",
                "video[src]",
                "iframe[src*='video']",
                "video:not([hidden])"
            ]
            
            video_found = False
            video_details = {}
            
            for selector in video_selectors:
                try:
                    elements = page.locator(selector)
                    count = elements.count()
                    if count > 0:
                        video_found = True
                        
                        # Получаем детали для первого видео
                        video_details = page.evaluate(f"""
                            (selector) => {{
                                const video = document.querySelector(selector);
                                if (!video) return {{}};
                                
                                return {{
                                    selector: selector,
                                    src: video.src,
                                    readyState: video.readyState,
                                    networkState: video.networkState,
                                    buffered: video.buffered.length,
                                    duration: video.duration,
                                    currentTime: video.currentTime,
                                    paused: video.paused,
                                    videoWidth: video.videoWidth,
                                    videoHeight: video.videoHeight
                                }};
                            }}
                        """, selector)
                        
                        break
                except:
                    continue
            
            self.metrics["videoFound"] = video_found
            self.metrics["videoDetails"] = video_details if video_found else {}
            
            # Если видео не найдено, добавляем предупреждение
            if not video_found:
                context.setdefault("warnings", []).append("Video element not found")
            
            print(f"[VIDEO METRICS] Видео найдено: {video_found}, детали: {video_details.get('src', 'N/A')}")
            return self.metrics
            
        except Exception as e:
            error_msg = f"Video check error: {str(e)}"
            context.setdefault("errors", []).append(error_msg)
            print(f"[VIDEO METRICS] Ошибка проверки: {e}")
            return self.metrics
    
    def _collect_video_metrics(self, page: Page, context: Dict) -> Dict:
        """Сбор метрик видео после готовности"""
        try:
            # Получаем метрики из JavaScript
            universal_metrics = page.evaluate("""
                () => {
                    return window.__universalVideoMetrics || {
                        videoElements: 0,
                        videoWithSrc: 0,
                        videoReadyState: 0,
                        videoEvents: [],
                        videoLoadStart: null,
                        firstFrameTime: null
                    };
                }
            """)
            
            # Рассчитываем время загрузки видео
            if universal_metrics.get("videoLoadStart") and universal_metrics.get("firstFrameTime"):
                video_load_time = universal_metrics["firstFrameTime"] - universal_metrics["videoLoadStart"]
                self.metrics["videoLoadTime"] = round(video_load_time)
                self.metrics["timeToFirstFrame"] = round(video_load_time)
            
            # Добавляем универсальные метрики
            self.metrics["universal"] = universal_metrics
            
            # Для браузеров без CDP используем альтернативные методы
            if self.browser_type != "chromium":
                self._collect_alternative_metrics(page)
            
            # Сохраняем в контекст
            if "video_metrics" not in context:
                context["video_metrics"] = {}
            
            context["video_metrics"]["universal"] = self.metrics
            
            # Прикрепляем к Allure
            allure.attach(
                json.dumps(self.metrics, indent=2, ensure_ascii=False),
                name="Universal Video Metrics",
                attachment_type=allure.attachment_type.JSON
            )
            
            print(f"[VIDEO METRICS] Собраны метрики: {self.metrics}")
            return self.metrics
            
        except Exception as e:
            error_msg = f"Video metrics collection error: {str(e)}"
            context.setdefault("errors", []).append(error_msg)
            print(f"[VIDEO METRICS] Ошибка сбора: {e}")
            return self.metrics
    
    def _collect_alternative_metrics(self, page: Page):
        """Альтернативные методы сбора метрик для не-Chromium браузеров"""
        try:
            # Используем Performance API для Firefox и WebKit
            performance_metrics = page.evaluate("""
                () => {
                    const metrics = {};
                    
                    // Собираем метрики навигации
                    const navigation = performance.getEntriesByType('navigation')[0];
                    if (navigation) {
                        metrics.navigation = {
                            dns: navigation.domainLookupEnd - navigation.domainLookupStart,
                            connect: navigation.connectEnd - navigation.connectStart,
                            ttfb: navigation.responseStart - navigation.requestStart,
                            domContentLoaded: navigation.domContentLoadedEventEnd,
                            load: navigation.loadEventEnd
                        };
                    }
                    
                    // Собираем метрики ресурсов (видео)
                    const resources = performance.getEntriesByType('resource');
                    const videoResources = resources.filter(r => 
                        r.initiatorType === 'video' || 
                        r.name.includes('.mp4') || 
                        r.name.includes('.m3u8') ||
                        r.name.includes('.webm')
                    );
                    
                    if (videoResources.length > 0) {
                        metrics.videoResources = videoResources.map(r => ({
                            name: r.name,
                            duration: r.duration,
                            startTime: r.startTime,
                            transferSize: r.transferSize
                        }));
                        
                        // Берем первое видео как основное
                        metrics.primaryVideo = videoResources[0];
                    }
                    
                    // Собираем метрики отрисовки
                    const paint = performance.getEntriesByType('paint');
                    if (paint.length > 0) {
                        metrics.paint = paint.map(p => ({
                            name: p.name,
                            startTime: p.startTime
                        }));
                    }
                    
                    return metrics;
                }
            """)
            
            self.metrics["performance_api"] = performance_metrics
            
        except Exception as e:
            print(f"[VIDEO METRICS] Альтернативные метрики недоступны: {e}")
    
    def _handle_video_error(self, page: Page, context: Dict, error: Any) -> Dict:
        """Обработка ошибок видео"""
        error_info = {
            "error": str(error) if error else "Unknown video error",
            "timestamp": time.time(),
            "browser": self.browser_type,
            "url": page.url
        }
        
        context.setdefault("video_errors", []).append(error_info)
        
        # Делаем скриншот при ошибке
        try:
            screenshot = page.screenshot()
            allure.attach(
                screenshot,
                name=f"video_error_{int(time.time())}",
                attachment_type=allure.attachment_type.PNG
            )
        except:
            pass
        
        print(f"[VIDEO METRICS] Ошибка видео: {error_info['error']}")
        return error_info
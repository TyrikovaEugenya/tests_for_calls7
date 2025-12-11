import time
from typing import Dict, List, Optional, Any
from playwright.sync_api import Page, CDPSession
import allure

from .base_plugin import FlowPlugin


class CDPPlugin(FlowPlugin):
    """Плагин для работы с Chrome DevTools Protocol (только Chromium)"""
    
    PLUGIN_NAME = "cdp"
    SUPPORTED_BROWSERS = ["chromium"]  # Только для Chromium!
    
    def __init__(self, browser_type: str):
        super().__init__(browser_type)
        self.cdp_session: Optional[CDPSession] = None
        self.video_metrics = {
            "rebufferCount": 0,
            "rebufferDuration": 0,
            "videoStartTime": None,
            "firstFrameTime": None
        }
    
    def get_supported_hooks(self) -> Dict[str, List[str]]:
        return {
            "before_test": ["Инициализация CDP сессии", []],
            "before_video_playback": ["Настройка мониторинга видео", []],
            "during_video_playback": ["Сбор метрик буферизации", []],
            "after_video_playback": ["Финализация метрик видео", []],
            "after_test": ["Закрытие CDP сессии", []],
        }
    
    def execute_hook(self, hook_name: str, page: Page, context: Dict, **kwargs) -> Optional[Any]:
        """Выполнение CDP операций"""
        
        if self._log_unsupported(hook_name):
            return None
        
        try:
            if hook_name == "before_test":
                return self._initialize_cdp(page)
            
            elif hook_name == "before_video_playback":
                return self._setup_video_monitoring(page)
            
            elif hook_name == "during_video_playback":
                return self._collect_video_metrics(page)
            
            elif hook_name == "after_video_playback":
                return self._finalize_video_metrics(page, context)
            
            elif hook_name == "after_test":
                return self._close_cdp()
            
        except Exception as e:
            error_msg = f"CDP Plugin error in {hook_name}: {str(e)}"
            context.setdefault("errors", []).append(error_msg)
            print(f"[CDP] Ошибка: {e}")
            return None
    
    def _initialize_cdp(self, page: Page) -> bool:
        """Инициализация CDP сессии"""
        try:
            # Получаем контекст страницы и создаем CDP сессию
            self.cdp_session = page.context.new_cdp_session(page)
            
            # Включаем необходимые домены
            self.cdp_session.send("Runtime.enable")
            self.cdp_session.send("Log.enable")
            self.cdp_session.send("Network.enable")
            self.cdp_session.send("Performance.enable")
            
            # Настраиваем слушатель логов для детекции видео событий
            self.cdp_session.on("Log.entryAdded", self._handle_log_entry)
            
            print("[CDP] Сессия инициализирована")
            return True
            
        except Exception as e:
            print(f"[CDP] Ошибка инициализации: {e}")
            return False
    
    def _setup_video_monitoring(self, page: Page) -> bool:
        """Настройка мониторинга видео через CDP"""
        try:
            # Внедряем JavaScript для отслеживания событий видео
            page.evaluate("""
                // Создаем глобальные переменные для метрик
                window.__videoMetrics = {
                    rebufferCount: 0,
                    rebufferDuration: 0,
                    videoStartTime: null,
                    firstFrameTime: null,
                    lastPlayTime: null,
                    waitingStart: null
                };
                
                // Функция для отслеживания событий видео
                function setupVideoMonitoring() {
                    const video = document.querySelector('video');
                    if (!video) return false;
                    
                    video.addEventListener('waiting', () => {
                        window.__videoMetrics.waitingStart = performance.now();
                        console.log('[CDP] Video waiting started');
                    });
                    
                    video.addEventListener('playing', () => {
                        if (window.__videoMetrics.waitingStart) {
                            const waitDuration = performance.now() - window.__videoMetrics.waitingStart;
                            window.__videoMetrics.rebufferDuration += waitDuration;
                            window.__videoMetrics.rebufferCount++;
                            window.__videoMetrics.waitingStart = null;
                            console.log(`[CDP] Rebuffer: ${waitDuration}ms`);
                        }
                        
                        if (!window.__videoMetrics.firstFrameTime) {
                            window.__videoMetrics.firstFrameTime = performance.now();
                        }
                    });
                    
                    video.addEventListener('loadeddata', () => {
                        if (!window.__videoMetrics.videoStartTime) {
                            window.__videoMetrics.videoStartTime = performance.now();
                            console.log('[CDP] Video data loaded');
                        }
                    });
                    
                    return true;
                }
                
                // Пытаемся найти видео и настроить мониторинг
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', setupVideoMonitoring);
                } else {
                    setupVideoMonitoring();
                }
                
                // Периодическая проверка появления видео
                const checkInterval = setInterval(() => {
                    if (document.querySelector('video') && !window.__videoMonitoringSetup) {
                        setupVideoMonitoring();
                        window.__videoMonitoringSetup = true;
                        clearInterval(checkInterval);
                    }
                }, 1000);
            """)
            
            print("[CDP] Мониторинг видео настроен")
            return True
            
        except Exception as e:
            print(f"[CDP] Ошибка настройки мониторинга: {e}")
            return False
    
    def _handle_log_entry(self, params: Dict):
        """Обработка логов из CDP"""
        try:
            entry = params.get("entry", {})
            text = entry.get("text", "")
            
            # Детектируем события видео из логов
            if "[Dc]" in text or "video" in text.lower() or "player" in text.lower():
                print(f"[CDP LOG] {text[:100]}")
                
        except Exception as e:
            print(f"[CDP] Ошибка обработки лога: {e}")
    
    def _collect_video_metrics(self, page: Page) -> Dict:
        """Сбор текущих метрик видео"""
        try:
            # Получаем метрики через JavaScript
            metrics = page.evaluate("""
                () => {
                    return window.__videoMetrics || {
                        rebufferCount: 0,
                        rebufferDuration: 0,
                        videoStartTime: null,
                        firstFrameTime: null
                    };
                }
            """)
            
            # Также пробуем получить метрики через Performance API
            perf_metrics = page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    if (videos.length === 0) return null;
                    
                    const video = videos[0];
                    const entries = performance.getEntriesByName(video.src);
                    const videoEntry = entries.length > 0 ? entries[0] : null;
                    
                    return {
                        readyState: video.readyState,
                        networkState: video.networkState,
                        buffered: video.buffered.length ? 
                            video.buffered.end(video.buffered.length - 1) - video.buffered.start(0) : 0,
                        loadTime: videoEntry ? videoEntry.duration : null,
                        currentTime: video.currentTime,
                        duration: video.duration
                    };
                }
            """)
            
            # Обновляем метрики
            self.video_metrics.update(metrics)
            if perf_metrics:
                self.video_metrics["performance"] = perf_metrics
            
            return self.video_metrics
            
        except Exception as e:
            print(f"[CDP] Ошибка сбора метрик: {e}")
            return self.video_metrics
    
    def _finalize_video_metrics(self, page: Page, context: Dict) -> Dict:
        """Финальный сбор и сохранение метрик видео"""
        try:
            # Финальный сбор метрик
            final_metrics = self._collect_video_metrics(page)
            
            # Рассчитываем время до первого кадра
            if final_metrics.get("videoStartTime") and final_metrics.get("firstFrameTime"):
                final_metrics["timeToFirstFrame"] = (
                    final_metrics["firstFrameTime"] - final_metrics["videoStartTime"]
                )
            
            # Сохраняем в контекст
            if "video_metrics" not in context:
                context["video_metrics"] = {}
            
            context["video_metrics"]["cdp"] = final_metrics
            
            # Прикрепляем к Allure
            allure.attach(
                json.dumps(final_metrics, indent=2, ensure_ascii=False),
                name="CDP Video Metrics",
                attachment_type=allure.attachment_type.JSON
            )
            
            print(f"[CDP] Финальные метрики: {final_metrics}")
            return final_metrics
            
        except Exception as e:
            error_msg = f"CDP finalization error: {str(e)}"
            context.setdefault("errors", []).append(error_msg)
            print(f"[CDP] Ошибка финализации: {e}")
            return self.video_metrics
    
    def _close_cdp(self) -> bool:
        """Закрытие CDP сессии"""
        try:
            if self.cdp_session:
                self.cdp_session.detach()
                self.cdp_session = None
                print("[CDP] Сессия закрыта")
            return True
        except Exception as e:
            print(f"[CDP] Ошибка закрытия сессии: {e}")
            return False
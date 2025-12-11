import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from playwright.sync_api import Page
import allure
import subprocess
import tempfile

from .base_plugin import FlowPlugin


class LighthousePlugin(FlowPlugin):
    """Плагин для сбора Lighthouse метрик (только Chromium)"""
    
    PLUGIN_NAME = "lighthouse"
    SUPPORTED_BROWSERS = ["chromium"]
    
    def __init__(self, browser_type: str, lighthouse_path: str = "lighthouse"):
        super().__init__(browser_type)
        self.lighthouse_path = lighthouse_path
        self.reports_dir = Path("reports") / "lighthouse"
        self.reports_dir.mkdir(exist_ok=True, parents=True)
    
    def get_supported_hooks(self) -> Dict[str, List[str]]:
        return {
            "after_page_load": ["Сбор Lighthouse метрик после загрузки страницы", ["url"]],
            "after_video_ready": ["Сбор Lighthouse метрик после готовности видео", ["url"]],
            "after_payment_page": ["Сбор Lighthouse метрик на странице оплаты", ["url"]],
        }
    
    def execute_hook(self, hook_name: str, page: Page, context: Dict, **kwargs) -> Optional[Any]:
        """Выполнение Lighthouse анализа"""
        
        # Проверяем поддержку браузера
        if self._log_unsupported(hook_name):
            return None
        
        try:
            # Получаем текущий URL
            url = kwargs.get('url') or page.url
            
            # Уникальное имя для отчета
            timestamp = int(time.time())
            safe_url = url.split("//")[-1].replace("/", "_")[:50]
            report_name = f"{hook_name}_{safe_url}_{timestamp}"
            
            with allure.step(f"Lighthouse анализ ({hook_name})"):
                print(f"[LIGHTHOUSE] Запуск для {url}")
                
                # Запускаем Lighthouse через CLI
                report_path = self.reports_dir / f"{report_name}.json"
                
                # Формируем команду для Lighthouse
                cmd = [
                    self.lighthouse_path,
                    url,
                    "--output=json",
                    f"--output-path={report_path}",
                    "--chrome-flags='--headless --no-sandbox'",
                    "--only-categories=performance,accessibility,best-practices,seo",
                    "--form-factor=desktop" if kwargs.get('device') == 'Desktop' else "--form-factor=mobile",
                    "--throttling.cpuSlowdownMultiplier=4" if kwargs.get('throttling') != 'No_throttling' else "",
                    "--quiet"
                ]
                
                # Запускаем процесс
                result = subprocess.run(
                    [arg for arg in cmd if arg],  # Убираем пустые аргументы
                    capture_output=True,
                    text=True,
                    timeout=120  # Таймаут 2 минуты
                )
                
                if result.returncode == 0:
                    # Читаем отчет
                    with open(report_path, 'r', encoding='utf-8') as f:
                        lh_report = json.load(f)
                    
                    # Извлекаем ключевые метрики
                    metrics = self._extract_metrics(lh_report)
                    
                    # Сохраняем в контекст
                    if "lighthouse" not in context:
                        context["lighthouse"] = {}
                    context["lighthouse"][hook_name] = metrics
                    
                    # Прикрепляем отчет к Allure
                    allure.attach.file(
                        str(report_path),
                        name=f"Lighthouse Report - {hook_name}",
                        extension="json"
                    )
                    
                    # Генерируем HTML отчет для удобства просмотра
                    html_report_path = self._generate_html_report(lh_report, report_name)
                    
                    print(f"[LIGHTHOUSE] Успешно: {metrics.get('performance_score', 0):.1f} баллов")
                    return metrics
                else:
                    error_msg = f"Lighthouse failed: {result.stderr}"
                    context.setdefault("errors", []).append(error_msg)
                    print(f"[LIGHTHOUSE] Ошибка: {error_msg}")
                    return None
                    
        except subprocess.TimeoutExpired:
            error_msg = "Lighthouse timeout (120 seconds)"
            context.setdefault("errors", []).append(error_msg)
            print(f"[LIGHTHOUSE] Таймаут")
            return None
        except Exception as e:
            error_msg = f"Lighthouse error: {str(e)}"
            context.setdefault("errors", []).append(error_msg)
            print(f"[LIGHTHOUSE] Ошибка: {e}")
            return None
    
    def _extract_metrics(self, lh_report: Dict) -> Dict:
        """Извлечение ключевых метрик из Lighthouse отчета"""
        try:
            audits = lh_report.get("audits", {})
            categories = lh_report.get("categories", {})
            
            return {
                "performance_score": round(categories.get("performance", {}).get("score", 0) * 100, 1),
                "accessibility_score": round(categories.get("accessibility", {}).get("score", 0) * 100, 1),
                "best_practices_score": round(categories.get("best-practices", {}).get("score", 0) * 100, 1),
                "seo_score": round(categories.get("seo", {}).get("score", 0) * 100, 1),
                
                # Core Web Vitals
                "lcp": audits.get("largest-contentful-paint", {}).get("numericValue", 0),
                "fcp": audits.get("first-contentful-paint", {}).get("numericValue", 0),
                "cls": audits.get("cumulative-layout-shift", {}).get("numericValue", 0),
                "tbt": audits.get("total-blocking-time", {}).get("numericValue", 0),
                "si": audits.get("speed-index", {}).get("numericValue", 0),
                
                # Дополнительные метрики
                "tti": audits.get("interactive", {}).get("numericValue", 0),
                "fmp": audits.get("first-meaningful-paint", {}).get("numericValue", 0),
                "fci": audits.get("first-cpu-idle", {}).get("numericValue", 0),
                "mpfid": audits.get("max-potential-fid", {}).get("numericValue", 0),
            }
        except Exception as e:
            print(f"[WARNING] Failed to extract Lighthouse metrics: {e}")
            return {}
    
    def _generate_html_report(self, lh_report: Dict, report_name: str) -> Path:
        """Генерация HTML отчета для удобства просмотра"""
        try:
            html_path = self.reports_dir / f"{report_name}.html"
            
            # Простой HTML шаблон
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Lighthouse Report - {report_name}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .metric {{ margin: 10px 0; padding: 10px; background: #f5f5f5; }}
                    .score {{ font-size: 24px; font-weight: bold; }}
                    .good {{ color: green; }}
                    .average {{ color: orange; }}
                    .poor {{ color: red; }}
                </style>
            </head>
            <body>
                <h1>Lighthouse Report: {report_name}</h1>
                <div id="metrics"></div>
                <script>
                    const report = {json.dumps(lh_report, indent=2)};
                    
                    function renderMetrics() {{
                        const container = document.getElementById('metrics');
                        const categories = report.categories || {{}};
                        
                        for (const [name, category] of Object.entries(categories)) {{
                            const score = category.score * 100;
                            const scoreClass = score >= 90 ? 'good' : score >= 50 ? 'average' : 'poor';
                            
                            container.innerHTML += `
                                <div class="metric">
                                    <h2>${{name.toUpperCase()}}</h2>
                                    <div class="score ${{scoreClass}}">${{score.toFixed(1)}}/100</div>
                                </div>
                            `;
                        }}
                    }}
                    
                    renderMetrics();
                </script>
            </body>
            </html>
            """
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_template)
            
            return html_path
        except Exception as e:
            print(f"[WARNING] Failed to generate HTML report: {e}")
            return None
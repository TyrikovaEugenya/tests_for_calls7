import subprocess
import json
import tempfile
from pathlib import Path
import config

def run_lighthouse_for_url(url: str, timeout_sec: int = 60) -> dict:
    chromium_path = config.CHROMIUM_PATH
    """Запускает Lighthouse CLI и возвращает JSON-отчёт."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "lh_report.json"
        cmd = [
            "lighthouse",
            url,
            "--port=9222",
            "--skip-autolaunch",
            "--output=json",
            f"--output-path={output}",
            "--quiet",
            f"--chrome-path={chromium_path}",
            "--chrome-flags=--headless=new --disable-gpu --disable-dev-shm-usage --disable-setuid-sandbox --single-process",
            "--only-categories=performance",
            "--disable-storage-reset",
            "--throttling-method=provided"  # используем сеть из Playwright (если настроена)
        ]

        try:
            subprocess.run(cmd, check=True, timeout=timeout_sec, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            with open(output, "r", encoding="utf-8") as f:
                return json.load(f)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Lighthouse timed out after {timeout_sec}s")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Lighthouse failed: {e.stderr.decode() if e.stderr else 'unknown error'}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error: {e}")


def extract_metrics_from_lighthouse(report: dict) -> dict:
    """Извлекает числовые метрики из Lighthouse-отчёта."""
    a = report.get("audits", {})
    return {
        "lcp": a.get("largest-contentful-paint", {}).get("numericValue"),
        "cls": a.get("cumulative-layout-shift", {}).get("numericValue"),
        "tbt": a.get("total-blocking-time", {}).get("numericValue"),
        "ttfb": a.get("server-response-time", {}).get("numericValue"),
        "inp": a.get("interaction-to-next-paint", {}).get("numericValue"),  # вместо FID
        "fcp": a.get("first-contentful-paint", {}).get("numericValue"),
        "performance_score": report.get("categories", {}).get("performance", {}).get("score")
    }
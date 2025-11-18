"""
Скрипт для сбора всех URL страниц фильмов на calls7.com
Поддерживает пагинацию через ?offset=...&limit=...
Сохраняет уникальные URL в films.json и films.txt
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def collect_film_urls(
    base_url: str = "https://calls7.com",
    limit: int = 100,
    max_pages: int = 200,  # ~20 000 страниц максимум
    output_dir: str = "data"
) -> list:
    """
    Собирает все URL фильмов с calls7.com через пагинацию.
    
    :param base_url: базовый URL
    :param limit: количество фильмов на странице (макс. 100)
    :param max_pages: максимальное число страниц для обхода
    :param output_dir: папка для сохранения результатов
    :return: список уникальных URL
    """
    print(f"🚀 Сбор URL фильмов с {base_url} (limit={limit})...")
    film_urls = set()
    total_scraped = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for page_num in range(max_pages):
            offset = page_num * limit
            url = f"{base_url}/?offset={offset}&limit={limit}"
            print(f"  📄 Страница {page_num + 1} ({offset}-{offset + limit}): {url}")

            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)

                # Извлекаем все ссылки на фильмы через JS (надёжнее, чем CSS)
                # Ищем ссылки, содержащие /movie/, /kvest/, /chernyy-zamok/, /mara/, /calls7/
                urls = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('.movie-card[data-url]'))
                        .map(el => el.getAttribute('data-url'))
                        .filter(Boolean)
                        .map(slug => {
                            const url = new URL(slug, document.baseURI);
                            url.search = '';
                            url.hash = '';
                            return url.href;
                        });
                }""")

                new_urls = [u for u in urls if u not in film_urls]
                film_urls.update(urls)
                total_scraped += len(new_urls)

                print(f"    ➕ Найдено: {len(new_urls)} новых URL (всего: {len(film_urls)})")

                # Если новых URL нет — выходим
                if len(new_urls) == 0 and page_num > 0:
                    print("    🛑 Новые фильмы не найдены — завершаем пагинацию.")
                    break

                # Защита от rate-limit
                time.sleep(0.5)

            except PlaywrightTimeoutError:
                print(f"    ⚠️ Таймаут при загрузке {url} — пропускаем.")
                break
            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
                break

        browser.close()

    print(f"\n✅ Всего собрано уникальных URL: {len(film_urls)}")
    return sorted(film_urls)


def save_results(film_urls: list, output_dir: str = "data"):
    """Сохраняет результаты в JSON и TXT."""
    Path(output_dir).mkdir(exist_ok=True)

    # JSON — для программной обработки
    json_path = Path(output_dir) / "films.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(film_urls),
            "urls": film_urls,
            "source": "calls7.com",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }, f, indent=2, ensure_ascii=False)
    print(f"📁 Сохранено: {json_path}")

    # TXT — для человека / grep / CI
    txt_path = Path(output_dir) / "films.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        for url in film_urls:
            f.write(url + "\n")
    print(f"📁 Сохранено: {txt_path}")


if __name__ == "__main__":
    urls = collect_film_urls(
        base_url="https://calls7.com",
        limit=100,          # максимум, который сайт принимает
        max_pages=200       # ~20 000 страниц
    )
    save_results(urls, output_dir="data")

    # Пример первых 5
    print("\n📋 Примеры URL:")
    for url in urls[:5]:
        print(f"  - {url}")
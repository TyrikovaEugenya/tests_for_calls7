import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # Запускаем и сразу закрываем, чтобы инициализировать
    b = p.chromium.launch(headless=True)
    b.close()

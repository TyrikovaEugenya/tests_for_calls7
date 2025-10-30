# tests_for_calls7

## Установка

1. **Клонируйте репозиторий**
   ```bash
   git clone https://github.com/your-username/calls7-tests.git
   cd calls7-tests
   ```

2. **Создайте виртуальное окружение**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate  # Windows
   ```

3. **Установите зависимости**
   ```bash
   pip install -r requirements.txt
   ```

4. **Установите браузер Playwright**
   ```bash
   playwright install chromium
   ```

5. **Установка Allure Cli**
Скачайте и распакуйте утилиту из официального репозитория [Releases · allure-framework/allure2](https://github.com/allure-framework/allure2/releases)

6. **Установка кодеков для Chromium**
Скачайте и распакуйте файлы для работы с видео-контентом через Chromium (например с сайта [Download latest stable Chromium binaries (64-bit and 32-bit)](https://chromium.woolyss.com/))
---

## Запуск тестов

### Минимальный запуск (по умолчанию)
```bash
python -m pytest tests/ --alluredir=./allure-results -v
```

 Тест автоматически использует URL фильма из фикстуры pytest_addoption (`conftest.py`).  
Чтобы задать свой URL, см. раздел «Запуск с кастомным URL».

---

## Генерация и просмотр отчёта

После завершения теста выполните:

```bash
# 1. Сгенерировать HTML-отчёт Allure
allure generate ./allure-results --clean -o ./allure-report

# 2. Запустить локальный сервер
cd allure-report
python3 -m http.server 8000
```

Откройте в браузере http://localhost:8000

Чтобы очистить папки с отчетами, выполните
```Shell
rm -rf allure-results allure-report reports
```

---

## Запуск с кастомным URL фильма

Чтобы протестировать конкретный фильм, укажите его URL через параметр `--film-url`:

```bash
python -m pytest tests/ \
  --film-url="https://calls7.com/kvest/5654" \
  --alluredir=./allure-results -v
```

---


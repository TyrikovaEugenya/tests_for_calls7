# tests_for_calls7
Данная инструкция по установке наиболее актуальна для использования на устройствах с macOS.

## Подготовка устройства
 1. **Установка Xcode Command Line Tools**
**Обязательный шаг** - устанавливает базовые инструменты разработчика:
```bash
xcode-select --install
```

Нажмите "Install" в появившемся окне. Процесс займет 10-15 минут.

 2. **Установка Homebrew**

**Менеджер пакетов для macOS** - упростит установку остальных компонентов:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

После установки выполните:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Перезапустите терминал и проверьте установку командой brew --version

3. **Установка python**
```bash
brew install python
python3 --version # Проверим установку
pip3 --version
```

4. **Установка Java**
Для работы Allure необходима установка Java.
```bash
# Прооверим установлена ли Java
java -version
# Если нет
brew install openjdk
```

## Установка проекта

1. **Клонируйте репозиторий** (пропустите этот шаг если скачали архив)
   ```bash
   git clone https://github.com/your-username/calls7-tests.git
   cd calls7-tests
   ```

2. **Создайте виртуальное окружение**
Перейдите в папку проекта, если еще не сделали этого (cd calls7-tests)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate  # Windows
   ```

3. **Установите зависимости**
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Установите браузеры Playwright**
   ```bash
   playwright install chromium
   playwright install firefox
   playwright install webkit
   ```

5. **Установка Allure Cli**
Установите через Homebrew:
```bash
brew install allure
allure --version
```
Если это не сработает:
```bash
# Скачайте последнюю версию
curl -L -o allure-2.24.0.tgz https://github.com/allure-framework/allure2/releases/download/2.24.0/allure-2.24.0.tgz

# Распакуйте
tar -xvzf allure-2.24.0.tgz

# Переместите в системную папку
sudo mv allure-2.24.0 /usr/local/allure

# Добавьте в PATH
echo 'export PATH="/usr/local/allure/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```
Или:
Скачайте и распакуйте утилиту из официального репозитория [Releases · allure-framework/allure2](https://github.com/allure-framework/allure2/releases)

6. **Установка кодеков для Chromium**
- Перейдите на [chromium.woolyss.com](https://chromium.woolyss.com/)
- Выберите: **macOS** → **64-bit** → **with widevine and additional codecs**
- Скачайте последнюю версию (например: `chromium-mac_xxxxxx.zip`)
- Распакуйте и установите:
```bash
# Распакуйте скачанный архив
unzip chromium-mac_xxxxxx.zip -d ChromiumApp

# Создайте папку для Chromium
mkdir -p ~/Applications/Chromium
mv ChromiumApp/chrome-mac/Chromium.app ~/Applications/Chromium/
```

7. Пропишите **CHROMIUM_PATH** в config.py
CHROMIUM_PATH = '/Users/ВАШЕ_ИМЯ_ПОЛЬЗОВАТЕЛЯ/Applications/Chromium/Chromium.app/Contents/MacOS/Chromium'
Чтобы узнать имя пользователя используйте команду whoami
8. Установить **Node.js**

```Shell
brew install node
node --version
npm --version

```
9. Установить **Lighthouse**
```Shell
npm install -g lighthouse
lighthouse --version
```

---

## Дополнительные настройки
Настройка прав для Chromium
```bash
# Дайте права на выполнение
chmod +x ~/Applications/Chromium/Chromium.app/Contents/MacOS/Chromium

# Если возникают проблемы с запуском, откройте Chromium через Finder первый раз
open ~/Applications/Chromium/Chromium.app
```
Настройка переменных окружения
```bash
echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
echo 'export PATH="/usr/local/allure/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---
## Запуск тестов

Для проверки работоспособности запускайте тесты по одному, для показательных отчетов - параметризованные.
Подробности о возможных опциях можно найти в документации файла conftest.py.

### Минимальный запуск для одного фильма (страница по умолчанию)
Для браузера Firefox (для Webkit в опции --browser указать webkit)
```bash
python -m pytest --browser=firefox --pay-method=sbp -m "domain_goodmovie and browser_firefox and single_run" --alluredir=./allure-results -v
```

Для браузера Chromium
```bash
python -m pytest --browser=chromium --pay-method=sbp -m "domain_goodmovie and browser_chromium and single_run" --alluredir=./allure-results -v
```
Тест автоматически использует URL фильма из фикстуры pytest_addoption (`conftest.py`).  
Чтобы задать свой URL, см. раздел «Запуск с кастомным URL».

### Запуск параметризованных тестов по браузерам (для одной страницы)
Предупреждение: параметризация позволяет составлять все возможные комбинации входных параметров, тестов создается и запускаестся много, на каждый такой запуск может потребоваться до часа. Эти тесты рекомендуется запускать при уверенности, что сборка работает. 
```bash
# Chromium
python -m pytest --pay-method=sbp -m "domain_goodmovie and parametrized and browser_chromium" --alluredir=./allure-results -v
# Firefox и Webkit
python -m pytest --pay-method=sbp -m "domain_goodmovie and parametrized and browser_firefox" --alluredir=./allure-results -v
```

### Запуск тестов для нескольких страниц фильмов
Для запуска тестов для набора страниц из файла использйте опции --film-list (путь до файла со списком) и --film-limit (количество страниц из списка).
Не рекомендуется использовать одновременно с маркером parametrized, так как продолжительность тестов вырастает.
Пример запуска:

```bash
python -m pytest --film-list=data/goodmovie_films.json --film-limit=3 --pay-method=sbp -m "domain_goodmovie and browser_chromium and single_run" --alluredir=./allure-results -v -s
```

### Запуск с кастомным URL фильма

Чтобы протестировать конкретный фильм, укажите его URL через параметр `--film-url`:

```bash
python -m pytest --film-url=https://tests.goodmovie.net/kulinarnyy-tehnikum/6110 --pay-method=sbp -m "domain_goodmovie and browser_chromium and single_run" --alluredir=./allure-results -v
```

---

## Генерация и просмотр отчёта Allure

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

## Просмотр отчетов в челокечитаемом формате
После завершения теста генерируются отчеты в папке reports.
Для просмотра файлов в формате .md вам может понадобиться скачать приложение (или воспользуйтесь онлайн ридерами).
- RUN_SUMMARY* - предоставляет основную информацию по запуску.
- CLUSTER_COMPARISON* - отчет по кластерам.
- issues.log - информация об ошибках для разработчиков.

---

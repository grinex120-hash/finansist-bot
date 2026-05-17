@echo off
chcp 65001 >nul
title Финансист - Установка и запуск

echo ========================================
echo   Финансист - установка зависимостей
echo ========================================
echo.

:: Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python с python.org
    pause
    exit /b 1
)

:: Создание виртуального окружения через venv (стандартный)
if not exist "venv" (
    echo [1/5] Создаём виртуальное окружение...
    python -m venv venv
    if errorlevel 1 (
        echo Не удалось создать venv. Пробуем через virtualenv...
        pip install virtualenv --quiet
        python -m virtualenv venv
        if errorlevel 1 (
            echo Не удалось создать виртуальное окружение.
            echo Устанавливаем зависимости глобально.
            set USE_GLOBAL=1
            goto install
        )
    )
)

:: Проверка существования activate.bat
if not exist "venv\Scripts\activate.bat" (
    echo [ОШИБКА] Файл activate.bat не найден в venv\Scripts\
    echo Пытаюсь пересоздать через virtualenv...
    rmdir /s /q venv 2>nul
    pip install virtualenv --quiet
    python -m virtualenv venv
    if not exist "venv\Scripts\activate.bat" (
        echo Не удалось создать виртуальное окружение. Установка глобально.
        set USE_GLOBAL=1
        goto install
    )
)

:: Активация
echo [2/5] Активируем окружение...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Не удалось активировать окружение. Устанавливаю глобально.
    set USE_GLOBAL=1
    goto install
)

:install
:: Обновление pip
echo [3/5] Обновляем pip...
python -m pip install --upgrade pip

:: Установка зависимостей
echo [4/5] Устанавливаем зависимости...
pip install -r requirements.txt

if errorlevel 1 (
    echo Ошибка при установке зависимостей.
    pause
    exit /b 1
)

:: Проверка наличия .env файла
echo [5/5] Проверяем настройки...
if not exist ".env" (
    echo.
    echo [ВНИМАНИЕ] Файл .env не найден.
    if exist ".env.example" (
        copy .env.example .env
        echo Создан .env из примера. Отредактируйте его своими токенами.
        echo Открываю блокнот для редактирования...
        notepad .env
    ) else (
        echo Создайте файл .env вручную с содержимым:
        echo TELEGRAM_TOKEN=ваш_токен_от_BotFather
        echo GIGACHAT_KEY=ваш_ключ_от_GigaChat
        echo.
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo   Готово! Запускаем бота...
echo ========================================
if "%USE_GLOBAL%"=="1" (
    echo ВНИМАНИЕ: Зависимости установлены глобально.
)
python main.py

pause
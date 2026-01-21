#!/bin/bash

echo "🚀 Быстрый запуск ASinglePoint_Bot"
echo "=================================="
echo ""

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен!"
    echo "Установите Python3:"
    echo "  Mac: brew install python"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    exit 1
fi

# Проверяем pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не установлен!"
    exit 1
fi

# Устанавливаем зависимости
echo "📦 Устанавливаю зависимости..."
pip3 install -r requirements.txt 2>/dev/null || {
    echo "⚠️  Использую pip вместо pip3..."
    pip install -r requirements.txt
}

# Проверяем токен
if grep -q "ВАШ_ТОКЕН_ЗДЕСЬ" bot.py || grep -q "8393104234:AAGwcbmK8qlxiIzcJIPIqeo3JAz8tBNuYfo" bot.py; then
    echo ""
    echo "⚠️  ВНИМАНИЕ: Используется демо-токен или шаблон!"
    echo "Замените токен в файле bot.py на свой:"
    echo "1. Напишите @BotFather в Telegram"
    echo "2. Создайте бота: /newbot"
    echo "3. Скопируйте токен"
    echo "4. Откройте bot.py и замените API_TOKEN"
    echo ""
    read -p "Запустить с текущим токеном? (y/n): " choice
    if [[ ! $choice =~ ^[Yy]$ ]]; then
        echo "❌ Запуск отменен"
        exit 1
    fi
fi

# Запускаем бота
echo "🤖 Запускаю бота..."
python3 bot.py
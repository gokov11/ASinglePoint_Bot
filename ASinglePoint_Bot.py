# ==================== КРИТИЧЕСКИЕ ИЗМЕНЕНИЯ ДЛЯ RENDER ====================
import os
import asyncio
import logging
from aiohttp import web
import threading

# Настройка для Render
PORT = int(os.environ.get("PORT", 8080))  # Render предоставляет порт через переменную окружения

# Создаем простой веб-сервер для проверки здоровья (health check)
async def health_check(request):
    return web.Response(text="Bot is running")

# Запуск веб-сервера в отдельном потоке
def run_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_server():
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        print(f"🌐 Web server started on port {PORT}")
    
    loop.run_until_complete(start_server())
    loop.run_forever()

# Запускаем веб-сервер в фоновом потоке
web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()
# ==========================================================================
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, date, timedelta
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import matplotlib.pyplot as plt
import io
import pytz
import numpy as np
from typing import Dict, List, Tuple
import random

# ==================== НАСТРОЙКИ ====================
API_TOKEN = os.getenv('TELEGRAM_TOKEN', '8393104234:AAGwcbmK8qlxiIzcJIPIqeo3JAz8tBNuYfo')
DATABASE = 'asinglepoint.db'
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
# ===================================================

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

# ==================== СОСТОЯНИЯ (FORMS) ====================
class DebtForm(StatesGroup):
    waiting_for_debt_name = State()
    waiting_for_debt_total = State()
    waiting_for_debt_payment = State()
    waiting_for_debt_date = State()

class PayDebtForm(StatesGroup):
    waiting_for_payment_amount = State()
    waiting_for_payment_type = State()

class ExpenseForm(StatesGroup):
    waiting_for_expense_amount = State()
    waiting_for_expense_category = State()
    waiting_for_expense_description = State()

class IncomeForm(StatesGroup):
    waiting_for_income_amount = State()
    waiting_for_income_source = State()
    waiting_for_income_description = State()

class NotificationForm(StatesGroup):
    waiting_for_days_before = State()

class EditDebtForm(StatesGroup):
    waiting_for_debt_selection = State()
    waiting_for_field_selection = State()
    waiting_for_new_value = State()

class SavingsGoalForm(StatesGroup):
    waiting_for_goal_name = State()
    waiting_for_goal_target = State()
    waiting_for_goal_deadline = State()
    waiting_for_goal_category = State()

class DepositToGoalForm(StatesGroup):
    waiting_for_goal_selection = State()
    waiting_for_deposit_amount = State()

class BudgetForm(StatesGroup):
    waiting_for_budget_category = State()
    waiting_for_budget_amount = State()
    waiting_for_budget_period = State()

class EditBudgetForm(StatesGroup):
    waiting_for_budget_selection = State()
    waiting_for_new_budget_amount = State()

# Категории расходов
EXPENSE_CATEGORIES = [
    "🍔 Еда", "🏠 Жилье", "🚗 Транспорт", "👕 Одежда",
    "💊 Здоровье", "🎮 Развлечения", "📱 Связь",
    "💼 Образование", "🎁 Подарки", "✈️ Путешествия",
    "🧾 Прочее"
]

# Категории для целей накоплений
GOAL_CATEGORIES = [
    "🏠 Жилье", "🚗 Автомобиль", "✈️ Путешествие", "💻 Техника",
    "🎓 Образование", "💍 Свадьба", "🏥 Здоровье", "🎁 Подарок",
    "📈 Инвестиции", "🎯 Другое"
]

# ==================== ВИЗУАЛЬНЫЕ УТИЛИТЫ ====================
def get_colored_progress_bar(percentage, width=12):
    """Прогресс-бар с цветовой индикацией"""
    filled = int(width * min(percentage, 100) / 100)
    empty = width - filled
    
    # Цвет в зависимости от процента
    if percentage <= 50:
        filled_char = '🟩'  # зеленый
    elif percentage <= 80:
        filled_char = '🟨'  # желтый
    elif percentage <= 95:
        filled_char = '🟧'  # оранжевый
    else:
        filled_char = '🟥'  # красный
    
    empty_char = '⬜'
    
    bar = filled_char * filled + empty_char * empty
    return f"{bar} {percentage:.1f}%"

def get_fancy_progress_bar(percentage, width=10):
    """Стилизованный прогресс-бар с символами Unicode"""
    if percentage >= 100:
        return "✨✅ Завершено! ✨"
    
    filled = int(width * min(percentage, 100) / 100)
    empty = width - filled
    
    # Разные символы для заполненной части
    filled_char = '█'
    empty_char = '░'
    
    bar = filled_char * filled + empty_char * empty
    emoji = "🟢" if percentage < 50 else "🟡" if percentage < 80 else "🟠" if percentage < 95 else "🔴"
    
    return f"{emoji} {bar} {percentage:.1f}%"

def create_fancy_table(headers, rows, column_widths=None):
    """Создает красивую текстовую таблицу"""
    if not rows:
        return "📭 Нет данных"
    
    if not column_widths:
        column_widths = [20] * len(headers)
    
    # Верхняя граница
    top_border = "┌" + "─".join(["─" * (w + 2) for w in column_widths]) + "┐"
    
    # Заголовок
    header_row = "│"
    for i, header in enumerate(headers):
        header_row += f" {header:<{column_widths[i]}} │"
    
    # Разделитель
    separator = "├" + "─".join(["─" * (w + 2) for w in column_widths]) + "┤"
    
    # Строки данных
    data_rows = ""
    for row in rows:
        data_row = "│"
        for i, cell in enumerate(row):
            data_row += f" {str(cell):<{column_widths[i]}} │"
        data_rows += data_row + "\n"
    
    # Нижняя граница
    bottom_border = "└" + "─".join(["─" * (w + 2) for w in column_widths]) + "┘"
    
    return f"<code>{top_border}\n{header_row}\n{separator}\n{data_rows}{bottom_border}</code>"

def create_goal_card(goal):
    """Создает красивую карточку для цели"""
    percentage = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
    progress_bar = get_fancy_progress_bar(percentage)
    
    # Иконки в зависимости от категории
    category_icons = {
        "🏠 Жилье": "🏠", "🚗 Автомобиль": "🚗", "✈️ Путешествие": "✈️",
        "💻 Техника": "💻", "🎓 Образование": "🎓", "💍 Свадьба": "💍",
        "🏥 Здоровье": "🏥", "🎁 Подарок": "🎁", "📈 Инвестиции": "📈", "🎯 Другое": "🎯"
    }
    
    icon = category_icons.get(goal['category'], "🎯")
    
    card = (
        f"{icon} <b>{goal['name']}</b>\n"
        f"┌──────────────────────\n"
        f"│ 💰 Цель: <b>{goal['target_amount']:,.0f} руб.</b>\n"
        f"│ 💎 Накоплено: <b>{goal['current_amount']:,.0f} руб.</b>\n"
        f"│ 📊 Прогресс: {progress_bar}\n"
    )
    
    if goal['deadline']:
        deadline = datetime.strptime(goal['deadline'], '%Y-%m-%d').date()
        today = date.today()
        days = (deadline - today).days
        if days >= 0:
            card += f"│ 📅 Осталось дней: <b>{days}</b>\n"
        else:
            card += f"│ ⚠️ Просрочено на: <b>{abs(days)} дн.</b>\n"
    
    card += "└──────────────────────"
    
    return card

def create_budget_dashboard(progress_data):
    """Создает визуальную панель бюджета"""
    if not progress_data:
        return "📭 Нет данных о бюджетах"
    
    dashboard = "💰 <b>Панель бюджета</b>\n"
    dashboard += "┌────────────────────────────────────────┐\n"
    
    for category, data in progress_data.items():
        percentage = data['percentage']
        remaining = data['remaining']
        
        # Индикатор
        indicator_length = 20
        filled = int(indicator_length * min(percentage, 100) / 100)
        indicator = "█" * filled + "░" * (indicator_length - filled)
        
        # Цветовой код
        if percentage <= 70:
            color = "🟢"
        elif percentage <= 90:
            color = "🟡"
        else:
            color = "🔴"
        
        dashboard += (
            f"│ {color} {category[:15]:<15}\n"
            f"│ {indicator} {percentage:>5.1f}%\n"
            f"│ Остаток: {remaining:>8.0f} руб.\n"
            f"│────────────────────────────────────────│\n"
        )
    
    dashboard += "└────────────────────────────────────────┘"
    return dashboard

def get_status_emoji(days_left):
    """Получить emoji статуса для дней"""
    if days_left < 0:
        return "🔴"  # Просрочено
    elif days_left <= 3:
        return "🟠"  # Срочно
    elif days_left <= 7:
        return "🟡"  # Скоро
    else:
        return "🟢"  # По графику

def get_random_emoji():
    """Получить случайный позитивный emoji"""
    emojis = ["✨", "🌟", "💫", "🎯", "💰", "💎", "💼", "🏆", "🎉", "🥇"]
    return random.choice(emojis)

async def show_typing_effect(chat_id, duration=1):
    """Показывает индикатор набора текста"""
    await bot.send_chat_action(chat_id, action="typing")
    await asyncio.sleep(duration)

async def show_loading_message(message: types.Message, text="Загружаю данные..."):
    """Показывает сообщение с анимацией загрузки"""
    loading_frames = ["⏳", "⌛", "⏳", "⌛"]
    loading_msg = await message.answer(f"{loading_frames[0]} {text}")
    
    for i in range(3):
        await asyncio.sleep(0.3)
        await loading_msg.edit_text(f"{loading_frames[i % len(loading_frames)]} {text}{'.' * (i + 1)}")
    
    return loading_msg

async def send_beautiful_notification(chat_id, title, content, notification_type="info"):
    """Отправка стилизованных уведомлений"""
    
    type_configs = {
        "success": {"icon": "✅", "border": "🟢", "color": "🟩"},
        "warning": {"icon": "⚠️", "border": "🟡", "color": "🟨"},
        "error": {"icon": "❌", "border": "🔴", "color": "🟥"},
        "info": {"icon": "ℹ️", "border": "🔵", "color": "🟦"},
        "celebration": {"icon": "🎉", "border": "🎊", "color": "🌈"}
    }
    
    config = type_configs.get(notification_type, type_configs["info"])
    
    notification = (
        f"{config['border'] * 5}\n"
        f"{config['icon']} <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{content}\n"
        f"{config['border'] * 5}"
    )
    
    await bot.send_message(chat_id, notification, parse_mode="HTML")

# ==================== КЛАВИАТУРЫ ====================
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить долг"), KeyboardButton(text="💸 Внести расход")],
            [KeyboardButton(text="📋 Мои долги"), KeyboardButton(text="✅ Оплатить")],
            [KeyboardButton(text="💰 Внести доход"), KeyboardButton(text="📈 Аналитика+")],
            [KeyboardButton(text="🎯 Мои цели"), KeyboardButton(text="💰 Бюджет")],
            [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_enhanced_analytics_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📅 Этот месяц", callback_data="analytics_current"))
    builder.add(InlineKeyboardButton(text="📅 Прошлый месяц", callback_data="analytics_previous"))
    builder.add(InlineKeyboardButton(text="📊 График расходов", callback_data="analytics_chart"))
    builder.add(InlineKeyboardButton(text="📈 Расширенный график", callback_data="analytics_enhanced"))
    builder.add(InlineKeyboardButton(text="📋 Детальная таблица", callback_data="analytics_table"))
    builder.adjust(2)
    return builder.as_markup()

def get_categories_keyboard():
    builder = InlineKeyboardBuilder()
    for category in EXPENSE_CATEGORIES:
        builder.add(InlineKeyboardButton(text=category, callback_data=f"category_{category}"))
    builder.adjust(2)
    return builder.as_markup()

def get_goal_categories_keyboard():
    builder = InlineKeyboardBuilder()
    for category in GOAL_CATEGORIES:
        builder.add(InlineKeyboardButton(text=category, callback_data=f"goal_category_{category}"))
    builder.adjust(2)
    return builder.as_markup()

def get_skip_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_description")]
        ]
    )
    return keyboard

def get_settings_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications"))
    builder.add(InlineKeyboardButton(text="📊 Категории расходов", callback_data="settings_categories"))
    builder.add(InlineKeyboardButton(text="🗑 Очистить данные", callback_data="settings_clear_data"))
    builder.add(InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu"))
    builder.adjust(1)
    return builder.as_markup()

def get_notifications_keyboard(enabled=True, days_before=3):
    builder = InlineKeyboardBuilder()
    status_text = "✅ Включены" if enabled else "❌ Выключены"
    builder.add(InlineKeyboardButton(text=f"Статус: {status_text}", callback_data="toggle_notifications"))
    days_options = [1, 2, 3, 5, 7]
    for days in days_options:
        builder.add(InlineKeyboardButton(
            text=f"{days} дн. {'✅' if days == days_before else ''}",
            callback_data=f"set_days_{days}"
        ))
    builder.add(InlineKeyboardButton(text="✏️ Ввести своё число", callback_data="set_custom_days"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings"))
    builder.adjust(2)
    return builder.as_markup()

def get_payment_type_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📅 Обычный платеж", callback_data="payment_type_regular"))
    builder.add(InlineKeyboardButton(text="🚀 Досрочный платеж", callback_data="payment_type_early"))
    builder.adjust(1)
    return builder.as_markup()

def get_edit_debt_keyboard(debt_id):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✏️ Название", callback_data=f"edit_field_name_{debt_id}"))
    builder.add(InlineKeyboardButton(text="💰 Общая сумма", callback_data=f"edit_field_total_{debt_id}"))
    builder.add(InlineKeyboardButton(text="💳 Сумма платежа", callback_data=f"edit_field_payment_{debt_id}"))
    builder.add(InlineKeyboardButton(text="📅 Дата платежа", callback_data=f"edit_field_date_{debt_id}"))
    builder.add(InlineKeyboardButton(text="🗑 Удалить долг", callback_data=f"edit_field_delete_{debt_id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к долгам", callback_data="edit_back_to_debts"))
    builder.adjust(2)
    return builder.as_markup()

def get_goals_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="➕ Добавить цель", callback_data="add_goal"))
    builder.add(InlineKeyboardButton(text="💰 Пополнить цель", callback_data="deposit_to_goal"))
    builder.add(InlineKeyboardButton(text="📊 Мои цели", callback_data="list_goals"))
    builder.add(InlineKeyboardButton(text="✅ Завершенные", callback_data="completed_goals"))
    builder.add(InlineKeyboardButton(text="📈 Цели прогресс", callback_data="goals_progress"))
    builder.add(InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu"))
    builder.adjust(1)
    return builder.as_markup()

def get_budget_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="➕ Установить бюджет", callback_data="budget_set"))
    builder.add(InlineKeyboardButton(text="📊 Мои бюджеты", callback_data="budget_list"))
    builder.add(InlineKeyboardButton(text="📈 Анализ бюджета", callback_data="budget_analysis"))
    builder.add(InlineKeyboardButton(text="📊 Панель бюджета", callback_data="budget_dashboard"))
    builder.add(InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu"))
    builder.adjust(1)
    return builder.as_markup()

def get_budget_categories_keyboard():
    builder = InlineKeyboardBuilder()
    for category in EXPENSE_CATEGORIES:
        builder.add(InlineKeyboardButton(text=category, callback_data=f"budget_cat_{category}"))
    builder.adjust(2)
    return builder.as_markup()

def get_budget_period_keyboard():
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    current_month = today.strftime('%Y-%m')
    next_month = (today.replace(day=28) + timedelta(days=4)).strftime('%Y-%m')
    
    builder.add(InlineKeyboardButton(text="📅 Текущий месяц", callback_data=f"budget_period_{current_month}"))
    builder.add(InlineKeyboardButton(text="🚀 Следующий месяц", callback_data=f"budget_period_{next_month}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="budget_back"))
    builder.adjust(1)
    return builder.as_markup()

# ==================== УТИЛИТНЫЕ ФУНКЦИИ ====================
def get_progress_bar(percentage, width=10):
    """Совместимая функция прогресс-бара"""
    return get_fancy_progress_bar(percentage, width)

def calculate_time_taken(created_at, completed_at):
    try:
        created = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        completed = datetime.strptime(completed_at, '%Y-%m-%d %H:%M:%S')
        diff = completed - created
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} год(а)"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} месяц(ев)"
        else:
            return f"{diff.days} день(ей)"
    except:
        return "Неизвестно"

def format_period(period_str: str) -> str:
    try:
        date_obj = datetime.strptime(period_str, '%Y-%m')
        months = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        month_name = months[date_obj.month - 1]
        return f"{month_name} {date_obj.year}"
    except:
        return period_str

# ==================== БАЗА ДАННЫХ ====================
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        # Таблица для долгов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                total_amount REAL NOT NULL,
                current_amount REAL NOT NULL,
                payment_amount REAL NOT NULL,
                next_payment_date TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица для расходов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица для доходов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS income (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                source TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица для настроек уведомлений
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 1,
                days_before INTEGER DEFAULT 3
            )
        ''')
        # Таблица для целей накоплений
        await db.execute('''
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                deadline TEXT,
                category TEXT DEFAULT 'Другое',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed BOOLEAN DEFAULT 0,
                completed_at TEXT
            )
        ''')
        # Таблица для достижений целей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS goal_achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                goal_name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                achieved_at TEXT NOT NULL
            )
        ''')
        # Таблица для бюджетов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                period TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category, period)
            )
        ''')
        await db.commit()
    logging.info("✅ База данных ASinglePoint инициализирована")

async def get_notification_settings(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT enabled, days_before FROM notification_settings WHERE user_id = ?",
            (user_id,)
        )
        result = await cursor.fetchone()
        if result:
            return {"enabled": bool(result[0]), "days_before": result[1]}
        else:
            await db.execute(
                "INSERT INTO notification_settings (user_id, enabled, days_before) VALUES (?, 1, 3)",
                (user_id,)
            )
            await db.commit()
            return {"enabled": True, "days_before": 3}

async def update_notification_settings(user_id: int, enabled: bool = None, days_before: int = None):
    async with aiosqlite.connect(DATABASE) as db:
        if enabled is not None and days_before is not None:
            await db.execute(
                "INSERT OR REPLACE INTO notification_settings (user_id, enabled, days_before) VALUES (?, ?, ?)",
                (user_id, enabled, days_before)
            )
        elif enabled is not None:
            await db.execute(
                "UPDATE notification_settings SET enabled = ? WHERE user_id = ?",
                (enabled, user_id)
            )
        elif days_before is not None:
            await db.execute(
                "UPDATE notification_settings SET days_before = ? WHERE user_id = ?",
                (days_before, user_id)
            )
        await db.commit()

async def get_budget_progress(user_id: int, period: str) -> Dict:
    """Получает прогресс бюджета для указанного периода"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute(
            "SELECT category, amount FROM budgets WHERE user_id = ? AND period = ?",
            (user_id, period)
        )
        budgets = await cursor.fetchall()
        
        cursor = await db.execute("""
            SELECT category, SUM(amount) as spent 
            FROM expenses 
            WHERE user_id = ? AND created_at LIKE ?
            GROUP BY category
        """, (user_id, f"{period}%"))
        expenses = await cursor.fetchall()
    
    budget_dict = {budget['category']: budget['amount'] for budget in budgets}
    expense_dict = {expense['category']: expense['spent'] for expense in expenses}
    
    result = {}
    for category, budget_amount in budget_dict.items():
        spent = expense_dict.get(category, 0)
        remaining = budget_amount - spent
        percentage = (spent / budget_amount * 100) if budget_amount > 0 else 0
        
        result[category] = {
            'budget': budget_amount,
            'spent': spent,
            'remaining': remaining,
            'percentage': percentage,
            'status': 'danger' if percentage > 90 else 'warning' if percentage > 70 else 'success'
        }
    
    return result

async def check_budget_overspending(user_id: int, category: str, amount: float):
    today = datetime.now()
    period = today.strftime('%Y-%m')
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND period = ?",
            (user_id, category, period)
        )
        budget = await cursor.fetchone()
        
        if not budget:
            return False, ""
        
        budget_amount = budget['amount']
        
        cursor = await db.execute("""
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE user_id = ? AND category = ? AND created_at LIKE ?
        """, (user_id, category, f"{period}%"))
        result = await cursor.fetchone()
        already_spent = result['total'] or 0
        
        if already_spent + amount > budget_amount:
            overspent = (already_spent + amount) - budget_amount
            return True, f"⚠️ Внимание! Превышение бюджета по категории {category} на {overspent:.2f} руб.!"
        
        elif already_spent + amount >= budget_amount * 0.8:
            return False, f"ℹ️ Вы близки к лимиту по категории {category} ({budget_amount:.2f} руб.)"
    
    return False, ""

# ==================== УВЕДОМЛЕНИЯ ====================
async def check_and_send_notifications():
    today = datetime.now(MOSCOW_TZ).date()
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT DISTINCT user_id FROM debts")
        users = await cursor.fetchall()
        for user_row in users:
            user_id = user_row['user_id']
            settings = await get_notification_settings(user_id)
            if not settings['enabled']:
                continue
            cursor = await db.execute(
                "SELECT * FROM debts WHERE user_id = ? AND current_amount > 0",
                (user_id,)
            )
            debts = await cursor.fetchall()
            for debt in debts:
                try:
                    payment_date = datetime.strptime(debt['next_payment_date'], '%Y-%m-%d').date()
                except ValueError:
                    try:
                        payment_date = datetime.fromisoformat(debt['next_payment_date']).date()
                    except:
                        continue
                
                days_left = (payment_date - today).days
                if 0 <= days_left <= settings['days_before']:
                    try:
                        emoji = get_status_emoji(days_left)
                        progress = ((debt['total_amount'] - debt['current_amount']) / debt['total_amount'] * 100) if debt['total_amount'] > 0 else 0
                        progress_bar = get_fancy_progress_bar(progress)
                        
                        message_text = (
                            f"🔔 <b>Напоминание о платеже!</b>\n\n"
                            f"{emoji} <b>Долг:</b> {debt['name']}\n"
                            f"📅 <b>Дата платежа:</b> {payment_date.strftime('%d.%m.%Y')}\n"
                            f"💳 <b>Сумма к оплате:</b> {debt['payment_amount']:.2f} руб.\n"
                            f"📊 <b>Текущий остаток:</b> {debt['current_amount']:.2f} руб.\n"
                            f"📈 <b>Прогресс погашения:</b> {progress_bar}\n\n"
                            f"<i>⏳ Осталось дней: {days_left}</i>"
                        )
                        await bot.send_message(user_id, message_text, parse_mode="HTML")
                        logging.info(f"Отправлено уведомление пользователю {user_id} о долге {debt['name']}")
                    except Exception as e:
                        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")

async def check_budget_warnings():
    today = datetime.now(MOSCOW_TZ)
    current_period = today.strftime('%Y-%m')
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT DISTINCT user_id FROM budgets WHERE period = ?", (current_period,))
        users = await cursor.fetchall()
        
        for user_row in users:
            user_id = user_row['user_id']
            progress = await get_budget_progress(user_id, current_period)
            
            if not progress:
                continue
            
            warnings = []
            for category, data in progress.items():
                percentage = data['percentage']
                remaining = data['remaining']
                
                if percentage >= 90:
                    warnings.append(f"🔴 {category}: превышен на {abs(remaining):.2f} руб.")
                elif percentage >= 80:
                    warnings.append(f"🟠 {category}: осталось {remaining:.2f} руб.")
                elif percentage >= 50 and today.day >= 20:
                    warnings.append(f"🟡 {category}: использовано {percentage:.1f}% бюджета")
            
            if warnings:
                try:
                    message_text = (
                        f"💰 <b>Ежедневный отчет по бюджетам</b>\n\n"
                        f"📅 <b>Статус на {today.strftime('%d.%m.%Y')}:</b>\n" +
                        "\n".join(warnings) +
                        f"\n\n<i>Проверить детали: нажмите '💰 Бюджет' → '📊 Панель бюджета'</i>"
                    )
                    await bot.send_message(user_id, message_text, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления о бюджете: {e}")

async def check_expired_goals():
    """Проверяет цели с истекшим сроком и отправляет уведомления"""
    today = date.today()
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT DISTINCT user_id FROM savings_goals 
            WHERE deadline IS NOT NULL 
            AND completed = 0 
            AND deadline < ?
        """, (today.isoformat(),))
        users = await cursor.fetchall()
        
        for user_row in users:
            user_id = user_row['user_id']
            cursor = await db.execute("""
                SELECT * FROM savings_goals 
                WHERE user_id = ? 
                AND deadline IS NOT NULL 
                AND completed = 0 
                AND deadline < ?
            """, (user_id, today.isoformat()))
            expired_goals = await cursor.fetchall()
            
            if expired_goals:
                goals_list = "\n".join([f"• {goal['name']} (до {goal['deadline']})" for goal in expired_goals])
                try:
                    await send_beautiful_notification(
                        user_id,
                        "⏰ Истек срок целей",
                        f"Следующие цели требуют вашего внимания:\n\n{goals_list}\n\n<i>Вы можете продлить срок или пересмотреть цель.</i>",
                        "warning"
                    )
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления об истекших целях: {e}")

async def schedule_notifications():
    scheduler.add_job(
        check_and_send_notifications,
        CronTrigger(hour=10, minute=0, timezone=MOSCOW_TZ),
        id='daily_notifications',
        replace_existing=True
    )
    
    scheduler.add_job(
        check_budget_warnings,
        CronTrigger(hour=20, minute=0, timezone=MOSCOW_TZ),
        id='daily_budget_check',
        replace_existing=True
    )
    
    scheduler.add_job(
        check_expired_goals,
        CronTrigger(hour=9, minute=0, timezone=MOSCOW_TZ),
        id='check_expired_goals',
        replace_existing=True
    )

# ==================== ОБЩИЕ ФУНКЦИИ ДЛЯ ОЧИСТКИ СОСТОЯНИЙ ====================
async def clear_state_and_show_menu(message: types.Message, state: FSMContext):
    """Очищает состояние и показывает главное меню"""
    await state.clear()
    await message.answer(f"{get_random_emoji()} Возвращаюсь в главное меню...", reply_markup=get_main_menu())

# ==================== КОМАНДА /start ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 1)
    
    welcome_text = (
        "🌟 <b>Добро пожаловать в ASinglePoint — ваш умный финансовый помощник!</b>\n\n"
        "✨ <b>Новые возможности:</b>\n"
        "• 📈 Улучшенная аналитика с графиками\n"
        "• 🎯 Красивые карточки для целей\n"
        "• 📊 Визуальные панели бюджета\n"
        "• 💎 Цветные прогресс-бары\n\n"
        "Используйте меню ниже для навигации."
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )
    
    # Отправляем красивую приветственную карточку
    await asyncio.sleep(0.5)
    await send_beautiful_notification(
        message.chat.id,
        "🚀 Начало работы",
        "Выберите раздел в меню, чтобы начать управление финансами!\n\n"
        "<i>Совет: начните с добавления долга или цели.</i>",
        "celebration"
    )

# ==================== КОМАНДА /help ====================
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await show_typing_effect(message.chat.id, 1)
    
    help_text = (
        "📚 <b>Справка по боту ASinglePoint</b>\n\n"
        "✨ <b>Новые визуальные функции:</b>\n"
        "• 📈 <b>Аналитика+</b> — расширенные графики и таблицы\n"
        "• 🎯 <b>Карточки целей</b> — красивое отображение прогресса\n"
        "• 📊 <b>Панель бюджета</b> — визуальная сводка\n"
        "• 💎 <b>Цветные прогресс-бары</b> — интуитивное понимание\n\n"
        "<b>Основные функции:</b>\n"
        "• 📋 Учет долгов\n"
        "• 💸 Учет расходов\n"
        "• 💰 Учет доходов\n"
        "• 🎯 Цели накоплений\n"
        "• 📊 Аналитика и графики\n"
        "• ⚙️ Настройки\n\n"
        "<b>Используйте меню или команды:</b>\n"
        "/start — показать главное меню\n"
        "/cancel — отменить текущее действие\n"
        "/help — показать эту справку"
    )
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_main_menu())

# ==================== КОМАНДА /cancel ====================
@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await clear_state_and_show_menu(message, state)

# ==================== ДОБАВЛЕНИЕ ДОЛГА ====================
@dp.message(F.text == "➕ Добавить долг")
async def add_debt_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    await message.answer("✨ <b>Введите название долга:</b>\nПример: Кредитная карта Тинькофф, Ипотека", parse_mode="HTML")
    await state.set_state(DebtForm.waiting_for_debt_name)

@dp.message(DebtForm.waiting_for_debt_name)
async def process_debt_name(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    await state.update_data(name=message.text)
    await message.answer("💰 <b>Введите общую сумму долга:</b>\nПример: 100000", parse_mode="HTML")
    await state.set_state(DebtForm.waiting_for_debt_total)

@dp.message(DebtForm.waiting_for_debt_total)
async def process_debt_total(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        total = float(message.text.replace(',', '.'))
        if total <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Введите общую сумму долга:")
            return
        await state.update_data(total_amount=total)
        await message.answer("💳 <b>Введите сумму ежемесячного платежа:</b>\nПример: 5000", parse_mode="HTML")
        await state.set_state(DebtForm.waiting_for_debt_payment)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 100000")

@dp.message(DebtForm.waiting_for_debt_payment)
async def process_debt_payment(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        payment = float(message.text.replace(',', '.'))
        if payment <= 0:
            await message.answer("❌ Сумма платежа должна быть больше 0. Введите сумму платежа:")
            return
        await state.update_data(payment_amount=payment)
        await message.answer("📅 <b>Введите дату следующего платежа:</b>\nФормат: ДД.ММ.ГГГГ\nПример: 15.04.2024", parse_mode="HTML")
        await state.set_state(DebtForm.waiting_for_debt_date)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 5000")

@dp.message(DebtForm.waiting_for_debt_date)
async def process_debt_date(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        payment_date = datetime.strptime(message.text, '%d.%m.%Y').date()
        today = date.today()
        if payment_date < today:
            await message.answer("⚠️ Вы указали прошедшую дату. Пожалуйста, введите будущую дату.")
            return
        data = await state.get_data()
        
        loading_msg = await show_loading_message(message, "Добавляю долг")
        
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute(
                """INSERT INTO debts
                (user_id, name, total_amount, current_amount, payment_amount, next_payment_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (message.from_user.id, data['name'], data['total_amount'],
                 data['total_amount'], data['payment_amount'], payment_date.isoformat())
            )
            await db.commit()
        
        await loading_msg.delete()
        
        # Отправляем красивую карточку добавленного долга
        card_text = (
            f"✨ <b>Долг успешно добавлен!</b>\n\n"
            f"🏷 <b>Название:</b> {data['name']}\n"
            f"💰 <b>Общая сумма:</b> {data['total_amount']:.2f} руб.\n"
            f"📅 <b>Следующий платеж:</b> {payment_date.strftime('%d.%m.%Y')}\n"
            f"💳 <b>Сумма платежа:</b> {data['payment_amount']:.2f} руб.\n"
            f"📊 <b>Статус:</b> {get_status_emoji((payment_date - today).days)}"
        )
        
        await send_beautiful_notification(
            message.chat.id,
            "✅ Долг добавлен",
            card_text,
            "success"
        )
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.")

# ==================== ПРОСМОТР СПИСКА ДОЛГОВ ====================
@dp.message(F.text == "📋 Мои долги")
async def list_debts(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 1)
    
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM debts WHERE user_id = ? ORDER BY next_payment_date",
            (user_id,)
        )
        debts = await cursor.fetchall()
        
        if not debts:
            await message.answer(
                "📭 <b>У вас пока нет добавленных долгов.</b>\n\n"
                "Нажмите «➕ Добавить долг», чтобы создать первый.",
                parse_mode="HTML"
            )
            return
        
        # Создаем красивую таблицу
        headers = ["Долг", "Остаток", "Платеж", "Дата", "Статус"]
        rows = []
        total_current = 0
        total_original = 0
        
        for debt in debts:
            debt_date = datetime.strptime(debt['next_payment_date'], '%Y-%m-%d').date()
            days_left = (debt_date - date.today()).days
            
            status_emoji = get_status_emoji(days_left)
            status_text = f"{status_emoji} {abs(days_left)}д"
            
            rows.append([
                debt['name'][:12],
                f"{debt['current_amount']:.0f}р",
                f"{debt['payment_amount']:.0f}р",
                debt_date.strftime('%d.%m'),
                status_text
            ])
            
            total_current += debt['current_amount']
            total_original += debt['total_amount']
        
        total_paid = total_original - total_current
        payment_progress = (total_paid / total_original * 100) if total_original > 0 else 0
        
        table = create_fancy_table(headers, rows, [12, 10, 10, 8, 8])
        
        summary = (
            f"📈 <b>Итоговая статистика:</b>\n"
            f"• 💰 Общая сумма долгов: {total_original:,.0f} руб.\n"
            f"• 🎯 Текущий остаток: {total_current:,.0f} руб.\n"
            f"• ✅ Уже погашено: {total_paid:,.0f} руб.\n"
            f"• 📊 Общий прогресс: {get_fancy_progress_bar(payment_progress)}"
        )
        
        await message.answer(
            f"📋 <b>Ваши долги</b>\n\n{table}\n\n{summary}",
            parse_mode="HTML"
        )

# ==================== ФУНКЦИЯ ОПЛАТЫ (С ДОСРОЧНЫМ ПЛАТЕЖОМ) ====================
@dp.message(F.text == "✅ Оплатить")
async def pay_debt_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM debts WHERE user_id = ? AND current_amount > 0",
            (user_id,)
        )
        debts = await cursor.fetchall()
        
        if not debts:
            await send_beautiful_notification(
                message.chat.id,
                "🎉 Нет активных долгов",
                "Все долги полностью погашены или добавьте новый долг.",
                "celebration"
            )
            return
        
        builder = InlineKeyboardBuilder()
        for debt in debts:
            progress = ((debt['total_amount'] - debt['current_amount']) / debt['total_amount'] * 100) if debt['total_amount'] > 0 else 0
            button_text = f"{debt['name'][:15]} - {debt['current_amount']:.0f}р ({progress:.0f}%)"
            builder.add(InlineKeyboardButton(
                text=button_text,
                callback_data=f"pay_debt_{debt['id']}"
            ))
        builder.adjust(1)
        
        await message.answer(
            "💳 <b>Выберите долг для оплаты:</b>\n\n"
            "Нажмите на кнопку с названием долга, по которому хотите внести платеж.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("pay_debt_"))
async def process_debt_selection(callback: types.CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,))
        debt = await cursor.fetchone()
        if not debt:
            await callback.message.edit_text("❌ Долг не найден.")
            return
    
    progress = ((debt['total_amount'] - debt['current_amount']) / debt['total_amount'] * 100) if debt['total_amount'] > 0 else 0
    progress_bar = get_fancy_progress_bar(progress)
    
    await state.update_data(debt_id=debt_id, debt_name=debt['name'],
                           current_amount=debt['current_amount'],
                           payment_amount=debt['payment_amount'])
    
    await callback.message.edit_text(
        f"💳 <b>Оплата долга:</b> {debt['name']}\n\n"
        f"💰 <b>Текущий остаток:</b> {debt['current_amount']:.2f} руб.\n"
        f"📅 <b>Рекомендуемый платеж:</b> {debt['payment_amount']:.2f} руб.\n"
        f"📊 <b>Прогресс погашения:</b> {progress_bar}\n\n"
        f"<b>Выберите тип платежа:</b>\n"
        f"• 📅 Обычный — дата следующего платежа сдвинется на месяц\n"
        f"• 🚀 Досрочный — дата платежа останется прежней",
        parse_mode="HTML",
        reply_markup=get_payment_type_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("payment_type_"))
async def process_payment_type(callback: types.CallbackQuery, state: FSMContext):
    payment_type = callback.data.split("_")[2]
    await state.update_data(payment_type=payment_type)
    data = await state.get_data()
    debt_id = data['debt_id']
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,))
        debt = await cursor.fetchone()
    
    builder = InlineKeyboardBuilder()
    payment_amount = debt['payment_amount']
    amounts = [payment_amount, payment_amount * 2, debt['current_amount']]
    
    for amount in amounts:
        if amount <= debt['current_amount']:
            builder.add(InlineKeyboardButton(
                text=f"{amount:.0f} руб.",
                callback_data=f"pay_amount_{amount}"
            ))
    
    builder.add(InlineKeyboardButton(
        text="✏️ Ввести свою сумму",
        callback_data="enter_custom_amount"
    ))
    builder.adjust(2)
    
    payment_type_text = "обычный" if payment_type == "regular" else "досрочный"
    await callback.message.edit_text(
        f"<b>Введите сумму для {payment_type_text} платежа:</b>\n"
        f"(или нажмите на одну из кнопок)",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.set_state(PayDebtForm.waiting_for_payment_amount)
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_amount_"))
async def process_amount_selection(callback: types.CallbackQuery, state: FSMContext):
    amount = float(callback.data.split("_")[2])
    await process_payment(callback, state, amount)

@dp.callback_query(F.data == "enter_custom_amount")
async def enter_custom_amount(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Введите сумму для оплаты:")
    await callback.answer()

@dp.message(PayDebtForm.waiting_for_payment_amount)
async def process_payment_amount(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        await process_payment(message, state, amount)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 5000")

async def process_payment(source, state: FSMContext, amount: float):
    data = await state.get_data()
    debt_id = data['debt_id']
    payment_type = data.get('payment_type', 'regular')
    
    if amount <= 0:
        if isinstance(source, types.Message):
            await source.answer("❌ Сумма должна быть больше 0.")
        else:
            await source.message.answer("❌ Сумма должна быть больше 0.")
        return
    
    loading_msg = None
    if isinstance(source, types.Message):
        loading_msg = await show_loading_message(source, "Обрабатываю платеж")
    else:
        loading_msg = await show_loading_message(source.message, "Обрабатываю платеж")
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,))
        debt = await cursor.fetchone()
        
        if not debt:
            if isinstance(source, types.Message):
                await source.answer("❌ Долг не найден.")
            else:
                await source.message.answer("❌ Долг не найден.")
            return
        
        if amount > debt['current_amount']:
            if isinstance(source, types.Message):
                await source.answer(f"❌ Сумма превышает остаток долга ({debt['current_amount']:.2f} руб.).")
            else:
                await source.message.answer(f"❌ Сумма превышает остаток долга ({debt['current_amount']:.2f} руб.).")
            return
        
        new_amount = debt['current_amount'] - amount
        next_date = datetime.strptime(debt['next_payment_date'], '%Y-%m-%d').date()
        
        if payment_type == 'regular':
            try:
                if next_date.month == 12:
                    next_date = next_date.replace(year=next_date.year + 1, month=1)
                else:
                    next_date = next_date.replace(month=next_date.month + 1)
            except ValueError:
                next_date = next_date + timedelta(days=30)
        
        await db.execute(
            """UPDATE debts
            SET current_amount = ?, next_payment_date = ?
            WHERE id = ?""",
            (new_amount, next_date.isoformat(), debt_id)
        )
        await db.commit()
    
    await loading_msg.delete()
    
    payment_type_text = "обычный" if payment_type == "regular" else "досрочный"
    new_progress = ((debt['total_amount'] - new_amount) / debt['total_amount'] * 100) if debt['total_amount'] > 0 else 0
    
    if new_amount <= 0:
        # Поздравление с полным погашением
        await send_beautiful_notification(
            source.from_user.id if isinstance(source, types.CallbackQuery) else source.from_user.id,
            "🎉 Долг полностью погашен!",
            f"🏷 <b>Долг:</b> {debt['name']}\n"
            f"💰 <b>Итоговая сумма:</b> {debt['total_amount']:.2f} руб.\n"
            f"✨ <b>Поздравляем с достижением!</b>",
            "celebration"
        )
    else:
        # Обычное уведомление о платеже
        message_text = (
            f"✅ <b>Платеж успешно внесен!</b>\n\n"
            f"🏷 <b>Долг:</b> {debt['name']}\n"
            f"📋 <b>Тип платежа:</b> {payment_type_text}\n"
            f"💸 <b>Сумма оплаты:</b> {amount:.2f} руб.\n"
            f"📊 <b>Новый остаток:</b> {new_amount:.2f} руб.\n"
            f"📅 <b>Следующий платеж:</b> {next_date.strftime('%d.%m.%Y')}\n"
            f"📈 <b>Общий прогресс:</b> {get_fancy_progress_bar(new_progress)}"
        )
        
        if isinstance(source, types.Message):
            await source.answer(message_text, parse_mode="HTML", reply_markup=get_main_menu())
        else:
            await source.message.answer(message_text, parse_mode="HTML", reply_markup=get_main_menu())
    
    await state.clear()

# ==================== РЕДАКТИРОВАНИЕ ДОЛГОВ ====================
@dp.message(F.text == "✏️ Редактировать")
async def edit_debt_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM debts WHERE user_id = ? ORDER BY next_payment_date",
            (user_id,)
        )
        debts = await cursor.fetchall()
        
        if not debts:
            await message.answer(
                "📭 <b>У вас пока нет добавленных долгов.</b>\n\n"
                "Нажмите «➕ Добавить долг», чтобы создать первый.",
                parse_mode="HTML"
            )
            return
        
        builder = InlineKeyboardBuilder()
        for debt in debts:
            progress = ((debt['total_amount'] - debt['current_amount']) / debt['total_amount'] * 100) if debt['total_amount'] > 0 else 0
            button_text = f"{debt['name'][:15]} ({progress:.0f}%)"
            builder.add(InlineKeyboardButton(
                text=button_text,
                callback_data=f"edit_debt_{debt['id']}"
            ))
        builder.adjust(1)
        
        await message.answer(
            "✏️ <b>Выберите долг для редактирования:</b>\n\n"
            "Нажмите на кнопку с названием долга, который хотите изменить.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(EditDebtForm.waiting_for_debt_selection)

@dp.callback_query(F.data.startswith("edit_debt_"), EditDebtForm.waiting_for_debt_selection)
async def process_edit_debt_selection(callback: types.CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,))
        debt = await cursor.fetchone()
        if not debt:
            await callback.message.edit_text("❌ Долг не найден.")
            return
    
    debt_date = datetime.strptime(debt['next_payment_date'], '%Y-%m-%d').date()
    days_left = (debt_date - date.today()).days
    progress = ((debt['total_amount'] - debt['current_amount']) / debt['total_amount'] * 100) if debt['total_amount'] > 0 else 0
    
    debt_info = (
        f"✏️ <b>Редактирование долга:</b> {debt['name']}\n\n"
        f"🏷 <b>Название:</b> {debt['name']}\n"
        f"💰 <b>Общая сумма:</b> {debt['total_amount']:.2f} руб.\n"
        f"📊 <b>Текущий остаток:</b> {debt['current_amount']:.2f} руб.\n"
        f"💳 <b>Сумма платежа:</b> {debt['payment_amount']:.2f} руб.\n"
        f"📅 <b>Дата платежа:</b> {debt_date.strftime('%d.%m.%Y')} ({'через' if days_left >= 0 else 'просрочено на'} {abs(days_left)} дн.)\n"
        f"📈 <b>Прогресс:</b> {get_fancy_progress_bar(progress)}\n\n"
        f"<b>Выберите что хотите изменить:</b>"
    )
    
    await state.update_data(edit_debt_id=debt_id)
    await callback.message.edit_text(
        debt_info,
        parse_mode="HTML",
        reply_markup=get_edit_debt_keyboard(debt_id)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_field_"))
async def process_edit_field_selection(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    field = data_parts[2]
    debt_id = int(data_parts[3]) if len(data_parts) > 3 else None
    
    if field == "delete":
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirm_delete_{debt_id}"))
        builder.add(InlineKeyboardButton(text="❌ Нет, отмена", callback_data=f"edit_debt_{debt_id}"))
        builder.adjust(2)
        
        await callback.message.edit_text(
            "⚠️ <b>Внимание! Вы уверены, что хотите удалить этот долг?</b>\n\n"
            "Это действие нельзя отменить. Все данные о долге будут удалены безвозвратно.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return
    
    await state.update_data(edit_field=field, edit_debt_id=debt_id)
    field_names = {
        "name": "название",
        "total": "общую сумму",
        "payment": "сумму платежа",
        "date": "дату следующего платежа"
    }
    field_hints = {
        "name": "Введите новое название долга:",
        "total": "Введите новую общую сумму долга (например: 100000):",
        "payment": "Введите новую сумму ежемесячного платежа (например: 5000):",
        "date": "Введите новую дату следующего платежа в формате ДД.ММ.ГГГГ:"
    }
    
    await callback.message.edit_text(
        f"✏️ <b>Редактирование:</b> {field_names.get(field, field)}\n\n"
        f"{field_hints.get(field, 'Введите новое значение:')}",
        parse_mode="HTML"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data=f"edit_debt_{debt_id}"))
    await callback.message.answer(
        "Или нажмите 'Отмена' для возврата:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(EditDebtForm.waiting_for_new_value)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def process_confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
        await db.commit()
    
    await send_beautiful_notification(
        callback.from_user.id,
        "✅ Долг удален",
        "Долг успешно удален из системы.\nВы можете продолжить редактирование других долгов.",
        "success"
    )
    
    await edit_debt_start(callback.message, state)
    await callback.answer()

@dp.message(EditDebtForm.waiting_for_new_value)
async def process_new_value(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    data = await state.get_data()
    field = data.get('edit_field')
    debt_id = data.get('edit_debt_id')
    
    if not field or not debt_id:
        await message.answer("❌ Ошибка. Начните редактирование заново.")
        await state.clear()
        return
    
    loading_msg = await show_loading_message(message, "Сохраняю изменения")
    
    try:
        async with aiosqlite.connect(DATABASE) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,))
            debt = await cursor.fetchone()
            
            if not debt:
                await message.answer("❌ Долг не найден.")
                await state.clear()
                return
            
            if field == "name":
                new_value = message.text
                await db.execute(
                    "UPDATE debts SET name = ? WHERE id = ?",
                    (new_value, debt_id)
                )
                success_msg = f"✅ Название долга изменено на: <b>{new_value}</b>"
                
            elif field == "total":
                new_value = float(message.text.replace(',', '.'))
                if new_value <= 0:
                    await message.answer("❌ Сумма должна быть больше 0.")
                    return
                
                old_total = debt['total_amount']
                old_current = debt['current_amount']
                new_current = (old_current / old_total) * new_value if old_total > 0 else new_value
                
                await db.execute(
                    "UPDATE debts SET total_amount = ?, current_amount = ? WHERE id = ?",
                    (new_value, new_current, debt_id)
                )
                success_msg = f"✅ Общая сумма изменена на: <b>{new_value:.2f}</b> руб.\nТекущий остаток: <b>{new_current:.2f}</b> руб."
                
            elif field == "payment":
                new_value = float(message.text.replace(',', '.'))
                if new_value <= 0:
                    await message.answer("❌ Сумма должна быть больше 0.")
                    return
                
                await db.execute(
                    "UPDATE debts SET payment_amount = ? WHERE id = ?",
                    (new_value, debt_id)
                )
                success_msg = f"✅ Сумма платежа изменена на: <b>{new_value:.2f}</b> руб."
                
            elif field == "date":
                new_date = datetime.strptime(message.text, '%d.%m.%Y').date()
                today = date.today()
                if new_date < today:
                    await message.answer("⚠️ Вы указали прошедшую дату. Пожалуйста, введите будущую дату.")
                    return
                
                await db.execute(
                    "UPDATE debts SET next_payment_date = ? WHERE id = ?",
                    (new_date.isoformat(), debt_id)
                )
                success_msg = f"✅ Дата платежа изменена на: <b>{new_date.strftime('%d.%m.%Y')}</b>"
                
            else:
                await message.answer("❌ Неизвестное поле для редактирования.")
                await state.clear()
                return
            
            await db.commit()
            
        await loading_msg.delete()
        await send_beautiful_notification(
            message.chat.id,
            "✅ Изменения сохранены",
            success_msg,
            "success"
        )
        
        # Возвращаем к редактированию того же долга
        await process_edit_debt_selection(message, state)
        
    except ValueError as e:
        await loading_msg.delete()
        if field == "date":
            await message.answer("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.")
        else:
            await message.answer("❌ Пожалуйста, введите число.")
    except Exception as e:
        await loading_msg.delete()
        await message.answer(f"❌ Ошибка при обновлении: {str(e)}")
    
    await state.clear()

@dp.callback_query(F.data == "edit_back_to_debts")
async def back_to_edit_debts(callback: types.CallbackQuery, state: FSMContext):
    await edit_debt_start(callback.message, state)
    await callback.answer()

# ==================== ЦЕЛИ И НАКОПЛЕНИЯ ====================
@dp.message(F.text == "🎯 Мои цели")
async def goals_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    
    await message.answer(
        "🎯 <b>Цели и накопления</b>\n\n"
        "✨ <b>Новые возможности:</b>\n"
        "• 🎨 Красивые карточки целей\n"
        "• 📊 Визуальный прогресс\n"
        "• 🏆 Отслеживание достижений\n\n"
        "<b>Примеры целей:</b>\n"
        "• 🚗 Накопить на машину - 500,000 руб.\n"
        "• ✈️ Отпуск в Турции - 150,000 руб.\n"
        "• 💻 Новый ноутбук - 80,000 руб.",
        parse_mode="HTML",
        reply_markup=get_goals_keyboard()
    )

@dp.callback_query(F.data == "add_goal")
async def add_goal_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎯 <b>Введите название цели:</b>\n"
        "Пример: 'Накопить на машину', 'Отпуск в Греции'",
        parse_mode="HTML"
    )
    await state.set_state(SavingsGoalForm.waiting_for_goal_name)
    await callback.answer()

@dp.message(SavingsGoalForm.waiting_for_goal_name)
async def process_goal_name(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    await state.update_data(name=message.text)
    await message.answer(
        "💰 <b>Введите целевую сумму:</b>\n"
        "Сколько рублей нужно накопить?",
        parse_mode="HTML"
    )
    await state.set_state(SavingsGoalForm.waiting_for_goal_target)

@dp.message(SavingsGoalForm.waiting_for_goal_target)
async def process_goal_target(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        target = float(message.text.replace(',', '.'))
        if target <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Введите целевую сумму:", parse_mode="HTML")
            return
        
        await state.update_data(target_amount=target)
        await message.answer(
            "📁 <b>Выберите категорию цели:</b>",
            parse_mode="HTML",
            reply_markup=get_goal_categories_keyboard()
        )
        await state.set_state(SavingsGoalForm.waiting_for_goal_category)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 500000", parse_mode="HTML")

@dp.callback_query(F.data.startswith("goal_category_"), SavingsGoalForm.waiting_for_goal_category)
async def process_goal_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("goal_category_", "")
    await state.update_data(category=category)
    
    await callback.message.answer(
        "📅 <b>Введите срок цели (необязательно):</b>\n"
        "Формат: ДД.ММ.ГГГГ\n"
        "Или отправьте '-', чтобы пропустить",
        parse_mode="HTML"
    )
    await state.set_state(SavingsGoalForm.waiting_for_goal_deadline)
    await callback.answer()

@dp.message(SavingsGoalForm.waiting_for_goal_deadline)
async def process_goal_deadline(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    data = await state.get_data()
    deadline = None
    
    if message.text != '-':
        try:
            deadline = datetime.strptime(message.text, '%d.%m.%Y').date()
            if deadline < date.today():
                await message.answer("⚠️ Вы указали прошедшую дату. Пожалуйста, введите будущую дату или '-'", parse_mode="HTML")
                return
        except ValueError:
            await message.answer("❌ Неверный формат даты. Введите ДД.ММ.ГГГГ или '-'", parse_mode="HTML")
            return
    
    loading_msg = await show_loading_message(message, "Создаю цель")
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """INSERT INTO savings_goals 
            (user_id, name, target_amount, current_amount, category, deadline) 
            VALUES (?, ?, ?, ?, ?, ?)""",
            (message.from_user.id, data['name'], data['target_amount'], 
             0, data['category'], deadline.isoformat() if deadline else None)
        )
        await db.commit()
    
    await loading_msg.delete()
    
    deadline_text = deadline.strftime('%d.%m.%Y') if deadline else 'Не установлен'
    
    # Создаем карточку цели
    goal_card = create_goal_card({
        'name': data['name'],
        'target_amount': data['target_amount'],
        'current_amount': 0,
        'category': data['category'],
        'deadline': deadline.isoformat() if deadline else None
    })
    
    await send_beautiful_notification(
        message.chat.id,
        "✅ Цель создана",
        f"{goal_card}\n\n<i>Вы можете пополнить цель через меню «🎯 Мои цели»</i>",
        "success"
    )
    
    await state.clear()

@dp.callback_query(F.data == "list_goals")
async def list_goals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await show_typing_effect(callback.message.chat.id, 1)
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? AND completed = 0 ORDER BY deadline IS NULL, deadline",
            (user_id,)
        )
        goals = await cursor.fetchall()
    
    if not goals:
        await callback.message.edit_text(
            "📭 <b>У вас пока нет активных целей.</b>\n\n"
            "Нажмите «➕ Добавить цель», чтобы создать первую.",
            parse_mode="HTML",
            reply_markup=get_goals_keyboard()
        )
        await callback.answer()
        return
    
    goals_text = []
    total_target = 0
    total_current = 0
    
    for goal in goals:
        goal_card = create_goal_card(goal)
        goals_text.append(goal_card)
        
        total_target += goal['target_amount']
        total_current += goal['current_amount']
    
    total_percentage = (total_current / total_target * 100) if total_target > 0 else 0
    
    await callback.message.edit_text(
        f"🎯 <b>Ваши цели накоплений</b>\n\n" +
        "\n\n".join(goals_text) +
        f"\n\n📈 <b>Итого по всем целям:</b>\n"
        f"💰 Общая цель: {total_target:,.0f} руб.\n"
        f"💎 Накоплено: {total_current:,.0f} руб.\n"
        f"📊 Общий прогресс: {get_fancy_progress_bar(total_percentage)}",
        parse_mode="HTML",
        reply_markup=get_goals_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "goals_progress")
async def show_goals_progress(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? AND completed = 0 ORDER BY (current_amount/target_amount) DESC",
            (user_id,)
        )
        goals = await cursor.fetchall()
    
    if not goals:
        await callback.message.answer(
            "📭 <b>У вас пока нет активных целей.</b>",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Создаем таблицу прогресса
    headers = ["Цель", "Прогресс", "Накоплено"]
    rows = []
    
    for goal in goals:
        percentage = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
        progress_bar = get_colored_progress_bar(percentage, width=8)
        
        rows.append([
            goal['name'][:12],
            progress_bar,
            f"{goal['current_amount']:.0f}/{goal['target_amount']:.0f}"
        ])
    
    table = create_fancy_table(headers, rows, [12, 20, 15])
    
    await callback.message.answer(
        f"📊 <b>Прогресс по целям</b>\n\n{table}",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "deposit_to_goal")
async def deposit_to_goal_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await show_typing_effect(callback.message.chat.id, 0.5)
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? AND completed = 0 ORDER BY name",
            (user_id,)
        )
        goals = await cursor.fetchall()
    
    if not goals:
        await callback.message.edit_text(
            "📭 <b>У вас нет активных целей для пополнения.</b>\n\n"
            "Сначала создайте цель через «➕ Добавить цель».",
            parse_mode="HTML",
            reply_markup=get_goals_keyboard()
        )
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for goal in goals:
        percentage = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
        button_text = f"{goal['name'][:15]} ({percentage:.0f}%)"
        builder.add(InlineKeyboardButton(
            text=button_text,
            callback_data=f"select_goal_{goal['id']}"
        ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "💰 <b>Выберите цель для пополнения:</b>\n\n"
        "Нажмите на кнопку с названием цели, которую хотите пополнить.",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.set_state(DepositToGoalForm.waiting_for_goal_selection)
    await callback.answer()

@dp.callback_query(F.data.startswith("select_goal_"), DepositToGoalForm.waiting_for_goal_selection)
async def select_goal_for_deposit(callback: types.CallbackQuery, state: FSMContext):
    goal_id = int(callback.data.split("_")[2])
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        goal = await cursor.fetchone()
    
    if not goal:
        await callback.message.edit_text("❌ Цель не найдена.")
        await callback.answer()
        return
    
    goal_card = create_goal_card(goal)
    
    await state.update_data(goal_id=goal_id, goal_name=goal['name'], 
                           current_amount=goal['current_amount'], 
                           target_amount=goal['target_amount'])
    
    await callback.message.answer(
        f"💰 <b>Пополнение цели</b>\n\n{goal_card}\n\n"
        f"<b>Введите сумму для пополнения:</b>",
        parse_mode="HTML"
    )
    await state.set_state(DepositToGoalForm.waiting_for_deposit_amount)
    await callback.answer()

@dp.message(DepositToGoalForm.waiting_for_deposit_amount)
async def process_deposit_amount(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0.", parse_mode="HTML")
            return
        
        data = await state.get_data()
        goal_id = data['goal_id']
        
        loading_msg = await show_loading_message(message, "Пополняю цель")
        
        async with aiosqlite.connect(DATABASE) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
            goal = await cursor.fetchone()
            
            new_amount = goal['current_amount'] + amount
            completed = new_amount >= goal['target_amount']
            
            await db.execute(
                """UPDATE savings_goals 
                SET current_amount = ?, completed = ?, completed_at = ?
                WHERE id = ?""",
                (new_amount, 1 if completed else 0, 
                 datetime.now().isoformat() if completed else None, goal_id)
            )
            
            if completed and not goal['completed']:
                await db.execute(
                    """INSERT INTO goal_achievements 
                    (user_id, goal_name, target_amount, achieved_at) 
                    VALUES (?, ?, ?, ?)""",
                    (message.from_user.id, goal['name'], goal['target_amount'], 
                     datetime.now().isoformat())
                )
            
            await db.commit()
        
        await loading_msg.delete()
        
        if completed:
            # Поздравление с достижением цели
            await send_beautiful_notification(
                message.chat.id,
                "🎉 Цель достигнута!",
                f"🏆 <b>Поздравляем!</b>\n\n"
                f"🎯 <b>Цель:</b> {goal['name']}\n"
                f"💰 <b>Целевая сумма:</b> {goal['target_amount']:.2f} руб.\n"
                f"💎 <b>Финальное пополнение:</b> {amount:.2f} руб.\n"
                f"✨ <b>Цель успешно достигнута!</b>",
                "celebration"
            )
        else:
            # Обычное уведомление о пополнении
            updated_goal = {
                'name': goal['name'],
                'target_amount': goal['target_amount'],
                'current_amount': new_amount,
                'category': goal['category'],
                'deadline': goal['deadline']
            }
            
            goal_card = create_goal_card(updated_goal)
            
            await send_beautiful_notification(
                message.chat.id,
                "✅ Цель пополнена",
                f"{goal_card}\n\n"
                f"💸 <b>Пополнено:</b> {amount:.2f} руб.",
                "success"
            )
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 5000", parse_mode="HTML")

@dp.callback_query(F.data == "completed_goals")
async def show_completed_goals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await show_typing_effect(callback.message.chat.id, 1)
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? AND completed = 1 ORDER BY completed_at DESC",
            (user_id,)
        )
        goals = await cursor.fetchall()
    
    if not goals:
        await callback.message.edit_text(
            "📭 <b>У вас пока нет завершенных целей.</b>\n\n"
            "Достигайте свои цели и они появятся здесь!",
            parse_mode="HTML",
            reply_markup=get_goals_keyboard()
        )
        await callback.answer()
        return
    
    goals_text = []
    total_achieved = 0
    
    for goal in goals:
        completed_at = datetime.strptime(goal['completed_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y') if goal['completed_at'] else 'Неизвестно'
        time_taken = calculate_time_taken(goal['created_at'], goal['completed_at'])
        
        goal_text = (
            f"🏆 <b>{goal['name']}</b>\n"
            f"📁 Категория: {goal['category']}\n"
            f"💰 Цель: {goal['target_amount']:.2f} руб.\n"
            f"✅ Достигнуто: {completed_at}\n"
            f"⏱ Время накопления: {time_taken}\n"
        )
        goals_text.append(goal_text)
        total_achieved += goal['target_amount']
    
    await callback.message.edit_text(
        f"🏆 <b>Ваши достижения</b>\n\n" +
        "\n\n".join(goals_text) +
        f"\n\n📈 <b>Всего накоплено:</b> {total_achieved:,.0f} руб.\n"
        f"🎯 <b>Завершено целей:</b> {len(goals)}",
        parse_mode="HTML",
        reply_markup=get_goals_keyboard()
    )
    await callback.answer()

# ==================== ВНЕСЕНИЕ РАСХОДОВ ====================
@dp.message(F.text == "💸 Внести расход")
async def add_expense_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    await message.answer("💸 <b>Введите сумму расхода:</b>\nПример: 2500", parse_mode="HTML")
    await state.set_state(ExpenseForm.waiting_for_expense_amount)

@dp.message(ExpenseForm.waiting_for_expense_amount)
async def process_expense_amount(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Введите сумму расхода:")
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            "📊 <b>Выберите категорию расхода:</b>",
            reply_markup=get_categories_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(ExpenseForm.waiting_for_expense_category)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 2500")

@dp.callback_query(F.data.startswith("category_"), ExpenseForm.waiting_for_expense_category)
async def process_expense_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("category_", "")
    await state.update_data(category=category)
    
    await callback.message.edit_text(
        f"📝 <b>Категория выбрана:</b> {category}\n\n"
        f"Введите описание расхода (необязательно):\n"
        f"<i>Пример: «Обед в ресторане», «Бензин на машину»</i>",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        "Или нажмите «Пропустить», если описание не нужно:",
        reply_markup=get_skip_keyboard()
    )
    
    await state.set_state(ExpenseForm.waiting_for_expense_description)
    await callback.answer()

@dp.callback_query(F.data == "skip_description")
async def skip_description(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ExpenseForm.waiting_for_expense_description.state:
        await save_expense(callback, state, "")
    elif current_state == IncomeForm.waiting_for_income_description.state:
        await save_income(callback, state, "")
    else:
        await callback.answer("Неизвестное состояние")

@dp.message(ExpenseForm.waiting_for_expense_description)
async def process_expense_description(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    await save_expense(message, state, message.text)

async def save_expense(source, state: FSMContext, description: str):
    data = await state.get_data()
    user_id = source.from_user.id if isinstance(source, types.Message) else source.from_user.id
    
    overspent, warning = await check_budget_overspending(
        user_id, data['category'], data['amount']
    )
    
    loading_msg = None
    if isinstance(source, types.Message):
        loading_msg = await show_loading_message(source, "Сохраняю расход")
    else:
        loading_msg = await show_loading_message(source.message, "Сохраняю расход")
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """INSERT INTO expenses (user_id, amount, category, description)
            VALUES (?, ?, ?, ?)""",
            (user_id, data['amount'], data['category'], description)
        )
        await db.commit()
    
    await loading_msg.delete()
    
    message_text = (
        f"✅ <b>Расход успешно добавлен!</b>\n\n"
        f"💸 <b>Сумма:</b> {data['amount']:.2f} руб.\n"
        f"📊 <b>Категория:</b> {data['category']}\n"
    )
    
    if description:
        message_text += f"📝 <b>Описание:</b> {description}\n"
    
    notification_type = "success"
    if warning:
        if overspent:
            message_text += f"\n⚠️ <b>ВНИМАНИЕ!</b> {warning}\n"
            notification_type = "error"
        else:
            message_text += f"\nℹ️ {warning}\n"
            notification_type = "warning"
    
    await send_beautiful_notification(
        user_id,
        "✅ Расход добавлен",
        message_text,
        notification_type
    )
    
    await state.clear()

# ==================== ВНЕСЕНИЕ ДОХОДОВ ====================
@dp.message(F.text == "💰 Внести доход")
async def add_income_start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    await message.answer("💰 <b>Введите сумму дохода:</b>\nПример: 50000", parse_mode="HTML")
    await state.set_state(IncomeForm.waiting_for_income_amount)

@dp.message(IncomeForm.waiting_for_income_amount)
async def process_income_amount(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Введите сумму дохода:")
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            "💼 <b>Введите источник дохода:</b>\n"
            "Пример: Зарплата, Фриланс, Инвестиции",
            parse_mode="HTML"
        )
        await state.set_state(IncomeForm.waiting_for_income_source)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 50000")

@dp.message(IncomeForm.waiting_for_income_source)
async def process_income_source(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    await state.update_data(source=message.text)
    await message.answer(
        "📝 <b>Введите описание дохода</b> (необязательно):\n"
        "<i>Пример: «Аванс за январь», «Оплата проекта»</i>",
        parse_mode="HTML"
    )
    
    await message.answer(
        "Или нажмите «Пропустить», если описание не нужно:",
        reply_markup=get_skip_keyboard()
    )
    
    await state.set_state(IncomeForm.waiting_for_income_description)

@dp.message(IncomeForm.waiting_for_income_description)
async def process_income_description(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    await save_income(message, state, message.text)

async def save_income(source, state: FSMContext, description: str = ""):
    data = await state.get_data()
    user_id = source.from_user.id if isinstance(source, types.Message) else source.from_user.id
    
    loading_msg = None
    if isinstance(source, types.Message):
        loading_msg = await show_loading_message(source, "Сохраняю доход")
    else:
        loading_msg = await show_loading_message(source.message, "Сохраняю доход")
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """INSERT INTO income (user_id, amount, source, description)
            VALUES (?, ?, ?, ?)""",
            (user_id, data['amount'], data['source'], description)
        )
        await db.commit()
    
    await loading_msg.delete()
    
    message_text = (
        f"✅ <b>Доход успешно добавлен!</b>\n\n"
        f"💰 <b>Сумма:</b> {data['amount']:.2f} руб.\n"
        f"💼 <b>Источник:</b> {data['source']}\n"
    )
    
    if description and description.strip():
        message_text += f"📝 <b>Описание:</b> {description}\n"
    
    await send_beautiful_notification(
        user_id,
        "✅ Доход добавлен",
        message_text,
        "success"
    )
    
    await state.clear()

# ==================== БЮДЖЕТИРОВАНИЕ ====================
@dp.message(F.text == "💰 Бюджет")
async def budget_main_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    
    await message.answer(
        "💰 <b>Управление бюджетами</b>\n\n"
        "✨ <b>Новые возможности:</b>\n"
        "• 📊 Визуальная панель бюджета\n"
        "• 🎨 Цветная индикация прогресса\n"
        "• 📈 Детальная аналитика\n\n"
        "<b>Функции:</b>\n"
        "• Установить бюджет на месяц\n"
        "• Отслеживать расходы по категориям\n"
        "• Получать уведомления о приближении к лимиту\n"
        "• Анализировать выполнение бюджета",
        parse_mode="HTML",
        reply_markup=get_budget_menu_keyboard()
    )

@dp.callback_query(F.data == "budget_back")
async def back_to_budget_menu(callback: types.CallbackQuery, state: FSMContext):
    await budget_main_menu(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "budget_set")
async def set_budget_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📊 <b>Выберите категорию для установки бюджета:</b>",
        parse_mode="HTML",
        reply_markup=get_budget_categories_keyboard()
    )
    await state.set_state(BudgetForm.waiting_for_budget_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("budget_cat_"), BudgetForm.waiting_for_budget_category)
async def process_budget_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("budget_cat_", "")
    await state.update_data(category=category)
    
    await callback.message.answer(
        f"💰 <b>Введите сумму бюджета для категории {category}:</b>\n\n"
        f"Пример: 10000 (для бюджета в 10,000 рублей)",
        parse_mode="HTML"
    )
    await state.set_state(BudgetForm.waiting_for_budget_amount)
    await callback.answer()

@dp.message(BudgetForm.waiting_for_budget_amount)
async def process_budget_amount(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0. Введите сумму бюджета:")
            return
        
        await state.update_data(amount=amount)
        
        await message.answer(
            "📅 <b>Выберите период для бюджета:</b>\n\n"
            "Бюджет устанавливается на месяц вперед.",
            parse_mode="HTML",
            reply_markup=get_budget_period_keyboard()
        )
        await state.set_state(BudgetForm.waiting_for_budget_period)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 10000")

@dp.callback_query(F.data.startswith("budget_period_"), BudgetForm.waiting_for_budget_period)
async def process_budget_period(callback: types.CallbackQuery, state: FSMContext):
    period = callback.data.replace("budget_period_", "")
    data = await state.get_data()
    
    user_id = callback.from_user.id
    category = data['category']
    amount = data['amount']
    
    loading_msg = await show_loading_message(callback.message, "Устанавливаю бюджет")
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ? AND period = ?",
            (user_id, category, period)
        )
        await db.execute(
            "INSERT INTO budgets (user_id, category, amount, period) VALUES (?, ?, ?, ?)",
            (user_id, category, amount, period)
        )
        await db.commit()
    
    await loading_msg.delete()
    
    period_display = format_period(period)
    
    await send_beautiful_notification(
        user_id,
        "✅ Бюджет установлен",
        f"📊 <b>Категория:</b> {category}\n"
        f"💰 <b>Сумма:</b> {amount:.2f} руб.\n"
        f"📅 <b>Период:</b> {period_display}\n\n"
        f"<i>Теперь при добавлении расходов я буду уведомлять вас о приближении к лимиту.</i>",
        "success"
    )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "budget_list")
async def list_budgets(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    today = datetime.now()
    current_period = today.strftime('%Y-%m')
    
    await show_typing_effect(callback.message.chat.id, 1)
    
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM budgets WHERE user_id = ? AND period = ? ORDER BY category",
            (user_id, current_period)
        )
        budgets = await cursor.fetchall()
    
    if not budgets:
        await callback.message.edit_text(
            "📭 <b>У вас нет установленных бюджетов на текущий месяц.</b>\n\n"
            "Нажмите «➕ Установить бюджет», чтобы создать первый.",
            parse_mode="HTML",
            reply_markup=get_budget_menu_keyboard()
        )
        await callback.answer()
        return
    
    progress = await get_budget_progress(user_id, current_period)
    
    budgets_text = []
    total_budget = 0
    total_spent = 0
    
    for budget in budgets:
        category = budget['category']
        budget_amount = budget['amount']
        cat_progress = progress.get(category, {})
        
        spent = cat_progress.get('spent', 0)
        remaining = cat_progress.get('remaining', budget_amount)
        percentage = cat_progress.get('percentage', 0)
        
        if percentage >= 100:
            status_emoji = "🔴"
            status_text = "ПРЕВЫШЕН"
        elif percentage >= 80:
            status_emoji = "🟠"
            status_text = "ПОЧТИ ИСЧЕРПАН"
        elif percentage >= 50:
            status_emoji = "🟡"
            status_text = "НОРМА"
        else:
            status_emoji = "🟢"
            status_text = "В НОРМЕ"
        
        progress_bar = get_fancy_progress_bar(percentage)
        
        budget_text = (
            f"{status_emoji} <b>{category}</b>\n"
            f"   💰 Бюджет: {budget_amount:.2f} руб.\n"
            f"   💸 Потрачено: {spent:.2f} руб.\n"
            f"   📊 Остаток: {remaining:.2f} руб.\n"
            f"   📈 Прогресс: {progress_bar}\n"
            f"   🎯 Статус: {status_text} ({percentage:.1f}%)\n"
        )
        budgets_text.append(budget_text)
        
        total_budget += budget_amount
        total_spent += spent
    
    total_percentage = (total_spent / total_budget * 100) if total_budget > 0 else 0
    
    message_text = (
        f"💰 <b>Ваши бюджеты на {format_period(current_period)}</b>\n\n" +
        "\n".join(budgets_text) +
        f"\n📊 <b>Итого по всем бюджетам:</b>\n"
        f"   💰 Общий бюджет: {total_budget:.2f} руб.\n"
        f"   💸 Всего потрачено: {total_spent:.2f} руб.\n"
        f"   📈 Общий прогресс: {get_fancy_progress_bar(total_percentage)}\n"
        f"   🎯 Среднее выполнение: {total_percentage:.1f}%\n\n"
        f"<i>🟢 В норме (< 80%) 🟡 Норма (50-80%) 🟠 Почти исчерпан (80-100%) 🔴 Превышен (> 100%)</i>"
    )
    
    await callback.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=get_budget_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "budget_dashboard")
async def show_budget_dashboard(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    today = datetime.now()
    current_period = today.strftime('%Y-%m')
    
    await show_typing_effect(callback.message.chat.id, 1)
    
    progress = await get_budget_progress(user_id, current_period)
    
    if not progress:
        await callback.message.answer(
            "📭 <b>Нет данных для панели бюджета.</b>\n\n"
            "Сначала установите бюджеты через меню управления бюджетами.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    dashboard = create_budget_dashboard(progress)
    
    # Добавляем статистику
    total_budget = sum(data['budget'] for data in progress.values())
    total_spent = sum(data['spent'] for data in progress.values())
    avg_percentage = np.mean([data['percentage'] for data in progress.values()]) if progress else 0
    
    stats = (
        f"\n📊 <b>Статистика за {format_period(current_period)}:</b>\n"
        f"• 💰 Общий бюджет: {total_budget:,.0f} руб.\n"
        f"• 💸 Всего потрачено: {total_spent:,.0f} руб.\n"
        f"• 📈 Средний прогресс: {get_colored_progress_bar(avg_percentage)}\n"
        f"• 🎯 Категорий: {len(progress)}"
    )
    
    await callback.message.answer(
        f"{dashboard}{stats}",
        parse_mode="HTML",
        reply_markup=get_budget_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "budget_analysis")
async def budget_analysis(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    today = datetime.now()
    current_period = today.strftime('%Y-%m')
    
    await show_typing_effect(callback.message.chat.id, 1)
    
    progress = await get_budget_progress(user_id, current_period)
    
    if not progress:
        await callback.message.answer(
            "📭 <b>Нет данных для анализа.</b>\n\n"
            "Сначала установите бюджеты через меню управления бюджетами.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    categories = list(progress.keys())
    budgets = [progress[cat]['budget'] for cat in categories]
    spent = [progress[cat]['spent'] for cat in categories]
    percentages = [progress[cat]['percentage'] for cat in categories]
    
    overspent_cats = [cat for cat, perc in zip(categories, percentages) if perc >= 100]
    warning_cats = [cat for cat, perc in zip(categories, percentages) if 80 <= perc < 100]
    good_cats = [cat for cat, perc in zip(categories, percentages) if perc < 80]
    
    analysis_text = f"📈 <b>Анализ бюджета за {format_period(current_period)}</b>\n\n"
    
    if overspent_cats:
        analysis_text += "🔴 <b>Превышены лимиты:</b>\n"
        for cat in overspent_cats:
            cat_data = progress[cat]
            overspent = cat_data['spent'] - cat_data['budget']
            analysis_text += f"   • {cat}: превышение на {overspent:.2f} руб. ({cat_data['percentage']:.1f}%)\n"
        analysis_text += "\n"
    
    if warning_cats:
        analysis_text += "🟠 <b>Близко к лимиту (80-100%):</b>\n"
        for cat in warning_cats:
            cat_data = progress[cat]
            analysis_text += f"   • {cat}: осталось {cat_data['remaining']:.2f} руб. ({cat_data['percentage']:.1f}%)\n"
        analysis_text += "\n"
    
    if good_cats:
        analysis_text += "🟢 <b>В пределах нормы:</b>\n"
        for cat in good_cats[:5]:
            cat_data = progress[cat]
            analysis_text += f"   • {cat}: остаток {cat_data['remaining']:.2f} руб. ({cat_data['percentage']:.1f}%)\n"
        if len(good_cats) > 5:
            analysis_text += f"   ... и еще {len(good_cats) - 5} категорий\n"
        analysis_text += "\n"
    
    total_budget = sum(budgets)
    total_spent = sum(spent)
    avg_percentage = np.mean(percentages) if percentages else 0
    
    analysis_text += (
        f"📊 <b>Общая статистика:</b>\n"
        f"   • Всего категорий с бюджетом: {len(categories)}\n"
        f"   • Общий бюджет: {total_budget:.2f} руб.\n"
        f"   • Всего потрачено: {total_spent:.2f} руб.\n"
        f"   • Среднее выполнение: {avg_percentage:.1f}%\n"
        f"   • Превышено лимитов: {len(overspent_cats)}\n"
        f"   • Близко к лимиту: {len(warning_cats)}\n"
    )
    
    analysis_text += "\n💡 <b>Рекомендации:</b>\n"
    if overspent_cats:
        analysis_text += "   • Рассмотрите увеличение бюджета для категорий с превышением\n"
    if warning_cats:
        analysis_text += "   • Будьте внимательны с расходами в категориях, близких к лимиту\n"
    if avg_percentage < 50:
        analysis_text += "   • Вы хорошо укладываетесь в бюджет! Продолжайте в том же духе!\n"
    
    await callback.message.edit_text(
        analysis_text,
        parse_mode="HTML",
        reply_markup=get_budget_menu_keyboard()
    )
    await callback.answer()

# ==================== АНАЛИТИКА ====================
@dp.message(F.text == "📈 Аналитика+")
async def show_enhanced_analytics(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 1)
    
    user_id = message.from_user.id
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    
    loading_msg = await show_loading_message(message, "Подготавливаю аналитику")
    
    async with aiosqlite.connect(DATABASE) as db:
        # Расходы по категориям
        cursor = await db.execute("""
            SELECT SUM(amount) as total, category
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, f"{current_month:02d}", str(current_year)))
        expenses_by_category = await cursor.fetchall()
        
        # Общие расходы
        cursor = await db.execute("""
            SELECT SUM(amount) as total
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
        """, (user_id, f"{current_month:02d}", str(current_year)))
        total_expenses_result = await cursor.fetchone()
        total_expenses = total_expenses_result[0] if total_expenses_result[0] else 0
        
        # Общие доходы
        cursor = await db.execute("""
            SELECT SUM(amount) as total
            FROM income
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
        """, (user_id, f"{current_month:02d}", str(current_year)))
        total_income_result = await cursor.fetchone()
        total_income = total_income_result[0] if total_income_result[0] else 0
        
        # Ежедневные расходы
        cursor = await db.execute("""
            SELECT strftime('%d', created_at) as day, SUM(amount) as total
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY day
            ORDER BY day
        """, (user_id, f"{current_month:02d}", str(current_year)))
        daily_expenses = await cursor.fetchall()
    
    await loading_msg.delete()
    
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    month_name = month_names[current_month - 1]
    
    # Создаем красивую сводку
    balance = total_income - total_expenses
    savings_percent = ((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0
    
    summary = (
        f"📊 <b>Расширенная аналитика за {month_name} {current_year}</b>\n\n"
        f"💰 <b>Доходы:</b> {total_income:,.0f} руб.\n"
        f"💸 <b>Расходы:</b> {total_expenses:,.0f} руб.\n"
        f"📈 <b>Баланс:</b> {balance:,.0f} руб.\n"
        f"💎 <b>Сбережения:</b> {savings_percent:.1f}% от доходов\n\n"
    )
    
    if expenses_by_category:
        # Создаем таблицу категорий
        headers = ["Категория", "Сумма", "Доля"]
        rows = []
        
        for expense in expenses_by_category:
            percent = (expense[0] / total_expenses * 100) if total_expenses > 0 else 0
            rows.append([
                expense[1],
                f"{expense[0]:,.0f}р",
                f"{percent:.1f}%"
            ])
        
        table = create_fancy_table(headers, rows, [12, 12, 10])
        summary += f"<b>Расходы по категориям:</b>\n{table}\n\n"
    
    if daily_expenses:
        summary += f"<b>Дней с расходами:</b> {len(daily_expenses)}\n"
    
    summary += "<i>Выберите опцию ниже для детальной аналитики:</i>"
    
    await message.answer(summary, parse_mode="HTML", reply_markup=get_enhanced_analytics_keyboard())

@dp.callback_query(F.data == "analytics_chart")
async def send_expenses_chart(callback: types.CallbackQuery):
    await show_typing_effect(callback.message.chat.id, 1)
    
    user_id = callback.from_user.id
    now = datetime.now()
    
    loading_msg = await show_loading_message(callback.message, "Создаю график")
    
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT strftime('%d', created_at) as day, SUM(amount) as total
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY day
            ORDER BY day
        """, (user_id, f"{now.month:02d}", str(now.year)))
        daily_expenses = await cursor.fetchall()
    
    if not daily_expenses:
        await loading_msg.delete()
        await callback.message.answer(
            "📭 <b>Нет данных для построения графика.</b>\nДобавьте расходы в этом месяце.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    days = [int(expense[0]) for expense in daily_expenses]
    amounts = [expense[1] for expense in daily_expenses]
    
    # Создаем график
    plt.figure(figsize=(12, 6))
    plt.style.use('seaborn-v0_8-darkgrid')
    
    # Основной график
    plt.subplot(1, 2, 1)
    bars = plt.bar(days, amounts, color='#4CAF50', edgecolor='#2E7D32', linewidth=1.5, alpha=0.8)
    plt.xlabel('День месяца', fontsize=11, fontweight='bold')
    plt.ylabel('Сумма расходов (руб.)', fontsize=11, fontweight='bold')
    plt.title(f'📅 Расходы по дням', fontsize=13, fontweight='bold', pad=15)
    plt.grid(axis='y', alpha=0.3, linestyle='--')
    
    # Добавляем значения на столбцы
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + max(amounts)*0.02,
                f'{height:.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    # График накопленных расходов
    plt.subplot(1, 2, 2)
    cumulative = np.cumsum(amounts)
    plt.plot(days, cumulative, color='#2196F3', linewidth=3, marker='o', markersize=6)
    plt.fill_between(days, cumulative, alpha=0.2, color='#2196F3')
    plt.xlabel('День месяца', fontsize=11, fontweight='bold')
    plt.ylabel('Накопленные расходы (руб.)', fontsize=11, fontweight='bold')
    plt.title(f'📈 Накопленные расходы', fontsize=13, fontweight='bold', pad=15)
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # Добавляем аннотации для конечной точки
    if cumulative.size > 0:
        plt.annotate(f'{cumulative[-1]:.0f} руб.', 
                    xy=(days[-1], cumulative[-1]),
                    xytext=(days[-1]-2, cumulative[-1] + max(cumulative)*0.1),
                    arrowprops=dict(arrowstyle='->', color='#FF5722'),
                    fontsize=10, fontweight='bold')
    
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    await loading_msg.delete()
    
    total_spent = sum(amounts)
    avg_daily = total_spent / len(days) if days else 0
    max_day = max(amounts) if amounts else 0
    
    caption = (
        f"📊 <b>График расходов за {now.month}.{now.year}</b>\n\n"
        f"📅 <b>Статистика:</b>\n"
        f"• Всего потрачено: {total_spent:,.0f} руб.\n"
        f"• Среднедневные расходы: {avg_daily:,.0f} руб.\n"
        f"• Максимум за день: {max_day:,.0f} руб.\n"
        f"• Дней с расходами: {len(days)}\n\n"
        f"<i>Левый график: ежедневные расходы\nПравый график: накопленные расходы</i>"
    )
    
    await callback.message.answer_photo(
        types.BufferedInputFile(buf.read(), filename="expenses_chart.png"),
        caption=caption,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "analytics_enhanced")
async def send_enhanced_chart(callback: types.CallbackQuery):
    await show_typing_effect(callback.message.chat.id, 2)
    
    user_id = callback.from_user.id
    now = datetime.now()
    
    loading_msg = await show_loading_message(callback.message, "Создаю расширенный график")
    
    async with aiosqlite.connect(DATABASE) as db:
        # Расходы по категориям
        cursor = await db.execute("""
            SELECT category, SUM(amount) as total
            FROM expenses
            WHERE user_id = ? 
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, f"{now.month:02d}", str(now.year)))
        category_expenses = await cursor.fetchall()
        
        # Доходы по источникам
        cursor = await db.execute("""
            SELECT source, SUM(amount) as total
            FROM income
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY source
            ORDER BY total DESC
        """, (user_id, f"{now.month:02d}", str(now.year)))
        income_sources = await cursor.fetchall()
    
    if not category_expenses and not income_sources:
        await loading_msg.delete()
        await callback.message.answer(
            "📭 <b>Нет данных для расширенного графика.</b>\nДобавьте расходы и доходы в этом месяце.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Создаем расширенный график
    fig = plt.figure(figsize=(14, 10))
    plt.style.use('seaborn-v0_8-darkgrid')
    
    # Цветовая палитра
    colors1 = plt.cm.Set3(np.linspace(0, 1, len(category_expenses) if category_expenses else 1))
    colors2 = plt.cm.Pastel1(np.linspace(0, 1, len(income_sources) if income_sources else 1))
    
    # 1. Круговая диаграмма расходов
    if category_expenses:
        ax1 = plt.subplot(2, 2, 1)
        categories = [expense[0] for expense in category_expenses]
        amounts = [expense[1] for expense in category_expenses]
        
        wedges, texts, autotexts = ax1.pie(amounts, labels=categories, colors=colors1,
                                          autopct=lambda pct: f'{pct:.1f}%\n({pct*sum(amounts)/100:.0f} руб.)',
                                          startangle=90, pctdistance=0.85)
        
        # Делаем подписи более читаемыми
        for text in texts:
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_fontsize(8)
            autotext.set_fontweight('bold')
        
        ax1.set_title('💸 Распределение расходов', fontsize=12, fontweight='bold', pad=20)
    
    # 2. Столбчатая диаграмма расходов
    if category_expenses:
        ax2 = plt.subplot(2, 2, 2)
        bars = ax2.barh(categories, amounts, color=colors1, edgecolor='black', linewidth=0.5)
        ax2.set_xlabel('Сумма (руб.)', fontsize=10, fontweight='bold')
        ax2.set_title('📊 Суммы по категориям', fontsize=12, fontweight='bold', pad=20)
        ax2.grid(axis='x', alpha=0.3, linestyle='--')
        
        # Добавляем значения
        for bar in bars:
            width = bar.get_width()
            ax2.text(width + max(amounts)*0.01, bar.get_y() + bar.get_height()/2,
                    f'{width:.0f}', va='center', fontsize=9, fontweight='bold')
    
    # 3. Круговая диаграмма доходов
    if income_sources:
        ax3 = plt.subplot(2, 2, 3)
        sources = [income[0] for income in income_sources]
        income_amounts = [income[1] for income in income_sources]
        
        wedges2, texts2, autotexts2 = ax3.pie(income_amounts, labels=sources, colors=colors2,
                                             autopct=lambda pct: f'{pct:.1f}%\n({pct*sum(income_amounts)/100:.0f} руб.)',
                                             startangle=90, pctdistance=0.85)
        
        for text in texts2:
            text.set_fontsize(9)
        for autotext in autotexts2:
            autotext.set_fontsize(8)
            autotext.set_fontweight('bold')
        
        ax3.set_title('💰 Источники доходов', fontsize=12, fontweight='bold', pad=20)
    
    # 4. Общая статистика
    ax4 = plt.subplot(2, 2, 4)
    ax4.axis('off')  # Отключаем оси
    
    # Рассчитываем статистику
    total_expenses = sum(amounts) if category_expenses else 0
    total_income = sum(income_amounts) if income_sources else 0
    balance = total_income - total_expenses
    savings_percent = ((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0
    
    stats_text = (
        f"📈 <b>Финансовая сводка</b>\n\n"
        f"💰 Доходы: {total_income:,.0f} руб.\n"
        f"💸 Расходы: {total_expenses:,.0f} руб.\n"
        f"📊 Баланс: {balance:,.0f} руб.\n"
        f"💎 Сбережения: {savings_percent:.1f}%\n\n"
        f"🎯 Категорий: {len(category_expenses)}\n"
        f"💼 Источников: {len(income_sources)}"
    )
    
    ax4.text(0.1, 0.5, stats_text, transform=ax4.transAxes,
             fontsize=11, verticalalignment='center',
             bbox=dict(boxstyle='round', facecolor='#E3F2FD', alpha=0.8))
    
    plt.suptitle(f'📊 Расширенная аналитика за {now.month}.{now.year}', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    await loading_msg.delete()
    
    caption = (
        f"📈 <b>Расширенная аналитика за {now.month}.{now.year}</b>\n\n"
        f"<b>Что на графике:</b>\n"
        f"1️⃣ 💸 Распределение расходов по категориям\n"
        f"2️⃣ 📊 Суммы расходов по категориям\n"
        f"3️⃣ 💰 Источники доходов\n"
        f"4️⃣ 📈 Общая финансовая сводка\n\n"
        f"<i>Этот график показывает полную картину ваших финансов за месяц.</i>"
    )
    
    await callback.message.answer_photo(
        types.BufferedInputFile(buf.read(), filename="enhanced_analytics.png"),
        caption=caption,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "analytics_table")
async def show_analytics_table(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    now = datetime.now()
    
    await show_typing_effect(callback.message.chat.id, 1)
    
    async with aiosqlite.connect(DATABASE) as db:
        # Расходы по категориям с детализацией
        cursor = await db.execute("""
            SELECT category, COUNT(*) as count, SUM(amount) as total, AVG(amount) as avg
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, f"{now.month:02d}", str(now.year)))
        category_details = await cursor.fetchall()
        
        # Общая статистика
        cursor = await db.execute("""
            SELECT 
                SUM(CASE WHEN strftime('%w', created_at) IN ('0', '6') THEN amount ELSE 0 END) as weekend_spending,
                SUM(CASE WHEN strftime('%w', created_at) NOT IN ('0', '6') THEN amount ELSE 0 END) as weekday_spending,
                COUNT(DISTINCT strftime('%d', created_at)) as active_days,
                MAX(amount) as max_expense,
                MIN(amount) as min_expense
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
        """, (user_id, f"{now.month:02d}", str(now.year)))
        stats = await cursor.fetchone()
    
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    month_name = month_names[now.month - 1]
    
    if not category_details:
        await callback.message.answer(
            f"📭 <b>Нет данных для таблицы за {month_name} {now.year}.</b>",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Создаем детальную таблицу расходов
    headers = ["Категория", "Транз.", "Сумма", "Среднее"]
    rows = []
    
    for detail in category_details:
        rows.append([
            detail[0],
            str(detail[1]),
            f"{detail[2]:,.0f}р",
            f"{detail[3]:,.0f}р"
        ])
    
    table = create_fancy_table(headers, rows, [12, 8, 12, 10])
    
    # Добавляем статистику
    total_transactions = sum(detail[1] for detail in category_details)
    total_amount = sum(detail[2] for detail in category_details)
    avg_transaction = total_amount / total_transactions if total_transactions > 0 else 0
    
    stats_text = (
        f"\n📊 <b>Детальная статистика за {month_name}:</b>\n"
        f"• Всего транзакций: {total_transactions}\n"
        f"• Общая сумма расходов: {total_amount:,.0f} руб.\n"
        f"• Средний чек: {avg_transaction:,.0f} руб.\n"
    )
    
    if stats:
        stats_text += (
            f"• Расходы в выходные: {stats[0] or 0:,.0f} руб.\n"
            f"• Расходы в будни: {stats[1] or 0:,.0f} руб.\n"
            f"• Дней с расходами: {stats[2] or 0}\n"
            f"• Максимальная покупка: {stats[3] or 0:,.0f} руб.\n"
            f"• Минимальная покупка: {stats[4] or 0:,.0f} руб.\n"
        )
    
    await callback.message.answer(
        f"📋 <b>Детальная таблица расходов</b>\n\n{table}{stats_text}",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "analytics_previous")
async def show_previous_month(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    now = datetime.now()
    
    # Получаем предыдущий месяц
    if now.month == 1:
        prev_month = 12
        prev_year = now.year - 1
    else:
        prev_month = now.month - 1
        prev_year = now.year
    
    await show_typing_effect(callback.message.chat.id, 1)
    
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT SUM(amount) as total, category
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, f"{prev_month:02d}", str(prev_year)))
        expenses_by_category = await cursor.fetchall()
        
        cursor = await db.execute("""
            SELECT SUM(amount) as total
            FROM expenses
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
        """, (user_id, f"{prev_month:02d}", str(prev_year)))
        total_expenses_result = await cursor.fetchone()
        total_expenses = total_expenses_result[0] if total_expenses_result[0] else 0
        
        cursor = await db.execute("""
            SELECT SUM(amount) as total
            FROM income
            WHERE user_id = ?
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
        """, (user_id, f"{prev_month:02d}", str(prev_year)))
        total_income_result = await cursor.fetchone()
        total_income = total_income_result[0] if total_income_result[0] else 0
    
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    month_name = month_names[prev_month - 1]
    
    message_text = (
        f"📊 <b>Аналитика за {month_name} {prev_year}</b>\n\n"
        f"💰 <b>Доходы:</b> {total_income:,.0f} руб.\n"
        f"💸 <b>Расходы:</b> {total_expenses:,.0f} руб.\n"
        f"📈 <b>Баланс:</b> {total_income - total_expenses:,.0f} руб.\n\n"
    )
    
    if total_income > 0:
        savings_percent = ((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0
        message_text += f"💎 <b>Сбережения:</b> {savings_percent:.1f}% от доходов\n\n"
    
    if expenses_by_category:
        # Создаем таблицу
        headers = ["Категория", "Сумма", "Доля"]
        rows = []
        
        for expense in expenses_by_category:
            percent = (expense[0] / total_expenses * 100) if total_expenses > 0 else 0
            rows.append([
                expense[1],
                f"{expense[0]:,.0f}р",
                f"{percent:.1f}%"
            ])
        
        table = create_fancy_table(headers, rows, [12, 12, 10])
        message_text += f"<b>Расходы по категориям:</b>\n{table}\n"
    
    if not expenses_by_category and total_expenses == 0:
        message_text += "\n📭 <i>Расходы за этот месяц отсутствуют.</i>\n"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📅 Этот месяц", callback_data="analytics_current"))
    builder.add(InlineKeyboardButton(text="📊 График расходов", callback_data="analytics_chart"))
    builder.add(InlineKeyboardButton(text="📈 Расширенный график", callback_data="analytics_enhanced"))
    builder.adjust(2)
    
    await callback.message.edit_text(message_text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "analytics_current")
async def show_current_month(callback: types.CallbackQuery):
    await show_enhanced_analytics(callback.message)
    await callback.answer()

# ==================== НАСТРОЙКИ ====================
@dp.message(F.text == "⚙️ Настройки")
async def settings_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    
    await message.answer(
        "⚙️ <b>Настройки ASinglePoint</b>\n\n"
        "✨ <b>Новые возможности:</b>\n"
        "• 🎨 Улучшенный интерфейс\n"
        "• 🔔 Стилизованные уведомления\n"
        "• 📊 Визуальные элементы\n\n"
        "Выберите раздел для настройки:",
        reply_markup=get_settings_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "settings_notifications")
async def notification_settings(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_notification_settings(user_id)
    
    await callback.message.edit_text(
        "🔔 <b>Настройка уведомлений</b>\n\n"
        "✨ <b>Новые функции:</b>\n"
        "• 🎨 Цветные уведомления\n"
        "• 📊 Прогресс-бары в напоминаниях\n"
        "• 🎯 Интуитивная настройка\n\n"
        f"<b>Текущие настройки:</b>\n"
        f"• Уведомления: {'Включены ✅' if settings['enabled'] else 'Выключены ❌'}\n"
        f"• Напоминать за: {settings['days_before']} дней до платежа",
        parse_mode="HTML",
        reply_markup=get_notifications_keyboard(settings['enabled'], settings['days_before'])
    )
    await callback.answer()

@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_notification_settings(user_id)
    new_enabled = not settings['enabled']
    
    await update_notification_settings(user_id, enabled=new_enabled)
    settings = await get_notification_settings(user_id)
    
    status_text = "включены" if new_enabled else "выключены"
    await send_beautiful_notification(
        user_id,
        "🔔 Уведомления обновлены",
        f"Уведомления о платежах теперь <b>{status_text}</b>.",
        "success" if new_enabled else "info"
    )
    
    await notification_settings(callback)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_days_"))
async def set_days_before(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    days = int(callback.data.split("_")[2])
    
    await update_notification_settings(user_id, days_before=days)
    settings = await get_notification_settings(user_id)
    
    await send_beautiful_notification(
        user_id,
        "📅 Напоминания обновлены",
        f"Теперь я буду напоминать вам о платежах за <b>{days} дней</b> до даты платежа.",
        "success"
    )
    
    await notification_settings(callback)
    await callback.answer()

@dp.callback_query(F.data == "set_custom_days")
async def set_custom_days(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "✏️ <b>Введите количество дней для напоминания:</b>\n"
        "(от 1 до 30 дней)",
        parse_mode="HTML"
    )
    await state.set_state(NotificationForm.waiting_for_days_before)
    await callback.answer()

@dp.message(NotificationForm.waiting_for_days_before)
async def process_custom_days(message: types.Message, state: FSMContext):
    if message.text in ["➕ Добавить долг", "💸 Внести расход", "📋 Мои долги", "✅ Оплатить", 
                       "💰 Внести доход", "📈 Аналитика+", "🎯 Мои цели", "💰 Бюджет", 
                       "✏️ Редактировать", "⚙️ Настройки"]:
        await clear_state_and_show_menu(message, state)
        return
    
    try:
        days = int(message.text)
        if 1 <= days <= 30:
            user_id = message.from_user.id
            await update_notification_settings(user_id, days_before=days)
            
            await send_beautiful_notification(
                user_id,
                "✅ Напоминания установлены",
                f"Теперь я буду напоминать вам о платежах за <b>{days} дней</b> до даты платежа.",
                "success"
            )
            
            settings = await get_notification_settings(user_id)
            await message.answer(
                f"✅ Установлено напоминание за {days} дней до платежа!",
                reply_markup=get_notifications_keyboard(settings['enabled'], settings['days_before'])
            )
        else:
            await message.answer("❌ Пожалуйста, введите число от 1 до 30.")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число.")
    
    await state.clear()

@dp.callback_query(F.data == "settings_categories")
async def category_settings(callback: types.CallbackQuery):
    categories_list = "\n".join([f"• {cat}" for cat in EXPENSE_CATEGORIES])
    
    await callback.message.edit_text(
        f"📊 <b>Категории расходов:</b>\n\n{categories_list}\n\n"
        "<i>✨ В следующем обновлении вы сможете добавлять свои категории и настраивать иконки.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
            ]
        )
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_clear_data")
async def clear_data_confirm(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🗑 Да, очистить все данные", callback_data="confirm_clear_data"))
    builder.add(InlineKeyboardButton(text="❌ Нет, отмена", callback_data="back_to_settings"))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "⚠️ <b>Внимание! Это действие нельзя отменить!</b>\n\n"
        "🔴 <b>Вы уверены, что хотите очистить ВСЕ данные?</b>\n\n"
        "❌ <b>Это удалит:</b>\n"
        "• Все ваши долги\n"
        "• Все расходы\n"
        "• Все доходы\n"
        "• Все цели\n"
        "• Все бюджеты\n\n"
        "<i>Настройки уведомлений останутся без изменений.</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "confirm_clear_data")
async def clear_data(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    loading_msg = await show_loading_message(callback.message, "Очищаю данные")
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM debts WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM income WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM savings_goals WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM goal_achievements WHERE user_id = ?", (user_id,))
        await db.commit()
    
    await loading_msg.delete()
    
    await send_beautiful_notification(
        user_id,
        "✅ Данные очищены",
        "Все ваши данные успешно удалены.\nВы можете начать заново, добавив новые данные.",
        "success"
    )
    
    await settings_menu(callback.message)
    await callback.answer("Данные очищены!")

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: types.CallbackQuery):
    await settings_menu(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_typing_effect(callback.message.chat.id, 0.5)
    
    await callback.message.answer(
        f"{get_random_emoji()} Возвращаюсь в главное меню...",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# ==================== ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД ====================
@dp.message()
async def handle_unknown_message(message: types.Message, state: FSMContext):
    await state.clear()
    await show_typing_effect(message.chat.id, 0.5)
    
    await send_beautiful_notification(
        message.chat.id,
        "🤔 Неизвестная команда",
        "Я не понял вашу команду.\nИспользуйте меню ниже или команду /start",
        "info"
    )
    
    await message.answer(
        "Используйте меню ниже для навигации:",
        reply_markup=get_main_menu()
    )

# ==================== ЗАПУСК БОТА ====================
async def main():
    scheduler.start()
    await init_db()
    await schedule_notifications()
    
    # Отправляем сообщение о запуске
    logging.info("🚀 ASinglePoint Bot с визуальными улучшениями запущен...")
    print("=" * 50)
    print("✨ ASinglePoint Financial Bot")
    print("📈 Улучшенная версия с визуальными элементами")
    print("🎨 Включены все визуальные улучшения:")
    print("   • Цветные прогресс-бары")
    print("   • Красивые таблицы")
    print("   • Карточки целей")
    print("   • Панели бюджета")
    print("   • Расширенные графики")
    print("   • Стилизованные уведомления")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import random
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =============== Настройка логирования ===============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


# =============== «ПАМЯТЬ» МОК-ХРАНИЛИЩЕ ===============
# (вместо Redis; просто для демонстрации)
users = {}          # telegram_id -> внутренний ID (например, ФИО)
availability = {}   # telegram_id -> список кортежей (start_datetime, end_datetime)
last_schedule = {}  # telegram_id -> строка с последним расписанием


# =============== СТЕЙТЫ ДЛЯ ConversationHandler ===============
AWAITING_INTERNAL_ID = 0
AWAITING_UNAVAILABLE = 1


# =============== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===============
def parse_unavailable_period(text: str):
    """
    Ожидается формат: 'YYYY-MM-DD HH:MM – YYYY-MM-DD HH:MM'
    Возвращает (start_datetime, end_datetime) или None, если парсинг не удался.
    """
    try:
        parts = text.split('–')
        if len(parts) != 2:
            return None
        start_str = parts[0].strip()
        end_str = parts[1].strip()
        start_dt = datetime.strptime(start_str, '%Y-%m-%d %H:%M')
        end_dt = datetime.strptime(end_str, '%Y-%m-%d %H:%M')
        if end_dt <= start_dt:
            return None
        return start_dt, end_dt
    except Exception:
        return None


def format_schedule_for_week(telegram_id: int, week_start: datetime) -> str:
    """
    Эмуляция генерации недельного расписания:
    - берём даты от week_start (понедельник) до следующего воскресенья
    - проверяем, попадает ли doctor в период недоступности
    - если попадает, отмечаем 'Недоступен'
    - иначе — присваиваем случайную смену (День/Ночь/Выходной)
    """
    periods = availability.get(telegram_id, [])
    schedule_lines = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        busy = False
        for (s, e) in periods:
            if s.date() <= day.date() <= e.date():
                busy = True
                break

        day_name = day.strftime('%A %d.%m.%Y')
        if busy:
            schedule_lines.append(f"{day_name}: Недоступен")
        else:
            choice = random.choice(['День (09:00–17:00)', 'Ночь (21:00–07:00)', 'Выходной'])
            schedule_lines.append(f"{day_name}: {choice}")

    header = (
        f"Ваш план на неделю с {week_start.strftime('%d.%m.%Y')} "
        f"по {(week_start + timedelta(days=6)).strftime('%d.%m.%Y')}:\n\n"
    )
    return header + "\n".join(schedule_lines)


# =============== ХЭНДЛЕРЫ ===============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start: если пользователь не зарегистрирован, запрашиваем его 'внутренний ID'.
    Иначе выдаём приветствие и список команд.
    """
    user_id = update.effective_user.id
    if user_id not in users:
        text = (
            "Добро пожаловать в систему планирования смен клиники «Здоровый Ребёнок».\n\n"
            "Похоже, вы ещё не привязаны к системе.\n"
            "Пожалуйста, введите ваш внутренний ID (ФИО или условный номер врача),\n"
            "чтобы я мог(ла) сопоставить вас с данными из 1С.\n\n"
            "Например: «Иван Иванов» или «Врач-12»."
        )
        await update.message.reply_text(text)
        return AWAITING_INTERNAL_ID
    else:
        name = users[user_id]
        keyboard = [
            [KeyboardButton('/unavailable'), KeyboardButton('/reschedule')],
            [KeyboardButton('/my_schedule')],
        ]
        await update.message.reply_text(
            f"С возвращением, {name}! 🎉\n"
            "Введите /help, чтобы увидеть доступные команды.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return ConversationHandler.END


async def register_internal_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запоминаем «внутренний ID врача» (ФИО, номер), кладём в users[user_id].
    Инициализируем пустые списки в availability и last_schedule.
    """
    user_id = update.effective_user.id
    text = update.message.text.strip()
    # В реальной системе вы бы проверили в 1С, существует ли такой ID.
    users[user_id] = text
    availability[user_id] = []
    last_schedule[user_id] = None

    await update.message.reply_text(
        f"Отлично, {text}! Ваш аккаунт привязан.\n\n"
        "Доступные команды:\n"
        "/unavailable — указать периоды недоступности\n"
        "/reschedule — пересчитать расписание\n"
        "/my_schedule — посмотреть своё расписание"
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /help — просто выводим список команд.
    """
    await update.message.reply_text(
        "Доступные команды:\n"
        "/unavailable — указать периоды недоступности\n"
        "/reschedule — инициировать пересчёт расписания\n"
        "/my_schedule — посмотреть текущее расписание\n"
        "/cancel — отменить текущее действие"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /cancel — прерываем ConversationHandler и возвращаемся в главное меню.
    """
    await update.message.reply_text("Действие отменено. Вы в главном меню.")
    return ConversationHandler.END


async def unavailable_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начало диалога /unavailable: просим врача ввести период недоступности.
    """
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Сначала выполните /start и привяжите свой аккаунт.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Укажите период недоступности в формате:\n"
        "ГГГГ-ММ-ДД ЧЧ:ММ – ГГГГ-ММ-ДД ЧЧ:ММ\n"
        "Пример: 2025-04-03 08:00 – 2025-04-05 20:00\n\n"
        "Если захотите отменить, отправьте /cancel."
    )
    return AWAITING_UNAVAILABLE


async def unavailable_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получили строку от врача, парсим формат, сохраняем период в availability.
    """
    user_id = update.effective_user.id
    text = update.message.text.strip()
    period = parse_unavailable_period(text)
    if period is None:
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, попробуйте снова или отправьте /cancel для отмены."
        )
        return AWAITING_UNAVAILABLE

    # Сохраняем период
    availability[user_id].append(period)
    start_dt, end_dt = period
    await update.message.reply_text(
        f"✅ Ваш период недоступности сохранён:\n"
        f"{start_dt.strftime('%d.%m.%Y %H:%M')} – {end_dt.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Чтобы добавить ещё один период, просто отправьте его в том же формате.\n"
        "Или введите /cancel, чтобы вернуться в главное меню."
    )
    return ConversationHandler.END


async def reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reschedule — «запрашиваем пересчёт расписания» и выдаём готовый текст.
    В реальности здесь publish в Redis, ждём Scheduler, читаем из Redis.
    Здесь эмулируем генерацию «настоящего» расписания.
    """
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Сначала выполните /start и привяжите свой аккаунт.")
        return

    await update.message.reply_text("Запрашиваю пересчёт расписания… ⏳")

    # Имитируем «поиск ближайшего понедельника»
    now = datetime.now()
    # если сегодня понедельник, то week_start = сегодня; иначе следующий понедельник
    delta_days = (7 - now.weekday()) % 7
    week_start = (now + timedelta(days=delta_days)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Эмуляция расчёта – вместо реального OR-Tools
    text_sched = format_schedule_for_week(user_id, week_start)
    last_schedule[user_id] = text_sched

    await update.message.reply_text(text_sched)


async def my_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /my_schedule — просто отдаём сохранённый в last_schedule текст. 
    Если ещё нет, просим выполнить /reschedule.
    """
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Сначала выполните /start и привяжите свой аккаунт.")
        return

    sched = last_schedule.get(user_id)
    if not sched:
        await update.message.reply_text(
            "У вас пока нет сформированного расписания.\n"
            "Введите /reschedule, чтобы пересчитать."
        )
    else:
        await update.message.reply_text(sched)


def main():
    # Здесь подставьте ваш токен, который вы получили от @BotFather
    TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"

    # ================= Создаём Application =================
    application = Application.builder().token(TOKEN).build()

    # ================= ConversationHandler для /start =================
    conv_start = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AWAITING_INTERNAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_internal_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_start)

    # ================= ConversationHandler для /unavailable =================
    conv_unavail = ConversationHandler(
        entry_points=[CommandHandler("unavailable", unavailable_start)],
        states={
            AWAITING_UNAVAILABLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, unavailable_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_unavail)

    # ================= Обычные командные хэндлеры =================
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reschedule", reschedule))
    application.add_handler(CommandHandler("my_schedule", my_schedule))
    application.add_handler(CommandHandler("cancel", cancel))

    # =============================================================
    # Запускаем «долгий опрос» (Long Polling)
    application.run_polling()


if __name__ == "__main__":
    main()

import os
import logging
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.executor import start_webhook

# --- КОНФИГУРАЦИЯ (Берем из Environment Variables) ---
TOKEN = os.getenv('BOT_TOKEN')
# Render автоматически дает URL, если добавить переменную RENDER_EXTERNAL_HOSTNAME
APP_NAME = os.getenv('RENDER_EXTERNAL_HOSTNAME') 
PORT = int(os.getenv('PORT', 5000))

WEBHOOK_PATH = f'/webhook/{TOKEN}'
WEBHOOK_URL = f"https://{APP_NAME}{WEBHOOK_PATH}"

# --- ССЫЛКИ НА ИЗОБРАЖЕНИЯ (Загружены на хостинг для работы) ---
# Если будешь менять, просто вставь прямые ссылки на свои картинки
IMG_URLS = {
    "main": "https://i.ibb.co/LzNf0m6/main.jpg", # Заглушка, замени на свои прямые ссылки если нужно
    "link": "https://i.ibb.co/k0m9mYn/1000081143.jpg",
    "withdraw": "https://i.ibb.co/V9z0kXh/1000081144.jpg",
    "promo": "https://i.ibb.co/fDb7m4L/1000081145.jpg",
    "bonus": "https://i.ibb.co/vYm6sH1/1000081146.jpg",
    "profile": "https://i.ibb.co/W2f9V4p/1000081147.jpg",
    "top": "https://i.ibb.co/PZ9mY5V/1000081148.jpg"
}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
app = Flask(__name__)

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🌟 Заработать звёзд", callback_data="earn"),
        types.InlineKeyboardButton("📥 Вывести звёзды", callback_data="withdraw")
    )
    kb.add(
        types.InlineKeyboardButton("👤 Мой профиль", callback_data="profile"),
        types.InlineKeyboardButton("🎁 Бонус", callback_data="bonus")
    )
    kb.add(
        types.InlineKeyboardButton("🎁 Промокод", callback_data="promo"),
        types.InlineKeyboardButton("🏆 Топ рефеводов", callback_data="top")
    )
    return kb

def get_back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return kb

def get_withdraw_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("25 ⭐", callback_data="w_25"),
        types.InlineKeyboardButton("50 ⭐", callback_data="w_50"),
        types.InlineKeyboardButton("100 ⭐", callback_data="w_100"),
        types.InlineKeyboardButton("300 ⭐", callback_data="w_300")
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return kb

# --- ОБРАБОТЧИКИ ---

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=IMG_URLS["main"],
        caption="✅ Все проверки пройдены!\n\n✨ Добро пожаловать в Mumistars!",
        reply_markup=get_main_kb()
    )

@dp.callback_query_handler(lambda c: c.data == 'main_menu')
async def back_to_main(callback_query: types.CallbackQuery):
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["main"], caption="✨ Добро пожаловать"),
        reply_markup=get_main_kb()
    )

@dp.callback_query_handler(lambda c: c.data == 'profile')
async def profile_handler(callback_query: types.CallbackQuery):
    text = (
        f"👤 Имя: <b>{callback_query.from_user.full_name}</b> 👑\n"
        f"🆔 ID: <code>{callback_query.from_user.id}</code>\n"
        f"💰 Баланс: 4.50 ⭐\n"
        f"👥 Приглашено: 2"
    )
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["profile"], caption=text),
        reply_markup=get_back_kb()
    )

@dp.callback_query_handler(lambda c: c.data == 'earn')
async def earn_handler(callback_query: types.CallbackQuery):
    text = (
        "<b>ТВОЯ ССЫЛКА</b>\n\n"
        "За каждого друга ты получаешь +8.5⭐!\n\n"
        f"🔗 Твоя ссылка:\nhttps://t.me/Wolfstarsrobot?start={callback_query.from_user.id}\n\n"
        "🎉 Приглашай друзей и зарабатывай!"
    )
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["link"], caption=text),
        reply_markup=get_back_kb()
    )

@dp.callback_query_handler(lambda c: c.data == 'top')
async def top_handler(callback_query: types.CallbackQuery):
    text = (
        "<b>ТОП ПО ПРИГЛАШЕНИЯМ</b> 🏆\n\n"
        "🫂 Топ по рефералам за сегодня (МСК):\n\n"
        "1. ✨°•мария_чалкова•°✨ - 1 реф."
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏆 За все время", callback_data="top_all"))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["top"], caption=text),
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data == 'promo')
async def promo_handler(callback_query: types.CallbackQuery):
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["promo"], caption="<b>ВВЕДИ ПРОМОКОД</b> 🎁\n\n✏️ Введите промокод:"),
        reply_markup=get_back_kb()
    )

@dp.callback_query_handler(lambda c: c.data == 'bonus')
async def bonus_handler(callback_query: types.CallbackQuery):
    text = "<b>ВЫ ПОЛУЧИЛИ БОНУС</b> 🎁\n\n🎉 Вам начислено 0.5 ⭐ бонуса!"
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["bonus"], caption=text),
        reply_markup=get_back_kb()
    )

@dp.callback_query_handler(lambda c: c.data == 'withdraw')
async def withdraw_handler(callback_query: types.CallbackQuery):
    await bot.edit_message_media(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        media=types.InputMediaPhoto(IMG_URLS["withdraw"], caption="<b>ВЫВОД ЗВЕЗДОЧЕК</b> ⭐\n\nВыберите сумму вывода:"),
        reply_markup=get_withdraw_kb()
    )

# --- WEBHOOK LOGIC ---

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        Dispatcher.set_current(dp)
        Bot.set_current(bot)
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(dp.process_update(update))
        return ''
    else:
        return 'Forbidden', 403

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        host='0.0.0.0',
        port=PORT,
    )

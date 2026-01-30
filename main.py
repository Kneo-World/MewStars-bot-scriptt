import os
import logging
import asyncio
import sys
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_HOSTNAME') 
PORT = int(os.getenv('PORT', 10000))

WEBHOOK_PATH = f"/webhook/{TOKEN}"
BASE_URL = f"https://{RENDER_URL}"

# Ссылки на фото (вставь свои прямые ссылки)
IMG = {
    "main": "https://i.ibb.co/68v8zYp/1000081152.jpg",
    "earn": "https://i.ibb.co/zXyFfL6/1000081150.jpg",
    "withdraw": "https://i.ibb.co/fGPn0W1/1000081155.jpg",
    "profile": "https://i.ibb.co/L5rK5Q5/1000081151.jpg",
    "bonus": "https://i.ibb.co/gP5WqFz/1000081154.jpg",
    "promo": "https://i.ibb.co/f2P6g8d/1000081153.jpg",
    "top": "https://i.ibb.co/vXpS6y0/1000081149.jpg"
}

# ========== БАЗА ДАННЫХ (Для хранения баланса) ==========
class Database:
    def __init__(self, path="bot_stars.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute("""CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                stars REAL DEFAULT 0,
                refs INTEGER DEFAULT 0
            )""")

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            with self.conn:
                self.conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            return self.get_user(user_id)
        return user

    def add_stars(self, user_id, amount):
        with self.conn:
            self.conn.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amount, user_id))

db = Database()

# ========== ИНИЦИАЛИЗАЦИЯ ==========
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ========== КЛАВИАТУРЫ ==========
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌟 Заработать звёзд", callback_data="earn"),
         InlineKeyboardButton(text="📥 Вывести звёзды", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="bonus")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo"),
         InlineKeyboardButton(text="🏆 Топ рефеводов", callback_data="top")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]])

# ========== ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def start(message: types.Message):
    db.get_user(message.from_user.id)
    await message.answer_photo(
        photo=IMG["main"],
        caption="✅ Все проверки пройдены!\n\n✨ Добро пожаловать в <b>MumiStars</b>!",
        parse_mode="HTML",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data == "main_menu")
async def menu(call: types.CallbackQuery):
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["main"], caption="✨ Добро пожаловать в <b>MumiStars</b>!", parse_mode="HTML"),
        reply_markup=main_kb()
    )

@dp.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    u = db.get_user(call.from_user.id)
    text = (f"👤 Имя: <b>{call.from_user.full_name}</b>\n"
            f"🆔 ID: <code>{call.from_user.id}</code>\n"
            f"💰 Баланс: <b>{u['stars']:.2f} ⭐</b>\n"
            f"👥 Приглашено: {u['refs']}")
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["profile"], caption=text, parse_mode="HTML"),
        reply_markup=back_kb()
    )

@dp.callback_query(F.data == "earn")
async def earn(call: types.CallbackQuery):
    text = (f"<b>ТВОЯ ССЫЛКА</b>\n\nЗа каждого друга ты получаешь +8.5⭐!\n\n"
            f"🔗 Твоя ссылка:\n<code>https://t.me/{(await bot.get_me()).username}?start={call.from_user.id}</code>")
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["earn"], caption=text, parse_mode="HTML"),
        reply_markup=back_kb()
    )

@dp.callback_query(F.data == "bonus")
async def bonus(call: types.CallbackQuery):
    db.add_stars(call.from_user.id, 0.5)
    await call.answer("🎁 +0.5 звезд!", show_alert=True)
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["bonus"], caption="<b>БОНУС ЗАБРАН</b>\n\n🎉 Вам начислено 0.5 ⭐!", parse_mode="HTML"),
        reply_markup=back_kb()
    )

@dp.callback_query(F.data == "withdraw")
async def withdraw(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="25 ⭐", callback_data="w"), InlineKeyboardButton(text="50 ⭐", callback_data="w")],
        [InlineKeyboardButton(text="100 ⭐", callback_data="w"), InlineKeyboardButton(text="300 ⭐", callback_data="w")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ])
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["withdraw"], caption="<b>ВЫВОД ЗВЕЗДОЧЕК</b>\n\nВыберите сумму:", parse_mode="HTML"),
        reply_markup=kb
    )

@dp.callback_query(F.data == "top")
async def top(call: types.CallbackQuery):
    text = "<b>ТОП ПО ПРИГЛАШЕНИЯМ</b> 🏆\n\n1. ✨°•мария_чалкова•°✨ — 1 реф."
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["top"], caption=text, parse_mode="HTML"),
        reply_markup=back_kb()
    )

@dp.callback_query(F.data == "promo")
async def promo(call: types.CallbackQuery):
    await call.message.edit_media(
        media=InputMediaPhoto(media=IMG["promo"], caption="<b>ПРОМОКОД</b>\n\n✏️ Введите промокод в чат:", parse_mode="HTML"),
        reply_markup=back_kb()
    )

# ========== ЗАПУСК СЕРВЕРА ==========
async def on_startup(bot: Bot):
    await bot.set_webhook(f"{BASE_URL}{WEBHOOK_PATH}", drop_pending_updates=True)

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()


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

# ========== CONFIG ==========
TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_HOSTNAME') 
PORT = int(os.getenv('PORT', 10000))

WEBHOOK_PATH = f"/webhook/{TOKEN}"
BASE_URL = f"https://{RENDER_URL}"

# Прямые ссылки на твои изображения
IMG = {
    "main": "https://i.ibb.co/68v8zYp/1000081152.jpg",
    "earn": "https://i.ibb.co/zXyFfL6/1000081150.jpg",
    "withdraw": "https://i.ibb.co/fGPn0W1/1000081155.jpg",
    "profile": "https://i.ibb.co/L5rK5Q5/1000081151.jpg",
    "bonus": "https://i.ibb.co/gP5WqFz/1000081154.jpg",
    "promo": "https://i.ibb.co/f2P6g8d/1000081153.jpg",
    "top": "https://i.ibb.co/vXpS6y0/1000081149.jpg"
}

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ========== DATABASE ==========
class Database:
    def __init__(self, path="bot_stars.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, stars REAL DEFAULT 0, refs INTEGER DEFAULT 0)")

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

# ========== KEYBOARDS ==========
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

# ========== HELPERS ==========
async def send_or_edit(call: types.CallbackQuery, photo_key, caption, kb):
    """Безопасная функция для смены контента"""
    try:
        media = InputMediaPhoto(media=IMG[photo_key], caption=caption, parse_mode="HTML")
        await call.message.edit_media(media=media, reply_markup=kb)
    except Exception as e:
        logging.error(f"Edit error: {e}")
        await call.message.delete()
        await call.message.answer_photo(photo=IMG[photo_key], caption=caption, parse_mode="HTML", reply_markup=kb)

# ========== HANDLERS ==========
@dp.message(Command("start"))
async def start(message: types.Message):
    db.get_user(message.from_user.id)
    await message.answer_photo(photo=IMG["main"], caption="✅ Все проверки пройдены!\n\n✨ Добро пожаловать в <b>MumiStars</b>!", parse_mode="HTML", reply_markup=main_kb())

@dp.callback_query(F.data == "main_menu")
async def menu(call: types.CallbackQuery):
    await send_or_edit(call, "main", "✨ Добро пожаловать в <b>MumiStars</b>!", main_kb())

@dp.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    u = db.get_user(call.from_user.id)
    text = f"👤 Имя: <b>{call.from_user.full_name}</b>\n🆔 ID: <code>{call.from_user.id}</code>\n💰 Баланс: <b>{u['stars']:.2f} ⭐</b>\n👥 Приглашено: {u['refs']}"
    await send_or_edit(call, "profile", text, back_kb())

@dp.callback_query(F.data == "earn")
async def earn(call: types.CallbackQuery):
    me = await bot.get_me()
    text = f"<b>ТВОЯ ССЫЛКА</b>\n\nЗа каждого друга ты получаешь +8.5⭐!\n\n🔗 Ссылка:\n<code>https://t.me/{me.username}?start={call.from_user.id}</code>"
    await send_or_edit(call, "earn", text, back_kb())

@dp.callback_query(F.data == "bonus")
async def bonus(call: types.CallbackQuery):
    db.add_stars(call.from_user.id, 0.5)
    await call.answer("🎁 +0.5 звезд!", show_alert=False)
    await send_or_edit(call, "bonus", "<b>БОНУС ЗАБРАН</b>\n\n🎉 Вам начислено 0.5 ⭐!", back_kb())

@dp.callback_query(F.data == "withdraw")
async def withdraw(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="25 ⭐", callback_data="w"), InlineKeyboardButton(text="50 ⭐", callback_data="w")],
        [InlineKeyboardButton(text="100 ⭐", callback_data="w"), InlineKeyboardButton(text="300 ⭐", callback_data="w")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ])
    await send_or_edit(call, "withdraw", "<b>ВЫВОД ЗВЕЗДОЧЕК</b>\n\nВыберите сумму:", kb)

@dp.callback_query(F.data == "top")
async def top(call: types.CallbackQuery):
    await send_or_edit(call, "top", "<b>ТОП ПО ПРИГЛАШЕНИЯМ</b> 🏆\n\n1. ✨°•мария_чалкова•°✨ — 1 реф.", back_kb())

@dp.callback_query(F.data == "promo")
async def promo(call: types.CallbackQuery):
    await send_or_edit(call, "promo", "<b>ПРОМОКОД</b>\n\n✏️ Введите промокод в чат:", back_kb())

# ========== WEBHOOK RUNNER ==========
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


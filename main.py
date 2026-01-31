#!/usr/bin/env python3
"""
Telegram бот для управления виртуальной валютой "Звезды"
С админ-панелью и системой чеков
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, 
    KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove, InputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, 
    BigInteger, DateTime, Boolean, ForeignKey, func, and_
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()] or [123456789]  # Ваш ID

# Настройки
REFERRAL_REWARD = 8.5
DAILY_BONUS = 0.5
WITHDRAWAL_OPTIONS = [25, 50, 100, 300]

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255))
    balance = Column(Float, default=0.0)
    referrer_id = Column(BigInteger, nullable=True)
    reg_date = Column(DateTime, default=datetime.now)
    last_bonus_date = Column(DateTime, nullable=True)
    is_banned = Column(Boolean, default=False)
    
    # Отношения
    sent_transactions = relationship('Transaction', foreign_keys='Transaction.sender_id', back_populates='sender')
    received_transactions = relationship('Transaction', foreign_keys='Transaction.receiver_id', back_populates='receiver')

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(BigInteger, ForeignKey('users.user_id'))
    receiver_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String(50), nullable=False)  # referral, bonus, admin_add, admin_remove, withdraw
    timestamp = Column(DateTime, default=datetime.now)
    description = Column(String(500), nullable=True)
    
    # Отношения
    sender = relationship('User', foreign_keys=[sender_id], back_populates='sent_transactions')
    receiver = relationship('User', foreign_keys=[receiver_id], back_populates='received_transactions')

class Promocode(Base):
    __tablename__ = 'promocodes'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    reward_amount = Column(Float, nullable=False)
    uses_left = Column(Integer, default=1)
    active_status = Column(Boolean, default=True)

# Инициализация БД
engine = create_engine('sqlite:///bot.db', echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

Base.metadata.create_all(bind=engine)

# ========== СОСТОЯНИЯ FSM ==========
class UserStates(StatesGroup):
    enter_promocode = State()
    withdraw_amount = State()

class AdminStates(StatesGroup):
    search_user = State()
    add_stars = State()
    remove_stars = State()
    broadcast_message = State()
    broadcast_photo = State()
    create_promocode = State()
    ban_user = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    """Главное меню пользователя"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎯 Заработать звёзды"), KeyboardButton(text="💳 Вывести звёзды")],
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="🎁 Бонус")],
            [KeyboardButton(text="🎟️ Промокод"), KeyboardButton(text="🏆 Топ рефереров")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def get_earn_keyboard():
    """Клавиатура для заработка"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Пригласить друга", callback_data="earn_referral")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_withdraw_keyboard():
    """Клавиатура для вывода"""
    builder = InlineKeyboardBuilder()
    for amount in WITHDRAWAL_OPTIONS:
        builder.button(text=f"{amount} звёзд", callback_data=f"withdraw_{amount}")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_keyboard():
    """Главное меню админа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Поиск пользователя", callback_data="admin_search")
    builder.button(text="💰 Управление балансом", callback_data="admin_balance")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
    builder.button(text="🚫 Бан пользователя", callback_data="admin_ban")
    builder.button(text="🎟️ Создать промокод", callback_data="admin_create_promo")
    builder.button(text="📋 Архив чеков", callback_data="admin_transactions")
    builder.adjust(2)
    return builder.as_markup()

def get_balance_keyboard():
    """Клавиатура управления балансом"""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Выдать звёзды", callback_data="admin_add")
    builder.button(text="➖ Забрать звёзды", callback_data="admin_remove")
    builder.button(text="💣 Обнулить баланс", callback_data="admin_reset")
    builder.button(text="⬅️ Назад", callback_data="back_to_admin")
    builder.adjust(2)
    return builder.as_markup()

def get_back_admin_keyboard():
    """Кнопка назад в админке"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад в админку", callback_data="back_to_admin")
    return builder.as_markup()

# ========== ХЕЛПЕРЫ БАЗЫ ДАННЫХ ==========
class Database:
    """Класс для работы с базой данных"""
    
    @staticmethod
    def get_user(user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        with SessionLocal() as session:
            return session.query(User).filter(User.user_id == user_id).first()
    
    @staticmethod
    def create_user(user_id: int, username: str = None, referrer_id: int = None) -> User:
        """Создать нового пользователя"""
        with SessionLocal() as session:
            user = User(user_id=user_id, username=username, referrer_id=referrer_id)
            session.add(user)
            session.commit()
            return user
    
    @staticmethod
    def update_balance(user_id: int, amount: float) -> Optional[User]:
        """Обновить баланс пользователя"""
        with SessionLocal() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.balance += amount
                session.commit()
            return user
    
    @staticmethod
    def create_transaction(sender_id: Optional[int], receiver_id: int, amount: float, 
                          trans_type: str, description: str = None) -> Transaction:
        """Создать запись о транзакции"""
        with SessionLocal() as session:
            transaction = Transaction(
                sender_id=sender_id,
                receiver_id=receiver_id,
                amount=amount,
                type=trans_type,
                description=description,
                timestamp=datetime.now()
            )
            session.add(transaction)
            session.commit()
            return transaction
    
    @staticmethod
    def get_referrals_count(user_id: int) -> int:
        """Получить количество рефералов пользователя"""
        with SessionLocal() as session:
            return session.query(User).filter(User.referrer_id == user_id).count()
    
    @staticmethod
    def get_top_referrers(limit: int = 10) -> List[User]:
        """Получить топ рефереров"""
        with SessionLocal() as session:
            # Подзапрос для подсчета рефералов
            from sqlalchemy import func
            return session.query(
                User,
                func.count(User.id).label('ref_count')
            ).join(User, User.referrer_id == User.user_id).group_by(User.referrer_id).order_by(func.count(User.id).desc()).limit(limit).all()
    
    @staticmethod
    def get_promocode(code: str) -> Optional[Promocode]:
        """Получить промокод по коду"""
        with SessionLocal() as session:
            return session.query(Promocode).filter(
                Promocode.code == code,
                Promocode.active_status == True,
                Promocode.uses_left > 0
            ).first()
    
    @staticmethod
    def use_promocode(code: str) -> bool:
        """Использовать промокод"""
        with SessionLocal() as session:
            promo = session.query(Promocode).filter(Promocode.code == code).first()
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
                if promo.uses_left <= 0:
                    promo.active_status = False
                session.commit()
                return True
            return False
    
    @staticmethod
    def create_promocode(code: str, reward_amount: float, uses: int = 1) -> Promocode:
        """Создать промокод"""
        with SessionLocal() as session:
            promo = Promocode(code=code, reward_amount=reward_amount, uses_left=uses)
            session.add(promo)
            session.commit()
            return promo
    
    @staticmethod
    def get_all_users() -> List[User]:
        """Получить всех пользователей"""
        with SessionLocal() as session:
            return session.query(User).filter(User.is_banned == False).all()
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """Получить статистику"""
        with SessionLocal() as session:
            total_users = session.query(User).count()
            total_balance = session.query(func.sum(User.balance)).scalar() or 0
            
            yesterday = datetime.now() - timedelta(days=1)
            transactions_24h = session.query(Transaction).filter(
                Transaction.timestamp >= yesterday
            ).count()
            
            return {
                'total_users': total_users,
                'total_balance': total_balance,
                'transactions_24h': transactions_24h
            }
    
    @staticmethod
    def get_user_transactions(user_id: int, limit: int = 20) -> List[Transaction]:
        """Получить транзакции пользователя"""
        with SessionLocal() as session:
            return session.query(Transaction).filter(
                Transaction.receiver_id == user_id
            ).order_by(Transaction.timestamp.desc()).limit(limit).all()
    
    @staticmethod
    def ban_user(user_id: int) -> bool:
        """Забанить пользователя"""
        with SessionLocal() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.is_banned = True
                session.commit()
                return True
            return False
    
    @staticmethod
    def unban_user(user_id: int) -> bool:
        """Разбанить пользователя"""
        with SessionLocal() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.is_banned = False
                session.commit()
                return True
            return False

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ========== МИДЛВАРЬ ==========
@dp.message.middleware
async def check_user_middleware(handler, event: Message, data: Dict[str, Any]):
    """Проверка пользователя в БД при каждом сообщении"""
    user = Database.get_user(event.from_user.id)
    
    if not user:
        # Создаем нового пользователя
        referrer_id = None
        if event.text and event.text.startswith('/start'):
            parts = event.text.split()
            if len(parts) > 1:
                try:
                    referrer_id = int(parts[1])
                except ValueError:
                    pass
        
        user = Database.create_user(
            user_id=event.from_user.id,
            username=event.from_user.username,
            referrer_id=referrer_id
        )
        
        # Если есть реферер, начисляем награду
        if referrer_id and referrer_id != event.from_user.id:
            referrer = Database.get_user(referrer_id)
            if referrer:
                Database.update_balance(referrer_id, REFERRAL_REWARD)
                Database.create_transaction(
                    sender_id=event.from_user.id,
                    receiver_id=referrer_id,
                    amount=REFERRAL_REWARD,
                    trans_type='referral',
                    description=f'Реферальная награда за пользователя {event.from_user.id}'
                )
    
    # Проверка бана
    if user and user.is_banned:
        await event.answer("❌ Вы заблокированы в этом боте!")
        return
    
    data['user'] = user
    return await handler(event, data)

@dp.callback_query.middleware
async def check_user_callback_middleware(handler, event: CallbackQuery, data: Dict[str, Any]):
    """Проверка пользователя для callback-запросов"""
    user = Database.get_user(event.from_user.id)
    
    if user and user.is_banned:
        await event.answer("❌ Вы заблокированы в этом боте!", show_alert=True)
        return
    
    data['user'] = user
    return await handler(event, data)

# ========== ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ==========
@router.message(CommandStart())
async def cmd_start(message: Message, user: User):
    """Обработка команды /start"""
    welcome_text = (
        "🌟 Добро пожаловать в бот с виртуальной валютой 'Звезды'!\n\n"
        "💰 Здесь вы можете зарабатывать, накапливать и выводить звёзды.\n"
        "👥 Приглашайте друзей и получайте бонусы!\n\n"
        "👇 Используйте кнопки ниже для навигации:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "👤 Мой профиль")
async def profile(message: Message, user: User):
    """Показ профиля пользователя"""
    referrals_count = Database.get_referrals_count(user.user_id)
    
    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{user.user_id}</code>\n"
        f"👤 Имя: @{user.username or 'Не указано'}\n"
        f"💰 Баланс: <b>{user.balance} звёзд</b>\n"
        f"👥 Приглашено друзей: <b>{referrals_count}</b>\n"
        f"📅 Регистрация: {user.reg_date.strftime('%d.%m.%Y')}"
    )
    
    await message.answer(profile_text, parse_mode='HTML')

@router.message(F.text == "🎯 Заработать звёзды")
async def earn_menu(message: Message):
    """Меню заработка"""
    earn_text = (
        "🎯 <b>Способы заработка звёзд</b>\n\n"
        "📢 <b>Пригласите друга</b> - получите 8.5 звёзд за каждого\n"
        "🎁 <b>Ежедневный бонус</b> - 0.5 звёзд каждый день\n"
        "🎟️ <b>Промокоды</b> - вводите промокоды и получайте звёзды"
    )
    
    await message.answer(earn_text, parse_mode='HTML', reply_markup=get_earn_keyboard())

@router.callback_query(F.data == "earn_referral")
async def referral_info(callback: CallbackQuery, user: User):
    """Информация о реферальной системе"""
    ref_link = f"https://t.me/{callback.from_user.username or 'your_bot'}?start={user.user_id}"
    
    ref_text = (
        "📢 <b>Реферальная система</b>\n\n"
        f"🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
        f"💰 За каждого приглашенного друга вы получаете <b>{REFERRAL_REWARD} звёзд</b>\n"
        "📊 Статистику приглашений можно посмотреть в профиле"
    )
    
    await callback.message.edit_text(ref_text, parse_mode='HTML', reply_markup=get_earn_keyboard())
    await callback.answer()

@router.message(F.text == "🎁 Бонус")
async def daily_bonus(message: Message, user: User):
    """Ежедневный бонус"""
    now = datetime.now()
    
    if user.last_bonus_date and (now - user.last_bonus_date).days < 1:
        next_bonus = user.last_bonus_date + timedelta(days=1)
        time_left = next_bonus - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        await message.answer(
            f"⏳ Вы уже получали бонус сегодня.\n"
            f"Следующий бонус через {hours}ч {minutes}м\n"
            f"Вернитесь после {next_bonus.strftime('%H:%M')}"
        )
        return
    
    # Начисляем бонус
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.user_id == user.user_id).first()
        db_user.balance += DAILY_BONUS
        db_user.last_bonus_date = now
        session.commit()
    
    # Создаем транзакцию
    transaction = Database.create_transaction(
        sender_id=None,
        receiver_id=user.user_id,
        amount=DAILY_BONUS,
        trans_type='bonus',
        description='Ежедневный бонус'
    )
    
    # Получаем обновленный баланс
    updated_user = Database.get_user(user.user_id)
    
    await message.answer(
        f"🎁 <b>Ежедневный бонус получен!</b>\n\n"
        f"💰 Начислено: +{DAILY_BONUS} звёзд\n"
        f"💳 Текущий баланс: {updated_user.balance} звёзд\n\n"
        f"📝 Чек #{transaction.id}\n"
        f"Тип: Бонус\n"
        f"Изменение: +{DAILY_BONUS} звёзд\n"
        f"Баланс: {updated_user.balance} звёзд",
        parse_mode='HTML'
    )

@router.message(F.text == "🎟️ Промокод")
async def promocode_menu(message: Message, state: FSMContext):
    """Меню ввода промокода"""
    await message.answer(
        "🎟️ Введите промокод:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(UserStates.enter_promocode)

@router.message(UserStates.enter_promocode)
async def process_promocode(message: Message, state: FSMContext, user: User):
    """Обработка введенного промокода"""
    promo_code = message.text.strip().upper()
    promocode = Database.get_promocode(promo_code)
    
    if not promocode:
        await message.answer("❌ Промокод не найден или неактивен!", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    # Используем промокод
    if not Database.use_promocode(promo_code):
        await message.answer("❌ Промокод уже использован!", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    # Начисляем награду
    Database.update_balance(user.user_id, promocode.reward_amount)
    
    # Создаем транзакцию
    transaction = Database.create_transaction(
        sender_id=None,
        receiver_id=user.user_id,
        amount=promocode.reward_amount,
        trans_type='promo',
        description=f'Промокод: {promo_code}'
    )
    
    # Получаем обновленный баланс
    updated_user = Database.get_user(user.user_id)
    
    await message.answer(
        f"✅ <b>Промокод активирован!</b>\n\n"
        f"🎟️ Код: {promo_code}\n"
        f"💰 Начислено: +{promocode.reward_amount} звёзд\n"
        f"💳 Текущий баланс: {updated_user.balance} звёзд\n\n"
        f"📝 Чек #{transaction.id}\n"
        f"Тип: Промокод\n"
        f"Изменение: +{promocode.reward_amount} звёзд\n"
        f"Баланс: {updated_user.balance} звёзд",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )
    await state.clear()

@router.message(F.text == "💳 Вывести звёзды")
async def withdraw_menu(message: Message, user: User):
    """Меню вывода"""
    if user.balance < min(WITHDRAWAL_OPTIONS):
        await message.answer(
            f"❌ Минимальная сумма для вывода: {min(WITHDRAWAL_OPTIONS)} звёзд\n"
            f"💰 Ваш баланс: {user.balance} звёзд"
        )
        return
    
    withdraw_text = (
        f"💳 <b>Вывод звёзд</b>\n\n"
        f"💰 Ваш баланс: <b>{user.balance} звёзд</b>\n"
        f"👇 Выберите сумму для вывода:"
    )
    
    await message.answer(withdraw_text, parse_mode='HTML', reply_markup=get_withdraw_keyboard())

@router.callback_query(F.data.startswith("withdraw_"))
async def process_withdraw(callback: CallbackQuery, user: User):
    """Обработка вывода"""
    amount = float(callback.data.split("_")[1])
    
    if user.balance < amount:
        await callback.answer(f"❌ Недостаточно звёзд! Баланс: {user.balance}", show_alert=True)
        return
    
    # Списываем сумму
    Database.update_balance(user.user_id, -amount)
    
    # Создаем транзакцию
    transaction = Database.create_transaction(
        sender_id=user.user_id,
        receiver_id=None,
        amount=amount,
        trans_type='withdraw',
        description=f'Запрос на вывод {amount} звёзд'
    )
    
    # Получаем обновленный баланс
    updated_user = Database.get_user(user.user_id)
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"⚠️ <b>Запрос на вывод</b>\n\n"
                f"👤 Пользователь: @{user.username or 'Нет username'}\n"
                f"🆔 ID: {user.user_id}\n"
                f"💰 Сумма: {amount} звёзд\n"
                f"💳 Баланс после: {updated_user.balance} звёзд\n"
                f"📝 Чек: #{transaction.id}",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")
    
    await callback.message.edit_text(
        f"✅ <b>Заявка на вывод создана!</b>\n\n"
        f"💰 Сумма: {amount} звёзд\n"
        f"💳 Текущий баланс: {updated_user.balance} звёзд\n\n"
        f"📝 Чек #{transaction.id}\n"
        f"Тип: Вывод\n"
        f"Изменение: -{amount} звёзд\n"
        f"Баланс: {updated_user.balance} звёзд\n\n"
        f"📞 Администратор свяжется с вами в ближайшее время для уточнения деталей вывода.",
        parse_mode='HTML'
    )
    await callback.answer()

@router.message(F.text == "🏆 Топ рефереров")
async def top_referrers(message: Message):
    """Топ рефереров"""
    try:
        # Получаем топ рефереров
        with SessionLocal() as session:
            from sqlalchemy import func
            
            # Подзапрос для подсчета рефералов
            subquery = session.query(
                User.referrer_id,
                func.count(User.id).label('ref_count')
            ).filter(User.referrer_id.isnot(None)).group_by(User.referrer_id).subquery()
            
            # Основной запрос
            top_users = session.query(
                User,
                subquery.c.ref_count
            ).join(subquery, User.user_id == subquery.c.referrer_id).order_by(subquery.c.ref_count.desc()).limit(10).all()
        
        if not top_users:
            await message.answer("📊 Топ рефереров пока пуст. Станьте первым!")
            return
        
        top_text = "🏆 <b>Топ 10 рефереров</b>\n\n"
        
        for i, (user, ref_count) in enumerate(top_users, 1):
            username = user.username or f"ID: {user.user_id}"
            top_text += f"{i}. {username} — {ref_count} реф.\n"
        
        await message.answer(top_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка получения топа: {e}")
        await message.answer("❌ Ошибка при получении топа рефереров")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Вернуться в главное меню"""
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

# ========== АДМИН ХЕНДЛЕРЫ ==========
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMIN_IDS

@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен!")
        return
    
    admin_text = (
        "⚙️ <b>Админ-панель</b>\n\n"
        "👇 Выберите действие:"
    )
    
    await message.answer(admin_text, parse_mode='HTML', reply_markup=get_admin_keyboard())

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin_panel(callback: CallbackQuery):
    """Вернуться в админ-панель"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    admin_text = (
        "⚙️ <b>Админ-панель</b>\n\n"
        "👇 Выберите действие:"
    )
    
    await callback.message.edit_text(admin_text, parse_mode='HTML', reply_markup=get_admin_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin_search")
async def admin_search_user(callback: CallbackQuery, state: FSMContext):
    """Поиск пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите user_id или username пользователя:",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.set_state(AdminStates.search_user)
    await callback.answer()

@router.message(AdminStates.search_user)
async def process_search_user(message: Message, state: FSMContext):
    """Обработка поиска пользователя"""
    if not is_admin(message.from_user.id):
        return
    
    search_query = message.text.strip()
    
    with SessionLocal() as session:
        try:
            # Пробуем найти по user_id
            user_id = int(search_query)
            user = session.query(User).filter(User.user_id == user_id).first()
        except ValueError:
            # Ищем по username
            user = session.query(User).filter(User.username.ilike(f"%{search_query}%")).first()
        
        if not user:
            await message.answer("❌ Пользователь не найден!", reply_markup=get_back_admin_keyboard())
            await state.clear()
            return
        
        referrals_count = session.query(User).filter(User.referrer_id == user.user_id).count()
        
        user_info = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 ID: <code>{user.user_id}</code>\n"
            f"👤 Username: @{user.username or 'Не указан'}\n"
            f"💰 Баланс: <b>{user.balance} звёзд</b>\n"
            f"👥 Рефералов: {referrals_count}\n"
            f"📅 Регистрация: {user.reg_date.strftime('%d.%m.%Y %H:%M')}\n"
            f"🚫 Статус: {'Забанен' if user.is_banned else 'Активен'}"
        )
        
        # Кнопки для управления пользователем
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Управление балансом", callback_data=f"user_balance_{user.user_id}")
        builder.button(text="📋 История транзакций", callback_data=f"user_transactions_{user.user_id}")
        if user.is_banned:
            builder.button(text="✅ Разбанить", callback_data=f"user_unban_{user.user_id}")
        else:
            builder.button(text="🚫 Забанить", callback_data=f"user_ban_{user.user_id}")
        builder.button(text="⬅️ Назад в админку", callback_data="back_to_admin")
        builder.adjust(1)
        
        await message.answer(user_info, parse_mode='HTML', reply_markup=builder.as_markup())
        await state.clear()

@router.callback_query(F.data == "admin_balance")
async def admin_balance_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления балансом"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💰 <b>Управление балансом</b>\n\n"
        "Сначала найдите пользователя через поиск, затем выберите действие.",
        parse_mode='HTML',
        reply_markup=get_balance_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("user_balance_"))
async def manage_user_balance(callback: CallbackQuery, state: FSMContext):
    """Управление балансом конкретного пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    user = Database.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    await state.update_data(admin_selected_user=user_id)
    
    await callback.message.edit_text(
        f"💰 <b>Управление балансом пользователя</b>\n\n"
        f"👤 @{user.username or 'Без username'}\n"
        f"🆔 ID: {user.user_id}\n"
        f"💳 Текущий баланс: {user.balance} звёзд\n\n"
        f"👇 Выберите действие:",
        parse_mode='HTML',
        reply_markup=get_balance_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_add")
async def admin_add_stars(callback: CallbackQuery, state: FSMContext):
    """Добавление звезд"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    data = await state.get_data()
    user_id = data.get('admin_selected_user')
    
    if not user_id:
        await callback.answer("❌ Сначала выберите пользователя!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ <b>Выдать звёзды</b>\n\n"
        "Введите сумму для начисления:",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.set_state(AdminStates.add_stars)
    await callback.answer()

@router.message(AdminStates.add_stars)
async def process_add_stars(message: Message, state: FSMContext):
    """Обработка добавления звезд"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную положительную сумму!", reply_markup=get_back_admin_keyboard())
        return
    
    data = await state.get_data()
    user_id = data.get('admin_selected_user')
    user = Database.get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден!", reply_markup=get_back_admin_keyboard())
        await state.clear()
        return
    
    # Начисляем сумму
    Database.update_balance(user_id, amount)
    
    # Создаем транзакцию
    transaction = Database.create_transaction(
        sender_id=message.from_user.id,
        receiver_id=user_id,
        amount=amount,
        trans_type='admin_add',
        description=f'Админ {message.from_user.id} выдал звёзды'
    )
    
    # Получаем обновленный баланс
    updated_user = Database.get_user(user_id)
    
    # Отправляем уведомление пользователю
    try:
        await bot.send_message(
            user_id,
            f"💰 <b>Вам начислены звёзды!</b>\n\n"
            f"📝 Чек #{transaction.id}\n"
            f"Тип: Начисление администратором\n"
            f"Изменение: +{amount} звёзд\n"
            f"Текущий баланс: {updated_user.balance} звёзд",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю: {e}")
    
    await message.answer(
        f"✅ <b>Звёзды успешно начислены!</b>\n\n"
        f"👤 Пользователь: @{user.username or 'Нет username'}\n"
        f"🆔 ID: {user.user_id}\n"
        f"💰 Сумма: +{amount} звёзд\n"
        f"💳 Новый баланс: {updated_user.balance} звёзд\n"
        f"📝 Чек: #{transaction.id}",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.clear()

@router.callback_query(F.data == "admin_remove")
async def admin_remove_stars(callback: CallbackQuery, state: FSMContext):
    """Удаление звезд"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    data = await state.get_data()
    user_id = data.get('admin_selected_user')
    
    if not user_id:
        await callback.answer("❌ Сначала выберите пользователя!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➖ <b>Забрать звёзды</b>\n\n"
        "Введите сумму для списания:",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.set_state(AdminStates.remove_stars)
    await callback.answer()

@router.message(AdminStates.remove_stars)
async def process_remove_stars(message: Message, state: FSMContext):
    """Обработка удаления звезд"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную положительную сумму!", reply_markup=get_back_admin_keyboard())
        return
    
    data = await state.get_data()
    user_id = data.get('admin_selected_user')
    user = Database.get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден!", reply_markup=get_back_admin_keyboard())
        await state.clear()
        return
    
    if user.balance < amount:
        await message.answer(
            f"❌ Недостаточно звёзд у пользователя!\n"
            f"Текущий баланс: {user.balance} звёзд",
            reply_markup=get_back_admin_keyboard()
        )
        return
    
    # Списываем сумму
    Database.update_balance(user_id, -amount)
    
    # Создаем транзакцию
    transaction = Database.create_transaction(
        sender_id=message.from_user.id,
        receiver_id=user_id,
        amount=amount,
        trans_type='admin_remove',
        description=f'Админ {message.from_user.id} забрал звёзды'
    )
    
    # Получаем обновленный баланс
    updated_user = Database.get_user(user_id)
    
    # Отправляем уведомление пользователю
    try:
        await bot.send_message(
            user_id,
            f"⚠️ <b>У вас списаны звёзды!</b>\n\n"
            f"📝 Чек #{transaction.id}\n"
            f"Тип: Списание администратором\n"
            f"Изменение: -{amount} звёзд\n"
            f"Текущий баланс: {updated_user.balance} звёзд",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю: {e}")
    
    await message.answer(
        f"✅ <b>Звёзды успешно списаны!</b>\n\n"
        f"👤 Пользователь: @{user.username or 'Нет username'}\n"
        f"🆔 ID: {user.user_id}\n"
        f"💰 Сумма: -{amount} звёзд\n"
        f"💳 Новый баланс: {updated_user.balance} звёзд\n"
        f"📝 Чек: #{transaction.id}",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.clear()

@router.callback_query(F.data == "admin_reset")
async def admin_reset_balance(callback: CallbackQuery, state: FSMContext):
    """Обнуление баланса"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    data = await state.get_data()
    user_id = data.get('admin_selected_user')
    user = Database.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    if user.balance == 0:
        await callback.answer("✅ Баланс уже нулевой!", show_alert=True)
        return
    
    old_balance = user.balance
    
    # Обнуляем баланс
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.user_id == user_id).first()
        db_user.balance = 0
        session.commit()
    
    # Создаем транзакцию
    transaction = Database.create_transaction(
        sender_id=callback.from_user.id,
        receiver_id=user_id,
        amount=old_balance,
        trans_type='admin_reset',
        description=f'Админ {callback.from_user.id} обнулил баланс'
    )
    
    # Отправляем уведомление пользователю
    try:
        await bot.send_message(
            user_id,
            f"⚠️ <b>Ваш баланс обнулен!</b>\n\n"
            f"📝 Чек #{transaction.id}\n"
            f"Тип: Обнуление баланса администратором\n"
            f"Изменение: -{old_balance} звёзд\n"
            f"Текущий баланс: 0 звёзд",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю: {e}")
    
    await callback.message.edit_text(
        f"💣 <b>Баланс обнулен!</b>\n\n"
        f"👤 Пользователь: @{user.username or 'Нет username'}\n"
        f"🆔 ID: {user.user_id}\n"
        f"💰 Списано: {old_balance} звёзд\n"
        f"💳 Новый баланс: 0 звёзд\n"
        f"📝 Чек: #{transaction.id}",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Статистика"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    stats = Database.get_stats()
    
    stats_text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"💰 Общая сумма звёзд: {stats['total_balance']:.2f}\n"
        f"📈 Транзакций за 24ч: {stats['transactions_24h']}\n\n"
        f"🎯 Реферальная награда: {REFERRAL_REWARD} звёзд\n"
        f"🎁 Ежедневный бонус: {DAILY_BONUS} звёзд"
    )
    
    await callback.message.edit_text(stats_text, parse_mode='HTML', reply_markup=get_back_admin_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_menu(callback: CallbackQuery):
    """Меню рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Текстовая рассылка", callback_data="broadcast_text")
    builder.button(text="🖼️ Рассылка с фото", callback_data="broadcast_photo")
    builder.button(text="⬅️ Назад в админку", callback_data="back_to_admin")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "👇 Выберите тип рассылки:",
        parse_mode='HTML',
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "broadcast_text")
async def broadcast_text_start(callback: CallbackQuery, state: FSMContext):
    """Начало текстовой рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 <b>Текстовая рассылка</b>\n\n"
        "Введите текст для рассылки:",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.set_state(AdminStates.broadcast_message)
    await callback.answer()

@router.message(AdminStates.broadcast_message)
async def process_broadcast_text(message: Message, state: FSMContext):
    """Обработка текстовой рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    text = message.text
    users = Database.get_all_users()
    
    await message.answer(f"🔄 Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await bot.send_message(user.user_id, text)
            success += 1
            await asyncio.sleep(0.05)  # Задержка для избежания лимитов
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user.user_id}: {e}")
            failed += 1
    
    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📊 Статистика:\n"
        f"✅ Успешно: {success}\n"
        f"❌ Не удалось: {failed}\n"
        f"👥 Всего: {len(users)}",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.clear()

@router.callback_query(F.data == "admin_create_promo")
async def create_promocode_start(callback: CallbackQuery, state: FSMContext):
    """Создание промокода"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎟️ <b>Создание промокода</b>\n\n"
        "Введите данные в формате:\n"
        "<code>КОД СУММА КОЛИЧЕСТВО_ИСПОЛЬЗОВАНИЙ</code>\n\n"
        "Пример: <code>NEWYEAR25 25 100</code>\n"
        "Создаст промокод NEWYEAR25 на 25 звёзд с 100 использованиями",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.set_state(AdminStates.create_promocode)
    await callback.answer()

@router.message(AdminStates.create_promocode)
async def process_create_promocode(message: Message, state: FSMContext):
    """Обработка создания промокода"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.strip().split()
        if len(parts) != 3:
            raise ValueError
        
        code = parts[0].upper()
        amount = float(parts[1])
        uses = int(parts[2])
        
        if amount <= 0 or uses <= 0:
            raise ValueError
        
        # Проверяем, существует ли уже такой код
        with SessionLocal() as session:
            existing = session.query(Promocode).filter(Promocode.code == code).first()
            if existing:
                await message.answer("❌ Промокод с таким кодом уже существует!", reply_markup=get_back_admin_keyboard())
                await state.clear()
                return
            
            # Создаем промокод
            promo = Promocode(
                code=code,
                reward_amount=amount,
                uses_left=uses
            )
            session.add(promo)
            session.commit()
        
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🎟️ Код: <code>{code}</code>\n"
            f"💰 Награда: {amount} звёзд\n"
            f"🔢 Использований: {uses}\n\n"
            f"Пользователи могут активировать его через меню 'Промокод'",
            parse_mode='HTML',
            reply_markup=get_back_admin_keyboard()
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат!\n\n"
            "Используйте: <code>КОД СУММА КОЛИЧЕСТВО</code>\n"
            "Пример: <code>WELCOME10 10 50</code>",
            parse_mode='HTML',
            reply_markup=get_back_admin_keyboard()
        )
    
    await state.clear()

@router.callback_query(F.data == "admin_ban")
async def admin_ban_menu(callback: CallbackQuery, state: FSMContext):
    """Меню бана пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🚫 <b>Бан пользователя</b>\n\n"
        "Введите user_id пользователя для бана/разбана:",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.set_state(AdminStates.ban_user)
    await callback.answer()

@router.message(AdminStates.ban_user)
async def process_ban_user(message: Message, state: FSMContext):
    """Обработка бана пользователя"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный user_id!", reply_markup=get_back_admin_keyboard())
        await state.clear()
        return
    
    user = Database.get_user(user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден!", reply_markup=get_back_admin_keyboard())
        await state.clear()
        return
    
    if user.is_banned:
        # Разбаниваем
        Database.unban_user(user_id)
        action = "разбанен"
        emoji = "✅"
    else:
        # Баним
        Database.ban_user(user_id)
        action = "забанен"
        emoji = "🚫"
    
    await message.answer(
        f"{emoji} <b>Пользователь {action}!</b>\n\n"
        f"👤 @{user.username or 'Без username'}\n"
        f"🆔 ID: {user.user_id}\n"
        f"💰 Баланс: {user.balance} звёзд\n"
        f"📅 Регистрация: {user.reg_date.strftime('%d.%m.%Y')}",
        parse_mode='HTML',
        reply_markup=get_back_admin_keyboard()
    )
    await state.clear()

@router.callback_query(F.data.startswith("user_ban_"))
async def ban_user_direct(callback: CallbackQuery):
    """Прямой бан пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    if Database.ban_user(user_id):
        await callback.answer("✅ Пользователь забанен!", show_alert=True)
        
        # Обновляем сообщение
        user = Database.get_user(user_id)
        referrals_count = Database.get_referrals_count(user_id)
        
        user_info = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 ID: <code>{user.user_id}</code>\n"
            f"👤 Username: @{user.username or 'Не указан'}\n"
            f"💰 Баланс: <b>{user.balance} звёзд</b>\n"
            f"👥 Рефералов: {referrals_count}\n"
            f"📅 Регистрация: {user.reg_date.strftime('%d.%m.%Y %H:%M')}\n"
            f"🚫 Статус: Забанен"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Управление балансом", callback_data=f"user_balance_{user.user_id}")
        builder.button(text="📋 История транзакций", callback_data=f"user_transactions_{user.user_id}")
        builder.button(text="✅ Разбанить", callback_data=f"user_unban_{user.user_id}")
        builder.button(text="⬅️ Назад в админку", callback_data="back_to_admin")
        builder.adjust(1)
        
        await callback.message.edit_text(user_info, parse_mode='HTML', reply_markup=builder.as_markup())
    else:
        await callback.answer("❌ Ошибка при бане пользователя!", show_alert=True)

@router.callback_query(F.data.startswith("user_unban_"))
async def unban_user_direct(callback: CallbackQuery):
    """Прямой разбан пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    if Database.unban_user(user_id):
        await callback.answer("✅ Пользователь разбанен!", show_alert=True)
        
        # Обновляем сообщение
        user = Database.get_user(user_id)
        referrals_count = Database.get_referrals_count(user_id)
        
        user_info = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 ID: <code>{user.user_id}</code>\n"
            f"👤 Username: @{user.username or 'Не указан'}\n"
            f"💰 Баланс: <b>{user.balance} звёзд</b>\n"
            f"👥 Рефералов: {referrals_count}\n"
            f"📅 Регистрация: {user.reg_date.strftime('%d.%m.%Y %H:%M')}\n"
            f"✅ Статус: Активен"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Управление балансом", callback_data=f"user_balance_{user.user_id}")
        builder.button(text="📋 История транзакций", callback_data=f"user_transactions_{user.user_id}")
        builder.button(text="🚫 Забанить", callback_data=f"user_ban_{user.user_id}")
        builder.button(text="⬅️ Назад в админку", callback_data="back_to_admin")
        builder.adjust(1)
        
        await callback.message.edit_text(user_info, parse_mode='HTML', reply_markup=builder.as_markup())
    else:
        await callback.answer("❌ Ошибка при разбане пользователя!", show_alert=True)

@router.callback_query(F.data.startswith("user_transactions_"))
async def show_user_transactions(callback: CallbackQuery):
    """Показать транзакции пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    user = Database.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    transactions = Database.get_user_transactions(user_id, limit=15)
    
    if not transactions:
        await callback.answer("📭 У пользователя нет транзакций!", show_alert=True)
        return
    
    trans_text = f"📋 <b>История транзакций</b>\n\n👤 Пользователь: @{user.username or 'Без username'}\n🆔 ID: {user_id}\n\n"
    
    for i, trans in enumerate(transactions[:15], 1):
        trans_text += f"{i}. #{trans.id} | {trans.type}\n"
        trans_text += f"   💰 {trans.amount:+.2f} | {trans.timestamp.strftime('%d.%m %H:%M')}\n"
        if trans.description:
            trans_text += f"   📝 {trans.description[:50]}\n"
        trans_text += "\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к пользователю", callback_data=f"user_balance_{user_id}")
    builder.button(text="⬅️ В админку", callback_data="back_to_admin")
    
    await callback.message.edit_text(trans_text, parse_mode='HTML', reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "admin_transactions")
async def admin_all_transactions(callback: CallbackQuery):
    """Все транзакции"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    # Получаем последние 20 транзакций
    with SessionLocal() as session:
        transactions = session.query(Transaction).order_by(Transaction.timestamp.desc()).limit(20).all()
    
    if not transactions:
        await callback.answer("📭 Транзакций нет!", show_alert=True)
        return
    
    trans_text = "📋 <b>Последние транзакции</b>\n\n"
    
    for i, trans in enumerate(transactions, 1):
        trans_text += f"{i}. #{trans.id} | {trans.type}\n"
        trans_text += f"   👤 Получатель: {trans.receiver_id}\n"
        if trans.sender_id:
            trans_text += f"   👤 Отправитель: {trans.sender_id}\n"
        trans_text += f"   💰 {trans.amount:+.2f} | {trans.timestamp.strftime('%d.%m %H:%M')}\n"
        trans_text += "\n"
    
    await callback.message.edit_text(trans_text, parse_mode='HTML', reply_markup=get_back_admin_keyboard())
    await callback.answer()

# ========== ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ ==========
@router.message()
async def handle_all_messages(message: Message):
    """Обработка всех сообщений"""
    await message.answer(
        "👋 Используйте кнопки меню для навигации\n"
        "Если меню пропало, введите /start",
        reply_markup=get_main_keyboard()
    )

# ========== ЗАПУСК БОТА ==========
async def main():
    """Основная функция запуска бота"""
    logger.info("Бот запускается...")
    
    # Пропускаем накопившиеся апдейты
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

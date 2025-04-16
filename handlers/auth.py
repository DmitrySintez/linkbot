from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from io import BytesIO

from database import db
from models import AuthStates
from config import ADMIN_IDS
from utils.keyboards import get_start_keyboard, get_main_keyboard, get_admin_keyboard
from utils.captcha import generate_captcha_text, generate_captcha_image
from utils.helpers import send_error_message, send_success_message

async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
    # Генерация капчи
    captcha_text = generate_captcha_text()
    captcha_image = generate_captcha_image(captcha_text)
    
    await state.update_data(captcha_text=captcha_text)
    
    await message.answer(
        "👋 Добро пожаловать в бот для управления ссылками!\n\n"
        "Для начала пройдите проверку, введя текст с картинки:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    await message.answer_photo(
        types.InputFile(BytesIO(captcha_image), filename="captcha.png")
    )
    await AuthStates.waiting_for_captcha.set()

async def cmd_login(message: types.Message):
    """Начало процесса авторизации"""
    await message.answer("Пожалуйста, введите ваш логин:", reply_markup=types.ReplyKeyboardRemove())
    await AuthStates.waiting_for_username.set()

async def process_captcha(message: types.Message, state: FSMContext):
    """Проверка капчи и запрос логина"""
    user_input = message.text.strip().upper()
    user_data = await state.get_data()
    captcha_text = user_data.get('captcha_text')
    
    if user_input != captcha_text:
        await send_error_message(message, "Неверный код с картинки. Начните сначала: /start")
        await state.finish()
        return
    
    await message.answer("Пожалуйста, введите ваш логин:", reply_markup=types.ReplyKeyboardRemove())
    await AuthStates.waiting_for_username.set()

async def process_username(message: types.Message, state: FSMContext):
    """Обработка ввода имени пользователя"""
    username = message.text.strip()
    await state.update_data(username=username)
    
    await message.answer("Теперь введите пароль:", reply_markup=types.ReplyKeyboardRemove())
    await AuthStates.waiting_for_password.set()

async def process_password(message: types.Message, state: FSMContext):
    """Обработка ввода пароля и завершение авторизации"""
    password = message.text.strip()
    user_data = await state.get_data()
    username = user_data.get('username')
    
    # Проверка учетных данных
    user_id = db.authenticate_user(username, password)
    
    if not user_id:
        await send_error_message(message, "Неверный логин или пароль. Попробуйте еще раз: /login")
        await state.finish()
        return
    
    # Обновление Telegram ID пользователя
    db.update_telegram_id(user_id, message.from_user.id)
    
    keyboard = get_admin_keyboard() if message.from_user.id in ADMIN_IDS else get_main_keyboard()
    
    await message.answer(
        "✅ Успешный вход!\n\n"
        "Теперь вы можете:\n"
        "- Установить свою ссылку: /setlink\n"
        "- Посмотреть текущую ссылку: /mylink\n"
        "- Выйти из аккаунта: /logout",
        reply_markup=keyboard
    )
    await state.finish()

async def cmd_logout(message: types.Message):
    """Выход из аккаунта"""
    user = db.get_user_by_telegram_id(message.from_user.id)
    
    if not user:
        await send_error_message(message, "Вы не авторизованы.", reply_markup=get_start_keyboard())
        return
    
    # Удаление привязки Telegram ID к аккаунту
    db.update_telegram_id(user[0], None)
    await message.answer("Вы успешно вышли из аккаунта.", reply_markup=get_start_keyboard())

def register_auth_handlers(dp: Dispatcher):
    """Регистрация обработчиков авторизации"""
    # Команды
    dp.register_message_handler(cmd_start, Command("start"))
    dp.register_message_handler(cmd_login, Command("login"))
    dp.register_message_handler(cmd_login, text="🔑 Авторизоваться")
    dp.register_message_handler(cmd_logout, Command("logout"))
    dp.register_message_handler(cmd_logout, text="🚪 Выйти")
    
    # Состояния авторизации
    dp.register_message_handler(process_captcha, state=AuthStates.waiting_for_captcha)
    dp.register_message_handler(process_username, state=AuthStates.waiting_for_username)
    dp.register_message_handler(process_password, state=AuthStates.waiting_for_password)

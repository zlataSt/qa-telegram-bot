import asyncio
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramBadRequest

from gemini_client import generate_test_cases, generate_autotest_code
from file_utils import save_to_docx, save_to_pdf, save_code_to_file, split_text

import uuid
import os
import json

router = Router()
SESSION_CACHE_FILE = "session_cache.json"

if os.path.exists(SESSION_CACHE_FILE):
    with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
        SESSION_CACHE = json.load(f)
else:
    SESSION_CACHE = {}

def save_cache():
    with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(SESSION_CACHE, f, ensure_ascii=False, indent=2)

def sanitize_markdown(text: str) -> str:
    text = text.replace(':**', ': **').replace('****', '**')
    return text

def sanitize_code_block(code: str, language: str) -> str:
    """Убирает внешние тройные кавычки и маркер языка."""
    clean_code = code.strip()
    if clean_code.startswith(f"```{language}"):
        clean_code = clean_code[len(f"```{language}"):]
    if clean_code.endswith("```"):
        clean_code = clean_code[:-3]
    return clean_code.strip()

def get_main_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для мануальных тестов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 DOCX", callback_data=f"docx:{session_id}"),
            InlineKeyboardButton(text="📑 PDF", callback_data=f"pdf:{session_id}")
        ],
        [InlineKeyboardButton(text="📋 Показать полностью", callback_data=f"full_manual:{session_id}")],
        [InlineKeyboardButton(text="🤖 Сгенерировать автотест", callback_data=f"autotest_menu:{session_id}")],
        [InlineKeyboardButton(text="✅ Новая фича", callback_data="new_feature")]
    ])

def get_autotest_lang_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора языка для автотеста."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🐍 Python", callback_data=f"gen_auto:python:{session_id}"),
            InlineKeyboardButton(text="☕ Java", callback_data=f"gen_auto:java:{session_id}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_manual:{session_id}")]
    ])

def get_autotest_result_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Клавиатура после генерации автотеста."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться к мануальному сценарию", callback_data=f"back_manual:{session_id}")]
    ])

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer("Привет! Пришли описание фичи, и я сгенерирую тест-кейсы ✍️")

@router.message(F.text)
async def handle_text(message: Message):
    await message.answer("Анализирую фичу и генерирую тесты... 🧠⏳")
    raw_result = generate_test_cases(message.text)
    result = sanitize_markdown(raw_result)
    session_id = str(uuid.uuid4())
    SESSION_CACHE[session_id] = {"manual": result}
    save_cache()
    preview_lines = result.split('\n')[:7]
    preview_text = "\n".join(preview_lines) + "\n\n..."
    keyboard = get_main_keyboard(session_id)
    await message.answer(
        "**Вот превью сгенерированных мануальных тестов:**\n\n" + preview_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith(("docx:", "pdf:", "full_manual:")))
async def manual_actions_handler(call: CallbackQuery):
    action, session_id = call.data.split(":", 1)
    session = SESSION_CACHE.get(session_id)
    if not session or "manual" not in session:
        await call.answer("Сессия устарела, начните заново.", show_alert=True)
        return
    content = session["manual"]
    if action == "docx":
        path = save_to_docx(content, session_id)
        await call.message.answer_document(FSInputFile(path))
        os.remove(path)
    elif action == "pdf":
        path = save_to_pdf(content, session_id)
        await call.message.answer_document(FSInputFile(path))
        os.remove(path)
    elif action == "full_manual":
        try:
            await call.message.answer(content, parse_mode="Markdown")
        except TelegramBadRequest:
            await call.message.answer(content)
        finally:
            keyboard = get_main_keyboard(session_id)
            await call.message.answer("🔽 Выберите следующее действие:", reply_markup=keyboard)
    await call.answer()

@router.callback_query(F.data.startswith("autotest_menu:"))
async def show_autotest_menu(call: CallbackQuery):
    """Показывает меню выбора языка."""
    session_id = call.data.split(":")[1]
    keyboard = get_autotest_lang_keyboard(session_id)
    await call.message.edit_text("Выберите язык для генерации автотеста:", reply_markup=keyboard)
    await call.answer()

@router.callback_query(F.data.startswith("gen_auto:"))
async def generate_autotest_handler(call: CallbackQuery):
    """Генерирует и отправляет автотест, деля его на части при необходимости."""
    _, language, session_id = call.data.split(":", 2)
    session = SESSION_CACHE.get(session_id)
    if not session or "manual" not in session:
        await call.answer("Сессия устарела, начните заново.", show_alert=True)
        return
    await call.message.edit_text(f"Генерирую автотест на {language.title()}... 🤖⏳")
    manual_test = session["manual"]
    raw_code = generate_autotest_code(manual_test, language)
    code = sanitize_code_block(raw_code, language)
    try:
        formatted_code = f'<pre><code class="language-{language}">{code}</code></pre>'
        if len(formatted_code) <= 4096:
            await call.message.answer(formatted_code, parse_mode="HTML")
        else:
            chunks = split_text(code)
            for i, chunk in enumerate(chunks):
                header = f"Код автотеста (часть {i+1}/{len(chunks)}):\n" if len(chunks) > 1 else ""
                await call.message.answer(f"{header}```{language}\n{chunk}\n```", parse_mode="MarkdownV2")
                await asyncio.sleep(0.2)
    except TelegramBadRequest:
        chunks = split_text(code)
        await call.message.answer("Не удалось отформатировать код, отправляю как простой текст:")
        for chunk in chunks:
            await call.message.answer(chunk)
            await asyncio.sleep(0.2)
    file_path = save_code_to_file(code, session_id, language)
    await call.message.answer_document(FSInputFile(file_path))
    os.remove(file_path)
    keyboard = get_autotest_result_keyboard(session_id)
    await call.message.answer("Автотест сгенерирован.", reply_markup=keyboard)
    await call.answer()

@router.callback_query(F.data.startswith("back_manual:"))
async def back_to_manual_handler(call: CallbackQuery):
    """Возвращает пользователя к меню мануальных тестов."""
    session_id = call.data.split(":")[1]
    session = SESSION_CACHE.get(session_id)
    if not session or "manual" not in session:
        await call.answer("Сессия устарела, начните заново.", show_alert=True)
        return

    content = session["manual"]
    preview_lines = content.split('\n')[:7]
    preview_text = "\n".join(preview_lines) + "\n\n..."
    keyboard = get_main_keyboard(session_id)
    
    await call.message.edit_text(
        "**Вот превью сгенерированных мануальных тестов:**\n\n" + preview_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await call.answer()

@router.callback_query(F.data == "new_feature")
async def handle_new_feature(call: CallbackQuery):
    """Сбрасывает диалог и приглашает к вводу новой фичи."""
    await call.message.edit_text("Отлично! Жду новое описание фичи. Просто пришли его в чат. ✍️")
    await call.answer()
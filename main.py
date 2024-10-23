"""
2024.10.21
Kwork
Телеграм-бот для проведения квиза в канале
"""

import asyncio
import json
import logging
import random
import gspread

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from oauth2client.service_account import ServiceAccountCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from model import Quiz, Settings
from state import CommonStates


with open('config.json', mode='r', encoding='utf-8') as config_file:
    config = json.load(config_file)


engine = create_engine(f'sqlite:///database.db', echo=False)
Session = sessionmaker(autoflush=False, bind=engine)


scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(config["google_api_json_path"], scope)
client = gspread.authorize(creds)


bot = Bot(token=config["tg_api_token"])
dp = Dispatcher()


scheduler = AsyncIOScheduler()


def is_admin(id:int) -> bool:
    """
    Функция проверки прав администратора.
    """
    return True if id in config["admin_id"] else False


def sort_answers(answers: str, correct: str) -> tuple[list, list]:
    """
    Функция сортировки списка ответов и соответствующих правильных индексов
    """
    answers_list = answers.split(";")
    correct_answer = answers_list[int(correct)-1]
    random.shuffle(answers_list)
    new_correct_indice = answers_list.index(correct_answer)
    return answers_list, new_correct_indice


@dp.message(Command("settings"))
async def update_parameters(message: Message, state: FSMContext):
    """
    Обновление параметров конфигурации
    """
    if not is_admin(message.from_user.id):
        await message.answer("Вы не являетесь администратором!")
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="Случайный режим", callback_data="random_mode")
    builder.button(text="Последовательный режим", callback_data="serial_mode")
    builder.button(text="Не изменять", callback_data="skip")
    await message.answer("Выберите режим", reply_markup=builder.as_markup())
    await state.set_state(CommonStates.quiz_mode_await)
    

@dp.callback_query(StateFilter(CommonStates.quiz_mode_await))
async def quiz_mode_handler(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.data == "random_mode":
        config["quiz_random"] = True
    elif callback_query.data == "serial_mode":
        config["quiz_random"] = False
        await state.set_state(CommonStates.period_await)
    elif callback_query.data == "skip":
        pass
    else:
        return

    # обновление конфига
    with open('config.json', 'w') as file:
        json.dump(config, file, indent=4)
    builder = InlineKeyboardBuilder()
    builder.button(text="Не изменять", callback_data="skip")
    await callback_query.message.answer("Введите период отправки квиза в минутах", reply_markup=builder.as_markup())
    await state.set_state(CommonStates.period_await)


@dp.message(StateFilter(CommonStates.period_await))
async def quiz_period_handler(message: Message, state: FSMContext):
    try:
        period = int(message.text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer("Неправильно введено число, введите повторно")
        return
    config["period"] = period
    with open('config.json', 'w') as file:
        json.dump(config, file, indent=4)
    builder = InlineKeyboardBuilder()
    builder.button(text="Не изменять", callback_data="skip")
    await message.answer("Введите id или адрес канала", reply_markup=builder.as_markup())
    await state.set_state(CommonStates.channel_id_await)


@dp.callback_query(StateFilter(CommonStates.period_await))
async def skip_pressed(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.data == "skip":
        builder = InlineKeyboardBuilder()
        builder.button(text="Не изменять", callback_data="skip")
        await callback_query.message.answer("Введите id или адрес канала", reply_markup=builder.as_markup())
        await state.set_state(CommonStates.channel_id_await)


@dp.message(StateFilter(CommonStates.channel_id_await))
async def quiz_period_handler(message: Message, state: FSMContext):
    config["channel_id"] = message.text
    with open('config.json', 'w') as file:
        json.dump(config, file, indent=4)
    await message.answer("Настройки применены успешно, для применения перезапустите бота командой /quiz")
    await state.clear()


@dp.callback_query(StateFilter(CommonStates.channel_id_await))
async def skip_pressed(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.data == "skip":
        await callback_query.message.answer("Настройки применены успешно, для применения перезапустите бота командой /quiz")
        await state.clear()


@dp.message(Command("update_questions"))
async def update_quiz_base(message: Message):
    """
    Обработчик команды на получение списка вопросов из Google Sheets и загрузка в database
    """
    if not is_admin(message.from_user.id):
        await message.answer("Вы не являетесь администратором!")
        return
    session = Session()
    try:
        data_from_table = await get_quiz_from_table()
        session.query(Quiz).delete()
        for item in data_from_table:
            new_question = Quiz(id=item["id"], question=item["question"], answers=item["answers"], correct=item["correct"])
            session.add(new_question)
        session.commit()
    except Exception as e:
        logging.error(f"Ошибка при обработке контакта: {e}")
    finally:
        session.close()


async def get_quiz_from_table():
    """
    Получение нового списка вопросов-ответов для квиза
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('quiz-bot-439309-01a11dadf94a.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(config["google_table_url"])
    worksheet = sheet.worksheet("Sheet1")
    data = worksheet.get_all_records()
    return data


async def send_periodic_message(chat_id: int):
    """
    Функция отправки викторины в чат
    """
    session = Session()
    try:
        quiz_questions = session.query(Quiz).all()
        quiz_list = []
        for quiz_question in quiz_questions:
            sorted_answer, sorted_correct = sort_answers(quiz_question.answers, quiz_question.correct)
            quiz_list.append({
                'num': quiz_question.id, 
                'question': quiz_question.question, 
                'answers': sorted_answer, 
                'correct': sorted_correct
            })
        if config["quiz_random"]:
            quiz = random.choice(quiz_list)
        else:
            settings = session.get(Settings, 1)
            last_question_index = settings.last_question_index
            if last_question_index == len(quiz_list) - 1:
                last_question_index = 0
            else:
                last_question_index += 1
            quiz = quiz_list[last_question_index]
            settings.last_question_index = last_question_index
            session.commit()
        await bot.send_poll(
            chat_id=config["channel_id"],
            question=quiz["question"],
            options=quiz["answers"],
            type='quiz',
            correct_option_id=quiz["correct"],
            is_anonymous=True
            )
    except Exception as e:
        logging.error(f"Ошибка при обработке контакта: {e}")
    finally:
        session.close()


@dp.message(Command("quiz"))
async def update_quiz_base(message: Message):
    # обьявление задачи, ее параметров
    scheduler.add_job(
        send_periodic_message,
        IntervalTrigger(minutes=config["period"]),
        args=(config["channel_id"],),
        id='periodic_message_job',
        replace_existing=True
    )
    await message.answer("Квиз запущен/обновлен")


async def main():
    scheduler.start()
    logging.getLogger('aiogram').setLevel(logging.INFO)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

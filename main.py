import asyncio
import json
import logging
import random
import gspread

from aiogram import Bot
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from oauth2client.service_account import ServiceAccountCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from model import Quiz


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
  

@dp.message(Command("update_quiz"))
async def update_quiz_base(message: Message):
    """
    Обработчик команды на получение списка вопросов из Google Sheets и загрузка в database
    """
    session = Session()
    try:
        if not is_admin(message.from_user.id):
            await message.answer("Вы не являетесь администратором!")
            return
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
        quiz = random.choice(quiz_list)
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


# обьявление задачи, ее параметров
scheduler.add_job(
    send_periodic_message,
    IntervalTrigger(seconds=config["period"]),
    args=(config["channel_id"],),
    id='periodic_message_job',
    replace_existing=True
)


async def main():
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

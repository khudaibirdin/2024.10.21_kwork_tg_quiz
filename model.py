from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Quiz(Base):
    __tablename__ = 'quiz'

    id = Column(Integer, primary_key=True)
    question = Column(String)
    answers = Column(String)
    correct = Column(String)


class Settings(Base):
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True)
    last_question_index = Column(Integer)

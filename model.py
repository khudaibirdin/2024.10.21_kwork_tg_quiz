from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class Quiz(Base):
    __tablename__ = 'quiz'

    id = Column(Integer, primary_key=True)
    question = Column(String)
    answers = Column(String)
    correct = Column(String)
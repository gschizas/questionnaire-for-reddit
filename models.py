from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

import os

Base = declarative_base()


# class Survey(Base):
#     __tablename__ = 'Surveys'
#
#     survey_id = Column(Integer, primary_key=True, autoincrement=True)
#     title = Column(String)
#     data = Column(Text)


class Vote(Base):
    __tablename__ = 'Votes'

    vote_id = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(String)
    # survey_id = Column(Integer, ForeignKey('Survey.id'))
    # survey = relationship('Survey', backref='votes')


class Answer(Base):
    __tablename__ = 'Answers'

    answer_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, primary_key=True)
    question_id = Column(String)
    answer_value = Column(String)
    vote_id = Column(Integer, ForeignKey('Vote.vote_id'))
    vote = relationship('Vote', backref='answers')


Session = sessionmaker()
engine = create_engine(os.getenv('DATABASE_URL'), echo=False)
Session.configure(bind=engine)

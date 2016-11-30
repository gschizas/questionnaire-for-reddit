from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# class Survey(Base):
#     __tablename__ = 'Surveys'
#
#     survey_id = Column(Integer, primary_key=True, autoincrement=True)
#     title = Column(String)
#     data = Column(Text)


class Vote(db.Model):
    __tablename__ = 'Votes'

    vote_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userid = db.Column(db.String)
    datestamp = db.Column(db.DateTime)
    # survey_id = Column(Integer, ForeignKey('Survey.id'))
    # survey = relationship('Survey', backref='votes')


class Answer(db.Model):
    __tablename__ = 'Answers'

    answer_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code = db.Column(db.String, primary_key=True)
    answer_value = db.Column(db.String)
    vote_id = db.Column(db.Integer, db.ForeignKey('Votes.vote_id'))
    vote = db.relationship('Vote', backref='answers')


class Receipt(db.Model):
    __tablename__ = 'Receipts'

    user_id = db.Column(db.String, primary_key=True)

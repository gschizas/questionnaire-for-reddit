import os

from faker import Faker
from faker.providers import internet, date_time
from flask import Blueprint, session, make_response, redirect, url_for
from werkzeug.exceptions import abort

from util import base36encode

fake = None
mock_app = Blueprint('mock', __name__)


def _init():
    global fake
    fake = Faker()
    fake.add_provider(internet)
    fake.add_provider(date_time)


@mock_app.route('/mock')
def mock_login():
    global fake
    if os.environ.get('MOCK') != '1':
        abort(404)
    if not fake:
        _init()
    session['me'] = {
        'comment_karma': fake.random.randrange(100, 1000),
        'created_utc': fake.date_time_between(start_date='-10y', end_date='-1y').timestamp() // 1000,
        'id': base36encode(fake.random.randrange(100000)), 'link_karma': fake.random.randrange(100, 1000),
        'name': fake.user_name()}
    return make_response(redirect(url_for('home')))


class MockRedditAgent:
    class auth:
        def url(self, scope, state, duration='temporary'):
            return '/mock'

    # noinspection PyMethodFirstArgAssignment

    class user:
        @staticmethod
        def me():
            pass

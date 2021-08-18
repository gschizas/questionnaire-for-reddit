#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import binascii
import datetime
import hashlib
import logging
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import uuid

import praw
import prawcore
import requests
import sqlalchemy
from flask import (Flask, render_template, make_response, request, redirect, url_for, session, abort, g, Response,
                   jsonify)
from flask_babel import Babel
from flask_caching import Cache
from werkzeug.middleware.proxy_fix import ProxyFix

import model

__version__ = '0.5'

from mock import mock_app, MockRedditAgent
from yaml_wrapper import yaml

USER_AGENT = 'python:gr.terrasoft.reddit:questionnaire:v{0} (by /u/gschizas)'.format(__version__)
EMOJI_FLAG_OFFSET = ord('🇦') - ord('A')

app = Flask(__name__)
babel = Babel(app)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=True, x_host=1)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

logging.basicConfig(level=logging.DEBUG)
first_run = False

model.db.init_app(app)
with app.app_context():
    model.db.create_all()

if os.environ.get('MOCK') == '1':
    app.register_blueprint(mock_app)


@app.context_processor
def inject_sysinfo():
    return dict(sysinfo=dict(build=__version__))


@app.context_processor
def inject_user():
    return dict(user=session['me']) if 'me' in session else dict(user=None)


@app.template_filter('maxlength')
def max_length(iterable):
    validators_max_length = [v.max for v in iterable.validators if 'wtforms.validators.Length' in str(type(v))]
    if len(validators_max_length) > 0:
        return max(validators_max_length)


@app.template_filter('emojiflag')
def emojiflag(flag_letters):
    if len(flag_letters) != 2:
        return flag_letters
    if flag_letters[0] < 'A' or flag_letters[0] > 'Z':
        return flag_letters
    if flag_letters[1] < 'A' or flag_letters[0] > 'Z':
        return flag_letters
    return chr(ord(flag_letters[0]) + EMOJI_FLAG_OFFSET) + chr(ord(flag_letters[1]) + EMOJI_FLAG_OFFSET)


@app.template_filter('quote_list')
def surround_by_quote(a_list):
    return ['"{}"'.format(an_element) for an_element in a_list]


@babel.localeselector
def get_locale():
    # if a user is logged in, use the locale from the user settings
    user = getattr(g, 'user', None)
    if user is not None:
        return user.locale
    # otherwise try to guess the language from the user accept
    # header the browser transmits.  We support de/fr/en in this
    # example.  The best match wins.
    return request.accept_languages.best_match(['en', 'el', 'de'])


@babel.timezoneselector
def get_timezone():
    user = getattr(g, 'user', None)
    if user is not None:
        return user.timezone


@app.route('/_dropdown/<table_name>', methods=('GET', 'POST'))
def dropdown(table_name):
    pass


@app.errorhandler(500)
def page_error(e):
    print(e, file=sys.stderr)
    return render_template('error.html'), 500


def reddit_agent():
    if os.environ.get('MOCK') == '1':
        return MockRedditAgent()
    redirect_uri = urllib.parse.urljoin(os.getenv('REDDIT_OAUTH_REDIRECT_URL'), url_for('authorize_callback'))
    r = praw.Reddit(
        client_id=os.getenv('REDDIT_OAUTH_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_OAUTH_CLIENT_SECRET'),
        redirect_uri=redirect_uri,
        user_agent=USER_AGENT)
    return r


def get_me_serializable(r):
    me = r.user.me()
    me_serializable = dict(comment_karma=me.comment_karma, created=me.created, created_utc=me.created_utc,
                           gold_creddits=me.gold_creddits, gold_expiration=me.gold_expiration,
                           has_verified_email=me.has_verified_email, hide_from_robots=me.hide_from_robots, id=me.id,
                           inbox_count=me.inbox_count, is_gold=me.is_gold, is_mod=me.is_mod,
                           link_karma=me.link_karma, name=me.name, over_18=me.over_18)
    return me_serializable


def make_authorize_url(r):
    scope = ['identity']
    session['state'] = str(uuid.uuid4())
    authorize_url = r.auth.url(scope, session['state'], 'temporary')
    return authorize_url


@app.route('/authorize_callback')
def authorize_callback():
    state = request.args.get('state')
    if state != session.get('state'):
        return make_response(redirect(url_for('index')))
    code = request.args.get('code')
    r = reddit_agent()
    try:
        r.auth.authorize(code)
    except prawcore.exceptions.OAuthException:
        return make_response(redirect(url_for('index')))
    session['me'] = get_me_serializable(r)
    return make_response(redirect(url_for('home')))


@app.route('/')
def index():
    global first_run
    if first_run:
        session.clear()
        first_run = False
    r = reddit_agent()
    return make_response(redirect(make_authorize_url(r)))


@app.route('/about')
def about_page():
    return render_template('about.html')


@app.route('/home')
def home():
    if 'me' not in session:
        return make_response(redirect(url_for('index')))
    questions = read_questionnaire()
    question_id = 1
    config = {}
    config_questions = [q for q in questions if q['kind'] == 'config']
    for cq in config_questions:
        config.update(cq['config'])
    questions = [q for q in questions if q['kind'] != 'config']

    for question in questions:
        if question['kind'] in ('header', 'config'):
            continue
        question['id'] = question_id
        question_id += 1

    if 'account_older_than' in config:
        created_date = datetime.datetime.fromtimestamp(session['me']['created_utc'])
        if created_date > config['account_older_than']:
            return Response('Your account is too new', mimetype='text/plain')

    answers = {}

    receipt = model.Receipt.query.filter_by(user_id=session['me']['id']).first()
    if receipt is not None:
        if request.cookies.get('receipt_id') is None:
            return render_template('done.html', nocookie=True)

        receipt_id_text = request.cookies['receipt_id']
        receipt_id_bytes = binascii.unhexlify(receipt_id_text.replace('-', ''))
        userhash = hashlib.sha256(session['me']['id'].encode('utf8') + receipt_id_bytes).hexdigest()

        vote = model.Vote.query.filter_by(user_hash=userhash).first()
        if vote is not None:
            answers = {a.code: a.answer_value for a in vote.answers}
        else:
            return render_template('done.html', tamper=True)

    return render_template(
        'home.html',
        questions=questions,
        answers=answers,
        config=config,
        recaptcha_site_key=os.environ.get('RECAPTCHA_SITE_KEY'))


@app.route('/results')
def results():
    if 'me' not in session:
        return make_response(redirect(url_for('index')))
    current_testers_text = os.getenv('TESTERS', '')
    current_testers = re.split(r'\W', current_testers_text)
    user_is_tester = session['me']['name'] in current_testers
    if not user_is_tester:
        abort(503)

    from sqlalchemy import func
    with app.app_context():
        questions = read_questionnaire()
        raw_results = model.db.session.query(
            model.Answer.code,
            model.Answer.answer_value,
            func.count(model.Answer.answer_id)).group_by(
            model.Answer.code,
            model.Answer.answer_value).all()

        pure_questions = [q for q in questions if q['kind'] not in ('config', 'header')]
        raw_results = sorted(
            [expand_question(result, pure_questions) for result in raw_results],
            key=lambda x: x['sort_order'])
        if request.query_string.lower() == b'json':
            for r in raw_results:
                r.pop('sort_order')
            response = make_response(jsonify(raw_results))
            response.headers['Content-Disposition'] = 'attachement; filename=results.json'
            return response
        else:
            return render_template('results.html', results=raw_results)


def expand_question(result, questions):
    question_code_raw = result[0]
    answer_value = result[1]
    vote_count = result[2]
    question_code_parts = question_code_raw.split('_')
    question_code = int(question_code_parts[1]) - 1
    question_suffix = question_code_parts[2] if len(question_code_parts) == 3 else ''
    answer_text = '\0'
    question = questions[question_code]
    question_kind = question['kind']
    question_text = question['title']
    if 'choices' in question:
        if question_kind == 'checkbox' and question_suffix != 'text':
            answer_value = question_suffix
        if question_kind == 'tree':
            answer_text = find_choice(question['choices'], answer_value)
        elif question_kind == 'checktree':
            answer_text = find_choice(question['choices'], question_code_parts[2])
        elif question_kind in ('radio', 'checkbox'):
            if answer_value in question['choices']:
                answer_text = question['choices'][answer_value]
            else:
                answer_text = answer_value
                answer_value = 'Other'
        elif question_kind == 'scale-matrix':
            subquestion = question['lines'][int(question_suffix) - 1]
            if subquestion:
                question_text += ': ' + subquestion
            answer_keys = list(question['choices'].keys())
            if answer_value not in ('maybe', 'no', 'yes'):
                answer_text = question['choices'][answer_keys[int(answer_value) - 1]]
            else:
                answer_text += f'†{answer_value}'
            # answer_value = question['choices'][f'A{answer_value}']

    sort_order = question_code, question_code_parts[2:]
    # question_code_raw += '::' + question['kind']
    return {
        'kind': question_kind,
        'question_number': 1 + question_code,
        'question_code': question_code_raw,
        'question_text': question_text,
        'answer_value': answer_value,
        'answer_text': answer_text,
        'vote_count': vote_count,
        'sort_order': sort_order}


def find_choice(choices, value):
    if value in choices:
        return choices[value]['title']

    new_value = ''
    for choice_name, choice in choices.items():
        if 'choices' in choice:
            new_value = find_choice(choice['choices'], value)
            if new_value:
                return new_value
    return new_value


@cache.cached(timeout=300)
def read_questionnaire():
    url = os.getenv('QUESTIONNAIRE_URL')
    if url.startswith('file://'):
        url_obj = urllib.parse.urlparse(url)
        file_path = urllib.request.url2pathname(url_obj.path)
        questions_list = pathlib.Path(file_path).read_text(encoding='utf8')
    else:
        questionnaire_data = requests.get(url, params=dict(raw_json=1), headers={'User-Agent': USER_AGENT}).json()
        if 'data' not in questionnaire_data:
            print(questionnaire_data)
            abort(503)
        questions_list = questionnaire_data['data']['content_md']
    questions = list(yaml.load_all(questions_list))
    return questions


@app.route('/restore_cookie', methods=('GET', 'POST'))
def restore_cookie():
    if 'me' not in session:
        return make_response(redirect(url_for('index')))
    if request.method == 'GET':
        return render_template('restore_cookie.html')
    else:
        receipt_id = request.form['receipt_id']
        response = redirect(url_for('home'))
        response.set_cookie('receipt_id', value=receipt_id, httponly=True)
        return response


def questions_sort(x):
    return int(x[0][2:]) if x[0][0:1] == 'q_' else '__' + x[0]


@app.route('/done', methods=('POST',))
def save():
    response = None
    with app.app_context():
        if 'RECAPTCHA_SECRET' in os.environ:
            recaptcha_secret = os.environ['RECAPTCHA_SECRET']
            recaptcha_response = request.form['g-recaptcha-response']
            remote_ip = request.remote_addr
            verification = requests.post(
                'https://www.google.com/recaptcha/api/siteverify',
                data=dict(
                    secret=recaptcha_secret,
                    response=recaptcha_response,
                    remoteip=remote_ip
                )).json()
            if not verification['success']:
                return make_response(redirect(url_for('index')))

        receipt = model.Receipt.query.filter_by(user_id=session['me']['id']).first()

        current_testers_text = os.getenv('TESTERS', '')
        current_testers = re.split(r'\W', current_testers_text)
        user_is_tester = session['me']['name'] in current_testers

        if receipt is not None:
            if request.cookies['receipt_id'] is None:
                return render_template('done.html', nocookie=True)

            receipt_id_text = request.cookies['receipt_id']
            receipt_id_bytes = binascii.unhexlify(receipt_id_text.replace('-', ''))
            userhash = hashlib.sha256(session['me']['id'].encode('utf8') + receipt_id_bytes).hexdigest()
            if model.Vote.query.filter_by(user_hash=userhash).count() == 0:
                return render_template('done.html', tamper=True)
            response = make_response(
                render_template('done.html', voted=True, receipt_id=receipt_id_text, request=request,
                                user_is_tester=user_is_tester))
        else:
            receipt_id = uuid.uuid4()
            receipt_id_text = str(receipt_id)
            userhash = hashlib.sha256(session['me']['id'].encode('utf8') + receipt_id.bytes).hexdigest()
            response = make_response(
                render_template('done.html', voted=True, receipt_id=receipt_id_text, request=request,
                                user_is_tester=user_is_tester))
            response.set_cookie('receipt_id', value=receipt_id_text)
            rct = model.Receipt()
            rct.user_id = session['me']['id']
            model.db.session.add(rct)

        v = model.Vote.query.filter_by(user_hash=userhash).first()
        if v is None:
            v = model.Vote()
            v.user_hash = userhash
        v.datestamp = datetime.datetime.utcnow()
        model.db.session.add(v)
        # response = 'userid=' + session['me']['id'] + '\n'
        for a in v.answers:
            model.db.session.delete(a)
        for field, value in sorted(request.form.items(), key=questions_sort):
            if value is None or value == '':
                continue
            if field in ('cmd_save', 'g-recaptcha-response'):
                continue
            if not field.startswith('q_'):
                continue
            a = model.Answer.query.filter_by(code=field, vote=v).first()
            if a is None:
                a = model.Answer()
                a.code = field
                a.vote = v
            if len(value) >= 512:
                value = value[:511] + '\u2026'
            a.answer_value = value
            a.vote = v
            model.db.session.add(a)
        try:
            model.db.session.commit()
        except sqlalchemy.exc.OperationalError as e:
            response = make_response(render_template('done.html', error=True))
    if response is None:
        response = make_response(render_template('done.html'))
    return response


def main():
    global first_run
    # app.session_interface = SqliteSessionInterface()
    first_run = True
    app.jinja_env.auto_reload = True
    app.run(port=5000, host='0.0.0.0', debug=True)


if __name__ == '__main__':
    main()

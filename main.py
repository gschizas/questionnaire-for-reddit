#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import collections
import datetime
import logging
import os
import pathlib
import urllib.parse
import urllib.request
import uuid

import praw
import prawcore
import requests
import ruamel.yaml as yaml
from flask import Flask, render_template, make_response, request, redirect, url_for, session, abort, g
from flask import Response
from flask_babel import Babel

import model

USER_AGENT = 'python:gr.terrasoft.reddit:questionnaire:v0.3 (by /u/gschizas)'
EMOJI_FLAG_OFFSET = ord('🇦') - ord('A')

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
babel = Babel(app)
logging.basicConfig(level=logging.DEBUG)
first_run = False

model.db.init_app(app)
with app.app_context():
    model.db.create_all()


def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))


def literal_str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data, style='|')
    else:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data)


def carry_over_compose_document(self):
    self.get_event()
    node = self.compose_node(None, None)
    self.get_event()
    # this prevents cleaning of anchors between documents in **one stream**
    # self.anchors = {}
    return node


yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dict_constructor)
yaml.add_representer(collections.OrderedDict, dict_representer)
yaml.add_representer(str, literal_str_representer)
yaml.composer.Composer.compose_document = carry_over_compose_document


@app.context_processor
def inject_sysinfo():
    return dict(sysinfo=dict(build="0.2"))


@app.context_processor
def inject_user():
    return dict(user=session['me']) if 'me' in session else None


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


def reddit_agent():
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


@app.route('/start')
def start_page():
    pass


@app.route('/about')
def about_page():
    return "Hello"


@app.route('/home')
def home():
    if 'me' not in session:
        return make_response(redirect(url_for('index')))
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
    questions = list(yaml.round_trip_load_all(questions_list))
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
            return make_response('Your account is too new')

    answers = {}
    vote = model.Vote.query.filter_by(userid=session['me']['id']).first()
    if vote is not None:
        answers = {a.code: a.answer_value for a in vote.answers}

    return render_template('home.html',
                           questions=questions,
                           answers=answers,
                           recaptcha_site_key=os.environ.get('RECAPTCHA_SITE_KEY'))


@app.route('/done', methods=('POST',))
def save():
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

        v = model.Vote.query.filter_by(userid=session['me']['id']).first()
        if v is None:
            v = model.Vote()
            v.userid = session['me']['id']
        v.datestamp = datetime.datetime.utcnow()
        model.db.session.add(v)
        # response = 'userid=' + session['me']['id'] + '\n'
        questions_sort = lambda x: int(x[0][2:]) if x[0][0:1] == 'q_' else '__' + x[0]
        for field, value in sorted(request.form.items(), key=questions_sort):
            if value is None or value == '':
                continue
            a = model.Answer.query.filter_by(code=field).first()
            if a is None:
                a = model.Answer()
                a.code = field
            a.answer_value = value
            a.vote = v
            model.db.session.add(a)
        model.db.session.commit()
    return Response("Thank you for voting", mimetype='text/plain')


def main():
    global first_run
    # app.session_interface = SqliteSessionInterface()
    first_run = True
    app.jinja_env.auto_reload = True
    app.run(port=5000, host='0.0.0.0', debug=True)


if __name__ == '__main__':
    main()

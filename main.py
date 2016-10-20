#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import collections
import datetime
import logging
import os
import urllib.parse

import praw
import yaml
from flask import Flask, render_template, make_response, request, redirect, url_for, session

# from SqliteSession import SqliteSessionInterface

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
logging.basicConfig(level=logging.DEBUG)


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


@app.route('/_dropdown/<table_name>', methods=('GET', 'POST'))
def dropdown(table_name):
    pass


def reddit_agent():
    r = praw.Reddit(user_agent='Questionnaire for Reddit by /u/gschizas version 0.1')
    r.config.decode_html_entities = True
    r.config.log_requests = 2

    client_id = os.getenv('REDDIT_OAUTH_CLIENT_ID')
    client_secret = os.getenv('REDDIT_OAUTH_CLIENT_SECRET')
    redirect_url = urllib.parse.urljoin(os.getenv('REDDIT_OAUTH_REDIRECT_URL'), url_for('authorize_callback'))
    r.set_oauth_app_info(client_id, client_secret, redirect_url)
    if 'access_info' in session:
        access_information = yaml.load(session['access_info'])
        if 'last_used' in session:
            last_used = session['last_used']
            minutes = (datetime.datetime.now() - last_used).total_seconds() / 60
        else:
            minutes = 365 * 24 * 60

        if minutes > 60:
            new_access_info = r.refresh_access_information(access_information['refresh_token'])
            session['access_info'] = yaml.dump(new_access_info)
        else:
            r.set_access_credentials(**access_information)
        session['me'] = get_me_serializable(r)
    return r


def get_me_serializable(r):
    me = r.get_me()
    me_serializable = dict(comment_karma=me.comment_karma, created=me.created, created_utc=me.created_utc,
                           gold_creddits=me.gold_creddits, gold_expiration=me.gold_expiration,
                           has_fetched=me.has_fetched,
                           has_verified_email=me.has_verified_email, hide_from_robots=me.hide_from_robots, id=me.id,
                           inbox_count=me.inbox_count, is_gold=me.is_gold, is_mod=me.is_mod, json_dict=me.json_dict,
                           link_karma=me.link_karma, name=me.name, over_18=me.over_18)
    return me_serializable


def make_authorize_url(r):
    scope = ['identity']
    authorize_url = r.get_authorize_url('RedditModHelper', scope, True)
    print(authorize_url)
    return authorize_url


@app.route('/authorize_callback')
def authorize_callback():
    state = request.args.get('state')
    code = request.args.get('code')
    r = reddit_agent()
    try:
        access_information = r.get_access_information(code)
    except praw.errors.OAuthInvalidGrant as ex:
        print(ex)
        return make_response(redirect(make_authorize_url(r)))
    session['access_info'] = yaml.dump(access_information)
    session['last_used'] = datetime.datetime.now()
    session['me'] = get_me_serializable(r)
    return make_response(redirect(url_for('home')))


@app.route('/')
def index():
    global first_run
    if first_run:
        session.clear()
        first_run = False
    if 'access_info' in session:
        return make_response(redirect(url_for('home')))
    else:
        r = reddit_agent()
        return make_response(redirect(make_authorize_url(r)))
        # return render_template('index.html')


@app.route('/home')
def home():
    with open('questionnaire.yml', 'r', encoding='utf8') as f:
        questions = list(yaml.load_all(f))
    for question_id, question in enumerate(questions):
        question['id'] = 1 + question_id
    return render_template('home.html', questions=questions)


def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))


def literal_str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data, style='|')
    else:
        return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data)


def main():
    global first_run
    # app.session_interface = SqliteSessionInterface()
    first_run = True
    yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dict_constructor)
    yaml.add_representer(collections.OrderedDict, dict_representer)
    yaml.add_representer(str, literal_str_representer)
    app.jinja_env.auto_reload = True
    app.run(port=5015, host='0.0.0.0', debug=True)


if __name__ == '__main__':
    main()
from datetime import timedelta, date

from wtforms import validators, HiddenField, TextField

from flask import request, jsonify
from flask_mako import render_template
from flask_security import roles_accepted, current_user, login_required
from sqlalchemy_fulltext import FullTextSearch
import sqlalchemy_fulltext.modes as FullTextMode

from dexter.app import app
from dexter.models import *  # noqa
from dexter.forms import Form, RadioField
from dexter.analysis import SourceAnalyser, MediaAnalyser
from dexter.utils import client_cache_for


@app.route('/mine/')
@login_required
@roles_accepted('monitor', 'miner')
@client_cache_for(minutes=10)
def mine_home():
    form = MineForm(request.args)

    ma = MediaAnalyser(doc_ids=form.document_ids(overview=True))
    ma.analyse()

    sa = SourceAnalyser(doc_ids=form.document_ids())
    sa.analyse()
    sa.load_utterances()

    return render_template('mine/index.haml',
                           form=form,
                           source_analyser=sa,
                           media_analyser=ma)


@app.route('/mine/people/<id>')
@login_required
@roles_accepted('monitor', 'miner')
@client_cache_for(minutes=10)
def mine_person(id):
    person = Person.query.get_or_404(id)
    form = MineForm(request.args)

    sa = SourceAnalyser(doc_ids=form.document_ids())
    sa.analyse()
    sa.load_utterances([person])

    source = sa.analysed_people.get(person.id)
    if not source:
        return jsonify({'row': '', 'utterances': ''})

    row = render_template('mine/_source.haml', i=-1, source=source)
    utterances = render_template("mine/_quotations.haml", i=-1, source=source, source_analyser=sa)

    return jsonify({
        'row': row,
        'utterances': utterances,
    })


@app.route('/mine/people/')
@login_required
@roles_accepted('monitor', 'miner')
@client_cache_for(minutes=10)
def mine_people():
    """ All the people that are in the documents covered by this span. """
    form = MineForm(request.args)

    sa = SourceAnalyser(doc_ids=form.document_ids())
    sa.load_people_sources()

    return jsonify({
        'people': [p.json() for p in sa.people.values()]
    })


class MineForm(Form):
    medium_id       = HiddenField('Medium', [validators.Optional()])
    # period to cover, expressed in days since yesterday
    period          = RadioField('Period', [validators.Optional()], choices=[('7', 'last 7 days'), ('30', 'last 30 days'), ('90', 'last 90 days')], default='7')
    source_person_id = TextField('With source', [validators.Optional()])
    # free text search
    q = TextField('Search', [validators.Optional()])

    nature_id = AnalysisNature.ANCHOR_ID

    def __init__(self, *args, **kwargs):
        super(MineForm, self).__init__(*args, **kwargs)
        self.country = current_user.country
        self.yesterday = date.today() - timedelta(days=1)

    @property
    def published_from(self):
        try:
            days = int(self.period.data)
        except ValueError:
            days = 7
        days = days

        return (self.yesterday - timedelta(days=days)).strftime('%Y-%m-%d 00:00:00')

    @property
    def published_to(self):
        return (self.yesterday - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')

    def document_ids(self, overview=False):
        return [d[0] for d in self.filter_query(db.session.query(Document.id), overview=overview).all()]

    @property
    def medium(self):
        if self.medium_id.data:
            return Medium.query.get(self.medium_id.data)

    def filter_query(self, query, overview=False):
        query = query.filter(
            Document.analysis_nature_id == self.nature_id,
            Document.country == self.country,
        )

        if not overview and self.medium:
            query = query.filter(Document.medium == self.medium)

        query = query.filter(
            Document.published_at >= self.published_from,
            Document.published_at <= self.published_to)

        if self.source_person_id.data:
            query = query\
                .join(DocumentSource)\
                .filter(DocumentSource.person_id == self.source_person_id.data)

        if self.q.data:
            # full text search
            query = query.filter(FullTextSearch(self.q.data, Document, FullTextMode.NATURAL))

        return query

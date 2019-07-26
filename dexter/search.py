from dexter.app import app
from flask import request, url_for, flash, redirect, make_response, jsonify, abort
from flask_mako import render_template
from flask_security import roles_accepted, current_user, login_required

from dexter.models import db, Person

@app.route('/search')
@login_required
@roles_accepted('monitor')
def search():
    q = request.args.get('q', '').strip()

    paged_people = None
    if q:
        paged_people = Person.query\
                .filter(Person.name.like('%' + q + '%'))\
                .order_by(Person.name)\
                .paginate(1, 50)


    return render_template('search/index.haml',
                           q=q,
                           paged_people=paged_people)

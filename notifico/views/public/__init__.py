import time
import datetime

from flask import (
    Blueprint,
    render_template,
    g,
    request,
    redirect,
    url_for
)
from flask.ext.sqlalchemy import Pagination
from sqlalchemy import func, extract

from notifico.models import User, Channel, Project
from notifico.services.hooks import HookService

public = Blueprint('public', __name__, template_folder='templates')


@public.route('/')
def landing():
    """
    Show a landing page giving a short intro blurb to unregistered users
    and very basic metrics such as total users.
    """
    # Create a list of total project counts in the form
    # [(day, count), ...].
    projects_graph_data = []
    now = datetime.datetime.utcnow()
    for day_ago in range(30):
        limit = now - datetime.timedelta(days=day_ago)

        projects_graph_data.append((
            time.mktime(limit.timetuple()) * 1000,
            Project.query.filter(Project.created <= limit).count()
        ))

    # Find the 10 latest public projects.
    new_projects = (
        Project.visible(Project.query, user=g.user)
        .order_by(False)
        .order_by(Project.created.desc())
    ).paginate(1, 10, False)

    # Sum the total number of messages across all projects, caching
    # it for the next two minutes.
    total_messages = g.redis.get('cache_message_count')
    if total_messages is None:
        total_messages = g.db.session.query(
            func.sum(Project.message_count)
        ).scalar()
        if total_messages is None:
            total_messages = 0

        g.redis.setex('cache_message_count', 120, total_messages)

    # Total # of users.
    total_users = User.query.count()

    # Find the 10 most popular networks.
    top_networks = (
        Channel.visible(g.db.session.query(
            Channel.host,
            func.count(func.distinct(Channel.channel)).label('count')
        ), user=g.user)
        .group_by(Channel.host)
        .order_by('count desc')
    )
    total_networks = top_networks.count()
    top_networks = top_networks.limit(10)

    return render_template(
        'landing.html',
        projects_graph_data=projects_graph_data,
        new_projects=new_projects,
        top_networks=top_networks,
        total_networks=total_networks,
        total_messages=total_messages,
        total_users=total_users
    )


@public.route('/s/networks/')
def networks():
    per_page = min(int(request.args.get('l', 25)), 100)
    page = max(int(request.args.get('page', 1)), 1)

    q = (
        Channel.visible(g.db.session.query(
            Channel.host,
            func.count(func.distinct(Channel.channel)).label('di_count'),
            func.count(Channel.channel).label('count')
        ), user=g.user)
        .group_by(Channel.host)
        .order_by('di_count desc')
    )
    total = q.count()
    items = q.limit(per_page).offset((page - 1) * per_page).all()
    pagination = Pagination(q, page, per_page, total, items)

    return render_template('networks.html',
        pagination=pagination,
        per_page=per_page
    )


@public.route('/s/networks/<network>/')
def network(network):
    per_page = min(int(request.args.get('l', 25)), 100)
    page = max(int(request.args.get('page', 1)), 1)

    q = Channel.visible(
        Channel.query.filter(Channel.host == network),
        user=g.user
    ).order_by(Channel.created.desc())

    pagination = q.paginate(page, per_page, False)

    return render_template('channels.html',
        per_page=per_page,
        network=network,
        pagination=pagination
    )


@public.route('/s/projects', defaults={'page': 1})
@public.route('/s/projects/<int:page>')
def projects(page=1):
    per_page = min(int(request.args.get('l', 25)), 100)
    sort_by = request.args.get('s', 'created')

    q = Project.visible(Project.query, user=g.user).order_by(False)
    q = q.order_by({
        'created': Project.created.desc(),
        'messages': Project.message_count.desc()
    }.get(sort_by, Project.created.desc()))

    pagination = q.paginate(page, per_page, False)

    return render_template('projects.html',
        pagination=pagination,
        per_page=per_page
    )


@public.route('/s/users', defaults={'page': 1})
@public.route('/s/users/<int:page>')
def users(page=1):
    per_page = min(int(request.args.get('l', 25)), 100)
    sort_by = request.args.get('s', 'created')

    q = User.query.order_by(False)
    q = q.order_by({
        'created': User.joined.desc()
    }.get(sort_by, User.joined.desc()))

    pagination = q.paginate(page, per_page, False)

    return render_template('users.html',
        pagination=pagination,
        per_page=per_page
    )


@public.route('/s/services')
def services():
    services = HookService.services
    return render_template('services.html',
        services=services
    )

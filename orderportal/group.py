"OrderPortal: Group pages."

from __future__ import print_function, absolute_import

import logging

import tornado.web

import orderportal
from orderportal import constants
from orderportal import saver
from orderportal import settings
from orderportal import utils
from orderportal.requesthandler import RequestHandler


class GroupSaver(saver.Saver):
    doctype = constants.GROUP


class Groups(RequestHandler):
    "Page for a list of all groups."

    @tornado.web.authenticated
    def get(self):
        self.check_staff()
        page = self.get_page(view=self.db.view('group/modified'))
        view = self.db.view('group/modified',
                            descending=True,
                            skip=page['start'],
                            limit=page['size'],
                            reduce=False,
                            include_docs=True)
        groups = [r.doc for r in view]
        self.render('groups.html',
                    groups=groups,
                    params=dict(),
                    page=page)


class GroupMixin(object):

    def check_readable(self, group):
        "Check if current user may read the group."
        if self.is_owner(group): return
        if self.current_user['email'] in group['members']: return
        if self.is_staff(): return
        raise tornado.web.HTTPError(403, reason='you may not read the group')

    def is_editable(self, group):
        "Is the group editable by the current user?"
        if self.is_admin(): return True
        if self.is_owner(group): return True
        return False

    def check_editable(self, group):
        "Check if current user may edit the group."
        if not self.is_editable(group):
            raise tornado.web.HTTPError(403,reason='you may not edit the group')


class Group(GroupMixin, RequestHandler):
    "Group page."

    @tornado.web.authenticated
    def get(self, iuid):
        group = self.get_entity(iuid, doctype=constants.GROUP)
        self.check_readable(group)
        self.render('group.html',
                    group=group,
                    is_editable=self.is_editable(group))

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        if self.get_argument('_http_method', None) == 'delete':
            self.delete(iuid)
            return
        raise tornado.web.HTTPError(405, reason='POST only allowed for DELETE')

    @tornado.web.authenticated
    def delete(self, iuid):
        group = self.get_entity(iuid, doctype=constants.GROUP)
        self.check_editable(group)
        self.delete_logs(group['_id'])
        self.db.delete(group)
        self.see_other('account', self.current_user['email'])


class GroupCreate(RequestHandler):
    "Create group page."

    @tornado.web.authenticated
    def get(self):
        self.render('group_create.html')

    @tornado.web.authenticated
    def post(self):
        with GroupSaver(rqh=self) as saver:
            saver['name'] = self.get_argument('name', '') or '[no name]'
            saver['owner'] = self.current_user['email']
            invited = set()
            value = self.get_argument('invited', '').replace(',', ' ').strip()
            for email in value.split():
                email = email.lower()
                try:
                    self.get_account(email)
                except tornado.web.HTTPError:
                    pass
                else:
                    invited.add(email)
            saver['invited'] = sorted(invited)
            saver['members'] = [self.current_user['email']]
        self.see_other('group', saver.doc['_id'])


class GroupEdit(GroupMixin, RequestHandler):
    "Edit group page."

    @tornado.web.authenticated
    def get(self, iuid):
        group = self.get_entity(iuid, doctype=constants.GROUP)
        self.check_editable(group)
        self.render('group_edit.html', group=group)

    @tornado.web.authenticated
    def post(self, iuid):
        group = self.get_entity(iuid, doctype=constants.GROUP)
        self.check_editable(group)
        with GroupSaver(doc=group, rqh=self) as saver:
            old_members = set(group['members'])
            old_invited = set(group['invited'])
            saver['name'] = self.get_argument('name', '') or '[no name]'
            owner = self.get_account(self.get_argument('owner'))
            if owner['email'] not in old_members:
                raise ValueError('new owner not among current members')
            saver['owner'] = owner['email']
            members = set()
            invited = set()
            value = self.get_argument('members', '').replace(',', ' ').strip()
            for email in value.split():
                email = email.lower()
                try:
                    self.get_account(email)
                except tornado.web.HTTPError:
                    pass
                if email in old_members:
                    members.add(email)
                else:
                    invited.add(email)
                if email in old_invited:
                    invited.add(email)
            members.add(owner['email'])
            saver['members'] = sorted(members)
            saver['invited'] = sorted(invited)
        self.see_other('group', saver.doc['_id'])


class GroupLogs(GroupMixin, RequestHandler):
    "Group log entries page."

    @tornado.web.authenticated
    def get(self, iuid):
        group = self.get_entity(iuid, doctype=constants.GROUP)
        self.check_readable(group)
        self.render('logs.html',
                    title="Logs for group '{0}'".format(group['name']),
                    entity=group,
                    logs=self.get_logs(group['_id']))


class GroupAccept(RequestHandler):
    "Accept group invitation. Only the user himself can do this."

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        group = self.get_entity(iuid, doctype=constants.GROUP)
        with GroupSaver(doc=group, rqh=self) as saver:
            invited = set(group['invited'])
            try:
                invited.remove(self.current_user['email'])
            except KeyError:
                raise tornado.web.HTTPError(403,reason='you are not invited')
            members = set(group['members'])
            members.add(self.current_user['email'])
            saver['invited'] = sorted(invited)
            saver['members'] = sorted(members)
        self.see_other('account', self.current_user['email'])


class GroupDecline(RequestHandler):
    "Decline group invitation or membership. Only the user himself can do this."

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        group = self.get_entity(iuid, doctype=constants.GROUP)
        with GroupSaver(doc=group, rqh=self) as saver:
            invited = set(group['invited'])
            invited.discard(self.current_user['email'])
            saver['invited'] = sorted(invited)
            if self.current_user['email'] != group['owner']:
                members = set(group['members'])
                members.discard(self.current_user['email'])
                saver['members'] = sorted(members)
        self.see_other('account', self.current_user['email'])

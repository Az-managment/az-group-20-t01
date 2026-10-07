import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

PALETTE = ['#3b82f6', '#14b8a6', '#f97316', '#8b5cf6', '#06b6d4', '#f59e0b',
           '#fb7185', '#a78bfa', '#22c55e', '#94a3b8']

ACTIVITY_MODELS = {
    'res.company': 'business',
    'hr.employee': 'person',
    'hr.department': 'account_tree',
    'project.project': 'rocket_launch',
    'project.task': 'task',
    'documents.document': 'description',
}


class AzmDashboard(models.AbstractModel):
    """Read-only services for the AZM screens.

    Nothing is stored here: every figure is read from res.company, HR,
    Project and Documents (or attachments when Documents is not installed).
    """
    _name = 'azm.dashboard'
    _description = 'AZM Dashboard Services'

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @api.model
    def _env_all_companies(self):
        # The AZM screens follow the company switcher, exactly like every other Odoo
        # screen: figures, lists and buttons always show the same scope.
        return self.env

    @api.model
    def _companies(self):
        return self.env['res.company'].search([('id', 'in', self.env.companies.ids)], order='sequence, id')

    @api.model
    def _has(self, model):
        return model in self.env

    @api.model
    def _selection_label(self, model, field_name, value):
        field = self.env[model]._fields[field_name]
        return dict(field._description_selection(self.env)).get(value, value or '')

    @api.model
    def _employees_by_department(self, company_ids):
        env = self._env_all_companies()
        if not self._has('hr.employee') or not env['hr.employee'].has_access('read'):
            return []
        groups = env['hr.employee']._read_group(
            [('company_id', 'in', company_ids)], ['department_id'], ['__count'])
        # Departments with the same name in several companies are merged for the group view
        by_name = {}
        for department, count in groups:
            key = department.name if department else False
            by_name[key] = by_name.get(key, 0) + count
        ranked = sorted(((k, v) for k, v in by_name.items() if k), key=lambda kv: -kv[1])
        result = [{'id': name, 'name': name, 'color': PALETTE[i % (len(PALETTE) - 1)], 'count': count}
                  for i, (name, count) in enumerate(ranked[:8])]
        other = sum(v for _k, v in ranked[8:]) + by_name.get(False, 0)
        if other:
            result.append({'id': 'other', 'name': _('Other'), 'color': PALETTE[-1], 'count': other})
        return result

    @api.model
    def _recent_activities(self, company_ids, limit=6):
        env = self._env_all_companies()
        parts = [Domain([('model', '=', 'res.company'), ('res_id', 'in', company_ids)])]
        for model in ACTIVITY_MODELS:
            if model == 'res.company' or model not in env or not env[model].has_access('read'):
                continue
            Model = env[model]
            if 'company_id' not in Model._fields:
                continue
            ids = Model.search([('company_id', 'in', company_ids)], order='write_date desc', limit=200).ids
            if ids:
                parts.append(Domain([('model', '=', model), ('res_id', 'in', ids)]))
        domain = Domain([('message_type', '!=', 'user_notification')]) & Domain.OR(parts)
        result = []
        for message in env['mail.message'].search(domain, limit=limit, order='date desc, id desc'):
            text = (message.preview or html2plaintext(message.body or '')).strip()
            if not text and message.tracking_value_ids:
                text = _('%s updated', message.tracking_value_ids[0].field_id.field_description)
            if not text:
                text = message.subtype_id.name or _('Updated')
            result.append({
                'id': message.id,
                'text': text[:120],
                'record': message.record_name or '',
                'model': message.model,
                'res_id': message.res_id,
                'date': fields.Datetime.to_string(message.date),
                'icon': ACTIVITY_MODELS.get(message.model, 'history'),
            })
        return result

    @api.model
    def _documents(self, company_ids, limit=6):
        env = self._env_all_companies()
        if 'documents.document' in env:
            if not env['documents.document'].has_access('read'):
                return []
            docs = env['documents.document'].search(
                [('company_id', 'in', company_ids), ('type', '!=', 'folder')], limit=limit,
                order='write_date desc')
            return [{'id': d.id, 'model': 'documents.document', 'name': d.name,
                     'type': d.mimetype or '', 'has_file': True} for d in docs]
        docs = env['ir.attachment'].search(
            [('company_id', 'in', company_ids), ('res_model', '!=', False), ('res_field', '=', False),
             ('res_model', 'not in', ('ir.ui.view', 'ir.module.module', 'res.company'))],
            limit=limit, order='create_date desc')
        return [{'id': d.id, 'model': 'ir.attachment', 'name': d.name,
                 'type': d.mimetype or '', 'has_file': True} for d in docs]

    @api.model
    def _company_row(self, company):
        return {
            'id': company.id,
            'name': company.name,
            'name_alt': company.azm_name_alt or '',
            'code': ''.join(w[0] for w in (company.name or '?').split()[:3]).upper(),
            'has_logo': bool(company.logo) and not company.uses_default_logo,
            'unique': fields.Datetime.to_string(company.write_date),
            'status': company.azm_status,
            'status_label': self._selection_label('res.company', 'azm_status', company.azm_status),
            'type_label': self._selection_label('res.company', 'azm_entity_type', company.azm_entity_type),
            'employees': company.azm_employee_count,
            'departments': company.azm_department_count,
            'projects': company.azm_project_count,
            'tasks': company.azm_task_count,
            'open_tasks': company.azm_open_task_count,
            'documents': company.azm_document_count,
            'has_data': company.azm_has_data,
            'progress': company.azm_progress,
        }

    # ------------------------------------------------------------------
    # Home dashboard
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self):
        env = self._env_all_companies()
        companies = self._companies()
        company_ids = companies.ids
        rows = [self._company_row(c) for c in companies]
        with_data = [r for r in rows if r['has_data']]
        completion = round(sum(r['progress'] for r in with_data) / len(with_data), 1) if with_data else None
        Task = env['project.task']
        open_tasks_domain = [('company_id', 'in', company_ids), ('project_id', '!=', False),
                             ('is_closed', '=', False)]
        overdue = Task.search_count(open_tasks_domain + [('date_deadline', '<', fields.Datetime.now())]) \
            if Task.has_access('read') else 0

        # My tasks (project tasks assigned to me + planned activities)
        tasks = []
        my_tasks = Task.search([('user_ids', 'in', self.env.uid), ('is_closed', '=', False),
                                ('project_id', '!=', False)], limit=10,
                               order='priority desc, date_deadline asc, id desc') if Task.has_access('read') else Task
        for task in my_tasks:
            tasks.append({
                'id': task.id, 'model': 'project.task', 'name': task.name,
                'entity': task.project_id.display_name,
                'priority': 'high' if task.priority in ('2', '3') else ('medium' if task.priority == '1' else 'low'),
                'overdue': bool(task.date_deadline and task.date_deadline < fields.Datetime.now()),
                'deadline': fields.Date.to_string(task.date_deadline.date()) if task.date_deadline else False,
            })
        for activity in env['mail.activity'].search([('user_id', '=', self.env.uid)], limit=6,
                                                    order='date_deadline asc'):
            tasks.append({
                'id': activity.res_id, 'model': activity.res_model,
                'name': activity.summary or activity.activity_type_id.name,
                'entity': activity.res_name, 'priority': 'medium',
                'overdue': activity.date_deadline < fields.Date.context_today(self),
                'deadline': fields.Date.to_string(activity.date_deadline),
            })

        kpis = {
            'entities': len(companies),
            'employees': sum(r['employees'] for r in rows),
            'departments': sum(r['departments'] for r in rows),
            'projects': sum(r['projects'] for r in rows),
            'open_tasks': sum(r['open_tasks'] for r in rows),
            'overdue_tasks': overdue,
            'documents': sum(r['documents'] for r in rows),
            'completion': completion,
            'active': len([r for r in rows if r['status'] == 'active']),
        }
        return {
            'kpis': kpis,
            'entities': rows[:8],
            'departments': self._employees_by_department(company_ids),
            'tasks': tasks,
            'activities': self._recent_activities(company_ids),
            'documents_model': 'documents.document' if 'documents.document' in env else 'ir.attachment',
        }

    @api.model
    def get_entity_stats(self):
        companies = self._companies()
        rows = [self._company_row(c) for c in companies]
        with_data = [r for r in rows if r['has_data']]
        types = sorted({r['type_label'] for r in rows if r['type_label']})
        return {
            'total': len(rows),
            'active': len([r for r in rows if r['status'] == 'active']),
            'in_progress': len([r for r in rows if r['status'] == 'in_progress']),
            'not_started': len([r for r in rows if r['status'] == 'not_started']),
            'employees': sum(r['employees'] for r in rows),
            'types': types,
            'progress': round(sum(r['progress'] for r in with_data) / len(with_data), 1) if with_data else None,
        }

    # ------------------------------------------------------------------
    # Entity (company) page
    # ------------------------------------------------------------------
    @api.model
    def get_company_overview(self, company_id):
        env = self._env_all_companies()
        company = env['res.company'].browse(company_id).exists()
        if not company or company.id not in self.env.companies.ids:
            return {}
        teams = []
        if 'hr.department' in env and env['hr.department'].has_access('read'):
            for department in env['hr.department'].search([('company_id', '=', company.id)], limit=6):
                teams.append({
                    'id': department.id,
                    'name': department.name,
                    'description': department.manager_id.name or '',
                    'members': department.total_employee,
                })
        projects = []
        project_records = env['project.project']
        if project_records.has_access('read'):
            project_records = project_records.search([('company_id', '=', company.id)], limit=6,
                                                     order='sequence, id')
        # two grouped counts for the whole set, not two searches per project
        totals, opens = {}, {}
        if project_records:
            Task = env['project.task']
            for project, count in Task._read_group(
                    [('project_id', 'in', project_records.ids)], ['project_id'], ['__count']):
                totals[project.id] = count
            for project, count in Task._read_group(
                    [('project_id', 'in', project_records.ids), ('is_closed', '=', False)],
                    ['project_id'], ['__count']):
                opens[project.id] = count
        for project in project_records:
            total = totals.get(project.id, 0)
            opened = opens.get(project.id, 0)
            projects.append({
                'id': project.id,
                'name': project.name,
                'manager': project.user_id.name or '',
                'tasks': total,
                'progress': round(100.0 * (total - opened) / total) if total else 0,
            })
        return {
            'departments': self._employees_by_department([company.id]),
            'documents': self._documents([company.id]),
            'teams': teams,
            'projects': projects,
            'activities': self._recent_activities([company.id], limit=5),
            'documents_model': 'documents.document' if 'documents.document' in env else 'ir.attachment',
        }

    # ------------------------------------------------------------------
    # Documents action (Documents app when installed, attachments otherwise)
    # ------------------------------------------------------------------
    @api.model
    def action_open_documents(self, company_id=None):
        ctx = {}
        if 'documents.document' in self.env:
            action = self.env['ir.actions.act_window']._for_xml_id('documents.document_action')
            if company_id:
                action['domain'] = [('company_id', '=', company_id)]
            action['context'] = ctx
            return action
        domain = [('res_model', '!=', False), ('res_field', '=', False),
                  ('res_model', 'not in', ('ir.ui.view', 'ir.module.module', 'res.company'))]
        if company_id:
            domain.append(('company_id', '=', company_id))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documents'),
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,list,form',
            'domain': domain,
            'context': ctx,
        }

    # ------------------------------------------------------------------
    # AI assistant
    # ------------------------------------------------------------------
    @api.model
    def ai_ask(self, question):
        # the key is the group's and the call is billed to it, so the question has to
        # come from someone the platform is for, and be of a size it is worth answering
        if not self.env.user.has_group('azm_platform.group_azm_user'):
            raise AccessError(_("The assistant is available to AZM users."))
        question = (question or '')[:2000]
        """Answer a question about the group with an LLM, grounded on live Odoo figures."""
        question = (question or '').strip()
        if not question:
            return {'ok': False, 'answer': _('Please type a question first.')}
        params = self.env['ir.config_parameter'].sudo()
        api_key = params.get_str('azm_platform.ai_api_key')
        if not api_key:
            return {'ok': False, 'answer': _(
                'The AI assistant is not configured yet. An administrator can add an '
                'Anthropic API key in Settings > AZM Platform.')}
        model = params.get_str('azm_platform.ai_model') or 'claude-sonnet-4-5'
        lines = []
        for company in self._companies():
            row = self._company_row(company)
            lines.append('- %(name)s: status=%(status)s, employees=%(employees)s, departments=%(departments)s, '
                         'projects=%(projects)s, open tasks=%(open_tasks)s/%(tasks)s, documents=%(documents)s, '
                         'progress=%(progress)s%%' % row)
        system = (
            'You are the AZM assistant inside the AZM Enterprise Operating Model Platform (built on Odoo). '
            'You help the group build a unified, governed operating model across its companies. '
            'Answer concisely, in the language of the question (Arabic or English). '
            'Live data from Odoo:\n' + '\n'.join(lines))
        try:
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01',
                         'content-type': 'application/json'},
                json={'model': model, 'max_tokens': 1024, 'system': system,
                      'messages': [{'role': 'user', 'content': question}]},
                timeout=60,
            )
            response.raise_for_status()
            content = response.json().get('content', [])
            answer = '\n'.join(b.get('text', '') for b in content if b.get('type') == 'text')
            return {'ok': True, 'answer': answer.strip()}
        except Exception as error:  # noqa: BLE001
            _logger.warning('AZM assistant call failed: %s', error)
            return {'ok': False, 'answer': _('The assistant could not answer right now (%s).', error)}

    @api.model
    def azm_rights(self):
        """What this reader may actually open, asked as access rather than membership.

        The screens used to decide by group — "is this user in project's user group" —
        and hide or deaden a link when the answer was no. That is the wrong question:
        access to a model comes from whatever groups and rules a deployment happens to
        use, and a reader who reaches Projects from the sidebar every day was being
        told by the same product that they could not. It asks the model instead.
        """
        def can(model):
            return model in self.env and self.env[model].has_access("read")

        return {
            "hr": can("hr.employee"),
            "project": can("project.project"),
            "tasks": can("project.task"),
            "documents": True,
            # these two are about changing configuration, where the group is the point
            "editCompany": self.env.user.has_group("base.group_erp_manager"),
            "settings": self.env.user.has_group("base.group_system"),
        }

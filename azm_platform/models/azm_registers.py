from odoo import api, fields, models

from odoo.addons.azm_operating_model.models.azm_assessment import PURCHASE_KINDS, SCENARIOS

OPEN_FINDING_STATES = ('candidate', 'confirmed', 'treatment')


class AzmDashboard(models.AbstractModel):
    _inherit = 'azm.dashboard'

    @api.model
    def _registers_env(self):
        env = self._env_all_companies()
        can_proc = 'azm.assessment' in env and env['azm.assessment'].has_access('read')
        can_fin = 'azm.fin.assessment' in env and env['azm.fin.assessment'].has_access('read')
        entities = env['azm.entity'].search(['|', ('company_id', '=', False), ('company_id', 'in', env.companies.ids)]) \
            if (can_proc or can_fin) else env['azm.entity']
        return env, can_proc, can_fin, entities

    @staticmethod
    def _date(value):
        return fields.Datetime.to_string(value) if value else False

    # ------------------------------------------------------------------
    # Assessments of every operating model in one list
    # ------------------------------------------------------------------
    @api.model
    def get_unified_assessments(self, include_archived=False):
        env, can_proc, can_fin, entities = self._registers_env()
        rows = []
        domain = [('entity_id', 'in', entities.ids)]
        if not include_archived:
            domain.append(('state', '!=', 'archived'))
        if can_proc:
            kinds, scenarios = dict(PURCHASE_KINDS), dict(SCENARIOS)
            labels = dict(env['azm.assessment']._fields['state']._description_selection(env))
            for a in env['azm.assessment'].search(domain):
                rows.append({
                    'model': 'procurement', 'res_model': 'azm.assessment', 'id': a.id, 'name': a.name,
                    'entity': a.entity_id.name, 'entity_id': a.entity_id.id,
                    'detail': f"{kinds.get(a.purchase_kind, '')} · {scenarios.get(a.scenario, '')}",
                    'state': a.state, 'state_label': labels.get(a.state, a.state), 'version': a.version,
                    'progress': round(a.progress), 'issues': a.risk_count, 'is_demo': a.is_demo,
                    'user': a.user_id.name or '', 'reviewer': a.reviewer_id.name or '',
                    'updated': self._date(a.write_date),
                })
        if can_fin:
            labels = dict(env['azm.fin.assessment']._fields['state']._description_selection(env))
            for a in env['azm.fin.assessment'].search(domain):
                rows.append({
                    'model': 'financial', 'res_model': 'azm.fin.assessment', 'id': a.id, 'name': a.name,
                    'entity': a.entity_id.name, 'entity_id': a.entity_id.id,
                    'detail': '، '.join(a.scope_ids.mapped('name')),
                    'state': a.state, 'state_label': labels.get(a.state, a.state), 'version': a.version,
                    'progress': round(a.progress), 'issues': a.gap_count, 'is_demo': a.is_demo,
                    'user': a.user_id.name or '', 'reviewer': a.reviewer_id.name or '',
                    'updated': self._date(a.write_date),
                })
        rows.sort(key=lambda r: r['updated'] or '', reverse=True)
        return {
            'available': can_proc or can_fin,
            'models': {'procurement': can_proc, 'financial': can_fin},
            'rows': rows,
            'entities': [{'id': e.id, 'name': e.name} for e in entities],
        }

    # ------------------------------------------------------------------
    # Risk register: procurement findings + financial gaps
    # ------------------------------------------------------------------
    @api.model
    def get_unified_register(self, include_closed=False):
        env, can_proc, can_fin, entities = self._registers_env()
        rows = []
        if can_proc:
            Finding = env['azm.finding']
            labels = dict(Finding._fields['state']._description_selection(env))
            domain = [('entity_id', 'in', entities.ids), ('assessment_id.state', '!=', 'archived')]
            if not include_closed:
                domain += [('state', 'in', OPEN_FINDING_STATES), ('triggered', '=', True)]
            for f in Finding.search(domain):
                rows.append({
                    'model': 'procurement', 'res_model': 'azm.finding', 'id': f.id, 'code': f.code,
                    'title': f.fact, 'detail': f.risk or '', 'action': f.control or '',
                    'area': f.stage_id.name, 'area_code': f.stage_id.code,
                    'entity': f.entity_id.name, 'entity_id': f.entity_id.id,
                    'assessment': f.assessment_id.name, 'assessment_id': f.assessment_id.id,
                    'state': f.state, 'state_label': labels.get(f.state, f.state),
                    'score': f.score, 'owner': f.user_id.name or f.owner_hint or '',
                    'due': fields.Date.to_string(f.due_date) if f.due_date else False,
                })
        if can_fin:
            Answer = env['azm.fin.answer']
            labels = dict(Answer._fields['state']._description_selection(env))
            states = ('partial', 'unavailable', 'na') if include_closed else ('partial', 'unavailable')
            domain = [('entity_id', 'in', entities.ids), ('applicable', '=', True), ('state', 'in', states),
                      ('assessment_id.state', '!=', 'archived')]
            for a in Answer.search(domain):
                text = a.gap if a.state == 'partial' else (a.future if a.state == 'unavailable' else a.reason)
                rows.append({
                    'model': 'financial', 'res_model': 'azm.fin.answer', 'id': a.id, 'code': a.code,
                    'title': a.requirement_id.title, 'detail': text or '',
                    'action': a.current or '',
                    'area': a.module_id.name, 'area_code': a.module_id.code,
                    'entity': a.entity_id.name, 'entity_id': a.entity_id.id,
                    'assessment': a.assessment_id.name, 'assessment_id': a.assessment_id.id,
                    'state': a.state, 'state_label': labels.get(a.state, a.state),
                    'score': False, 'owner': a.assessment_id.user_id.name or '', 'due': False,
                })
        return {
            'available': can_proc or can_fin,
            'models': {'procurement': can_proc, 'financial': can_fin},
            'rows': rows,
            'entities': [{'id': e.id, 'name': e.name} for e in entities],
        }

from odoo import _, api, fields, models

ENTITY_TYPES = [
    ('university', 'University'),
    ('school', 'School'),
    ('faculty', 'Faculty'),
    ('institute', 'Institute'),
    ('company', 'Company'),
    ('holding', 'Holding Company'),
    ('office', 'Private Office'),
    ('residence', 'Residence'),
    ('other', 'Other'),
]

SECTORS = [
    ('higher_education', 'Higher Education'),
    ('k12', 'K-12 Education'),
    ('training', 'Training & Languages'),
    ('contracting', 'Contracting'),
    ('facilities', 'Facilities Management'),
    ('tourism', 'Tourism & Hospitality'),
    ('investment', 'Investment'),
    ('real_estate', 'Real Estate'),
    ('other', 'Other'),
]

STATUSES = [
    ('not_started', 'Not Started'),
    ('in_progress', 'In Preparation'),
    ('active', 'Active'),
]


class ResCompany(models.Model):
    """Each Odoo company is an AZM entity. Only presentation fields are added;
    every figure is computed live from HR, Project and Documents/Attachments."""
    _inherit = 'res.company'

    # Optional presentation fields (nothing is required)
    azm_name_alt = fields.Char('Name (other language)',
                               help='Shown under the company name, e.g. the Arabic or English name.')
    azm_entity_type = fields.Selection(ENTITY_TYPES, 'Entity Type', default='company')
    azm_sector = fields.Selection(SECTORS, 'Sector')
    azm_cover_image = fields.Image('Cover Image', max_width=1920, max_height=1080)
    azm_tagline = fields.Char('Tagline')
    azm_tagline_alt = fields.Char('Tagline (other language)')
    azm_description = fields.Text('Short Description')
    azm_show_on_login = fields.Boolean('Show on Login Page', default=True)

    # Live indicators (not stored: always read from the source apps)
    azm_employee_count = fields.Integer('Employees', compute='_compute_azm_indicators')
    azm_department_count = fields.Integer('Departments', compute='_compute_azm_indicators')
    azm_project_count = fields.Integer('Projects', compute='_compute_azm_indicators')
    azm_task_count = fields.Integer('Tasks', compute='_compute_azm_indicators')
    azm_open_task_count = fields.Integer('Open Tasks', compute='_compute_azm_indicators')
    azm_document_count = fields.Integer('Documents', compute='_compute_azm_indicators')
    azm_progress = fields.Float('Progress', compute='_compute_azm_indicators',
                                help='Share of closed tasks in the projects of this company.')
    azm_has_data = fields.Boolean(compute='_compute_azm_indicators')
    azm_status = fields.Selection(STATUSES, 'Platform Status', compute='_compute_azm_indicators')

    # Parent / children limited to the companies the current user may open, so the
    # Group Structure never points to a company the user has no access to.
    azm_parent_id = fields.Many2one('res.company', 'Parent Entity', compute='_compute_azm_parent_id',
                                    search='_search_azm_parent_id')
    azm_child_ids = fields.One2many('res.company', string='Child Entities', compute='_compute_azm_child_ids')

    def _azm_visible_parent_map(self):
        """{company_id: nearest ancestor the user can access (or False)} for the user's companies."""
        allowed = set(self.env.companies.ids)
        result = {}
        for company in self.env.companies.sudo():
            parent = company.parent_id
            while parent and parent.id not in allowed:
                parent = parent.parent_id
            result[company.id] = parent.id or False
        return result

    def _compute_azm_parent_id(self):
        parents = self._azm_visible_parent_map()
        for company in self:
            company.azm_parent_id = parents.get(company.id, False)

    def _compute_azm_child_ids(self):
        parents = self._azm_visible_parent_map()
        for company in self:
            company.azm_child_ids = self.browse([c for c, p in parents.items() if p == company.id])

    def _search_azm_parent_id(self, operator, value):
        parents = self._azm_visible_parent_map()
        if operator in ('=', '!='):
            value = [value]
        elif operator not in ('in', 'not in'):
            return NotImplemented
        targets = {v or False for v in value}
        ids = [c for c, p in parents.items() if p in targets]
        return [('id', 'in' if operator in ('=', 'in') else 'not in', ids)]

    def _azm_env(self):
        """Environment of the counts: the companies selected in the company switcher."""
        return self.env  # follows the company switcher

    def _azm_count_by_company(self, model, domain=None):
        env = self._azm_env()
        if model not in env:
            return {}
        # Counts respect the access rights and record rules of the current user:
        # every person only counts the records they are allowed to open.
        Model = env[model]
        if 'company_id' not in Model._fields or not Model.has_access('read'):
            return {}
        groups = Model._read_group(
            [('company_id', 'in', self.ids)] + (domain or []), ['company_id'], ['__count'])
        return {company.id: count for company, count in groups}

    def _azm_document_counts(self):
        env = self._azm_env()
        if 'documents.document' in env:
            return self._azm_count_by_company('documents.document', [('type', '!=', 'folder')])
        if not env['ir.attachment'].has_access('read'):
            return {}
        groups = env['ir.attachment']._read_group(
            [('company_id', 'in', self.ids), ('res_model', '!=', False), ('res_field', '=', False),
             ('res_model', 'not in', ('ir.ui.view', 'ir.module.module', 'res.company'))],
            ['company_id'], ['__count'])
        return {company.id: count for company, count in groups}

    def _compute_azm_indicators(self):
        employees = self._azm_count_by_company('hr.employee')
        departments = self._azm_count_by_company('hr.department')
        projects = self._azm_count_by_company('project.project')
        tasks = self._azm_count_by_company('project.task', [('project_id', '!=', False)])
        open_tasks = self._azm_count_by_company(
            'project.task', [('project_id', '!=', False), ('is_closed', '=', False)])
        documents = self._azm_document_counts()
        for company in self:
            total = tasks.get(company.id, 0)
            opened = open_tasks.get(company.id, 0)
            company.azm_employee_count = employees.get(company.id, 0)
            company.azm_department_count = departments.get(company.id, 0)
            company.azm_project_count = projects.get(company.id, 0)
            company.azm_task_count = total
            company.azm_open_task_count = opened
            company.azm_document_count = documents.get(company.id, 0)
            company.azm_progress = round(100.0 * (total - opened) / total, 1) if total else 0.0
            company.azm_has_data = bool(total)
            filled = sum(bool(x) for x in (company.azm_employee_count, company.azm_department_count,
                                           company.azm_project_count))
            company.azm_status = 'active' if filled == 3 else ('in_progress' if filled else 'not_started')

    # ------------------------------------------------------------------
    # Navigation to the source apps (filtered on this company)
    # ------------------------------------------------------------------
    def _azm_action(self, xmlid, name, domain, context=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        ctx = dict(context or {})
        action.update({
            'name': '%s – %s' % (name, self.name),
            'domain': domain,
            'context': ctx,
        })
        return action

    def action_azm_employees(self):
        return self._azm_action('hr.open_view_employee_list_my', _('Employees'),
                                [('company_id', '=', self.id)])

    def action_azm_departments(self):
        return self._azm_action('hr.hr_department_kanban_action', _('Departments'),
                                [('company_id', '=', self.id)])

    def action_azm_projects(self):
        return self._azm_action('project.open_view_project_all', _('Projects'),
                                [('company_id', '=', self.id)])

    def action_azm_tasks(self):
        return self._azm_action('project.action_view_all_task', _('Open Tasks'),
                                [('company_id', '=', self.id), ('project_id', '!=', False),
                                 ('is_closed', '=', False)])

    def action_azm_documents(self):
        return self.env['azm.dashboard'].action_open_documents(company_id=self.id)

    def action_azm_edit_company(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.company',
            'res_id': self.id,
            'views': [[self.env.ref('base.view_company_form').id, 'form']],
            'target': 'current',
        }

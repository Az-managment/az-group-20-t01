from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home


class AzmHome(Home):
    """Login page language: ?lang=xx is remembered; Arabic is the default when installed."""

    def _azm_login_lang(self):
        installed = dict(request.env['res.lang'].sudo().get_installed())
        lang = request.params.get('lang')
        if lang and lang in installed:
            request.session['azm_login_lang'] = lang
        lang = request.session.get('azm_login_lang')
        if not lang:
            lang = next((code for code in installed if code.startswith('ar')), None)
        if lang and lang in installed:
            request.update_context(lang=lang)

    @http.route()
    def web_login(self, redirect=None, **kw):
        if request.db:
            self._azm_login_lang()
        return super().web_login(redirect=redirect, **kw)

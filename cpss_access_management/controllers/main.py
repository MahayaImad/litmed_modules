# -*- coding: utf-8 -*-
from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet


class CpssAccessDataSet(DataSet):
    """Blocks the RPC call behind a hidden button.

    Hiding a button in the arch only removes it from the screen. The web
    client posts the button's ``name`` — the method it calls — to
    ``/web/dataset/call_button``, which is exactly what a button rule stores,
    so the same rule can be enforced here for real.
    """

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        buttons = request.env['cpss.access.resolver']._get_user_restrictions()[
            'buttons'].get(model, {})
        if method in buttons.get('button', ()):
            raise AccessError(_(
                "Your access profile does not allow you to use this button."))
        return super().call_button(model, method, args, kwargs, path=path)

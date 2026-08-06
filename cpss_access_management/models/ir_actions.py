# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import AccessError


class IrActionsActions(models.Model):
    """Hides the contextual "Action" and "Print" menus of a restricted model.

    ``get_bindings`` is what feeds the cog menu of a view. The native method is
    cached on the group set of the user, so the filtering is done around it,
    never inside it.
    """
    _inherit = 'ir.actions.actions'

    @api.model
    def get_bindings(self, model_name):
        bindings = super().get_bindings(model_name)
        restrictions = self.env['cpss.access.resolver']._get_user_restrictions()
        operations = restrictions['models'].get(model_name, ())
        hidden_reports = restrictions['reports']
        if not operations and not hidden_reports:
            return bindings
        bindings = dict(bindings)
        if 'actions' in operations:
            bindings.pop('action', None)
        if 'print' in operations:
            bindings.pop('report', None)
        elif hidden_reports and bindings.get('report'):
            reports = [
                report for report in bindings['report']
                if report.get('id') not in hidden_reports
            ]
            if reports:
                bindings['report'] = reports
            else:
                bindings.pop('report')
        return bindings


class IrActionsReport(models.Model):
    """Blocks the actual rendering of a restricted report."""
    _inherit = 'ir.actions.report'

    def report_action(self, docids, data=None, config=True):
        self._cpss_check_print()
        return super().report_action(docids, data=data, config=config)

    def _cpss_check_print(self):
        resolver = self.env['cpss.access.resolver']
        restrictions = resolver._get_user_restrictions()
        for report in self:
            if report.id in restrictions['reports']:
                raise AccessError(_(
                    "Your access profile does not allow you to print the "
                    "report %(report)s.", report=report.display_name))
            if resolver._is_operation_forbidden(report.model, 'print'):
                raise AccessError(_(
                    "Your access profile does not allow you to print the "
                    "reports of type %(model)s.", model=report.model))

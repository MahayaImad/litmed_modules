# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval


class IrRule(models.Model):
    """Combines the access domains of the module with the native record rules.

    The native ``_compute_domain`` is cached per user, so wrapping it keeps
    the restriction user-specific. The extra domains are always AND-ed: a
    domain rule may only ever remove records from what the standard rules
    already allow.
    """
    _inherit = 'ir.rule'

    @api.model
    def _compute_domain(self, model_name, mode='read'):
        domain = super()._compute_domain(model_name, mode)
        extra_domains = self.env['cpss.access.resolver']._get_domain_restrictions(
            model_name, mode)
        if not extra_domains:
            return domain
        eval_context = self._eval_context()
        return Domain.AND(
            [domain] + [
                Domain(safe_eval(extra, eval_context))
                for extra in extra_domains
            ]
        ).optimize(self.env[model_name])

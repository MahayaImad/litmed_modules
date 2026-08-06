# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class CpssAccessDomainRule(models.Model):
    """Narrows the records of a model a user may reach.

    The domain is combined with the native record rules by
    ``ir.rule._compute_domain``, with an AND. Going through a real
    ``ir.rule`` record would do the opposite of what is wanted here: rules of
    different groups are OR-ed, so adding a group rule *widens* what the user
    sees. An AND on the computed domain is the only way to express "on top of
    everything else, this user also sees less".
    """
    _name = 'cpss.access.domain.rule'
    _description = "Access Rule: Domain"
    _inherit = ['cpss.access.rule.mixin']
    _order = 'model_name, id'

    name = fields.Char(
        string="Description",
        help="Free label, e.g. \"only the orders of their own team\".")
    model_id = fields.Many2one(
        'ir.model',
        string="Model",
        required=True,
        ondelete='cascade',
        index=True)
    model_name = fields.Char(
        related='model_id.model', store=True, index=True, string="Model Name")
    domain = fields.Char(
        string="Domain",
        required=True,
        default='[]',
        help="Records matching this domain stay reachable, the others become "
             "invisible. The usual record rule variables are available, "
             "including 'user' and 'company_ids'.")
    perm_read = fields.Boolean(string="Read", default=True)
    perm_write = fields.Boolean(string="Write", default=True)
    perm_create = fields.Boolean(string="Create", default=True)
    perm_unlink = fields.Boolean(string="Delete", default=True)

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        """Reject a domain the ORM would choke on at access time."""
        for rule in self:
            try:
                domain = safe_eval(
                    rule.domain, self.env['ir.rule']._eval_context())
                self.env[rule.model_name]._search(domain, limit=1)
            except Exception as error:
                raise ValidationError(_(
                    "Invalid domain for model %(model)s: %(error)s",
                    model=rule.model_name, error=error)) from error

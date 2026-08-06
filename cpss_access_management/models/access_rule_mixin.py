# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CpssAccessRuleMixin(models.AbstractModel):
    """Common ground of every access rule line.

    A rule always has exactly one target: a reusable profile, or a single
    user. Both are resolved together by ``cpss.access.resolver``, the profile
    being nothing more than a named bundle of rules shared by several users.

    Any write on a rule invalidates the resolution cache, so a change is
    effective on the next request without restarting the server.
    """
    _name = 'cpss.access.rule.mixin'
    _description = "Access Rule Mixin"

    profile_id = fields.Many2one(
        'cpss.access.profile',
        string="Access Profile",
        ondelete='cascade',
        index=True,
        help="Profile carrying this rule. Leave empty to target a single user.")
    user_id = fields.Many2one(
        'res.users',
        string="User",
        ondelete='cascade',
        index=True,
        domain="[('share', '=', False)]",
        help="User this rule applies to. Leave empty to use a profile.")
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        help="Restrict this rule to a single company. Empty means it applies "
             "whatever the company.")
    active = fields.Boolean(default=True)

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('profile_id', 'user_id')
    def _check_single_target(self):
        for rule in self:
            if bool(rule.profile_id) == bool(rule.user_id):
                raise ValidationError(_(
                    "An access rule must target either an access profile or a "
                    "user, not both and not neither."))

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        # ``@api.constrains`` only fires for the fields present in the values,
        # so a rule created without any target has to be checked explicitly.
        rules._check_single_target()
        self.env['cpss.access.resolver']._clear_caches()
        return rules

    def write(self, vals):
        result = super().write(vals)
        self.env['cpss.access.resolver']._clear_caches()
        return result

    def unlink(self):
        result = super().unlink()
        self.env['cpss.access.resolver']._clear_caches()
        return result

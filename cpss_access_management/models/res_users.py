# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Fields whose modification changes the restrictions resolved for a user.
# ``groups_id``, ``company_ids`` and ``active`` are deliberately absent: Odoo
# already drops its own caches for them, and the resolution cache is keyed on
# the active company anyway.
CACHE_SENSITIVE_FIELDS = frozenset({
    'access_profile_ids',
    'access_menu_rule_ids',
    'access_model_rule_ids',
    'access_field_rule_ids',
    'access_button_rule_ids',
    'access_report_rule_ids',
    'access_domain_rule_ids',
    'access_hide_chatter',
})


class ResUsers(models.Model):
    _inherit = 'res.users'

    access_profile_ids = fields.Many2many(
        'cpss.access.profile',
        'cpss_access_profile_users_rel', 'user_id', 'profile_id',
        string="Access Profiles",
        help="Reusable profiles restricting what this user may see and do. "
             "Restrictions of every profile add up.")
    access_menu_rule_ids = fields.One2many(
        'cpss.access.menu.rule', 'user_id', string="Menu Restrictions")
    access_model_rule_ids = fields.One2many(
        'cpss.access.model.rule', 'user_id', string="Model Restrictions")
    access_field_rule_ids = fields.One2many(
        'cpss.access.field.rule', 'user_id', string="Field Restrictions")
    access_button_rule_ids = fields.One2many(
        'cpss.access.button.rule', 'user_id', string="Button Restrictions")
    access_report_rule_ids = fields.One2many(
        'cpss.access.report.rule', 'user_id', string="Report Restrictions")
    access_domain_rule_ids = fields.One2many(
        'cpss.access.domain.rule', 'user_id', string="Domain Restrictions")
    access_hide_chatter = fields.Boolean(
        string="Hide Chatter Everywhere",
        help="Remove the chatter from every form view for this user.")
    access_restriction_count = fields.Integer(
        string="Restrictions", compute='_compute_access_restriction_count')

    # -------------------------------------------------------------------------
    # COMPUTE
    # -------------------------------------------------------------------------

    @api.depends('access_profile_ids', 'access_menu_rule_ids',
                 'access_model_rule_ids', 'access_field_rule_ids',
                 'access_button_rule_ids', 'access_report_rule_ids',
                 'access_domain_rule_ids')
    def _compute_access_restriction_count(self):
        for user in self:
            user.access_restriction_count = (
                sum(user.access_profile_ids.mapped('rule_count'))
                + len(user.access_menu_rule_ids)
                + len(user.access_model_rule_ids)
                + len(user.access_field_rule_ids)
                + len(user.access_button_rule_ids)
                + len(user.access_report_rule_ids)
                + len(user.access_domain_rule_ids)
            )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    # Odoo 16 has no ``_get_invalidation_fields`` extension point, so the
    # resolution cache is dropped explicitly whenever a field feeding it
    # changes. Companies are absent on purpose: the cache key already carries
    # the active company.

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if any(CACHE_SENSITIVE_FIELDS.intersection(vals) for vals in vals_list):
            self.env['cpss.access.resolver']._clear_caches()
        return users

    def write(self, values):
        result = super().write(values)
        if CACHE_SENSITIVE_FIELDS.intersection(values):
            self.env['cpss.access.resolver']._clear_caches()
        return result

# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Fields whose modification changes the restrictions resolved for a user.
# ``group_ids``, ``company_ids`` and ``active`` are deliberately absent: they
# already belong to the native invalidation set.
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

    @api.model
    def _get_invalidation_fields(self):
        # Native extension point: ``write`` already drops the registry cache
        # for these, no need to wrap it.
        return super()._get_invalidation_fields() | CACHE_SENSITIVE_FIELDS

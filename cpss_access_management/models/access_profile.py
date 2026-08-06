# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CpssAccessProfile(models.Model):
    """A reusable bundle of access rules assigned to several users.

    A profile owns nothing by itself: it is a container whose rules are merged
    with the user's own rules by ``cpss.access.resolver``. Assigning a profile
    to a user is therefore purely additive and always restrictive.
    """
    _name = 'cpss.access.profile'
    _description = "Access Profile"
    _order = 'sequence, name'

    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        help="Restrict the whole profile to a single company. Empty means it "
             "applies whatever the company.")
    note = fields.Text(string="Internal Note")
    hide_chatter = fields.Boolean(
        string="Hide Chatter Everywhere",
        help="Remove the chatter from every form view. Use a model rule "
             "instead to hide it on a single model.")
    user_ids = fields.Many2many(
        'res.users',
        'cpss_access_profile_users_rel', 'profile_id', 'user_id',
        string="Users",
        domain="[('share', '=', False)]",
        help="Users this profile is assigned to.")
    menu_rule_ids = fields.One2many(
        'cpss.access.menu.rule', 'profile_id', string="Menu Rules")
    model_rule_ids = fields.One2many(
        'cpss.access.model.rule', 'profile_id', string="Model Rules")
    field_rule_ids = fields.One2many(
        'cpss.access.field.rule', 'profile_id', string="Field Rules")
    button_rule_ids = fields.One2many(
        'cpss.access.button.rule', 'profile_id', string="Button Rules")
    report_rule_ids = fields.One2many(
        'cpss.access.report.rule', 'profile_id', string="Report Rules")
    domain_rule_ids = fields.One2many(
        'cpss.access.domain.rule', 'profile_id', string="Domain Rules")
    user_count = fields.Integer(
        string="Users Count", compute='_compute_user_count')
    rule_count = fields.Integer(
        string="Rules", compute='_compute_rule_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name)',
         "An access profile with this name already exists."),
    ]

    # -------------------------------------------------------------------------
    # COMPUTE
    # -------------------------------------------------------------------------

    @api.depends('user_ids')
    def _compute_user_count(self):
        for profile in self:
            profile.user_count = len(profile.user_ids)

    @api.depends('menu_rule_ids', 'model_rule_ids', 'field_rule_ids',
                 'button_rule_ids', 'report_rule_ids', 'domain_rule_ids')
    def _compute_rule_count(self):
        for profile in self:
            profile.rule_count = (
                len(profile.menu_rule_ids)
                + len(profile.model_rule_ids)
                + len(profile.field_rule_ids)
                + len(profile.button_rule_ids)
                + len(profile.report_rule_ids)
                + len(profile.domain_rule_ids)
            )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        self.env['cpss.access.resolver']._clear_caches()
        return profiles

    def write(self, vals):
        result = super().write(vals)
        self.env['cpss.access.resolver']._clear_caches()
        return result

    def unlink(self):
        result = super().unlink()
        self.env['cpss.access.resolver']._clear_caches()
        return result

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_view_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Users"),
            'res_model': 'res.users',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.user_ids.ids)],
        }

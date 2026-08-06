# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Les six familles de règles qu'un profil regroupe.
RULE_FIELDS = (
    'menu_rule_ids', 'model_rule_ids', 'field_rule_ids',
    'button_rule_ids', 'report_rule_ids', 'domain_rule_ids',
)


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
        help="Company the whole profile applies in. Empty means it applies "
             "whatever the active company.\n"
             "When set, every rule of the profile is dormant in the other "
             "companies: there is then no need to repeat the company on each "
             "rule.")
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

    @api.depends(*RULE_FIELDS)
    def _compute_rule_count(self):
        for profile in self:
            profile.rule_count = sum(
                len(profile[nom]) for nom in RULE_FIELDS)

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('company_id')
    def _check_rules_company(self):
        """Restreindre le profil ne doit pas rendre ses règles inopérantes.

        Un profil portant une société est dormant dans toutes les autres :
        une règle visant une société différente ne s'appliquerait jamais.
        """
        for profile in self:
            if not profile.company_id:
                continue
            for nom in RULE_FIELDS:
                incompatibles = profile[nom].filtered(
                    lambda regle: regle.company_id
                    and regle.company_id != profile.company_id)
                if incompatibles:
                    raise ValidationError(_(
                        "This profile only applies in %(profile_company)s, but "
                        "%(count)s of its rules target another company: they "
                        "could never apply.\n\n"
                        "Clear the company of those rules — the profile "
                        "already decides — or align them."
                    ) % {
                        'profile_company': profile.company_id.display_name,
                        'count': len(incompatibles),
                    })

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

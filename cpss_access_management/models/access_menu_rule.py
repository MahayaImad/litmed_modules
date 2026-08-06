# -*- coding: utf-8 -*-
from odoo import fields, models


class CpssAccessMenuRule(models.Model):
    """Hides a menu — and optionally its whole sub-tree — from a user.

    Hiding a menu is cosmetic by nature: it removes an entry point, not the
    underlying rights. Model rules and standard ACLs remain the only real
    protection, which is why both families live side by side in a profile.
    """
    _name = 'cpss.access.menu.rule'
    _description = "Access Rule: Menu"
    _inherit = ['cpss.access.rule.mixin']
    _order = 'menu_id'

    menu_id = fields.Many2one(
        'ir.ui.menu',
        string="Menu",
        required=True,
        ondelete='cascade',
        index=True,
        help="Menu hidden from the target user.")
    include_children = fields.Boolean(
        string="Hide Sub-Menus",
        default=True,
        help="Also hide every menu located under this one.")

    _menu_target_uniq = models.Constraint(
        'unique(menu_id, profile_id, user_id)',
        "This menu is already hidden for this profile or user.",
    )

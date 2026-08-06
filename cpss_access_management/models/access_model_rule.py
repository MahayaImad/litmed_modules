# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CpssAccessModelRule(models.Model):
    """Forbids operations on a model for a user.

    Each flag is enforced twice: once in the interface (the matching root
    attribute of the list/form/kanban arch is turned off) and once in the ORM
    (``check_access``, ``copy``, ``export_data``, archiving), because hiding a
    button is not security.
    """
    _name = 'cpss.access.model.rule'
    _description = "Access Rule: Model"
    _inherit = ['cpss.access.rule.mixin']
    _order = 'model_name'

    model_id = fields.Many2one(
        'ir.model',
        string="Model",
        required=True,
        ondelete='cascade',
        index=True,
        help="Model the restrictions below apply to.")
    model_name = fields.Char(
        related='model_id.model', store=True, index=True, string="Model Name")
    disable_create = fields.Boolean(
        string="Forbid Create",
        help="The user can no longer create records of this model.")
    disable_edit = fields.Boolean(
        string="Forbid Edit",
        help="The user can no longer modify records of this model.")
    disable_delete = fields.Boolean(
        string="Forbid Delete",
        help="The user can no longer delete records of this model.")
    disable_duplicate = fields.Boolean(
        string="Forbid Duplicate",
        help="The user can no longer duplicate records of this model.")
    disable_export = fields.Boolean(
        string="Forbid Export",
        help="The user can no longer export records of this model.")
    disable_archive = fields.Boolean(
        string="Forbid Archive",
        help="The user can no longer archive or unarchive records of this "
             "model.")
    disable_actions = fields.Boolean(
        string="Forbid Actions",
        help="Hide the action menu (server actions, automations) on this "
             "model.")
    disable_print = fields.Boolean(
        string="Forbid Print",
        help="The user can no longer print the reports of this model.")
    hide_chatter = fields.Boolean(
        string="Hide Chatter",
        help="Remove the chatter (messages, log notes, followers) from the "
             "form view of this model.")
    hide_filters = fields.Boolean(
        string="Hide Filters",
        help="Remove the predefined filters from the search view of this "
             "model. Group by entries are kept.")
    hide_group_by = fields.Boolean(
        string="Hide Group By",
        help="Remove the predefined group by entries from the search view of "
             "this model.")

    _model_target_uniq = models.Constraint(
        'unique(model_id, profile_id, user_id)',
        "This model already has a rule for this profile or user.",
    )

    # -------------------------------------------------------------------------
    # ONCHANGE
    # -------------------------------------------------------------------------

    @api.onchange('disable_edit')
    def _onchange_disable_edit(self):
        """Forbidding edition implies forbidding creation and duplication."""
        for rule in self:
            if rule.disable_edit:
                rule.disable_create = True
                rule.disable_duplicate = True

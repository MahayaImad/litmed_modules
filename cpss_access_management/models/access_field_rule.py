# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CpssAccessFieldRule(models.Model):
    """Changes how a single field behaves for a user.

    ``invisible`` and ``no_open`` are interface-only attributes injected in the
    view arch. ``readonly`` is also enforced on write, so a restricted user
    cannot change the value through an RPC call, and ``required`` is a data
    quality rule pushed to the client.
    """
    _name = 'cpss.access.field.rule'
    _description = "Access Rule: Field"
    _inherit = ['cpss.access.rule.mixin']
    _order = 'model_name, field_name'

    model_id = fields.Many2one(
        'ir.model',
        string="Model",
        required=True,
        ondelete='cascade',
        index=True)
    model_name = fields.Char(
        related='model_id.model', store=True, index=True, string="Model Name")
    field_id = fields.Many2one(
        'ir.model.fields',
        string="Field",
        required=True,
        ondelete='cascade',
        domain="[('model_id', '=', model_id)]",
        help="Field the attribute below applies to.")
    field_name = fields.Char(
        related='field_id.name', store=True, string="Field Name")
    attribute = fields.Selection(
        [('invisible', "Invisible"),
         ('readonly', "Read-only"),
         ('required', "Required"),
         ('no_open', "No External Link")],
        string="Attribute",
        required=True,
        default='readonly',
        help="Invisible: the field disappears from the views. Read-only: the "
             "value can no longer be changed. Required: the value becomes "
             "mandatory. No External Link: the internal link opening the "
             "related record is removed.")

    _sql_constraints = [
        ('field_attribute_uniq',
         'unique(field_id, attribute, profile_id, user_id)',
         "This attribute is already set on this field for this profile or "
         "user."),
    ]

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('field_id', 'attribute', 'profile_id', 'user_id')
    def _check_required_not_invisible(self):
        """A required field that is also hidden makes saving impossible."""
        for rule in self:
            if rule.attribute not in ('required', 'invisible'):
                continue
            conflict = 'invisible' if rule.attribute == 'required' else 'required'
            if self.search_count([
                ('id', '!=', rule.id),
                ('field_id', '=', rule.field_id.id),
                ('attribute', '=', conflict),
                ('profile_id', '=', rule.profile_id.id),
                ('user_id', '=', rule.user_id.id),
            ]):
                raise ValidationError(_(
                    "Field %(field)s cannot be required and invisible at the "
                    "same time: the records could no longer be saved."
                ) % {'field': rule.field_id.display_name})

    # -------------------------------------------------------------------------
    # ONCHANGE
    # -------------------------------------------------------------------------

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for rule in self:
            if rule.field_id.model_id != rule.model_id:
                rule.field_id = False

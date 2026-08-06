# -*- coding: utf-8 -*-
from odoo import fields, models


class CpssAccessButtonRule(models.Model):
    """Hides a button, a notebook page or a named link of a model's views.

    Buttons are matched on their ``name`` attribute, which for an object
    button is the method it calls. That is also what the web client sends to
    ``/web/dataset/call_button``, so the very same rule hides the button and
    blocks the call, instead of only removing it from the screen.

    Pages and links have no server-side counterpart: they are containers, and
    what they contain is restricted by the field and model rules.
    """
    _name = 'cpss.access.button.rule'
    _description = "Access Rule: Button"
    _inherit = ['cpss.access.rule.mixin']
    _order = 'model_name, element_type, element_name'

    model_id = fields.Many2one(
        'ir.model',
        string="Model",
        required=True,
        ondelete='cascade',
        index=True)
    model_name = fields.Char(
        related='model_id.model', store=True, index=True, string="Model Name")
    element_type = fields.Selection(
        [('button', "Button"),
         ('page', "Notebook Page"),
         ('link', "Link")],
        string="Element",
        required=True,
        default='button',
        help="Button: an action or object button of the views, also blocked "
             "server side. Notebook Page: a tab of the form view. Link: a "
             "named anchor, typically in a kanban card.")
    element_name = fields.Char(
        string="Technical Name",
        required=True,
        help="Value of the 'name' attribute of the element in the view. For "
             "an object button this is the name of the python method it "
             "calls. A notebook page can also be matched on its label.")

    _sql_constraints = [
        ('element_target_uniq',
         'unique(model_id, element_type, element_name, profile_id, user_id)',
         "This element is already restricted for this profile or user."),
    ]

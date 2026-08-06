# -*- coding: utf-8 -*-
from odoo import fields, models


class CpssAccessReportRule(models.Model):
    """Hides a single report and blocks its rendering.

    ``cpss.access.model.rule.disable_print`` forbids every report of a model;
    this rule is the fine-grained version, for the frequent case where a user
    may print the delivery slip but not the invoice.
    """
    _name = 'cpss.access.report.rule'
    _description = "Access Rule: Report"
    _inherit = ['cpss.access.rule.mixin']
    _order = 'model_name, report_id'

    report_id = fields.Many2one(
        'ir.actions.report',
        string="Report",
        required=True,
        ondelete='cascade',
        index=True,
        help="Report the target user may no longer print.")
    model_name = fields.Char(
        related='report_id.model', store=True, index=True, string="Model Name")

    _sql_constraints = [
        ('report_target_uniq', 'unique(report_id, profile_id, user_id)',
         "This report is already restricted for this profile or user."),
    ]

# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class InheritIrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    dynamic_report_id = fields.Many2one('dynamic.report.configure', 'Dynamic Reference')

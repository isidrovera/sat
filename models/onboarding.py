# models/onboarding.py
from odoo import api, models

class Onboarding(models.Model):
    _inherit = 'onboarding.onboarding'

    @api.model 
    def action_close_panel_alquiler(self):
        self.action_close_panel('alquiler_onboarding.action_close_panel_alquiler')

class OnboardingStep(models.Model):
    _inherit = 'onboarding.onboarding.step'

    @api.model
    def action_open_alquiler_onboarding_sample(self):
        action = self.env['ir.actions.actions']._for_xml_id(
            'alquiler.alquiler_tree_action')
        action.update({
            'views': [[self.env.ref('alquiler.alquiler_form_view').id, 'form']],
            'view_mode': 'form',
            'target': 'main',
        })
        return action
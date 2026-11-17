# -*- coding: utf-8 -*-
"""Enlaces privados de seguimiento por visita, no por máquina."""
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class SatVisitaTecnicaMapa(models.Model):
    _inherit = 'sat.visita.tecnica'

    gps_public_token = fields.Char(copy=False, readonly=True, groups='base.group_system')
    gps_public_expira = fields.Datetime(copy=False, readonly=True)
    gps_public_revocado = fields.Boolean(default=False, copy=False, readonly=True)
    gps_link_cliente = fields.Char(compute='_compute_gps_link_cliente')

    @api.depends('gps_public_token', 'gps_public_expira', 'gps_public_revocado')
    def _compute_gps_link_cliente(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            vigente = (rec.gps_public_token and not rec.gps_public_revocado
                       and rec.gps_public_expira and rec.gps_public_expira > fields.Datetime.now())
            rec.gps_link_cliente = ('%s/seguimiento/%s' % (base, rec.gps_public_token)) if vigente else False

    def action_generar_link_gps(self):
        self.ensure_one()
        if not (self.env.user.has_group('sat.sat_jefes_group_user')
                or self.env.user.has_group('base.group_system')):
            raise AccessError(_('Solo gerencia o jefatura puede generar enlaces GPS.'))
        if self.estado in ('cancelada', 'salida_confirmada'):
            raise UserError(_('La visita ya no permite seguimiento público.'))
        # Rotar el token invalida inmediatamente cualquier enlace anterior.
        self.sudo().write({
            'gps_public_token': secrets.token_urlsafe(32),
            'gps_public_expira': fields.Datetime.now() + timedelta(hours=24),
            'gps_public_revocado': False,
        })
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form', 'target': 'current',
        }

    def action_revocar_link_gps(self):
        for rec in self:
            if not (self.env.user.has_group('sat.sat_jefes_group_user')
                    or self.env.user.has_group('base.group_system')):
                raise AccessError(_('No está autorizado para revocar enlaces.'))
            rec.sudo().write({'gps_public_revocado': True})
        return True

    @api.model
    def _gps_buscar_token_valido(self, token):
        if not token or len(token) > 256:
            return self.browse()
        visita = self.sudo().search([
            ('gps_public_token', '=', token),
            ('gps_public_revocado', '=', False),
            ('gps_public_expira', '>', fields.Datetime.now()),
            ('estado', '!=', 'cancelada'),
        ], limit=1)
        if not visita:
            return visita
        # Los técnicos pueden acabar en instantes diferentes.
        if visita.participante_ids and all(p.estado in ('salida_confirmada', 'cancelada')
                                           for p in visita.participante_ids):
            return self.browse()
        return visita


class TicketAlquilerMapa(models.Model):
    _inherit = 'ticket.alquiler'

    def action_ver_mapa_gps(self):
        self.ensure_one()
        if not self.gps_visita_id:
            raise UserError(_('Este ticket aún no tiene una visita GPS vinculada.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/sat/gps/visita/%s?ticket_id=%s' % (self.gps_visita_id.id, self.id),
            'target': 'new',
        }

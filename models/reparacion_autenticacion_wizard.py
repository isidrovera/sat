
from odoo import api, fields, models, exceptions, _
import re
import logging

_logger = logging.getLogger(__name__)

class ReparacionAutenticacionWizard(models.TransientModel):
    _name = 'reparacion.autenticacion.wizard'
    _description = 'Autenticación de Serie y Modelo para Reparaciones'

    serie = fields.Char(string="Serie del Equipo", required=True)
    modelo_id = fields.Many2one('modelo.maquina', string="Modelo del Equipo", required=True)
    
    def validar_acceso(self):
        reparacion_id = self.env.context.get('active_id')
        reparacion = self.env['reparaciones.reparaciones'].browse(reparacion_id)

        # Normalizar las series para comparar
        serie_ingresada = self.serie.strip().lower().replace(" ", "")
        serie_registrada = reparacion.maquina_id.serie_id.strip().lower().replace(" ", "")

        if serie_ingresada != serie_registrada:
            raise exceptions.ValidationError(_("❗ Error: La serie ingresada no coincide con la serie registrada en el sistema. Revise nuevamente la serie física en la máquina."))

        if self.modelo_id.id != reparacion.maquina_id.name.id:
             raise exceptions.ValidationError(_("❗ Error: El modelo seleccionado no coincide con el equipo asignado. Revise el modelo físico en la máquina."))


        # Marcar la autenticación como correcta
        reparacion.autenticacion_correcta = True

        # Redirigir al formulario de reparación tras autenticación exitosa
        return {
            'type': 'ir.actions.act_window',
            'name': 'Editar Reparación',
            'res_model': 'reparaciones.reparaciones',
            'res_id': reparacion.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }
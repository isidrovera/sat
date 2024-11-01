from odoo import api, fields, models, exceptions
import re
import logging

_logger = logging.getLogger(__name__)

class ReparacionAutenticacionWizard(models.TransientModel):
    _name = 'reparacion.autenticacion.wizard'
    _description = 'Autenticación de Serie y Modelo para Reparaciones'

    serie = fields.Char(string="Serie del Equipo", required=True)
    modelo_id = fields.Many2one('modelo.maquina', string="Modelo del Equipo", required=True)
    
    def validar_acceso(self):
        # Obtener la reparación y el equipo asignado desde el contexto
        reparacion_id = self.env.context.get('active_id')
        reparacion = self.env['reparaciones.reparaciones'].browse(reparacion_id)
        equipo_asignado = reparacion.maquina_id

        # Normalizar la serie para comparar sin importar mayúsculas o espacios
        serie_ingresada = re.sub(r'\s+', '', self.serie.strip().lower())
        serie_equipo = re.sub(r'\s+', '', equipo_asignado.serie_id.strip().lower())

        # Validar la serie
        if serie_ingresada != serie_equipo:
            raise exceptions.ValidationError(_("❗ Error: La serie ingresada no coincide con la serie registrada en el sistema. Revise nuevamente la serie física en la máquina."))

        # Validar el modelo seleccionado
        if self.modelo_id != equipo_asignado.name:
            raise exceptions.ValidationError(_("❗ Error: El modelo seleccionado no coincide con el modelo registrado en el sistema. Revise nuevamente el modelo físico en la máquina."))

        # Confirmación de que la revisión física se ha hecho correctamente
        return {
            'type': 'ir.actions.act_window',
            'name': 'Editar Reparación',
            'res_model': 'reparaciones.reparaciones',
            'res_id': reparacion.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

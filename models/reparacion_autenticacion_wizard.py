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
        _logger.info("Iniciando validación de acceso en el wizard de autenticación")

        # Obtener el ID de la reparación desde el contexto
        reparacion_id = self.env.context.get('active_id')
        reparacion = self.env['reparaciones.reparaciones'].browse(reparacion_id)
        equipo_asignado = reparacion.maquina_id

        # Normalizar la serie para comparar sin importar mayúsculas o espacios
        serie_ingresada = re.sub(r'\s+', '', self.serie.strip().lower())
        serie_equipo = re.sub(r'\s+', '', equipo_asignado.serie_id.strip().lower())

        _logger.info(f"Serie ingresada: {serie_ingresada}, Serie equipo asignado: {serie_equipo}")

        # Validar la serie
        if serie_ingresada != serie_equipo:
            _logger.error("La serie ingresada no coincide con la del equipo asignado.")
            raise exceptions.ValidationError("❌ La serie ingresada no coincide con la del equipo asignado. Verifique la serie e intente nuevamente.")

        # Validar el modelo seleccionado
        if self.modelo_id != equipo_asignado.name:
            _logger.error("El modelo seleccionado no coincide con el equipo asignado.")
            raise exceptions.ValidationError("❌ El modelo seleccionado no coincide con el equipo asignado. Por favor, seleccione el modelo correcto.")

        # Verificar si el equipo es color o monocromático
        equipo_es_color = 'c' in equipo_asignado.name.name.lower()
        ingreso_es_color = 'c' in self.modelo_id.name.lower()
        if equipo_es_color != ingreso_es_color:
            tipo_correcto = "Color" if equipo_es_color else "Monocromático"
            _logger.warning("El tipo de equipo no coincide.")
            raise exceptions.ValidationError(f"⚠️ El tipo de equipo no coincide. Este equipo es {tipo_correcto}. Asegúrese de seleccionar el equipo correcto.")

        _logger.info("Validación exitosa, redirigiendo al formulario de reparación")

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

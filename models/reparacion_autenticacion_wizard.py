from odoo import api, fields, models, exceptions
import re

class ReparacionAutenticacionWizard(models.TransientModel):
    _name = 'reparacion.autenticacion.wizard'
    _description = 'Autenticación de Serie y Modelo para Reparaciones'

    serie = fields.Char(string="Serie del Equipo", required=True)
    modelo_id = fields.Many2one('modelo.maquina', string="Modelo del Equipo", required=True)
    
    
    def validar_acceso(self):
        # Obtener el ID de la reparación desde el contexto
        reparacion_id = self.env.context.get('active_id')
        reparacion = self.env['reparaciones.reparaciones'].browse(reparacion_id)
        equipo_asignado = reparacion.maquina_id

        # Normalizar la serie para comparar sin importar mayúsculas o espacios
        serie_ingresada = re.sub(r'\s+', '', self.serie.strip().lower())
        serie_equipo = re.sub(r'\s+', '', equipo_asignado.serie_id.strip().lower())

        # Validar la serie
        if serie_ingresada != serie_equipo:
            raise exceptions.ValidationError("La serie ingresada no coincide con la del equipo asignado.")

        # Validar el modelo seleccionado
        if self.modelo_id != equipo_asignado.name:
            raise exceptions.ValidationError("El modelo seleccionado no coincide con el equipo asignado.")
        
        # Verificar si el equipo es color o monocromático
        equipo_es_color = 'c' in equipo_asignado.name.name.lower()
        ingreso_es_color = 'c' in self.modelo_id.name.lower()
        if equipo_es_color != ingreso_es_color:
            tipo_correcto = "Color" if equipo_es_color else "Monocromático"
            raise exceptions.ValidationError(f"El tipo de equipo no coincide. Este equipo es {tipo_correcto}.")

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
from odoo import api, fields, models, exceptions, _
import logging

_logger = logging.getLogger(__name__)

class ReparacionAutenticacionWizard(models.TransientModel):
    _name = 'reparacion.autenticacion.wizard'
    _description = 'Autenticación de Serie y Modelo para Reparaciones'

    serie = fields.Char(string="Serie del Equipo", required=True)
    modelo_id = fields.Many2one('modelo.maquina', string="Modelo del Equipo", required=True)

    @api.model
    def default_get(self, field_list):
        """
        Seguridad: no permitir precarga de valores (para que no copien/peguen).
        Aunque alguien mande default_serie/default_modelo_id, se limpian.
        """
        res = super().default_get(field_list)
        res['serie'] = False
        res['modelo_id'] = False
        return res

    def validar_acceso(self):
        self.ensure_one()

        # Tomar reparación desde active_id
        reparacion_id = self.env.context.get('active_id')
        reparacion = self.env['reparaciones.reparaciones'].browse(reparacion_id)

        if not reparacion or not reparacion.exists():
            raise exceptions.ValidationError(_("No se encontró la reparación activa."))

        if not reparacion.maquina_id:
            raise exceptions.ValidationError(_("La reparación no tiene un equipo asignado."))

        # Normalizador robusto
        def norm(s):
            return (s or '').strip().lower().replace(" ", "")

        serie_ingresada = norm(self.serie)

        # OJO: en tu modelo reparaciones, serie_id es related a maquina_id.serie_id
        # aquí uso reparacion.serie_id (ya lo tienes en el modelo)
        serie_registrada = norm(reparacion.serie_id)

        if not serie_ingresada:
            raise exceptions.ValidationError(_("Debe ingresar la serie del equipo."))

        if serie_ingresada != serie_registrada:
            raise exceptions.ValidationError(_(
                "❗ Error: La serie ingresada no coincide con la registrada en el sistema.\n"
                "Revise la serie física en la máquina."
            ))

        # Modelo registrado (en tu estructura: reparacion.maquina_id.name es Many2one a modelo.maquina)
        modelo_registrado = reparacion.maquina_id.name
        if not modelo_registrado:
            raise exceptions.ValidationError(_("El equipo no tiene modelo asignado en el sistema."))

        if self.modelo_id.id != modelo_registrado.id:
            raise exceptions.ValidationError(_(
                "❗ Error: El modelo seleccionado no coincide con el equipo asignado.\n"
                "Revise el modelo físico en la máquina."
            ))

        # Marcar autenticación
        reparacion.autenticacion_correcta = True

        return {
            'type': 'ir.actions.act_window',
            'name': 'Editar Reparación',
            'res_model': 'reparaciones.reparaciones',
            'res_id': reparacion.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

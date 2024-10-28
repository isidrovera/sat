from odoo import models, fields, api
from odoo.tools.translate import _
import base64
import io
import pandas as pd
import logging
import odoo.tools as tools

_logger = logging.getLogger(__name__)

class ExcelImportModel(models.Model):
    _name = 'excel.import.model'
    _description = 'Importar Registros desde Excel'
    _inherit = ['mail.thread']  # Hereda de mail.thread para permitir message_post

    name = fields.Char(string="Nombre", required=True, default=lambda self: _('Nueva Importación'))
    model_id = fields.Many2one(
        'ir.model', 
        string='Modelo', 
        help="Selecciona el modelo en el cual se actualizarán los registros."
    )
    identifier_field_id = fields.Many2one(
        'ir.model.fields', 
        string='Campo Identificador', 
        help="Selecciona el campo que se usará como identificador"
    )
    excel_file = fields.Binary('Archivo Excel', required=True, help="Selecciona el archivo Excel para la importación")
    file_name = fields.Char('Nombre del archivo')

    def import_excel(self):
        self.ensure_one()
        try:
            _logger.info("Inicio de la importación desde Excel.")
            
            if not self.excel_file:
                raise ValueError(_("No se ha seleccionado ningún archivo Excel."))

            # Decodificar y leer el archivo Excel
            decoded_file = base64.b64decode(self.excel_file)
            file_stream = io.BytesIO(decoded_file)
            df = pd.read_excel(file_stream)
            _logger.info("Archivo Excel decodificado y leído correctamente.")

            # Verificar que el campo identificador existe en el archivo Excel
            if self.identifier_field_id.name not in df.columns:
                raise ValueError(_("El campo '{}' no se encuentra en el archivo Excel.").format(self.identifier_field_id.name))

            _logger.info("Verificación del campo identificador completada.")

            # Obtener los nombres de los campos del modelo seleccionado
            model_fields = self.env['ir.model.fields'].search([('model_id', '=', self.model_id.id)])
            model_field_names = model_fields.mapped('name')
            _logger.info(f"Nombres de campos del modelo seleccionado: {model_field_names}")

            # Contadores para el resumen de importación
            updated_records = 0
            skipped_records = 0

            # Procesar cada registro del archivo Excel
            for _, row in df.iterrows():
                # Buscar el registro según el identificador
                record = self.env[self.model_id.model].search([(self.identifier_field_id.name, '=', row[self.identifier_field_id.name])])

                # Si el registro existe, actualizarlo
                if record:
                    # Filtrar solo las columnas que existen en el modelo
                    update_data = {col: row[col] for col in df.columns if col in model_field_names}
                    if update_data:
                        record.write(update_data)
                        updated_records += 1
                        _logger.info(f"Registro actualizado: {record.id} con datos: {update_data}")
                    else:
                        _logger.warning(f"No hay datos válidos para actualizar en el registro con {self.identifier_field_id.name} = {row[self.identifier_field_id.name]}.")
                        skipped_records += 1
                else:
                    _logger.warning(f"Registro con {self.identifier_field_id.name} = {row[self.identifier_field_id.name]} no encontrado.")
                    skipped_records += 1

            # Registrar en el log
            _logger.info(f"Importación completada: {updated_records} registros actualizados, {skipped_records} registros omitidos.")

            # Crear mensaje en el chatter
            message = tools.translate._('Importación Completa: {} registros actualizados, {} registros omitidos.').format(updated_records, skipped_records)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': tools.translate._('Importación Exitosa'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }

        except Exception as e:
            _logger.error(f"Error durante la importación del archivo Excel: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': tools.translate._('Error en la Importación'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
from odoo import models, fields, api, _
import base64
import io
import pandas as pd
import logging

_logger = logging.getLogger(__name__)

class ExcelImportModel(models.Model):
    _name = 'excel.import.model'
    _description = 'Importar Registros desde Excel'
    _inherit = ['mail.thread']

    name = fields.Char(
        string="Nombre", 
        required=True, 
        tracking=True,
        default=lambda self: _('Nueva Importación')
    )
    model_id = fields.Many2one(
        'ir.model', 
        string='Modelo', 
        required=True,
        ondelete='cascade',
        tracking=True,
        help="Selecciona el modelo en el cual se actualizarán los registros."
    )
    identifier_field_id = fields.Many2one(
        'ir.model.fields', 
        string='Campo Identificador', 
        required=True,
        ondelete='cascade',
        tracking=True,
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        help="Selecciona el campo que se usará como identificador"
    )
    excel_file = fields.Binary(
        'Archivo Excel', 
        required=True, 
        help="Selecciona el archivo Excel para la importación"
    )
    file_name = fields.Char('Nombre del archivo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Completado'),
        ('error', 'Error')
    ], string='Estado', default='draft', tracking=True, copy=False)

    def _convert_field_value(self, field, value):
        """
        Convierte el valor según el tipo de campo
        """
        if pd.isna(value):
            return False

        try:
            if field.ttype == 'many2one':
                return self._handle_many2one_field(field, value)
            elif field.ttype == 'selection':
                return self._handle_selection_field(field, value)
            elif field.ttype == 'boolean':
                return self._handle_boolean_field(value)
            elif field.ttype in ['integer', 'float', 'monetary']:
                return self._handle_numeric_field(field, value)
            elif field.ttype == 'date':
                return self._handle_date_field(value)
            elif field.ttype == 'datetime':
                return self._handle_datetime_field(value)
            else:
                return str(value) if value else False
        except Exception as e:
            _logger.warning(
                "Error convirtiendo valor '%s' para campo %s (tipo %s): %s",
                value, field.name, field.ttype, str(e)
            )
            return False

    def _handle_many2one_field(self, field, value):
        """
        Maneja campos many2one intentando diferentes estrategias de búsqueda
        """
        if not value:
            return False

        value = str(value).strip()
        related_model = self.env[field.relation]
        
        # Buscar primero por ID si es un número
        if str(value).isdigit():
            record = related_model.browse(int(value)).exists()
            if record:
                return record.id

        # Buscar por nombre exacto
        record = related_model.search([('name', '=', value)], limit=1)
        if record:
            return record.id

        # Buscar por nombre similar
        record = related_model.search([('name', 'ilike', value)], limit=1)
        if record:
            return record.id

        # Si no se encuentra, intentar crear si el modelo lo permite
        try:
            if hasattr(related_model, 'create'):
                new_record = related_model.create({'name': value})
                return new_record.id
        except Exception as e:
            _logger.warning(
                "No se pudo crear el registro para %s con valor '%s': %s",
                field.relation, value, str(e)
            )
        
        return False

    def _handle_selection_field(self, field, value):
        """
        Maneja campos de selección
        """
        if not value:
            return False

        # Obtener las opciones válidas del campo
        selection_options = dict(self.env[field.model]._fields[field.name].selection)
        value_str = str(value).strip().lower()

        # Buscar coincidencia exacta en keys
        if value_str in [str(k).lower() for k in selection_options.keys()]:
            return next(k for k in selection_options.keys() if str(k).lower() == value_str)

        # Buscar coincidencia en valores de selección
        for key, val in selection_options.items():
            if value_str == str(val).lower():
                return key

        return False

    def _handle_boolean_field(self, value):
        """
        Maneja campos booleanos
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ['1', 'true', 'si', 'sí', 'yes', 'verdadero', 't', 'y']
        return False

    def _handle_numeric_field(self, field, value):
        """
        Maneja campos numéricos
        """
        if isinstance(value, (int, float)):
            return float(value) if field.ttype == 'float' else int(value)
        if isinstance(value, str):
            # Limpiar el string de caracteres no numéricos
            clean_value = ''.join(c for c in value if c.isdigit() or c in '.-')
            try:
                if field.ttype == 'float':
                    return float(clean_value)
                return int(float(clean_value))
            except ValueError:
                return 0
        return 0

    def _handle_date_field(self, value):
        """
        Maneja campos de fecha
        """
        try:
            if isinstance(value, str):
                return pd.to_datetime(value).date()
            if isinstance(value, pd.Timestamp):
                return value.date()
            return value
        except Exception:
            return False

    def _handle_datetime_field(self, value):
        """
        Maneja campos de fecha y hora
        """
        try:
            if isinstance(value, str):
                return pd.to_datetime(value)
            return value
        except Exception:
            return False

    def import_excel(self):
        self.ensure_one()
        try:
            if not self.excel_file:
                raise ValueError(_("No se ha seleccionado ningún archivo Excel."))

            _logger.info("Iniciando importación de Excel para el modelo: %s", self.model_id.model)
            
            # Leer archivo Excel
            decoded_file = base64.b64decode(self.excel_file)
            file_stream = io.BytesIO(decoded_file)
            
            try:
                df = pd.read_excel(file_stream)
                _logger.info("Archivo Excel leído correctamente. Columnas encontradas: %s", list(df.columns))
            except Exception as e:
                raise ValueError(_("Error al leer el archivo Excel: %s") % str(e))

            if df.empty:
                raise ValueError(_("El archivo Excel está vacío."))

            # Verificar campo identificador
            if self.identifier_field_id.name not in df.columns:
                raise ValueError(_("El campo '%s' no se encuentra en el archivo Excel.") % 
                               self.identifier_field_id.name)

            # Obtener campos del modelo
            model_fields = self.env['ir.model.fields'].search([
                ('model_id', '=', self.model_id.id),
                ('store', '=', True),
                ('readonly', '=', False)
            ])
            fields_by_name = {field.name: field for field in model_fields}

            # Contadores
            updated_records = 0
            skipped_records = 0
            errors = []

            # Procesar registros
            for index, row in df.iterrows():
                try:
                    # Obtener valor del identificador
                    identifier_value = row[self.identifier_field_id.name]
                    if pd.isna(identifier_value):
                        continue

                    # Buscar registro existente
                    record = self.env[self.model_id.model].search([
                        (self.identifier_field_id.name, '=', identifier_value)
                    ], limit=1)

                    if not record:
                        errors.append(_("Fila %d: No se encontró el registro con %s=%s") % 
                                   (index + 2, self.identifier_field_id.name, identifier_value))
                        skipped_records += 1
                        continue

                    # Preparar datos para actualización
                    update_data = {}
                    for column in df.columns:
                        if column in fields_by_name:
                            field = fields_by_name[column]
                            value = self._convert_field_value(field, row[column])
                            if value is not False:
                                update_data[column] = value

                    if update_data:
                        try:
                            record.write(update_data)
                            updated_records += 1
                            _logger.info("Registro %s actualizado con datos: %s", record.id, update_data)
                        except Exception as e:
                            errors.append(_("Fila %d: Error actualizando registro: %s") % (index + 2, str(e)))
                            skipped_records += 1
                    else:
                        skipped_records += 1

                except Exception as e:
                    errors.append(_("Fila %d: %s") % (index + 2, str(e)))
                    skipped_records += 1

            # Actualizar estado y crear mensaje
            self.state = 'done' if updated_records > 0 else 'error'
            message = _("""
Resumen de la importación:
- Registros actualizados: %d
- Registros omitidos: %d
""") % (updated_records, skipped_records)

            if errors:
                message += _("\nErrores encontrados:\n")
                message += "\n".join([f"• {error}" for error in errors[:10]])
                if len(errors) > 10:
                    message += _("\n... y %d errores más") % (len(errors) - 10)

            self.message_post(body=message)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Importación Completada'),
                    'message': _('Se actualizaron %d registros. Revise el chatter para más detalles.') % updated_records,
                    'type': 'success' if updated_records > 0 else 'warning',
                    'sticky': bool(errors),
                }
            }

        except Exception as e:
            self.state = 'error'
            _logger.error("Error durante la importación: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error en la Importación'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
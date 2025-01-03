from odoo import models, fields, api, _
import base64
import io
import pandas as pd
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class UniversalExcelImport(models.Model):
    _name = 'universal.excel.import'
    _inherit = ['mail.thread']
    _description = 'Importador Universal desde Excel'
    _order = 'id desc'

    name = fields.Char(
        string="Nombre", 
        required=True, 
        tracking=True,
        default=lambda self: _('Nueva Importación')
    )
    model_id = fields.Many2one(
        'ir.model',
        string='Modelo Destino',
        required=True,
        ondelete='cascade',
        tracking=True,
        help="Seleccione el modelo donde se crearán los registros"
    )
    identifier_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo Excel',
        required=True,
        ondelete='cascade',
        tracking=True,
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        help="Campo del modelo destino que corresponde al identificador en el Excel"
    )
    comparison_model_id = fields.Many2one(
        'ir.model',
        string='Modelo de Comparación',
        ondelete='cascade',
        tracking=True,
        help="Modelo con el que se compararán los registros (ej: alquiler)"
    )
    comparison_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo de Comparación',
        ondelete='cascade',
        tracking=True,
        domain="[('model_id', '=', comparison_model_id), ('store', '=', True)]",
        help="Campo del modelo de comparación (ej: serie)"
    )
    excel_file = fields.Binary(
        'Archivo Excel', 
        required=True, 
        help="Selecciona el archivo Excel para importar registros"
    )
    file_name = fields.Char('Nombre del archivo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Completado'),
        ('error', 'Error')
    ], string='Estado', default='draft', tracking=True)

    total_records = fields.Integer(string='Total Registros', readonly=True, tracking=True)
    processed_records = fields.Integer(string='Procesados', readonly=True, tracking=True)
    failed_records = fields.Integer(string='Fallidos', readonly=True, tracking=True)
    unique_identifiers = fields.Integer(string='Identificadores Únicos', readonly=True, tracking=True)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        """Limpiar campos dependientes al cambiar el modelo"""
        self.identifier_field_id = False
        self.comparison_model_id = False
        self.comparison_field_id = False
        _logger.debug(f"Modelo cambiado a: {self.model_id.model if self.model_id else 'None'}")

    @api.onchange('comparison_model_id')
    def _onchange_comparison_model_id(self):
        """Limpiar campo de comparación al cambiar el modelo de comparación"""
        self.comparison_field_id = False
        _logger.debug(f"Modelo de comparación cambiado a: {self.comparison_model_id.model if self.comparison_model_id else 'None'}")

    def _convert_field_value(self, field, value, index=None):
        """Convertir valores según el tipo de campo"""
        log_prefix = f"[Fila {index + 2 if index is not None else 'N/A'}] " if index is not None else ""
        try:
            if pd.isna(value):
                _logger.debug(f"{log_prefix}Valor vacío para campo {field.name}")
                return False

            _logger.debug(f"{log_prefix}Convirtiendo valor para campo {field.name} ({field.ttype}): {value}")

            # Many2one fields
            if field.ttype == 'many2one':
                if not value:
                    return False
                related_model = self.env[field.relation]
                if str(value).isdigit():
                    record = related_model.browse(int(value)).exists()
                    if record:
                        _logger.debug(f"{log_prefix}Encontrado registro por ID: {record.id}")
                        return record.id

                value = str(value).strip()
                record = related_model.search([('name', '=', value)], limit=1)
                if record:
                    _logger.debug(f"{log_prefix}Encontrado registro por nombre: {record.id}")
                    return record.id
                return False

            # Selection fields
            elif field.ttype == 'selection':
                if not value:
                    return False
                selection_options = dict(self.env[field.model]._fields[field.name].selection)
                value_str = str(value).strip().lower()
                for key, val in selection_options.items():
                    if value_str == str(val).lower() or value_str == str(key).lower():
                        _logger.debug(f"{log_prefix}Valor de selección encontrado: {key}")
                        return key
                return False

            # Numeric fields (integer, float, monetary)
            elif field.ttype in ['integer', 'float', 'monetary']:
                try:
                    if isinstance(value, (int, float)):
                        result = float(value) if field.ttype == 'float' else int(value)
                        return result
                    if isinstance(value, str):
                        clean_value = ''.join(c for c in value if c.isdigit() or c in '.-')
                        result = float(clean_value) if field.ttype == 'float' else int(float(clean_value))
                        return result
                except:
                    return 0 if field.ttype == 'integer' else 0.0

            # Boolean fields
            elif field.ttype == 'boolean':
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ['1', 'true', 'si', 'sí', 'yes', 'verdadero', 't', 'y']
                return bool(value)

            # Date and Datetime fields
            elif field.ttype in ['date', 'datetime']:
                if not value:
                    return False
                try:
                    parsed_date = pd.to_datetime(value)
                    return parsed_date.date() if field.ttype == 'date' else parsed_date
                except:
                    return False

            # Default: convert to string
            return str(value) if value else False

        except Exception as e:
            _logger.error(f"{log_prefix}Error convirtiendo valor '{value}' para campo {field.name}: {str(e)}")
            return False

    def create_records(self):
        """Método principal para crear registros desde Excel sin duplicados"""
        self.ensure_one()
        start_time = datetime.now()
        _logger.info(f"Iniciando importación: {self.name}")
        
        try:
            if not self.excel_file:
                raise ValueError(_("No se ha seleccionado ningún archivo Excel."))
    
            # Leer archivo Excel
            decoded_file = base64.b64decode(self.excel_file)
            excel_data = io.BytesIO(decoded_file)
            df = pd.read_excel(excel_data)
    
            if df.empty:
                raise ValueError(_("El archivo Excel está vacío."))
    
            # Inicializar contadores
            self.total_records = len(df)
            self.processed_records = 0
            self.failed_records = 0
    
            # Verificar campo identificador
            identifier_field_name = self.identifier_field_id.name
            if identifier_field_name not in df.columns:
                raise ValueError(_(f"El campo '{identifier_field_name}' no está presente en el Excel."))
    
            # Obtener campos del modelo
            model_fields = self.env['ir.model.fields'].search([
                ('model_id', '=', self.model_id.id),
                ('store', '=', True),
                ('readonly', '=', False)
            ])
            fields_dict = {field.name: field for field in model_fields}
    
            # Procesar registros
            target_model = self.env[self.model_id.model]
            processed_rows = []
            stats_by_identifier = {}
    
            # Pre-validar y agrupar registros por identificador
            for index, row in df.iterrows():
                identifier_value = str(row[identifier_field_name]).strip()
                if pd.isna(identifier_value):
                    self.failed_records += 1
                    _logger.error(f"Valor de identificador vacío en fila {index + 2}")
                    continue
    
                # Si es el primer registro para este identificador, procesar normalmente
                if identifier_value not in stats_by_identifier:
                    _logger.info(f"Nuevo identificador encontrado: {identifier_value}")
                    stats_by_identifier[identifier_value] = {
                        'rows': [row],
                        'index': index,
                        'records': []
                    }
                else:
                    # Si ya existe, agregar a la lista de rows para ese identificador
                    _logger.info(f"Identificador existente: {identifier_value}, agregando fila {index + 2}")
                    stats_by_identifier[identifier_value]['rows'].append(row)
    
            # Procesar cada identificador único
            for identifier_value, stats in stats_by_identifier.items():
                try:
                    _logger.info(f"Procesando identificador: {identifier_value} con {len(stats['rows'])} registros")
    
                    # Verificar registro relacionado en el modelo de comparación
                    related_record = None
                    if self.comparison_model_id and self.comparison_field_id:
                        related_record = self.env[self.comparison_model_id.model].search([
                            (self.comparison_field_id.name, '=', identifier_value)
                        ], limit=1)
    
                        if not related_record:
                            error_msg = f"No se encontró registro en {self.comparison_model_id.name} con {self.comparison_field_id.name}={identifier_value}"
                            _logger.error(error_msg)
                            self.failed_records += len(stats['rows'])
                            continue
    
                        _logger.info(f"Registro relacionado encontrado: ID {related_record.id}")
    
                    # Procesar cada fila para este identificador
                    for row in stats['rows']:
                        try:
                            record_vals = {}
                            # Procesar cada columna
                            for column in df.columns:
                                if column in fields_dict:
                                    value = self._convert_field_value(fields_dict[column], row[column])
                                    if value is not False:
                                        record_vals[column] = value
    
                            # Agregar campos relacionados
                            if related_record:
                                for field in model_fields:
                                    if (field.ttype == 'many2one' and 
                                        field.relation == self.comparison_model_id.model and
                                        field.name not in record_vals):
                                        record_vals[field.name] = related_record.id
    
                            # Crear registro
                            new_record = target_model.create(record_vals)
                            self.processed_records += 1
                            stats['records'].append(new_record.id)
                            _logger.info(f"Registro creado: ID {new_record.id}")
    
                            self.message_post(body=_(
                                f"Registro creado para {identifier_value}: ID {new_record.id}"
                            ))
    
                        except Exception as e:
                            self.failed_records += 1
                            error_msg = f"Error procesando registro para {identifier_value}: {str(e)}"
                            _logger.error(error_msg)
                            self.message_post(body=_(error_msg))
    
                except Exception as e:
                    self.failed_records += len(stats['rows'])
                    error_msg = f"Error procesando identificador {identifier_value}: {str(e)}"
                    _logger.error(error_msg)
                    self.message_post(body=_(error_msg))
    
            # Actualizar estado
            self.state = 'done' if self.processed_records > 0 else 'error'
            self.unique_identifiers = len(stats_by_identifier)
    
            # Crear mensaje resumen
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            message = f"""
    Resumen de la importación:
    - Tiempo de procesamiento: {duration:.2f} segundos
    - Total registros en Excel: {self.total_records}
    - Identificadores únicos: {self.unique_identifiers}
    - Registros creados: {self.processed_records}
    - Errores: {self.failed_records}
    
    Detalles por identificador:"""
    
            for identifier, stats in stats_by_identifier.items():
                message += f"\n- {identifier}: {len(stats['records'])} registros creados"
                message += f"\n  IDs creados: {stats['records']}"
    
            _logger.info(message)
            self.message_post(body=message)
    
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Importación Completada'),
                    'message': f'Creados {self.processed_records} registros en {duration:.2f} segundos. '
                              f'Ver chatter para más detalles.',
                    'type': 'success' if self.processed_records > 0 else 'warning',
                    'sticky': True,
                }
            }
    
        except Exception as e:
            self.state = 'error'
            error_message = f"Error general en la importación: {str(e)}"
            _logger.error(error_message)
            self.message_post(body=error_message)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error en la Importación'),
                    'message': error_message,
                    'type': 'danger',
                    'sticky': True,
                }
            }
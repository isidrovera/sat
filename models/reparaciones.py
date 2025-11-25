from odoo import _, models, fields, api, exceptions, _
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
import qrcode
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)
import requests
import json
from odoo.tools import config
from odoo.exceptions import UserError
import zipfile
import io
from odoo.http import request
import uuid

class Reparaciones(models.Model):
    _name = 'reparaciones.reparaciones'
    _description = 'Reparaciones Ventas'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Reparacion N°', default=lambda self: _('New'),
                       copy=False, readonly=True, required=True, tracking=True)
    fotos_ids = fields.One2many('reparaciones.foto', 'reparacion_id', string='Galería de Fotos')
    foto_galeria_nombre = fields.Char(string='Nombre de Carpeta')
    def action_print_reparacion_pdf(self):
        """Imprimir / descargar el PDF de la reparación"""
        self.ensure_one()
        try:
            report = self.env.ref('sat.action_report_reparaciones_ventas')
        except ValueError:
            raise UserError(_("No se encontró la acción de reporte 'sat.action_report_reparaciones_ventas'."))
        return report.report_action(self)
    @api.model_create_multi
    def create(self, vals_list):
        """ Crea una secuencia para el modelo de reparaciones y gestiona la creación de carpetas en pCloud """
        
        # ========================================
        # VALIDACIÓN PREVIA: Verificar configuración del modelo
        # ========================================
        for vals in vals_list:
            maquina_id = vals.get('maquina_id')
            if maquina_id:
                maquina = self.env['sat.sat'].browse(maquina_id)
                if maquina and maquina.name:  # maquina.name es el modelo
                    modelo = maquina.name
                    
                    # Buscar componentes y accesorios configurados
                    componentes = self.env['modelo.maquina.componente'].search_count([
                        ('modelo_id', '=', modelo.id)
                    ])
                    accesorios = self.env['modelo.maquina.accesorio'].search_count([
                        ('modelo_id', '=', modelo.id)
                    ])
                    
                    # ❌ BLOQUEAR si no tiene configuración
                    if componentes == 0 and accesorios == 0:
                        raise ValidationError(_(
                            "⚠️ Configuración Incompleta del Modelo\n\n"
                            "El modelo '%s' no tiene componentes ni accesorios configurados.\n\n"
                            "Para crear una reparación de este modelo, primero debe configurar:\n"
                            "• Componentes: Sistema de taller → Configuración → Componentes por Modelo\n"
                            "• Accesorios: Sistema de taller → Configuración → Accesorios por Modelo\n\n"
                            "Es obligatorio configurar al menos un componente o accesorio."
                        ) % modelo.name)
                    
                    # ⚠️ ADVERTIR si solo tiene uno
                    if componentes == 0:
                        raise ValidationError(_(
                            "⚠️ Modelo sin Componentes Configurados\n\n"
                            "El modelo '%s' no tiene componentes técnicos configurados.\n\n"
                            "Configure al menos los componentes básicos en:\n"
                            "Sistema de taller → Configuración → Componentes por Modelo"
                        ) % modelo.name)
                    
                    if accesorios == 0:
                        _logger.warning(f"⚠️ Modelo {modelo.name} no tiene accesorios configurados")
                        # No bloqueamos, solo advertimos en log
        
        # ========================================
        # CONTINUAR CON CREACIÓN NORMAL
        # ========================================
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('reparaciones.reparaciones') or '/'
                _logger.info("Número secuencial asignado al campo 'name': %s", vals['name'])

            if 'contometrok_id' in vals:
                vals['contometro_inicial'] = vals['contometrok_id']
                _logger.info("Asignado 'contometro_inicial' a partir de 'contometrok_id': %s", vals['contometro_inicial'])

        try:
            records = super(Reparaciones, self).create(vals_list)
            for record in records:
                _logger.info("Registro de reparación creado exitosamente con ID: %s", record.id)

                # Crear la carpeta en pCloud
                try:
                    folder_id = record.create_folder_in_pcloud()
                    record.foto_galeria_nombre = f"{record.maquina_id.name.name}_{record.serie_id or 'sin_serie'}"
                    _logger.info("Carpeta en pCloud creada o asignada correctamente para el registro ID: %s", record.id)
                except Exception as folder_error:
                    _logger.error("Error al crear la carpeta en pCloud para el registro ID %s: %s", record.id, str(folder_error))
                    raise ValidationError(_("Error al crear la carpeta en pCloud: %s") % str(folder_error))

                # Generar el código QR
                try:
                    record.sudo().generate_qr_code()
                    _logger.info("Código QR generado correctamente para el registro ID: %s", record.id)
                except Exception as qr_error:
                    _logger.error("Error al generar el código QR para el registro ID %s: %s", record.id, str(qr_error))

                # Auto-cargar evaluaciones
                try:
                    record._seed_evaluaciones_from_modelo()
                    _logger.info("Evaluaciones auto-cargadas para reparación ID: %s", record.id)
                except Exception as eval_error:
                    _logger.warning("No se pudieron auto-cargar evaluaciones para reparación ID %s: %s", record.id, str(eval_error))

            return records

        except KeyError as e:
            _logger.error("KeyError: Campo faltante o no definido - %s", str(e))
            raise ValidationError(_("Ocurrió un error al intentar crear la reparación. Verifique los campos: %s") % str(e))

        except Exception as create_error:
            _logger.error("Error durante la creación de la reparación: %s", str(create_error))
            raise

    def _seed_evaluaciones_from_modelo(self):
        """Carga automáticamente componentes y accesorios según el modelo"""
        self.ensure_one()
        
        if not self.maquina_id or not self.maquina_id.name:
            _logger.info(f"Reparación {self.id}: No tiene máquina o modelo asignado")
            return
        
        modelo = self.maquina_id.name
        _logger.info(f"Auto-cargando evaluaciones para reparación {self.id}, modelo: {modelo.name}")
        
        # ========================================
        # AUTO-CARGAR COMPONENTES
        # ========================================
        componentes_modelo = self.env['modelo.maquina.componente'].search([
            ('modelo_id', '=', modelo.id)
        ])
        
        if not componentes_modelo:
            _logger.warning(f"⚠️ Modelo {modelo.name} no tiene componentes configurados")
            return
        
        Eval = self.env['reparacion.componente.evaluacion']
        Color = self.env['color.tipo']
        componentes_creados = 0
        
        for comp_line in componentes_modelo:
            # ✅ CONVERTIR color (Selection) a color_id (Many2one)
            color_id = False
            if comp_line.color:
                # Buscar el registro de color.tipo correspondiente
                color_obj = Color.search([('code', '=', comp_line.color)], limit=1)
                if color_obj:
                    color_id = color_obj.id
                else:
                    _logger.warning(f"Color '{comp_line.color}' no encontrado en color.tipo")
            
            # Evitar duplicados
            dup_domain = [
                ('reparacion_id', '=', self.id),
                ('componente_tipo_id', '=', comp_line.tipo_id.id),
            ]
            if color_id:
                dup_domain.append(('color_id', '=', color_id))
            else:
                dup_domain.append(('color_id', '=', False))
            
            exists = Eval.search(dup_domain, limit=1)
            if exists:
                _logger.debug(f"Componente {comp_line.tipo_id.name} ({comp_line.color or 'sin color'}) ya existe, skip")
                continue
            
            # Crear evaluación
            vals = {
                'reparacion_id': self.id,
                'componente_tipo_id': comp_line.tipo_id.id,
                'color_id': color_id,
                'estado_id': comp_line.estado_sugerido_id.id if comp_line.estado_sugerido_id else False,
                'observaciones': comp_line.frase_desgaste or '',
            }
            
            try:
                Eval.create(vals)
                componentes_creados += 1
                _logger.debug(f"✓ Creado: {comp_line.tipo_id.name} ({comp_line.color or 'sin color'})")
            except Exception as e:
                _logger.error(f"Error creando evaluación para {comp_line.tipo_id.name}: {e}")
        
        _logger.info(f"✅ Creados {componentes_creados} componentes para reparación {self.id}")
        
        # ========================================
        # AUTO-CARGAR ACCESORIOS
        # ========================================
        accesorios_modelo = self.env['modelo.maquina.accesorio'].search([
            ('modelo_id', '=', modelo.id)
        ])
        
        if not accesorios_modelo:
            _logger.warning(f"⚠️ Modelo {modelo.name} no tiene accesorios configurados")
            return
        
        AccEval = self.env['reparacion.accesorio.evaluacion']
        accesorios_creados = 0
        
        for acc_line in accesorios_modelo:
            # Evitar duplicados
            exists = AccEval.search([
                ('reparacion_id', '=', self.id),
                ('tipo_id', '=', acc_line.tipo_id.id)
            ], limit=1)
            
            if exists:
                _logger.debug(f"Accesorio {acc_line.tipo_id.name} ya existe, skip")
                continue
            
            # Crear evaluación
            vals = {
                'reparacion_id': self.id,
                'tipo_id': acc_line.tipo_id.id,
                'estado_id': acc_line.estado_predeterminado_id.id if acc_line.estado_predeterminado_id else False,
                'observaciones': acc_line.nota or '',
            }
            
            try:
                AccEval.create(vals)
                accesorios_creados += 1
                _logger.debug(f"✓ Creado: {acc_line.tipo_id.name}")
            except Exception as e:
                _logger.error(f"Error creando evaluación de accesorio {acc_line.tipo_id.name}: {e}")
        
        _logger.info(f"✅ Creados {accesorios_creados} accesorios para reparación {self.id}")
        _logger.info(f"🎉 Total evaluaciones auto-cargadas: {componentes_creados + accesorios_creados}")
    # --- NUEVOS CAMPOS EN Reparaciones ---
    pcloud_folder_id = fields.Char(string='pCloud Folder ID', copy=False)
    pcloud_upload_code = fields.Char(string='pCloud Upload Code', copy=False)
    pcloud_upload_expires = fields.Datetime(string='pCloud Upload Expira', copy=False)
    pcloud_upload_maxfiles = fields.Integer(string='pCloud Max Files', copy=False)
    pcloud_upload_maxspace = fields.Integer(string='pCloud Max Bytes', copy=False)

    def _ensure_pcloud_folder(self):
        """Asegura y devuelve el folder_id en pCloud para esta reparación."""
        self.ensure_one()
        # Reutiliza tu lógica existente para crear/obtener carpeta:
        folder_id = self.pcloud_folder_id
        if not folder_id:
            folder_id = str(self.create_folder_in_pcloud())  # ya tienes create_folder_in_pcloud()
            self.pcloud_folder_id = folder_id
        return int(folder_id)

    def _ensure_upload_link(self, file_count=1, total_size=10_000_000, hours_valid=3):
        """Crea o reutiliza un upload link de pCloud (code) para subir desde el browser sin exponer token."""
        self.ensure_one()
        pcloud_config = self.env['pcloud.configuracion'].sudo().search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            raise ValidationError("Falta configuración de pCloud o access_token.")

        # Reutilizar si sigue vigente y cubre el lote actual:
        if (self.pcloud_upload_code and self.pcloud_upload_expires and
            fields.Datetime.now() < self.pcloud_upload_expires and
            (not self.pcloud_upload_maxfiles or self.pcloud_upload_maxfiles >= file_count) and
            (not self.pcloud_upload_maxspace or self.pcloud_upload_maxspace >= total_size)):
            return {
                'code': self.pcloud_upload_code,
                'expires': self.pcloud_upload_expires,
            }

        folder_id = self._ensure_pcloud_folder()

        # Crear upload link en pCloud
        import requests
        from datetime import timedelta
        expires_dt = fields.Datetime.now() + timedelta(hours=hours_valid)

        url = f"{pcloud_config.hostname}/createuploadlink"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': folder_id,
            'comment': f"Upload desde Odoo – Reparación {self.name or self.id}",
            'expire': fields.Datetime.to_string(expires_dt),
            'maxspace': int(total_size),         # bytes
            'maxfiles': int(file_count)
        }
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if resp.status_code != 200 or data.get('result') != 0:
            raise ValidationError(f"No se pudo crear upload link en pCloud: {data}")

        # Guardar para reusar
        self.write({
            'pcloud_upload_code': data.get('code'),
            'pcloud_upload_expires': expires_dt,
            'pcloud_upload_maxfiles': file_count,
            'pcloud_upload_maxspace': total_size,
        })
        return {
            'code': data.get('code'),
            'expires': expires_dt,
        }

    def create_folder_in_pcloud(self):
        """Crea una subcarpeta dentro de 'fotos_reparaciones' en pCloud."""
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            raise ValidationError(_("Falta la configuración de pCloud o el token de acceso."))

        fotos_reparaciones_id = self.get_or_create_folder_id('fotos_reparaciones')
        if not fotos_reparaciones_id:
            raise ValidationError(_("No se encontró ni se pudo crear la carpeta principal 'fotos_reparaciones'."))

        # Nombre seguro
        serie = self.serie_id if self.serie_id else 'sin_serie'
        maquina = self.maquina_id.name.name if self.maquina_id and self.maquina_id.name else 'sin_maquina'
        folder_name = f"{maquina}_{serie}".replace("/", "_").replace("\\", "_").strip()
        _logger.info("Intentando crear carpeta '%s' en pCloud dentro de 'fotos_reparaciones'", folder_name)

        # Verificar si ya existe
        existing_id = self.get_folder_id(folder_name, fotos_reparaciones_id)
        if existing_id:
            _logger.info("Carpeta '%s' ya existe en pCloud con ID %s", folder_name, existing_id)
            return existing_id

        # Crear la carpeta
        try:
            url = f"{pcloud_config.hostname}/createfolder"
            params = {
                'access_token': pcloud_config.access_token,
                'folderid': fotos_reparaciones_id,
                'name': folder_name
            }
            response = requests.get(url, params=params)
            result = response.json()
            _logger.info("Respuesta de pCloud al crear carpeta: %s", result)

            if result.get('result') == 0 and 'metadata' in result:
                return result['metadata']['folderid']
            elif result.get('result') == 2004:
                return self.get_folder_id(folder_name, fotos_reparaciones_id)
            else:
                raise ValidationError(_("Error al crear la carpeta '%s': %s") %
                                    (folder_name, result.get('error', 'Sin detalle')))
        except Exception as e:
            _logger.error("Error HTTP al crear carpeta en pCloud: %s", str(e))
            raise ValidationError(_("No se pudo crear la carpeta en pCloud: %s") % str(e))


    def get_folder_id(self, folder_name, parent_id):
        """Busca una carpeta por nombre dentro del folder_id especificado."""
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        try:
            url = f"{pcloud_config.hostname}/listfolder"
            params = {
                'access_token': pcloud_config.access_token,
                'folderid': parent_id
            }
            response = requests.get(url, params=params)
            result = response.json()

            if result.get('result') == 0:
                for item in result['metadata'].get('contents', []):
                    if item['isfolder'] and item['name'] == folder_name:
                        return item['folderid']
            return None
        except Exception as e:
            _logger.error("Error al obtener folder ID desde pCloud: %s", str(e))
            raise ValidationError(_("No se pudo obtener folder ID de pCloud: %s") % str(e))


    def get_or_create_folder_id(self, folder_name):
        """Busca o crea una carpeta directamente en la raíz de pCloud."""
        folder_id = self.get_folder_id(folder_name, 0)
        if folder_id:
            return folder_id

        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        url = f"{pcloud_config.hostname}/createfolder"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': 0,
            'name': folder_name
        }
        response = requests.get(url, params=params)
        result = response.json()

        if result.get('result') == 0 and 'metadata' in result:
            return result['metadata']['folderid']
        else:
            _logger.error("Error al crear carpeta raíz '%s': %s", folder_name, result)
            return None

    def action_open_gallery(self):
        """Abre la galería de fotos asociada a esta reparación."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/gallery/{self.id}',
            'target': 'new',  # Abrir en una nueva pestaña
        }

    
    maquina_id = fields.Many2one('sat.sat', string='Maquina',  tracking=True )
     # Restricción SQL para evitar duplicados de serie_id
    _sql_constraints = [
        ('unique_serie_id', 'unique(serie_id)', 'El número de serie ya existe.')
    ]
    

    marca = fields.Char(string='Marca', related='maquina_id.marca', readonly=True, store=True)
    importacion = fields.Char(string='Importación',
                              related='maquina_id.importacion')
    nombre_proveedor = fields.Char(
        related='maquina_id.proveedor_id.name', string="Proveedor")
    nombre_maquina = fields.Char(related='maquina_id.name.name', store=True)

    
    tipo_machine = fields.Char(string='Tipo de maquina', related='maquina_id.tipo_maquina',
                               readonly=True

                               )
   
    tipo_revision = fields.Selection(related='maquina_id.tipo_revision', readonly=True,store=True)
    ubicacion_id = fields.Selection(related='maquina_id.ubicacion_id', readonly=True, store=True)
    prioridad = fields.Selection(related='maquina_id.prioridad',readonly=True,store=True)

    estado_id = fields.Selection([('sin_revisar', 'Sin revisar'),('para_revision', 'Para revision'),('en_revision', 'En revisión'), ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), ('de_partes', 'De partes'), ('entregada', 'Entregada')],
                                 string='Estado de revisión',
                                 related='maquina_id.estado_ventas_id',
                                 readonly=False,
                                         store=True,                                         
                                 )
    serie_id = fields.Char(string='Serie', related='maquina_id.serie_id', readonly=False, store=True )
    # Campos de estado físico exterior
    tapas_id = fields.Selection([
        ('blancas', 'Carcasa Original Color Blanco - Todo el Contorno en Buen Estado'),
        ('amarillas', 'Carcasa Color Amarillo por Desgaste - Todo el Contorno Afectado'),
        ('rotas', 'Carcasa con Daños o Roturas en Alguna Sección del Contorno'),
        ('le_faltan', 'Carcasa con Piezas Faltantes en el Contorno'),
        ('no_aplica', 'Evaluación de Carcasa No Aplicable')
    ], string='Estado General de la Carcasa', tracking=True)

    panel_id = fields.Selection([
        ('blanco', 'Panel de Control Color Blanco Original Sin Desgaste'),
        ('amarillo', 'Panel de Control Amarillento por Uso y Exposición'),
        ('no_aplica', 'Evaluación de Panel No Aplicable')
    ], string='Estado del Panel de Control', tracking=True)

    # Componentes básicos y accesorios
    lct_id = fields.Selection([
        ('si', 'Bandeja LCT Presente y en Condiciones Operativas'),
        ('no', 'Bandeja LCT No Instalada o Faltante')
    ], string='Bandeja de Alta Capacidad (LCT)', tracking=True)

    ot_id = fields.Selection([
        ('si', 'Bandeja de Salida OT Instalada y Funcional'),
        ('no', 'Bandeja de Salida OT No Presente')
    ], string='Estado Bandeja de Salida OT', tracking=True)

    hdd_id = fields.Selection([
        ('si', 'Disco Duro Interno Instalado y Operativo'),
        ('no', 'Sin Disco Duro Interno Instalado')
    ], string='Estado del Disco Duro', tracking=True)

    tipo_id = fields.Selection([
        ('color', 'Equipo Multifuncional a Color (CMYK)'),
        ('monocromatica', 'Equipo Multifuncional Monocromático')
    ], string='Tipo de Sistema Multifuncional', related='maquina_id.tipo_id', readonly=True)

    tray_id = fields.Char("Número Total de Bandejas de Papel Instaladas", tracking=True)

    # Componentes de alimentación de documentos
    adf_simple_id = fields.Selection([
        ("si", "Alimentador de Documentos Simple Instalado y Funcional"),
        ("no", "Sin Alimentador de Documentos Simple")
    ], string="Alimentador Automático Simple", tracking=True)

    adf_dual_id = fields.Selection([
        ("si", "Alimentador Dual Scan Instalado y Operativo"),
        ("no", "Sin Sistema de Escaneo Dual")
    ], string="Alimentador Automático Doble Cara", tracking=True)
    # Sistemas de finalizado y accesorios
    finalizador_interno_id = fields.Selection([
        ("si", "Finalizador Interno Instalado y en Funcionamiento"),
        ("no", "Sin Finalizador Interno")
    ], string="Sistema de Finalizado Interno", tracking=True)

    finalizador_externo_id = fields.Selection([
        ("si", "Finalizador Externo Instalado y en Funcionamiento"),
        ("no", "Sin Finalizador Externo")
    ], string="Sistema de Finalizado Externo", tracking=True)

    mueble_id = fields.Selection([
        ("si", "Mueble Base Original Instalado y Estable"),
        ("no", "Sin Mueble Base")
    ], string="Estado del Mueble Base", tracking=True)

    # Tipos de panel y conectividad
    panel_smart_id = fields.Selection([
        ("si", "Panel Smart Touch Instalado y Respondiendo"),
        ("no", "Sin Panel Smart Touch")
    ], string="Panel Táctil Inteligente", tracking=True)

    panel_normal_id = fields.Selection([
        ("si", "Panel LCD Estándar Instalado y Funcionando"),
        ("no", "Sin Panel LCD Estándar")
    ], string="Panel LCD Básico", tracking=True)

    wi_fi_id = fields.Selection([
        ("si", "Módulo Wi-Fi Instalado y Conectando"),
        ("no", "Sin Capacidad Wi-Fi")
    ], string="Conectividad Inalámbrica", tracking=True)

    cable_poder_id = fields.Selection([
        ("si", "Cable de Alimentación Original en Buen Estado"),
        ("no", "Cable de Alimentación Ausente")
    ], string="Cable de Alimentación Principal", tracking=True)
    # Estado de tóners y consumibles
    toner_black_id = fields.Selection([
        ("nuevo", "Tóner Negro Nuevo - Capacidad al 100%"),
        ("regular", "Tóner Negro en Uso - Aproximadamente 50%"),
        ("bajo", "Tóner Negro en Uso - Aproximadamente 25%"),
        ("vacio", "Tóner Negro Agotado - 0% Restante"),
        ("sin_botella", "Contenedor de Tóner Negro No Instalado")
    ], string="Estado Tóner Negro", tracking=True)

    toner_magenta_id = fields.Selection([
        ("nuevo", "Tóner Magenta Nuevo - Capacidad al 100%"),
        ("regular", "Tóner Magenta en Uso - Aproximadamente 50%"),
        ("bajo", "Tóner Magenta en Uso - Aproximadamente 25%"),
        ("vacio", "Tóner Magenta Agotado - 0% Restante"),
        ("sin_botella", "Contenedor de Tóner Magenta No Instalado"),
        ("no_aplica", "Tóner Magenta No Aplica en Este Modelo")
    ], string="Estado Tóner Magenta", tracking=True)

    toner_cyan_id = fields.Selection([
        ("nuevo", "Tóner Cyan Nuevo - Capacidad al 100%"),
        ("regular", "Tóner Cyan en Uso - Aproximadamente 50%"),
        ("bajo", "Tóner Cyan en Uso - Aproximadamente 25%"),
        ("vacio", "Tóner Cyan Agotado - 0% Restante"),
        ("sin_botella", "Contenedor de Tóner Cyan No Instalado"),
        ("no_aplica", "Tóner Cyan No Aplica en Este Modelo")
    ], string="Estado Tóner Cyan", tracking=True)

    toner_yellow_id = fields.Selection([
        ("nuevo", "Tóner Amarillo Nuevo - Capacidad al 100%"),
        ("regular", "Tóner Amarillo en Uso - Aproximadamente 50%"),
        ("bajo", "Tóner Amarillo en Uso - Aproximadamente 25%"),
        ("vacio", "Tóner Amarillo Agotado - 0% Restante"),
        ("sin_botella", "Contenedor de Tóner Amarillo No Instalado"),
        ("no_aplica", "Tóner Amarillo No Aplica en Este Modelo")
    ], string="Estado Tóner Amarillo", tracking=True)
    # Estado de funciones principales
    copia_id = fields.Selection([
        ("correcto", "Función de Copiado Funcionando Correctamente"),
        ("sin_probar", "Función de Copiado Sin Verificación"),
        ("falla", "Función de Copiado Presenta Errores")
    ], string="Funcionalidad de Copiado", tracking=True)

    impresion_id = fields.Selection([
        ("correcto", "Función de Impresión en Red Operativa"),
        ("sin_probar", "Función de Impresión Sin Verificación"),
        ("falla", "Función de Impresión con Errores"),
        ("no_aplica", "Función de Impresión No Disponible")
    ], string="Funcionalidad de Impresión", tracking=True)

    impresion_usb_id = fields.Selection([
        ("correcto", "Impresión desde USB Funcionando"),
        ("sin_probar", "Impresión USB Sin Verificación"),
        ("falla", "Impresión USB con Errores"),
        ("no_aplica", "Impresión USB No Disponible")
    ], string="Funcionalidad Impresión USB", tracking=True)

    # Funcionalidades de escaneo
    scaner_smb_id = fields.Selection([
        ("correcto", "Escaneo a Carpeta de Red Funcionando"),
        ("sin_probar", "Escaneo a Red Sin Verificación"),
        ("falla", "Escaneo a Red con Errores"),
        ("no_aplica", "Escaneo a Red No Disponible")
    ], string="Funcionalidad Escaneo a Red", tracking=True)

    scaner_usb_id = fields.Selection([
        ("correcto", "Escaneo a USB Funcionando"),
        ("sin_probar", "Escaneo a USB Sin Verificación"),
        ("falla", "Escaneo a USB con Errores"),
        ("no_aplica", "Escaneo a USB No Disponible")
    ], string="Funcionalidad Escaneo a USB", tracking=True)

    scaner_ftp_id = fields.Selection([
        ("correcto", "Escaneo a FTP Funcionando"),
        ("sin_probar", "Escaneo a FTP Sin Verificación"),
        ("falla", "Escaneo a FTP con Errores"),
        ("no_aplica", "Escaneo a FTP No Disponible")
    ], string="Funcionalidad Escaneo a FTP", tracking=True)

    scaner_mail_id = fields.Selection([
        ("correcto", "Escaneo a Email Funcionando"),
        ("sin_probar", "Escaneo a Email Sin Verificación"),
        ("falla", "Escaneo a Email con Errores"),
        ("no_aplica", "Escaneo a Email No Disponible")
    ], string="Funcionalidad Escaneo a Email", tracking=True)
    # Estado de bandejas y alimentador
    adf_id = fields.Selection([
        ("sin_revisar", "ADF Pendiente de Revisión Técnica"),
        ("mantenimiento", "ADF Necesita Mantenimiento Preventivo"),
        ("cambio_de_repuestos", "ADF Requiere Reemplazo de Componentes"),
        ("revisado", "ADF Verificado y Funcionando"),
        ("no_aplica", "ADF No Presente en Este Modelo")
    ], string="Estado del Alimentador Automático", tracking=True)

    tray1_id = fields.Selection([
        ("sin_revisar", "Bandeja 1 Pendiente de Revisión"),
        ("revisado", "Bandeja 1 Verificada y Operativa")
    ], string="Estado Bandeja Principal", tracking=True)

    tray2_id = fields.Selection([
        ("sin_revisar", "Bandeja 2 Pendiente de Revisión"),
        ("revisado", "Bandeja 2 Verificada y Operativa"),
        ("no_aplica", "Bandeja 2 No Instalada")
    ], string="Estado Segunda Bandeja", tracking=True)

    tray3_id = fields.Selection([
        ("sin_revisar", "Bandeja 3 Pendiente de Revisión"),
        ("revisado", "Bandeja 3 Verificada y Operativa"),
        ("no_aplica", "Bandeja 3 No Instalada")
    ], string="Estado Tercera Bandeja", tracking=True)

    tray4_id = fields.Selection([
        ("sin_revisar", "Bandeja 4 Pendiente de Revisión"),
        ("revisado", "Bandeja 4 Verificada y Operativa"),
        ("no_aplica", "Bandeja 4 No Instalada")
    ], string="Estado Cuarta Bandeja", tracking=True)

    bypass_id = fields.Selection([
        ("sin_revisar", "Bypass Pendiente de Revisión"),
        ("revisado", "Bypass Verificado y Operativo"),
        ("no_aplica", "Bypass No Instalado")
    ], string="Estado Bandeja Bypass", tracking=True)

    finalizador_id = fields.Selection([
        ("sin_revisar", "Finalizador Pendiente de Revisión"),
        ("revisado", "Finalizador Verificado y Operativo"),
        ("no_aplica", "Sin Sistema de Finalizado")
    ], string="Estado Sistema Finalizador", tracking=True)
    # Unidades de imagen y developers negro
    black_id = fields.Selection([
        ('requiere_cambio', 'Unidad de Imagen Negro Requiere Reemplazo Urgente'),
        ('nuevo', 'Unidad de Imagen Negro Nueva - 100% Vida Útil'),
        ('regular', 'Unidad de Imagen Negro con Desgaste Normal - 50% Vida Útil'),
        ('gastada_pero_puede_trabajar', 'Unidad de Imagen Negro Desgastada pero Funcional - 25% Vida Útil')
    ], string="Estado Unidad de Imagen Negro", tracking=True)

    developerk_id = fields.Selection([
        ('requiere_cambio', 'Developer Negro Requiere Reemplazo Urgente'),
        ('nuevo', 'Developer Negro Nuevo - 100% Rendimiento'),
        ('regular', 'Developer Negro con Desgaste Normal - 50% Rendimiento'),
        ('gastada_pero_puede_trabajar', 'Developer Negro Desgastado pero Funcional - 25% Rendimiento')
    ], string="Estado Developer Negro", tracking=True)

    # Unidades de imagen y developers magenta
    magenta_id = fields.Selection([
        ('requiere_cambio', 'Unidad de Imagen Magenta Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Modelo Monocromático'),
        ('nuevo', 'Unidad de Imagen Magenta Nueva - 100% Vida Útil'),
        ('regular', 'Unidad de Imagen Magenta con Desgaste Normal - 50% Vida Útil'),
        ('gastada_pero_puede_trabajar', 'Unidad de Imagen Magenta Desgastada pero Funcional - 25% Vida Útil')
    ], string="Estado Unidad de Imagen Magenta", tracking=True)

    developerm_id = fields.Selection([
        ('requiere_cambio', 'Developer Magenta Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Modelo Monocromático'),
        ('nuevo', 'Developer Magenta Nuevo - 100% Rendimiento'),
        ('regular', 'Developer Magenta con Desgaste Normal - 50% Rendimiento'),
        ('gastada_pero_puede_trabajar', 'Developer Magenta Desgastado pero Funcional - 25% Rendimiento')
    ], string="Estado Developer Magenta", tracking=True)

    # Unidades de imagen y developers cyan
    cyan_id = fields.Selection([
        ('requiere_cambio', 'Unidad de Imagen Cyan Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Modelo Monocromático'),
        ('nuevo', 'Unidad de Imagen Cyan Nueva - 100% Vida Útil'),
        ('regular', 'Unidad de Imagen Cyan con Desgaste Normal - 50% Vida Útil'),
        ('gastada_pero_puede_trabajar', 'Unidad de Imagen Cyan Desgastada pero Funcional - 25% Vida Útil')
    ], string="Estado Unidad de Imagen Cyan", tracking=True)

    developerc_id = fields.Selection([
        ('requiere_cambio', 'Developer Cyan Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Modelo Monocromático'),
        ('nuevo', 'Developer Cyan Nuevo - 100% Rendimiento'),
        ('regular', 'Developer Cyan con Desgaste Normal - 50% Rendimiento'),
        ('gastada_pero_puede_trabajar', 'Developer Cyan Desgastado pero Funcional - 25% Rendimiento')
    ], string="Estado Developer Cyan", tracking=True)

    # Unidades de imagen y developers amarillo
    yellow_id = fields.Selection([
        ('requiere_cambio', 'Unidad de Imagen Amarillo Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Modelo Monocromático'),
        ('nuevo', 'Unidad de Imagen Amarillo Nueva - 100% Vida Útil'),
        ('regular', 'Unidad de Imagen Amarillo con Desgaste Normal - 50% Vida Útil'),
        ('gastada_pero_puede_trabajar', 'Unidad de Imagen Amarillo Desgastada pero Funcional - 25% Vida Útil')
    ], string="Estado Unidad de Imagen Amarillo", tracking=True)

    developery_id = fields.Selection([
        ('requiere_cambio', 'Developer Amarillo Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Modelo Monocromático'),
        ('nuevo', 'Developer Amarillo Nuevo - 100% Rendimiento'),
        ('regular', 'Developer Amarillo con Desgaste Normal - 50% Rendimiento'),
        ('gastada_pero_puede_trabajar', 'Developer Amarillo Desgastado pero Funcional - 25% Rendimiento')
    ], string="Estado Developer Amarillo", tracking=True)
    calidad_id = fields.Selection([
    ("buena", "Calidad de Impresión Óptima - Cumple Estándares"),
    ("regular", "Calidad de Impresión Aceptable - Requiere Ajustes"),
    ("mala", "Calidad de Impresión Deficiente - Requiere Atención Inmediata")
    ], string="Nivel de Calidad de Impresión", tracking=True)
    # Sistema óptico y transfer
    optico_id = fields.Selection([
        ("sin_revisar", "Sistema Óptico Pendiente de Revisión Técnica"),
        ("mantenimiento", "Sistema Óptico Requiere Limpieza y Mantenimiento"),
        ("revisado", "Sistema Óptico Revisado y Calibrado Correctamente")
    ], string="Estado Sistema Óptico", tracking=True)

    transfer_id = fields.Selection([
        ('requiere_cambio', 'Banda de Transferencia Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Este Modelo'),
        ('nuevo', 'Banda de Transferencia Nueva - 100% Vida Útil'),
        ('regular', 'Banda de Transferencia con Desgaste Normal - 50% Vida Útil'),
        ('gastada_pero_puede_trabajar', 'Banda de Transferencia Desgastada pero Operativa - 25% Vida Útil')
    ], string="Estado Banda de Transferencia", tracking=True)
    calor_id = fields.Selection([
        ('requiere_cambio', 'Rodillo de Calor Requiere Reemplazo Urgente'),
        ('no_aplica', 'No Aplica en Este Modelo'),
        ('nuevo', 'Rodillo de Calor Nuevo - 100% Vida Útil'),
        ('regular', 'Rodillo de Calor con Desgaste Normal - 50% Vida Útil'),
        ('gastada_pero_puede_trabajar', 'Rodillo de Calor Desgastado pero Operativo - 25% Vida Útil')
    ], string="Estado Rodillo de Calor", tracking=True)
    tacho_id = fields.Selection([
        ("si", "Contenedor de Residuos Instalado y en Buen Estado"),
        ("no", "Contenedor de Residuos Faltante o Dañado"),
        ("no_aplica", "No Requiere Contenedor de Residuos")
    ], string="Estado Contenedor de Residuos de Tóner", tracking=True)
    fusora_id = fields.Selection([
        ('requiere_cambio', 'Faja Fusora Requiere Reemplazo Inmediato'),
        ('nuevo', 'Faja Fusora Nueva'),
        ('regular', 'Faja Fusora en Estado Regular'),
        ('gastada_pero_puede_trabajar', 'Faja Fusora Desgastada pero Operativa'),
        ("no_aplica", "No Aplica")
    ], string="Estado Faja Fusora", tracking=True)
    rodillo_id = fields.Selection([
        ('requiere_cambio', 'Rodillo de Presión Requiere Reemplazo Inmediato'),
        ('nuevo', 'Rodillo de Presión Nuevo'),
        ('regular', 'Rodillo de Presión Estado Regular'),
        ('gastada_pero_puede_trabajar', 'Rodillo de Presión Desgastado pero Operativo'),
        ("no_aplica", "No Aplica")
    ], string="Estado Rodillo de Presión", tracking=True)

    foto_problema = fields.Binary(related='maquina_id.foto_problema', string="Foto de problema")
    # Campo de descripción
    informe = fields.Html(string='Descripción Detallada de la Revisión')
    contometrok_id = fields.Char(string="Contometro", related='maquina_id.contometro', readonly=False, store=True,  tracking=True)
    contometro_inicial = fields.Char(string="Contometro Inicial", readonly=True, tracking=True )
    responsable_id = fields.Many2one( 'res.users', string='Responsable', tracking=True )
    nombre_responsable  = fields.Char(related='responsable_id.name', string='Nombre responsable',store=True )
    cliente_id = fields.Many2one('res.partner', string='Cliente', related='maquina_id.cliente_id', readonly=True, store=True, tracking=True)
    
    falla_proveedor = fields.Html(string="Descripción")
    falla_ventas = fields.Text(string='Descripción',related='maquina_id.descripcion',readonly=False, store=True)
    responsable_mobile_clean = fields.Char(string='Número de celular (limpio)', compute='_compute_responsable_mobile_clean', store=True )
    asesora_id  = fields.Char(related='maquina_id.asesora_id',string='Asesora')
    
    fecha_finalizacion = fields.Datetime(string='Fecha de Finalización', readonly=True, store=True)
   
    asesora_mobile_clean = fields.Char(
        string='Número de celular asesora (limpio)',
        compute='_compute_asesora_mobile_clean',
        store=True
    )

   
    @api.depends('maquina_id.cliente_id.asesora_id.mobile')
    def _compute_asesora_mobile_clean(self):
        for record in self:
            if record.maquina_id.cliente_id.asesora_id.mobile:
                phone = record.maquina_id.cliente_id.asesora_id.mobile.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.asesora_mobile_clean = phone
            else:
                record.asesora_mobile_clean = ''


    qr_code_ventas = fields.Binary(string='QR Code Relacionado', related='maquina_id.qr_image', readonly=True)
    

    qr_image = fields.Binary("QR Image", compute="generate_qr_code", attachment=True, store=True)
    qr_url = fields.Char("QR URL", compute="generate_qr_code", store=True)

    @api.depends('name')
    def generate_qr_code(self):
        for record in self:
            try:
                _logger.info("Generating QR code for record ID: %s", record.id)
                url = self.generate_record_url(record)
                _logger.info("Generated URL for record ID %s: %s", record.id, url)
                record.qr_url = url

                if not url:
                    _logger.error("No URL generated for record %s", record.id)
                    continue

                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4
                )
                qr.add_data(url)
                qr.make(fit=True)

                img = qr.make_image(fill_color="black", back_color="white")
                temp = BytesIO()
                img.save(temp, format="PNG")
                temp.seek(0)
                qr_base64 = base64.b64encode(temp.read()).decode('utf-8')
                record.qr_image = qr_base64

                _logger.info("QR code generated and stored for record %s", record.id)

            except Exception as e:
                _logger.error("Error generating QR code for record %s: %s", record.id, str(e))

    @api.model
    def generate_record_url(self, record):
        """Genera la URL completa para acceder al registro"""
        try:
            base_url = self.get_base_url()
            action_id = self.env.ref('sat.action_reparaciones_window').id
            menu_id = self.env.ref('sat.reparaciones').id
            url = f"{base_url}/web#id={record.id}&view_type=form&model=reparaciones.reparaciones&action={action_id}&menu_id={menu_id}"
            return url
        except Exception as e:
            _logger.error("Error generating URL: %s", str(e))
            return ""

    def action_generate_qr_for_all(self):
        all_records = self.search([])
        for record in all_records:
            record.generate_qr_code()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
          
                
    
            
    def write(self, vals):
        finalizado = vals.get('estado_id') == 'finalizado'
        if finalizado:
            for rec in self:
                if rec.estado_id == 'en_revision':
                    vals['fecha_finalizacion'] = fields.Datetime.now()

        res = super(Reparaciones, self).write(vals)

        if 'falla_proveedor' in vals:
            for rec in self:
                existing_record = rec.env['fallas'].search([
                    ('name', '=', rec.maquina_id.invoice),
                    ('modelo_id', '=', rec.maquina_id.name.name),
                    ('importacion', '=', rec.maquina_id.importacion),
                    ('proveedor_id', '=', rec.maquina_id.proveedor_id.name),
                    ('marca', '=', rec.maquina_id.marca),
                    ('serie', '=', rec.maquina_id.serie_id),
                    ('usuario_id', '=', rec.responsable_id.name),
                ], limit=1)
                if existing_record:
                    existing_record.write({
                        'descripcion': rec.falla_proveedor,
                        'foto': rec.foto_problema,  # Agregamos el campo foto
                    })
                else:
                    rec.env['fallas'].create({
                        'descripcion': rec.falla_proveedor,
                        'name': rec.maquina_id.invoice,
                        'modelo_id': rec.maquina_id.name.name,
                        'importacion': rec.maquina_id.importacion,
                        'proveedor_id': rec.maquina_id.proveedor_id.name,
                        'marca': rec.maquina_id.marca,
                        'serie': rec.maquina_id.serie_id,
                        'usuario_id': rec.responsable_id.name,
                        'foto': rec.foto_problema,  # Agregamos el campo foto
                    })

        return res
        

  
    def generate_pdf_report_url(self):
        # Obtener el reporte
        report = self.env.ref('sat.report_reparaciones_ventas')
        
        if not report:
            raise UserError("No se encontró el reporte especificado.")
        
        # Obtener la URL base
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        
        # Generar la URL del PDF
        pdf_url = f"{base_url}/report/pdf/sat.report_reparaciones_ventas/{self.id}?cid=1"

        return pdf_url


    

    autorizacion_cambio_digitos = fields.Boolean(related='maquina_id.autorizacion_cambio_digitos',readonly=False, string="Autorización de Modificación")
            
    
    autenticacion_correcta = fields.Boolean(string="Autenticación Correcta", default=False)
    def get_base_url(self):
        """Obtener la URL base del sistema"""
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    def _create_next_reparacion(self):
        _logger.info('Inicio de la función _create_next_reparacion para el registro con ID %s', self.id)

        # Verificar si el técnico tiene algún registro en estado 'en_revision'
        if self.env['reparaciones.reparaciones'].search_count([('responsable_id', '=', self.responsable_id.id), ('estado_id', '=', 'en_revision')]) > 0:
            _logger.info('El técnico con ID %s ya tiene un registro en estado "en_revision". Saliendo de la función.', self.responsable_id.id)
            return

        # Buscar la siguiente máquina en estado 'para_revision'
        next_maquina = self.env['sat.sat'].search([
            ('estado_ventas_id', '=', 'para_revision'),
            ('contometro', '!=', False),
            ('contometro', '!=', '0')
        ], order='fecha_para_revision asc', limit=1)

        if not next_maquina:
            _logger.info('No se encontró ninguna máquina en estado "para_revision", buscando máquinas "sin_revisar" y disponibles en ubicaciones específicas.')
            next_maquina = self.env['sat.sat'].search([
                ('estado_ventas_id', '=', 'sin_revisar'),
                ('disponibilidad_id', '=', 'disponible'),
                ('ubicacion_id', 'in', ['primer_piso', 'tercer_piso']),
                ('contometro', '!=', False),
                ('contometro', '!=', '0')
            ], order='create_date asc', limit=1)

        if next_maquina:
            _logger.info('Máquina seleccionada con ID %s para revisión.', next_maquina.id)
            
            # La verificación del contómetro ya no es necesaria aquí porque está incluida en las búsquedas

            # Verificar duplicado de serie_id
            existing_record = self.env['reparaciones.reparaciones'].search([('serie_id', '=', next_maquina.serie_id)])
            if existing_record:
                _logger.error('Ya existe un registro con el serie_id %s', next_maquina.serie_id)
                _logger.info('No se creará una nueva reparación debido a serie duplicada. Finalizando proceso.')
                return  # En lugar de lanzar error, simplemente salimos

            empleado = self.env['hr.employee'].search([('user_id', '=', self.responsable_id.id)], limit=1)
            if empleado:
                _logger.info('Empleado encontrado con ID %s vinculado al usuario responsable.', empleado.id)
                next_maquina.write({
                    'estado_ventas_id': 'en_revision',
                    'trabajadores_id': empleado.id
                })
                _logger.info('Estado de la máquina con ID %s actualizado a "en_revision" y asignado al empleado con ID %s.', next_maquina.id, empleado.id)
                
                nueva_reparacion = self.env['reparaciones.reparaciones'].create({
                    'maquina_id': next_maquina.id,
                    'responsable_id': self.responsable_id.id,
                    'contometro_inicial': next_maquina.contometro,
                    'contometrok_id': next_maquina.contometro
                })
                _logger.info('Nueva reparación creada con ID %s.', nueva_reparacion.id)
                
                nueva_reparacion.enviar_mensaje_whatsapp_reparaciones()
                _logger.info('Mensaje de WhatsApp enviado para la reparación con ID %s.', nueva_reparacion.id)
            else:
                _logger.error('El responsable con ID %s no está vinculado a ningún empleado.', self.responsable_id.id)
                _logger.info('No se creará una nueva reparación debido a falta de empleado. Finalizando proceso.')
                return  # En lugar de lanzar error, simplemente salimos
        else:
            _logger.info('No se encontró ninguna máquina que cumpla con los criterios de selección.')
    
    
    def action_finalizar_reparacion(self):
        """
        Finaliza la reparación validando todos los requisitos necesarios.
        
        Validaciones realizadas:
        - Campos básicos: informe y calidad
        - Evaluaciones de componentes completadas
        - Evaluaciones de accesorios completadas
        - Contómetro actualizado y validado
        - Mínimo de fotos requeridas
        - Autenticación del usuario
        """
        self.ensure_one()
        
        _logger.info(f"Iniciando proceso de finalización para reparación ID: {self.id}")
        
        # ====== VALIDACIONES DE CAMPOS BÁSICOS ======
        self._validar_campos_basicos()
        
        # ====== VALIDACIONES DE EVALUACIONES ======
        self._validar_evaluaciones_componentes()
        self._validar_evaluaciones_accesorios()
        
        # ====== VALIDACIÓN DE AUTENTICACIÓN ======
        if not self._validar_autenticacion():
            return self._abrir_wizard_autenticacion()
        
        # ====== VALIDACIÓN DE CONTÓMETRO ======
        self._validar_contometro()
        
        # ====== VALIDACIÓN DE FOTOS ======
        self._validar_fotos_minimas()
        
        # ====== PROCESO DE FINALIZACIÓN ======
        _logger.info(f"Todas las validaciones pasaron. Procediendo con la finalización.")
        
        # Usar sudo() solo para operaciones específicas
        self_sudo = self.sudo()
        
        # Generar reporte QR (no crítico si falla)
        self._generar_reporte_qr()
        
        # Enviar notificaciones (registrar errores pero no detener)
        self._enviar_notificaciones()
        
        # Cambiar estado a finalizado
        _logger.info(f"Cambiando estado a 'finalizado' para reparación ID: {self.id}")
        self_sudo.estado_id = "finalizado"
        _logger.info(f"Estado cambiado exitosamente a 'finalizado'")
        
        # Crear siguiente reparación
        try:
            _logger.info(f"Creando siguiente reparación para reparación ID: {self.id}")
            self_sudo._create_next_reparacion()
            _logger.info(f"Siguiente reparación creada exitosamente")
        except Exception as e:
            _logger.error(f"Error creando siguiente reparación para ID {self.id}: {e}")
        
        _logger.info(f"Proceso de finalización completado exitosamente para reparación ID: {self.id}")
        
        # Retornar a la vista de lista
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'list',
            'res_model': 'reparaciones.reparaciones',
            'view_id': False,
            'target': 'main',
        }


    def _validar_campos_basicos(self):
        """Valida que los campos básicos estén completados"""
        self.ensure_one()
        
        campos_faltantes = []
        
        if not self.informe or not self.informe.strip():
            campos_faltantes.append('Informe')
        
        if not self.calidad_id:
            campos_faltantes.append('Calidad')
        
        if campos_faltantes:
            raise ValidationError(_(
                "❗ <b>Campos Requeridos Incompletos</b>\n\n"
                "Para finalizar la reparación, debes completar los siguientes campos:\n"
                "• %s"
            ) % "\n• ".join(campos_faltantes))
        
        _logger.info(f"Validación de campos básicos completada para reparación ID: {self.id}")


    def _validar_evaluaciones_componentes(self):
        """Valida que todos los componentes tengan estado completado"""
        self.ensure_one()
        
        evaluaciones_componentes = self.env['reparacion.componente.evaluacion'].search([
            ('reparacion_id', '=', self.id)
        ])
        
        if not evaluaciones_componentes:
            _logger.warning(f"No se encontraron evaluaciones de componentes para reparación ID: {self.id}")
            return
        
        sin_estado = evaluaciones_componentes.filtered(lambda e: not e.estado_id)
        
        if sin_estado:
            nombres_faltantes = []
            for evaluacion in sin_estado:
                nombre = evaluacion.componente_tipo_id.name
                if evaluacion.color_id:
                    nombre += f" ({evaluacion.color_id.name})"
                nombres_faltantes.append(nombre)
            
            raise ValidationError(_(
                "❗ <b>Evaluación de Componentes Incompleta</b>\n\n"
                "Para finalizar la reparación, debes completar el estado de los siguientes componentes:\n"
                "• %s"
            ) % "\n• ".join(nombres_faltantes))
        
        _logger.info(f"Validación de componentes completada: {len(evaluaciones_componentes)} componentes evaluados")


    def _validar_evaluaciones_accesorios(self):
        """Valida que todos los accesorios tengan estado completado"""
        self.ensure_one()
        
        evaluaciones_accesorios = self.env['reparacion.accesorio.evaluacion'].search([
            ('reparacion_id', '=', self.id)
        ])
        
        if not evaluaciones_accesorios:
            _logger.warning(f"No se encontraron evaluaciones de accesorios para reparación ID: {self.id}")
            return
        
        sin_estado = evaluaciones_accesorios.filtered(lambda e: not e.estado_id)
        
        if sin_estado:
            nombres_faltantes = [e.tipo_id.name for e in sin_estado]
            
            raise ValidationError(_(
                "❗ <b>Evaluación de Accesorios Incompleta</b>\n\n"
                "Para finalizar la reparación, debes completar el estado de los siguientes accesorios:\n"
                "• %s"
            ) % "\n• ".join(nombres_faltantes))
        
        _logger.info(f"Validación de accesorios completada: {len(evaluaciones_accesorios)} accesorios evaluados")


    def _validar_autenticacion(self):
        """Verifica si el usuario necesita autenticación"""
        if self.autenticacion_correcta:
            return True
        
        try:
            grupo_validacion = self.env.ref('sat.sat_tecnica_group_user')
            necesita_autenticacion = grupo_validacion in self.env.user.groups_id
            
            if necesita_autenticacion:
                _logger.info(f"Usuario {self.env.user.name} requiere autenticación")
            
            return not necesita_autenticacion
        except Exception as e:
            _logger.error(f"Error verificando grupo de autenticación: {e}")
            return True


    def _abrir_wizard_autenticacion(self):
        """Abre el wizard de autenticación"""
        _logger.info(f"Abriendo wizard de autenticación para usuario {self.env.user.name}")
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'reparacion.autenticacion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_reparacion_id': self.id},
        }


    def _normalizar_contometro(self, valor):
        """
        Normaliza el valor del contómetro eliminando caracteres no numéricos.
        
        Args:
            valor: Valor del contómetro (puede contener comas, puntos, espacios, letras)
        
        Returns:
            str: Solo los dígitos numéricos
        """
        if not valor:
            return ""
        
        import re
        valor_limpio = re.sub(r'[^\d]', '', str(valor))
        
        return valor_limpio


    def _validar_contometro(self):
        """
        Valida que el contómetro haya sido actualizado correctamente con lógica inteligente
        que considera las actualizaciones de SNMP durante la reparación.
        """
        self.ensure_one()
        
        # ====== VALIDACIÓN INICIAL ======
        if not self.contometrok_id or not self.contometro_inicial:
            raise UserError(_(
                "❗ <b>Error en el Contómetro</b>\n\n"
                "Los valores del contómetro no están configurados correctamente.\n"
                "Verifique e intente nuevamente."
            ))
        
        # ====== NORMALIZAR VALORES ======
        contometro_tecnico = self._normalizar_contometro(self.contometrok_id)
        contometro_inicial = self._normalizar_contometro(self.contometro_inicial)
        contometro_maquina_actual = self._normalizar_contometro(self.maquina_id.contometro)
        
        _logger.info(f"[Validación Contador] Reparación ID: {self.id}")
        _logger.info(f"[Validación Contador] Inicial: {contometro_inicial}")
        _logger.info(f"[Validación Contador] Técnico ingresó: {contometro_tecnico}")
        _logger.info(f"[Validación Contador] Máquina actual (SNMP): {contometro_maquina_actual}")
        
        # ====== VALIDAR FORMATO ======
        if not contometro_tecnico or not contometro_inicial:
            raise UserError(_(
                "❗ <b>Error en el Contómetro</b>\n\n"
                "Los valores del contómetro no contienen números válidos.\n"
                "Contómetro ingresado: %s\n"
                "Contómetro inicial: %s"
            ) % (self.contometrok_id, self.contometro_inicial))
        
        # ====== CONVERTIR A ENTEROS ======
        try:
            contador_tecnico_int = int(contometro_tecnico)
            contador_inicial_int = int(contometro_inicial)
            contador_maquina_int = int(contometro_maquina_actual)
        except ValueError as e:
            _logger.error(f"Error convirtiendo contómetros a enteros: {e}")
            raise UserError(_(
                "❗ <b>Error en el Contómetro</b>\n\n"
                "Los valores del contómetro contienen caracteres inválidos.\n"
                "Solo se permiten números."
            ))
        
        # ====== PARÁMETROS DE TOLERANCIA ======
        TOLERANCIA_INFERIOR = 100   # Puede estar hasta 100 copias por debajo del SNMP
        TOLERANCIA_SUPERIOR = 500   # Puede estar hasta 500 copias por encima del SNMP
        
        _logger.info(f"[Validación Contador] Tolerancias: -{TOLERANCIA_INFERIOR} / +{TOLERANCIA_SUPERIOR}")
        
        # ====== CASO 1: Contador menor que el inicial (ERROR) ======
        if contador_tecnico_int < contador_inicial_int:
            raise UserError(_(
                "❌ <b>Error: Contador Menor que el Inicial</b>\n\n"
                "El contador no puede retroceder.\n\n"
                "• Contador inicial: <b>%s</b>\n"
                "• Contador ingresado: <b>%s</b>\n"
                "• Diferencia: <b>-%s</b>\n\n"
                "Por favor, verifique el valor ingresado."
            ) % (
                f"{contador_inicial_int:,}",
                f"{contador_tecnico_int:,}",
                f"{contador_inicial_int - contador_tecnico_int:,}"
            ))
        
        # ====== CASO 2: Contador igual al SNMP actual (ACEPTAR) ======
        if contador_tecnico_int == contador_maquina_int:
            _logger.info(f"[Validación Contador] ✅ ACEPTADO: Igual al SNMP ({contador_maquina_int})")
            
            # Registrar actualización en la máquina
            self.maquina_id.sudo().write({
                'ultima_fuente_actualizacion': 'reparacion',
            })
            
            self.message_post(
                body=_(
                    "✅ <b>Contador Validado Automáticamente</b><br/>"
                    "El contador coincide con la última actualización SNMP.<br/>"
                    "Valor: <b>%s</b>"
                ) % f"{contador_tecnico_int:,}"
            )
            return True
        
        # ====== CASO 3: Técnico está dentro de tolerancia INFERIOR del SNMP ======
        if contador_maquina_int - TOLERANCIA_INFERIOR <= contador_tecnico_int < contador_maquina_int:
            diferencia = contador_maquina_int - contador_tecnico_int
            _logger.info(f"[Validación Contador] ✅ ACEPTADO: Dentro de tolerancia inferior (-%s)", diferencia)
            
            # Registrar actualización
            self.maquina_id.sudo().write({
                'contometro': contometro_tecnico,
                'ultima_fuente_actualizacion': 'reparacion',
            })
            
            self.message_post(
                body=_(
                    "✅ <b>Contador Validado con Tolerancia</b><br/>"
                    "El técnico tomó el contador antes de la actualización SNMP.<br/>"
                    "• Contador ingresado: <b>%s</b><br/>"
                    "• Último SNMP: <b>%s</b><br/>"
                    "• Diferencia aceptable: <b>-%s copias</b>"
                ) % (
                    f"{contador_tecnico_int:,}",
                    f"{contador_maquina_int:,}",
                    f"{diferencia:,}"
                )
            )
            return True
        
        # ====== CASO 4: Técnico está dentro de tolerancia SUPERIOR ======
        if contador_maquina_int < contador_tecnico_int <= contador_maquina_int + TOLERANCIA_SUPERIOR:
            diferencia = contador_tecnico_int - contador_maquina_int
            _logger.info(f"[Validación Contador] ✅ ACEPTADO: Copias de prueba (+%s)", diferencia)
            
            # Actualizar contador de la máquina
            self.maquina_id.sudo().write({
                'contometro': contometro_tecnico,
                'ultima_fuente_actualizacion': 'reparacion',
            })
            
            self.message_post(
                body=_(
                    "✅ <b>Contador Actualizado: Copias de Prueba</b><br/>"
                    "El técnico realizó copias de prueba adicionales.<br/>"
                    "• Contador ingresado: <b>%s</b><br/>"
                    "• Último SNMP: <b>%s</b><br/>"
                    "• Copias de prueba: <b>+%s</b>"
                ) % (
                    f"{contador_tecnico_int:,}",
                    f"{contador_maquina_int:,}",
                    f"{diferencia:,}"
                )
            )
            return True
        
        # ====== CASO 5: Contador demasiado bajo (ERROR) ======
        if contador_tecnico_int < contador_maquina_int - TOLERANCIA_INFERIOR:
            diferencia = contador_maquina_int - contador_tecnico_int
            raise UserError(_(
                "❌ <b>Error: Contador Demasiado Bajo</b>\n\n"
                "El contador ingresado está muy por debajo del valor reportado por SNMP.\n\n"
                "• Contador inicial: <b>%s</b>\n"
                "• Último SNMP: <b>%s</b>\n"
                "• Contador ingresado: <b>%s</b>\n"
                "• Diferencia: <b>-%s</b>\n\n"
                "Tolerancia máxima: <b>-%s copias</b>\n\n"
                "Por favor, verifique el contador de la máquina."
            ) % (
                f"{contador_inicial_int:,}",
                f"{contador_maquina_int:,}",
                f"{contador_tecnico_int:,}",
                f"{diferencia:,}",
                TOLERANCIA_INFERIOR
            ))
        
        # ====== CASO 6: Contador demasiado alto (ERROR) ======
        if contador_tecnico_int > contador_maquina_int + TOLERANCIA_SUPERIOR:
            diferencia = contador_tecnico_int - contador_maquina_int
            raise UserError(_(
                "❌ <b>Error: Contador Irreal</b>\n\n"
                "El contador ingresado es demasiado alto en comparación con el SNMP.\n\n"
                "• Contador inicial: <b>%s</b>\n"
                "• Último SNMP: <b>%s</b>\n"
                "• Contador ingresado: <b>%s</b>\n"
                "• Diferencia: <b>+%s</b>\n\n"
                "Tolerancia máxima: <b>+%s copias</b>\n\n"
                "¿Realmente se hicieron tantas copias de prueba?"
            ) % (
                f"{contador_inicial_int:,}",
                f"{contador_maquina_int:,}",
                f"{contador_tecnico_int:,}",
                f"{diferencia:,}",
                TOLERANCIA_SUPERIOR
            ))
        
        # ====== VALIDACIÓN DE CAMBIO DE DÍGITOS ======
        if len(contometro_tecnico) != len(contometro_inicial):
            if not self.autorizacion_cambio_digitos:
                raise UserError(_(
                    "❗ <b>Error en el Número de Dígitos</b>\n\n"
                    "La cantidad de dígitos del contómetro ha cambiado:\n"
                    "• Contómetro inicial: %s dígitos (%s)\n"
                    "• Contómetro actual: %s dígitos (%s)\n\n"
                    "Contacte al administrador para obtener autorización de cambio."
                ) % (
                    len(contometro_inicial), f"{contador_inicial_int:,}",
                    len(contometro_tecnico), f"{contador_tecnico_int:,}"
                ))
            else:
                _logger.info(f"Cambio de dígitos autorizado para reparación ID: {self.id}")
        
        _logger.info(f"[Validación Contador] ✅ Validación completada exitosamente")
        return True

    def _validar_fotos_minimas(self):
        """Valida que haya suficientes fotos documentadas"""
        self.ensure_one()
        
        FOTOS_MINIMAS = 10
        cantidad_fotos = len(self.fotos_ids)
        
        if cantidad_fotos < FOTOS_MINIMAS:
            raise UserError(_(
                "❗ <b>Error en la Documentación Fotográfica</b>\n\n"
                "Se requieren al menos <b>%s fotos</b> para finalizar la reparación.\n"
                "Actualmente hay <b>%s fotos</b> adjuntas.\n\n"
                "Por favor, agregue %s fotos más."
            ) % (FOTOS_MINIMAS, cantidad_fotos, FOTOS_MINIMAS - cantidad_fotos))
        
        _logger.info(f"Validación de fotos completada: {cantidad_fotos} fotos documentadas")


    def _generar_reporte_qr(self):
        """Genera el reporte QR de la reparación (operación no crítica)"""
        try:
            _logger.info(f"Generando reporte QR para reparación ID: {self.id}")
            report = self.env.ref('sat.action_report_qr_codes_reparaciones_template')
            report.with_context(discard_logo_check=True).report_action(self)
            _logger.info(f"Reporte QR generado exitosamente")
        except Exception as e:
            _logger.warning(f"No se pudo generar el reporte QR para reparación ID {self.id}: {e}")


    def _enviar_notificaciones(self):
        """Envía todas las notificaciones de finalización (operación no crítica)"""
        
        try:
            _logger.info(f"Enviando mensaje a la asesora para reparación ID: {self.id}")
            self.enviar_mensaje_finalizacion_asesora()
            _logger.info(f"Mensaje enviado exitosamente a la asesora")
        except Exception as e:
            _logger.error(f"Error enviando mensaje a la asesora para reparación ID {self.id}: {e}")
        
        try:
            _logger.info(f"Enviando correo de finalización para reparación ID: {self.id}")
            template_id = self.env.ref('sat.email_template_finalizacion_reparacion')
            template_id.send_mail(self.id, force_send=True)
            _logger.info(f"Correo de finalización enviado exitosamente")
        except Exception as e:
            _logger.error(f"Error enviando correo de finalización para reparación ID {self.id}: {e}")

    def imprimir_reporte_qr(self):
        self.ensure_one()
        try:
            _logger.info(f"Generando reporte QR para reparación ID: {self.id}")
            report = self.env.ref('sat.action_report_qr_codes_reparaciones_template')
            return report.with_context(discard_logo_check=True).report_action(self)
        except Exception as e:
            _logger.error(f"Error generando reporte QR para reparación ID {self.id}: {e}")
            raise UserError(_("❗ Error generando el reporte QR. Por favor, contacte al administrador."))
            
    @api.depends('tipo_revision')
    def obtener_tipo_revision_legible(self):
        tipo_revision_legible = ""
        selection = self._fields['tipo_revision'].selection
        if callable(selection):
            selection = selection(self)
        tipo_revision_legible = dict(selection).get(self.tipo_revision)
        return tipo_revision_legible

    @api.depends('ubicacion_id')
    def obtener_ubicacion_legible(self):
        ubicacion_legible = ""
        selection = self._fields['ubicacion_id'].selection
        if callable(selection):
            selection = selection(self)
        ubicacion_legible = dict(selection).get(self.ubicacion_id)
        return ubicacion_legible

    @api.depends('prioridad')
    def obtener_prioridad_legible(self):
        prioridad_legible = ""
        selection = self._fields['prioridad'].selection
        if callable(selection):
            selection = selection(self)
        prioridad_legible = dict(selection).get(self.prioridad)
        return prioridad_legible
    @api.depends('estado_id')
    def obtener_estado_legible(self):
        estado_legible = ""
        selection = self._fields['estado_id'].selection
        if callable(selection):
            selection = selection(self)
        estado_legible = dict(selection).get(self.estado_id)
        return estado_legible

    parts_request_ids = fields.One2many(
        'copier.parts.request', 
        'reparacion_id', 
        string='Solicitudes de Partes'
    )

    parts_request_count = fields.Integer(
        'Cantidad de Solicitudes', 
        compute='_compute_parts_request_count'
    )

    def _compute_parts_request_count(self):
        for record in self:
            record.parts_request_count = len(record.parts_request_ids)

    def action_request_parts(self):
        """Abre el formulario de solicitud de partes precargando los datos de la reparación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitar Partes',
            'res_model': 'copier.parts.request',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_maquina_id': self.maquina_id.id,
                'default_reparacion_id': self.id,
                'default_solicitante_id': self.env.user.id,
            }
        }

    def action_view_parts_requests(self):
        """Abre la vista de solicitudes de partes relacionadas"""
        self.ensure_one()
        return {
            'name': 'Solicitudes de Partes',
            'type': 'ir.actions.act_window',
            'res_model': 'copier.parts.request',
            'view_mode': 'list,form',
            'domain': [('reparacion_id', '=', self.id)],
            'context': {'default_reparacion_id': self.id, 'default_maquina_id': self.maquina_id.id}
        }



class CopierPartsRequest(models.Model):
    _name = 'copier.parts.request'
    _description = 'Solicitud de Partes de Fotocopiadora'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc'

    name = fields.Char('Solicitud N°', default=lambda self: _('New'), readonly=True, required=True, copy=False, tracking=True)
    fecha = fields.Date('Fecha de Solicitud', default=fields.Date.context_today, required=True, tracking=True)
    
    # Campos relacionados a la máquina
    maquina_id = fields.Many2one('sat.sat', string='Máquina', required=True, tracking=True)
    reparacion_id = fields.Many2one('reparaciones.reparaciones', string='Reparación', 
                                   domain="[('maquina_id', '=', maquina_id)]", tracking=True)
    proveedor = fields.Char(related='maquina_id.proveedor_id.name', readonly=True, store=True)
    importacion = fields.Char(related='maquina_id.importacion', readonly=True, store=True)
    marca = fields.Char(related='maquina_id.marca', readonly=True, store=True)
    modelo = fields.Char(related='maquina_id.name.name', readonly=True, store=True)
    serie = fields.Char(related='maquina_id.serie_id', readonly=True, store=True)
    contometro = fields.Char(related='maquina_id.contometro', readonly=True, store=True)
    
    # Campos de solicitud
    solicitante_id = fields.Many2one('res.users', string='Solicitante', default=lambda self: self.env.user, required=True, tracking=True)
    disco_duro_requerido = fields.Boolean('Requiere Disco Duro', tracking=True)
    motivo_disco = fields.Selection([
        ('sin_disco', 'Llegó sin Disco'),
        ('malogrado', 'Disco Malogrado')
    ], string='Motivo Solicitud Disco', tracking=True)
    
    ruedas_requeridas = fields.Boolean('Requiere Ruedas', tracking=True)
    cantidad_ruedas = fields.Integer('Cantidad de Ruedas', default=4, readonly=True)
    # Nuevo campo para solicitud de cable de poder
    cable_poder_requerido = fields.Boolean('Requiere Cable de Poder', tracking=True)
    motivo_cable = fields.Selection([
        ('sin_cable', 'Llegó sin Cable'),
        ('danado', 'Cable Dañado'),
        ('extraviado', 'Cable Extraviado')
    ], string='Motivo Solicitud Cable', tracking=True)

    motivo_cable_display = fields.Char(
        string='Motivo Cable Display', 
        compute='_compute_motivo_cable_display',
        store=True
    )

    @api.depends('motivo_cable')
    def _compute_motivo_cable_display(self):
        for record in self:
            record.motivo_cable_display = dict(
                self._fields['motivo_cable'].selection
            ).get(record.motivo_cable, '')

    state = fields.Selection([
        ('draft', 'Pendiente'),
        ('approved', 'Aprobado'),
        ('delivered', 'Entregado')
    ], string='Estado', default='draft', tracking=True)
    
    access_token = fields.Char('Token de Acceso', copy=False)

    def _get_default_access_token(self):
        return str(uuid.uuid4())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Generar número de secuencia
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('copier.parts.request') or _('New')
            
            # Generar token de acceso
            if not vals.get('access_token'):
                vals['access_token'] = str(uuid.uuid4())
        
        records = super().create(vals_list)
        
        for record in records:
            if record.disco_duro_requerido:
                record._actualizar_falla_proveedor()
            record._enviar_correo_solicitud()
            
            # Enviar mensaje de WhatsApp al crear la solicitud
            logistics_phone = "51922541085"
            message = record._get_whatsapp_message_creation()
            record.send_whatsapp_message(logistics_phone, message)
        
        return records

    def _actualizar_falla_proveedor(self):
        """Actualiza el campo falla_proveedor en reparaciones"""
        fallas = []
        
        if self.disco_duro_requerido:
            descripcion_disco = 'Llegó sin disco duro' if self.motivo_disco == 'sin_disco' else 'Disco duro malogrado'
            fallas.append(descripcion_disco)
            
        if self.cable_poder_requerido:
            motivos_cable = {
                'sin_cable': 'Llegó sin cable de poder',
                'danado': 'Cable de poder dañado',
                'extraviado': 'Cable de poder extraviado'
            }
            descripcion_cable = motivos_cable.get(self.motivo_cable, '')
            if descripcion_cable:
                fallas.append(descripcion_cable)
        
        if fallas:
            reparacion = self.reparacion_id or self.env['reparaciones.reparaciones'].search(
                [('maquina_id', '=', self.maquina_id.id)], limit=1)
            
            if reparacion:
                fallas_html = ''.join(f'<p>{falla}</p>' for falla in fallas)
                reparacion.write({
                    'falla_proveedor': fallas_html
                })

    def get_motivo_disco_display(self):
        """Obtiene el texto a mostrar del motivo de solicitud de disco"""
        motivos = dict(self._fields['motivo_disco'].selection)
        return motivos.get(self.motivo_disco, '')

    def _enviar_correo_solicitud(self):
        """Envía el correo inicial de solicitud"""
        template = self.env.ref('sat.email_template_parts_request')
        template.send_mail(self.id, force_send=True)

    def action_approve(self):
        """Aprueba la solicitud y envía notificaciones"""
        self.ensure_one()
        self.write({'state': 'approved'})
        
        # Enviar correo de aprobación
        template = self.env.ref('sat.email_template_logistics_approval')
        template.send_mail(self.id, force_send=True)
        
        # Notificar por el chat
        self.message_post(
            body=f"Solicitud aprobada. Se ha notificado a logística para la entrega.",
            partner_ids=[self.solicitante_id.partner_id.id]
        )
        
        # Enviar mensaje de WhatsApp al solicitante
        if self.solicitante_id.mobile:
            message = self._get_whatsapp_message_approval()
            self.send_whatsapp_message(self.solicitante_id.mobile, message)

    def action_deliver(self):
        """Marca como entregado y envía notificación"""
        self.ensure_one()
        self.write({'state': 'delivered'})
        # Notificar al solicitante
        self.message_post(
            body=f"Las partes han sido entregadas.",
            partner_ids=[self.solicitante_id.partner_id.id]
        )
        
    def generate_approval_url(self):
        """Genera la URL para aprobar la solicitud de partes"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/parts/approve/{self.access_token}"


    def send_whatsapp_message(self, phone, message):
        """Envía un mensaje de WhatsApp utilizando la API externa."""
        url = 'https://boot.andessolutioncopiers.com/api/send-message'
        data = {
            'to': phone,
            'message': message
        }
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816'
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            _logger.info("Código de estado: %s", response.status_code)
            _logger.info("Respuesta de la API: %s", response.text)
            
            try:
                response_json = response.json()
                _logger.info("Respuesta JSON: %s", response_json)
                
                # Validar respuesta exitosa
                if response.status_code == 200 and response_json.get('success'):
                    _logger.info("✅ Mensaje enviado exitosamente a %s", phone)
                    return response_json
                else:
                    error_msg = response_json.get('error', 'Error desconocido')
                    _logger.error("❌ Error en API: %s", error_msg)
                    return {"error": error_msg, "success": False}
                    
            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error(error_msg)
                _logger.error("Respuesta raw: %s", response.text)
                return {"error": error_msg, "success": False}
                
        except requests.exceptions.Timeout:
            error_msg = f"Timeout al enviar mensaje a {phone}"
            _logger.error("❌ %s", error_msg)
            return {"error": error_msg, "success": False}
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de red al enviar mensaje: {str(e)}"
            _logger.error("❌ %s", error_msg)
            return {"error": error_msg, "success": False}
            
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            _logger.error("❌ %s", error_msg)
            return {"error": error_msg, "success": False}
    def _get_whatsapp_message_creation(self):
        """Genera el mensaje de WhatsApp para la creación de solicitud"""
        return f"""Nueva solicitud de partes #{self.name}
Máquina: {self.marca} {self.modelo}
Serie: {self.serie}
Solicitante: {self.solicitante_id.name}
Disco Duro: {'Sí' if self.disco_duro_requerido else 'No'}
Ruedas: {'Sí' if self.ruedas_requeridas else 'No'}
Cable de Poder: {'Sí' if self.cable_poder_requerido else 'No'}
Estado: Pendiente de aprobación

Ver solicitud: {self.generate_approval_url()}"""

    def _get_whatsapp_message_approval(self):
        """Genera el mensaje de WhatsApp para la aprobación"""
        items = []
        if self.disco_duro_requerido:
            items.append(" - Disco Duro")
        if self.ruedas_requeridas:
            items.append(f" - {self.cantidad_ruedas} Ruedas")
        if self.cable_poder_requerido:
            items.append(" - Cable de Poder")
            
        items_text = "\n".join(items)
        
        return f"""¡Solicitud de partes #{self.name} aprobada!
        
Puede pasar a recoger los siguientes items:
{items_text}

Máquina: {self.marca} {self.modelo}
Serie: {self.serie}"""



class PartsRequestWizard(models.TransientModel):
    _name = 'copier.parts.request.wizard'
    _description = 'Asistente de Solicitud de Partes'

    # Campos relacionados a la máquina
    reparacion_id = fields.Many2one('reparaciones.reparaciones', string='Reparación', readonly=True)
    maquina_id = fields.Many2one('sat.sat', string='Máquina', required=True, readonly=True)
    proveedor = fields.Char(related='maquina_id.proveedor_id.name', readonly=True)
    importacion = fields.Char(related='maquina_id.importacion', readonly=True)
    marca = fields.Char(related='maquina_id.marca', readonly=True)
    modelo = fields.Char(related='maquina_id.name.name', readonly=True)
    serie = fields.Char(related='maquina_id.serie_id', readonly=True)
    contometro = fields.Char(related='maquina_id.contometro', readonly=True)
    
    # Campos de solicitud
    disco_duro_requerido = fields.Boolean('Requiere Disco Duro')
    motivo_disco = fields.Selection([
        ('sin_disco', 'Llegó sin Disco'),
        ('malogrado', 'Disco Malogrado')
    ], string='Motivo Solicitud Disco', states={
        'invisible': [('disco_duro_requerido', '=', False)],
        'required': [('disco_duro_requerido', '=', True)]
    })
    
    ruedas_requeridas = fields.Boolean('Requiere Ruedas')
    cantidad_ruedas = fields.Integer('Cantidad de Ruedas', default=4,
        states={
            'invisible': [('ruedas_requeridas', '=', False)],
            'required': [('ruedas_requeridas', '=', True)]
        })
    
    notas = fields.Text('Notas Adicionales')

    @api.onchange('disco_duro_requerido')
    def _onchange_disco_duro(self):
        if not self.disco_duro_requerido:
            self.motivo_disco = False

    @api.onchange('ruedas_requeridas')
    def _onchange_ruedas(self):
        if not self.ruedas_requeridas:
            self.cantidad_ruedas = 0
        else:
            self.cantidad_ruedas = 4

    @api.constrains('disco_duro_requerido', 'ruedas_requeridas', 'motivo_disco')
    def _check_required_fields(self):
        for record in self:
            if not record.disco_duro_requerido and not record.ruedas_requeridas:
                raise ValidationError('Debe seleccionar al menos una opción: Disco Duro o Ruedas')
            if record.disco_duro_requerido and not record.motivo_disco:
                raise ValidationError('Debe seleccionar el motivo de la solicitud del disco duro')

    def action_create_request(self):
        self.ensure_one()
        
        # Validar que al menos una opción esté seleccionada
        if not self.disco_duro_requerido and not self.ruedas_requeridas:
            raise ValidationError('Debe seleccionar al menos una opción: Disco Duro o Ruedas')
            
        vals = {
            'maquina_id': self.maquina_id.id,
            'reparacion_id': self.reparacion_id.id,
            'disco_duro_requerido': self.disco_duro_requerido,
            'motivo_disco': self.motivo_disco,
            'ruedas_requeridas': self.ruedas_requeridas,
            'cantidad_ruedas': self.cantidad_ruedas if self.ruedas_requeridas else 0,
        }
        
        request = self.env['copier.parts.request'].create(vals)
        
        # Mensaje en el chatter de la reparación
        if self.reparacion_id:
            message = f"<b>Solicitud de Partes Creada:</b><br/>"
            if self.disco_duro_requerido:
                message += f"- Disco Duro: {dict(self._fields['motivo_disco'].selection).get(self.motivo_disco)}<br/>"
            if self.ruedas_requeridas:
                message += f"- Ruedas: {self.cantidad_ruedas}<br/>"
            if self.notas:
                message += f"<b>Notas:</b><br/>{self.notas}"
            
            self.reparacion_id.message_post(body=message)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'copier.parts.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

class ReportReparacionView(models.AbstractModel):
    _name = 'report.sat.report_reparaciones_ventas'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['reparaciones.reparaciones'].browse(docids)
        selection_labels = {}
        for doc in docs:
            selection_labels[doc.id] = doc.get_selection_labels() if doc else {}
        return {
            'doc_ids': docids,
            'doc_model': 'reparaciones.reparaciones',
            'docs': docs,
            'selection_labels': selection_labels,
        }

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

    @api.model_create_multi
    def create(self, vals_list):
        """ Crea una secuencia para el modelo de reparaciones y gestiona la creación de carpetas en pCloud """
        for vals in vals_list:
            # Asegurar que el nombre se genere si no está presente o tiene el valor por defecto 'New'
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('reparaciones.reparaciones') or '/'
                _logger.info("Número secuencial asignado al campo 'name': %s", vals['name'])

            # Asignar el valor inicial del contómetro al campo 'contometro_inicial' si 'contometrok_id' tiene un valor
            if 'contometrok_id' in vals:
                vals['contometro_inicial'] = vals['contometrok_id']
                _logger.info("Asignado 'contometro_inicial' a partir de 'contometrok_id': %s", vals['contometro_inicial'])

        try:
            # Crear los registros
            records = super(Reparaciones, self).create(vals_list)
            for record in records:
                _logger.info("Registro de reparación creado exitosamente con ID: %s", record.id)

                # Crear la carpeta en pCloud
                try:
                    folder_id = record.create_folder_in_pcloud()  # Crear la carpeta automáticamente
                    record.foto_galeria_nombre = f"{record.maquina_id.name.name}_{record.serie_id or 'sin_serie'}"  # Guardar el nombre de la carpeta
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

            return records

        except KeyError as e:
            _logger.error("KeyError: Campo faltante o no definido - %s", str(e))
            raise ValidationError(_("Ocurrió un error al intentar crear la reparación. Verifique los campos: %s") % str(e))

        except Exception as create_error:
            _logger.error("Error durante la creación de la reparación: %s", str(create_error))
            raise
    
    def create_folder_in_pcloud(self):
        """Crea una carpeta en pCloud dentro de 'fotos_reparaciones' usando modelo_id y serie."""
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            _logger.error("Configuración de pCloud no encontrada o falta el token de acceso.")
            raise ValidationError(_("Configuración de pCloud no encontrada o falta el token de acceso."))

        # Verificar y crear la carpeta 'fotos_reparaciones' si no existe
        fotos_reparaciones_id = self.get_or_create_folder_id('fotos_reparaciones')
        if not fotos_reparaciones_id:
            _logger.error("No se encontró ni se pudo crear la carpeta 'fotos_reparaciones' en pCloud.")
            raise ValidationError(_("No se encontró ni se pudo crear la carpeta 'fotos_reparaciones' en pCloud."))

        folder_name = f"{self.maquina_id.name.name}_{self.serie_id or 'sin_serie'}"
        _logger.info("Intentando crear la carpeta '%s' en pCloud", folder_name)
        url = f"{pcloud_config.hostname}/createfolder"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': fotos_reparaciones_id,  # ID de la carpeta 'fotos_reparaciones'
            'name': folder_name
        }
        response = requests.post(url, params=params)
        _logger.info("Respuesta de la creación de carpeta: %s", response.text)
        result = response.json()
        if response.status_code == 200 and 'metadata' in result:
            _logger.info("Carpeta '%s' creada exitosamente en pCloud.", folder_name)
            return result['metadata']['folderid']
        elif response.status_code == 200 and result.get('result') == 2004:  # Código para carpeta existente
            _logger.info("La carpeta '%s' ya existe en pCloud.", folder_name)
            return self.get_folder_id(folder_name)
        else:
            _logger.error("Error al crear la carpeta: %s", result)
            raise ValidationError(_("No se pudo crear la carpeta: %s") % result.get('error'))

    def get_or_create_folder_id(self, folder_name):
        """Obtiene el folderid de una carpeta existente en pCloud o la crea si no existe."""
        folder_id = self.get_folder_id(folder_name)
        if folder_id:
            return folder_id

        # Si no existe, intentamos crearla
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        url = f"{pcloud_config.hostname}/createfolder"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': 0,  # ID raíz para crear en la raíz
            'name': folder_name
        }
        response = requests.post(url, params=params)
        result = response.json()
        if response.status_code == 200 and 'metadata' in result:
            _logger.info("Carpeta '%s' creada exitosamente en pCloud.", folder_name)
            return result['metadata']['folderid']
        else:
            _logger.error("Error al crear la carpeta '%s': %s", folder_name, result)
            raise ValidationError(_("No se pudo crear la carpeta '%s' en pCloud: %s") % (folder_name, result.get('error')))

    def get_folder_id(self, folder_name):
        """Obtiene el folderid de una carpeta existente en pCloud."""
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        url = f"{pcloud_config.hostname}/listfolder"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': 0,  # Empezar desde la raíz
            'recursive': 1  # Buscar en subcarpetas también
        }
        
        try:
            response = requests.get(url, params=params)
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                # Primero buscar en fotos_reparaciones
                fotos_reparaciones_id = None
                for folder in result['metadata']['contents']:
                    if folder['isfolder'] and folder['name'] == 'fotos_reparaciones':
                        fotos_reparaciones_id = folder['folderid']
                        break
                
                if not fotos_reparaciones_id:
                    return None  # Si 'fotos_reparaciones' no existe, se retorna None
                
                # Ahora buscar la carpeta específica dentro de fotos_reparaciones
                for folder in result['metadata']['contents']:
                    if folder['isfolder'] and folder['name'] == folder_name:
                        return folder['folderid']
                
                return None
            else:
                _logger.error(f"Error al listar carpetas: {result}")
                raise ValidationError(_("Error al listar carpetas en pCloud: %s") % result.get('error'))
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error de conexión con pCloud: {str(e)}")
            raise ValidationError(_("Error de conexión con pCloud: %s") % str(e))
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
    fusora_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar'), ("no_aplica", "No aplica")],
                                 string="Faja fusora", tracking=True)
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
    @api.depends('responsable_id.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            if record.responsable_id.mobile_phone:
                # Remove '+' and all types of spaces
                phone = record.responsable_id.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                # Ensure phone starts with '51'
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_mobile_clean = phone
            else:
                record.responsable_mobile_clean = ''
                record.responsable_mobile_clean = ''


    def send_whatsapp_message(self, phone, message):
        """Envía un mensaje de WhatsApp utilizando la API externa."""
        url = 'https://whatsapp.andessolutioncopiers.com/api/message'
        data = {
            'phone': phone,
            'message': message
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data)

        print("Código de estado:", response.status_code)
        print("Respuesta de la API:", response.text)

        # Verificar si la respuesta contiene un cuerpo JSON válido
        try:
            response_json = response.json()
            print("Respuesta JSON:", response_json)
            return response_json
        except json.JSONDecodeError as e:
            error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
            print(error_msg)
            return {"error": error_msg}  # Devuelve un diccionario con la clave 'error' y el mensaje de error como valor
    def get_selection_labels(self):
        selection_labels = {}
        for field_name, field in self._fields.items():
            if field.type == 'selection' and hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    selection = field.selection
                    if callable(selection):
                        selection = selection(self)
                    for option_value, option_label in selection:
                        if option_value == value:
                            selection_labels[field_name] = option_label
                            break
                else:
                    selection_labels[field_name] = 'NA'
        return selection_labels
    def enviar_mensaje_whatsapp_reparaciones(self):
        selection_labels = self.get_selection_labels()
        # Contexto para las plantillas de correo
        context = dict(self.env.context or {})
        context.update({
            'selection_labels': selection_labels
        })
        # Lógica para enviar correos
        template = self.env.ref('sat.email_template_reparaciones')
        template.with_context(**context).send_mail(self.id, force_send=True)

        #additional_template = self.env.ref('sat.email_template_reparacion_creada')
        #additional_template.with_context(**context).send_mail(self.id, force_send=True)

        # Generar URL del registro y la galería de fotos
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_reparaciones_window').id
        menu_id = self.env.ref('sat.reparaciones').id
        record_url = f"{base_url}/web#id={self.id}&view_type=form&model=reparaciones.reparaciones&action={action_id}&menu_id={menu_id}"
        gallery_url = f"{base_url}/gallery/{self.id}"

        # Construir y enviar el mensaje de WhatsApp
        msg = f"""Hola;\n*{self.responsable_id.name if self.responsable_id.name else 'NA'}*\n
    Se te ha asignado la inspección y elaboración del informe de la máquina que se encuentra en el taller.
    
    *REPARACIÓN N°:* {self.name if self.name else 'NA'}
    *Cliente:* {self.cliente_id.name if self.cliente_id.name else 'NA'}
    *Importación:* {self.importacion if self.importacion else 'NA'}
    *Tipo de equipo:* {self.tipo_machine if self.tipo_machine else 'NA'}
    *Marca:* {self.marca if self.marca else 'NA'}
    *Modelo:* {self.maquina_id.name.name if self.maquina_id.name and self.maquina_id.name.name else 'NA'}
    *Serie:* {self.serie_id if self.serie_id else 'NA'}
    *Estado:* {selection_labels.get('estado_id', 'NA')}
    *Tipo de revisión:* {selection_labels.get('tipo_revision', 'NA')}
    *Prioridad:* {selection_labels.get('prioridad', 'NA')}
    *Ubicación:* {selection_labels.get('ubicacion_id', 'NA')}
    *Asesora:* {self.maquina_id.asesora_id if self.maquina_id.asesora_id else 'NA'}

    *Enlaces:*
    - Acceso al registro: {record_url}
    - Galería de fotos: {gallery_url}"""

        if self.responsable_id and self.responsable_mobile_clean:
            phone_number = self.responsable_mobile_clean
            self.send_whatsapp_message(phone_number, msg)

        # Actualizar estado de la reparación
        self.estado_id = 'en_revision'
        return {
            'type': 'ir.actions.act_window_close'  # Cerrar ventana tras completar la acción
        }

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


    def enviar_mensaje_finalizacion_asesora(self):
        pdf_url = self.generate_pdf_report_url()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        gallery_url = f'{base_url}/gallery/{self.id}'
        action_id = self.env.ref('sat.action_reparaciones_window').id
        menu_id = self.env.ref('sat.reparaciones').id
        record_url = f"{base_url}/web#id={self.id}&view_type=form&model=reparaciones.reparaciones&action={action_id}&menu_id={menu_id}"
        #Registro: {record_url}
        msg = f"""*Reparación Finalizada*
            *Cliente:* {self.cliente_id.name if self.cliente_id.name else 'NA'}
            *Marca:* {self.marca if self.marca else 'NA'}
            *Modelo:* {self.nombre_maquina if self.nombre_maquina else 'NA'}
            *Serie:* {self.serie_id if self.serie_id else 'NA'}
            *Contómetro:* {self.contometrok_id if self.contometrok_id else 'NA'}
            *Estado:* {self.obtener_estado_legible() if self.obtener_estado_legible() else 'NA'}
            *Técnico:* {self.responsable_id.name if self.responsable_id.name else 'NA'}

            *Enlaces:*
            Reporte: {pdf_url}
            Fotos: {gallery_url}
            """

        if self.asesora_mobile_clean:
            phone_number = self.asesora_mobile_clean
            self.send_whatsapp_message(phone_number, msg)
    

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
            ('estado_ventas_id', '=', 'para_revision')
        ], order='fecha_para_revision asc', limit=1)

        if not next_maquina:
            _logger.info('No se encontró ninguna máquina en estado "para_revision", buscando máquinas "sin_revisar" y disponibles en ubicaciones específicas.')
            next_maquina = self.env['sat.sat'].search([
                ('estado_ventas_id', '=', 'sin_revisar'),
                ('disponibilidad_id', '=', 'disponible'),
                ('ubicacion_id', 'in', ['primer_piso', 'tercer_piso'])
            ], order='create_date asc', limit=1)

        if next_maquina:
            _logger.info('Máquina seleccionada con ID %s para revisión.', next_maquina.id)
            
            # Verificación del valor de contometro
            if not next_maquina.contometro or int(next_maquina.contometro) == 0:
                _logger.error('La máquina con ID %s no tiene un valor de contómetro válido.', next_maquina.id)
                raise ValidationError("La máquina seleccionada no tiene un valor de contómetro válido.")

            # Verificar duplicado de serie_id
            existing_record = self.env['reparaciones.reparaciones'].search([('serie_id', '=', next_maquina.serie_id)])
            if existing_record:
                _logger.error('Ya existe un registro con el serie_id %s', next_maquina.serie_id)
                raise ValidationError(_('Ya existe un registro con el serie_id %s.') % next_maquina.serie_id)

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
                raise ValidationError("El responsable asignado no está vinculado a ningún empleado. Por favor, revise la configuración.")
        else:
            _logger.info('No se encontró ninguna máquina que cumpla con los criterios de selección.')


    def action_finalizar_reparacion(self):
        # Deshabilitar las reglas de acceso temporalmente para evitar restricciones
        self = self.sudo()  # Utilizamos sudo() para evitar restricciones de acceso
    
        _logger.info(f"Iniciando proceso de finalización para reparación ID: {self.id}")
    
        # Verificar si la autenticación ya fue realizada
        if not self.autenticacion_correcta:
            _logger.info(f"Autenticación requerida para el usuario {self.env.user.id}")
            grupo_validacion = self.env.ref('sat.sat_tecnica_group_user')
            if grupo_validacion in self.env.user.groups_id:
                _logger.info("Usuario pertenece al grupo que necesita autenticación. Llamando al wizard de autenticación.")
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'reparacion.autenticacion.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {'default_reparacion_id': self.id},
                }
    
        # Verificar que contometrok_id y contometro_inicial sean cadenas y no estén vacíos
        if not self.contometrok_id or not self.contometro_inicial:
            _logger.error(f"Reparación ID {self.id}: Los datos del contómetro no están configurados correctamente.")
            raise UserError(_("❗ <b>Error en el Contómetro</b>: Los valores del contómetro no están configurados correctamente. Verifique e intente nuevamente."))
    
        # Verificar si el contómetro fue actualizado
        if self.contometrok_id == self.contometro_inicial:
            _logger.warning(f"Reparación ID {self.id}: El contómetro no ha sido actualizado. Contómetro actual: {self.contometrok_id}")
            raise UserError(_("❗ Error en el Contómetro: El contómetro no ha sido actualizado. Debe ser diferente del valor inicial."))
    
        # Validar la cantidad de dígitos
        if len(self.contometrok_id) != len(self.contometro_inicial):
            if not self.autorizacion_cambio_digitos:
                _logger.warning(f"Reparación ID {self.id}: Diferencia en la cantidad de dígitos del contómetro y sin autorización. Contómetro actual: {self.contometrok_id}, Contómetro inicial: {self.contometro_inicial}")
                raise UserError(_("❗ Error en el Número de Dígitos: La cantidad de dígitos del contómetro actual no coincide con el inicial. Contacte al administrador para obtener autorización de cambio."))
    
        # Validar cantidad mínima de fotos
        if len(self.fotos_ids) < 10:
            _logger.warning(f"Reparación ID {self.id}: Número insuficiente de fotos. Cantidad actual: {len(self.fotos_ids)}")
            raise UserError(_("❗ Error en la Documentación Fotográfica: Se requieren al menos 10 fotos para finalizar la reparación. Actualmente hay %s fotos.") % len(self.fotos_ids))
    
        # Continuar con el proceso de finalización
        _logger.info(f"Generando reporte para reparación ID: {self.id}")
        try:
            _logger.info(f"Intentando generar reporte QR para reparación ID: {self.id}")
            report = self.env.ref('sat.action_report_qr_codes_reparaciones_template')
            # Generamos el reporte sin esperar a que termine
            report.with_context(discard_logo_check=True).report_action(self.id)
        except Exception as e:
            _logger.error(f"Error generando reporte QR para reparación ID {self.id}: {e}")
            raise UserError(_("❗ Error generando el reporte QR. Por favor, contacte al administrador."))
    
        try:
            _logger.info(f"Enviando mensaje a la asesora para reparación ID: {self.id}")
            self.enviar_mensaje_finalizacion_asesora()
        except Exception as e:
            _logger.error(f"Error enviando el mensaje a la asesora para reparación ID {self.id}: {e}")
    
        try:
            _logger.info(f"Enviando correo de finalización para reparación ID: {self.id}")
            template_id = self.env.ref('sat.email_template_finalizacion_reparacion')
            template_id.send_mail(self.id, force_send=True)
        except Exception as e:
            _logger.error(f"Error enviando el correo para reparación ID {self.id}: {e}")
    
        _logger.info(f"Cambiando estado a 'finalizado' para reparación ID: {self.id}")
        self.estado_id = "finalizado"
        _logger.info(f"Estado cambiado a 'finalizado' para reparación ID: {self.id}")
        
        # Crear la próxima reparación sin verificar el estado
        _logger.info(f"Creando siguiente reparación para reparación ID: {self.id}")
        self.sudo()._create_next_reparacion()
    
        _logger.info(f"Proceso de finalización completado para reparación ID: {self.id}")
        
        # Retornamos directamente a la vista de lista
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'list',
            'res_model': 'reparaciones.reparaciones',
            'view_id': False,
            'target': 'main',
        }

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
    
    # Campos de solicitud
    solicitante_id = fields.Many2one('res.users', string='Solicitante', default=lambda self: self.env.user, required=True, tracking=True)
    disco_duro_requerido = fields.Boolean('Requiere Disco Duro', tracking=True)
    motivo_disco = fields.Selection([
        ('sin_disco', 'Llegó sin Disco'),
        ('malogrado', 'Disco Malogrado')
    ], string='Motivo Solicitud Disco', tracking=True)
    
    ruedas_requeridas = fields.Boolean('Requiere Ruedas', tracking=True)
    cantidad_ruedas = fields.Integer('Cantidad de Ruedas', default=4, readonly=True)
    
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
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('copier.parts.request') or _('New')
            vals['access_token'] = self._get_default_access_token()
        records = super().create(vals_list)
        for record in records:
            if record.disco_duro_requerido:
                record._actualizar_falla_proveedor()
            record._enviar_correo_solicitud()
        return records

    def _actualizar_falla_proveedor(self):
        """Actualiza el campo falla_proveedor en reparaciones"""
        if self.disco_duro_requerido:
            descripcion = 'Llegó sin disco duro' if self.motivo_disco == 'sin_disco' else 'Disco duro malogrado'
            
            # Actualizar en reparaciones.reparaciones
            reparacion = self.reparacion_id or self.env['reparaciones.reparaciones'].search(
                [('maquina_id', '=', self.maquina_id.id)], limit=1)
            
            if reparacion:
                reparacion.write({
                    'falla_proveedor': f'<p>{descripcion}</p>'
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
        """Aprueba la solicitud y envía notificación"""
        self.ensure_one()
        self.write({'state': 'approved'})
        template = self.env.ref('sat.email_template_logistics_approval')
        template.send_mail(self.id, force_send=True)
        # Notificar al solicitante
        self.message_post(
            body=f"Solicitud aprobada. Se ha notificado a logística para la entrega.",
            partner_ids=[self.solicitante_id.partner_id.id]
        )

    def action_deliver(self):
        """Marca como entregado y envía notificación"""
        self.ensure_one()
        self.write({'state': 'delivered'})
        # Notificar al solicitante
        self.message_post(
            body=f"Las partes han sido entregadas.",
            partner_ids=[self.solicitante_id.partner_id.id]
        )
        )

class PartsRequestWizard(models.TransientModel):
    _name = 'copier.parts.request.wizard'
    _description = 'Asistente de Solicitud de Partes'

    maquina_id = fields.Many2one('sat.sat', string='Máquina', required=True)
    disco_duro_requerido = fields.Boolean('Requiere Disco Duro')
    motivo_disco = fields.Selection([
        ('sin_disco', 'Llegó sin Disco'),
        ('malogrado', 'Disco Malogrado')
    ], string='Motivo Solicitud Disco')
    ruedas_requeridas = fields.Boolean('Requiere Ruedas')

    def action_create_request(self):
        self.ensure_one()
        vals = {
            'maquina_id': self.maquina_id.id,
            'disco_duro_requerido': self.disco_duro_requerido,
            'motivo_disco': self.motivo_disco,
            'ruedas_requeridas': self.ruedas_requeridas,
        }
        request = self.env['copier.parts.request'].create(vals)
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

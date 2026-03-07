from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import xlwt
import re
import base64
from io import BytesIO
import logging



_logger = logging.getLogger(__name__)


class ReporteEstadoMaquina(models.Model):
    _name = 'reporte.estado.maquina'
    _description = 'Reporte de Estado de Máquinas'
    _order = 'fecha_generacion desc, estado_maquina, serie'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Campos de identificación del reporte
    fecha_generacion = fields.Date(
        string='Fecha de Generación',
        default=fields.Date.context_today,
        required=True,
        index=True
    )
    semana_reporte = fields.Char(
        string='Semana del Reporte',
        compute='_compute_semana_reporte',
        store=True,
        help='Semana del año en formato YYYY-WXX'
    )
    
    # Datos básicos de la máquina
    maquina_id = fields.Many2one(
        'alquiler',
        string='Máquina',
        required=True,
        ondelete='cascade'
    )
    serie = fields.Char(string='Serie', required=True, index=True)
    modelo = fields.Char(string='Modelo', required=True)
    marca = fields.Char(string='Marca', required=True)
    tipo_maquina = fields.Selection([
        ('color', 'Color'),
        ('monocromatica', 'Monocromática')
    ], string='Tipo de Máquina')
    
    estado_maquina = fields.Selection([
        ('sin_revisar', 'Sin Revisar'),
        ('revisada', 'Revisada'),
        ('lista', 'Lista'),
        ('alquilada', 'Alquilada'),
        ('con_problemas', 'Con Problemas'),
        ('partes', 'De Partes'),
        ('externo', 'Externo'),
        ('vendida', 'Vendida')
    ], string='Estado de Máquina', required=True, index=True)
    
    ubicacion_fisica = fields.Selection([
        ('primer_piso', 'Primer Piso'),
        ('tercer_piso', 'Tercer Piso'),
        ('segundo_local', 'Segundo Local'),
        ('covida', 'Covida')
    ], string='Ubicación Física')
    
    # Datos del último ticket
    ultimo_ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Último Ticket',
        help='Último ticket de servicio registrado para esta máquina'
    )
    ultimo_ticket_fecha = fields.Datetime(string='Fecha Último Ticket')
    ultimo_ticket_tipo = fields.Char(string='Tipo de Servicio')
    tecnico_responsable = fields.Char(string='Técnico Responsable')
    informe_tecnico = fields.Html(string='Informe Técnico')
    
    # Contómetros
    contador_bn = fields.Integer(string='Contador B/N', default=0)
    contador_color = fields.Integer(string='Contador Color', default=0)
    contador_total = fields.Integer(
        string='Contador Total (B/N + Color)',
        compute='_compute_contador_total',
        store=True
    )
    contador_scanner = fields.Integer(string='Contador Scanner', default=0)
    
    # Cliente anterior (historial de alquiler)
    cliente_anterior_id = fields.Many2one(
        'res.partner',
        string='Cliente Anterior',
        help='Último cliente donde estuvo alquilada la máquina'
    )
    direccion_anterior = fields.Text(string='Dirección Anterior')
    fecha_ultimo_retiro = fields.Date(string='Fecha Último Retiro')
    
    # Campos de accesorios (del último ticket)
    transformador = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Transformador')
    
    estabilizador = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Estabilizador')
    
    adf_simple = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='ADF Simple')
    
    adf_dual = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='ADF Dual Scan')
    
    finalizador_interno = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Finalizador Interno')
    
    finalizador_externo = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Finalizador Externo')
    
    mueble = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Mueble')
    
    panel_smart = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Panel Smart')
    
    panel_normal = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Panel Normal')
    
    wifi = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Wi-Fi')
    
    bluetooth = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Bluetooth')
    
    cable_usb = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Cable USB de Impresión')
    
    cable_red = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Cable de Red')
    
    numero_caseteras = fields.Char(string='Número de Caseteras')
    
    # Check List - Funciones
    copia_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Función Copia')
    
    impresion_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Función Impresión')
    
    impresion_usb_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Impresión USB')
    
    scanner_smb_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner SMB')
    
    scanner_usb_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner USB')
    
    scanner_ftp_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner FTP')
    
    scanner_mail_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner Mail')
    
    # Check List - Componentes
    adf_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado ADF')
    
    tray1_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 1')
    
    tray2_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 2')
    
    tray3_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 3')
    
    tray4_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 4')
    
    bypass_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Bypass')
    
    finalizador_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Finalizador')
    
    # Check List - Partes Críticas
    tacho_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tacho Residual')
    
    fusora_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Fusora')
    
    transfer_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Faja Transfer')
    
    optico_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Óptica')
    
    unidad_imagen_black_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Black')
    
    unidad_imagen_magenta_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Magenta')
    
    unidad_imagen_cyan_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Cyan')
    
    unidad_imagen_yellow_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Yellow')
    
    # Check List - Toners
    toner_black_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Black')
    
    toner_magenta_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Magenta')
    
    toner_cyan_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Cyan')
    
    toner_yellow_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Yellow')
    
    # Información específica para máquinas de partes o con problemas
    partes_retiradas_ids = fields.One2many(
        'reporte.estado.maquina.parte',
        'reporte_id',
        string='Partes Retiradas/Reemplazadas'
    )
    partes_tecnico_ids = fields.One2many(
        'reporte.gestion.partes.tecnico',
        'maquina_id',
        string='Partes Técnicos'
    )
    
    # Historial de alquileres
    historial_alquileres_ids = fields.One2many(
        'reporte.estado.maquina.alquiler',
        'reporte_id',
        string='Historial de Alquileres'
    )
    
    # Campo para mostrar en la lista
    display_name = fields.Char(
        string='Nombre del Reporte',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('fecha_generacion')
    def _compute_semana_reporte(self):
        for record in self:
            if record.fecha_generacion:
                año, semana, _ = record.fecha_generacion.isocalendar()
                record.semana_reporte = f"{año}-W{semana:02d}"
            else:
                record.semana_reporte = False

    @api.depends('contador_bn', 'contador_color')
    def _compute_contador_total(self):
        for record in self:
            record.contador_total = (record.contador_bn or 0) + (record.contador_color or 0)

    @api.depends('serie', 'modelo', 'estado_maquina', 'fecha_generacion')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.serie} - {record.modelo} ({record.estado_maquina}) - {record.fecha_generacion}"

    @api.model
    def generar_reporte_semanal(self):
        """
        Método para generar el reporte semanal automáticamente.
        Se ejecutará mediante un cron job.
        """
        _logger.info("Iniciando generación de reporte semanal de estado de máquinas")
        
        fecha_reporte = fields.Date.context_today(self)
        
        # Eliminar reportes existentes de la misma fecha para evitar duplicados
        reportes_existentes = self.search([('fecha_generacion', '=', fecha_reporte)])
        if reportes_existentes:
            reportes_existentes.unlink()
            _logger.info(f"Eliminados {len(reportes_existentes)} reportes existentes de la fecha {fecha_reporte}")
        
        # Estados a incluir en el reporte (excluir alquiladas, externo y vendidas)
        estados_incluir = ['sin_revisar', 'revisada', 'lista', 'con_problemas', 'partes']
        
        # Obtener todas las máquinas en los estados relevantes
        maquinas = self.env['alquiler'].search([
            ('estado_alquiler_id', 'in', estados_incluir)
        ])
        
        reportes_creados = 0
        
        for maquina in maquinas:
            try:
                self._crear_reporte_maquina(maquina, fecha_reporte)
                reportes_creados += 1
            except Exception as e:
                _logger.error(f"Error al crear reporte para máquina {maquina.serie}: {str(e)}")
                continue
        
        _logger.info(f"Reporte semanal generado exitosamente: {reportes_creados} máquinas procesadas")
        
        # Generar PDF del reporte
        self._generar_pdf_reporte(fecha_reporte)
        
        return True

    def _crear_reporte_maquina(self, maquina, fecha_reporte):
        """
        Crea un registro de reporte para una máquina específica
        """
        # Buscar el último ticket de la máquina
        ultimo_ticket = self.env['ticket.alquiler'].search([
            ('product_alquiler', '=', maquina.id),
            ('estado', '=', 'finalizado')
        ], order='agenda desc', limit=1)
        
        # Obtener cliente anterior (último cliente donde estuvo alquilada)
        cliente_anterior = self._obtener_cliente_anterior(maquina)
        
        # Crear el registro del reporte
        valores_reporte = {
            'fecha_generacion': fecha_reporte,
            'maquina_id': maquina.id,
            'serie': maquina.serie,
            'modelo': maquina.name.name if maquina.name else '',
            'marca': maquina.marca,
            'tipo_maquina': maquina.tipo_maquina_id,
            'estado_maquina': maquina.estado_alquiler_id,
            'ubicacion_fisica': maquina.ubicacion_id,
        }
        
        # Agregar datos del cliente anterior
        if cliente_anterior:
            valores_reporte.update({
                'cliente_anterior_id': cliente_anterior['cliente_id'],
                'direccion_anterior': cliente_anterior['direccion'],
                'fecha_ultimo_retiro': cliente_anterior['fecha_retiro']
            })
        
        # Agregar datos del último ticket si existe
        if ultimo_ticket:
            valores_reporte.update(self._extraer_datos_ticket(ultimo_ticket))
        
        # Crear el registro
        reporte = self.create(valores_reporte)
        
        # Crear registros relacionados
        self._crear_historial_alquileres(reporte, maquina)
        
        if maquina.estado_alquiler_id in ['con_problemas', 'partes']:
            self._crear_registro_partes_retiradas(reporte, maquina)
        
        return reporte

    def _obtener_cliente_anterior(self, maquina):
        """
        Obtiene información del último cliente donde estuvo alquilada la máquina
        """
        # Buscar el último ticket de retiro
        ticket_retiro = self.env['ticket.alquiler'].search([
            ('product_alquiler', '=', maquina.id),
            ('tipo_servicio_id', '=', 'retiro'),
            ('estado', '=', 'finalizado')
        ], order='agenda desc', limit=1)
        
        if ticket_retiro:
            return {
                'cliente_id': ticket_retiro.partner_id.id if ticket_retiro.partner_id else None,
                'direccion': ticket_retiro.direccion_id_r,
                'fecha_retiro': ticket_retiro.agenda.date() if ticket_retiro.agenda else None
            }
        
        return None

    def _extraer_datos_ticket(self, ticket):
        """
        Extrae todos los datos relevantes del último ticket
        """
        # Limpiar y convertir contómetros
        contador_bn = self._limpiar_contador(ticket.contometrok_id)
        contador_color = self._limpiar_contador(ticket.contometroc_id)
        contador_scanner = self._limpiar_contador(ticket.contometros_id)
        
        datos = {
            'ultimo_ticket_id': ticket.id,
            'ultimo_ticket_fecha': ticket.agenda,
            'ultimo_ticket_tipo': dict(ticket._fields['tipo_servicio_id'].selection).get(ticket.tipo_servicio_id, ''),
            'tecnico_responsable': ticket.responsable.name if ticket.responsable else '',
            'informe_tecnico': ticket.informe_id,
            'contador_bn': contador_bn,
            'contador_color': contador_color,
            'contador_scanner': contador_scanner,
            
            # Accesorios
            'transformador': ticket.transformador_id,
            'estabilizador': ticket.estabilizador,
            'adf_simple': ticket.adf_simple_id,
            'adf_dual': ticket.adf_dual_id,
            'finalizador_interno': ticket.finalizador_interno_id,
            'finalizador_externo': ticket.finalizador_externo_id,
            'mueble': ticket.mueble_id,
            'panel_smart': ticket.panel_smart_id,
            'panel_normal': ticket.panel_normal_id,
            'wifi': ticket.wi_fi_id,
            'bluetooth': ticket.bluetooth_id,
            'cable_usb': ticket.cable_usb_id,
            'cable_red': ticket.cable_red_id,
            'numero_caseteras': ticket.tray_id,
            
            # Check List - Funciones
            'copia_estado': ticket.copia_id,
            'impresion_estado': ticket.impresion_id,
            'impresion_usb_estado': ticket.impresion_usb_id,
            'scanner_smb_estado': ticket.scaner_smb_id,
            'scanner_usb_estado': ticket.scaner_usb_id,
            'scanner_ftp_estado': ticket.scaner_ftp_id,
            'scanner_mail_estado': ticket.scaner_mail_id,
            
            # Check List - Componentes
            'adf_estado': ticket.adf_id,
            'tray1_estado': ticket.tray1_id,
            'tray2_estado': ticket.tray2_id,
            'tray3_estado': ticket.tray3_id,
            'tray4_estado': ticket.tray4_id,
            'bypass_estado': ticket.bypass_id,
            'finalizador_estado': ticket.finalizador_id,
            
            # Check List - Partes Críticas
            'tacho_estado': ticket.tacho_id,
            'fusora_estado': ticket.fusora_id,
            'transfer_estado': ticket.transfer_id,
            'optico_estado': ticket.optico_id,
            'unidad_imagen_black_estado': ticket.black_id,
            'unidad_imagen_magenta_estado': ticket.magenta_id,
            'unidad_imagen_cyan_estado': ticket.cyan_id,
            'unidad_imagen_yellow_estado': ticket.yellow_id,
            
            # Toners
            'toner_black_nivel': ticket.toner_black_id,
            'toner_magenta_nivel': ticket.toner_magenta_id,
            'toner_cyan_nivel': ticket.toner_cyan_id,
            'toner_yellow_nivel': ticket.toner_yellow_id,
        }
        
        return datos

    def _limpiar_contador(self, contador_str):
        """
        Limpia y convierte el valor del contador a entero
        """
        if not contador_str:
            return 0
        
        try:
            # Remover comas y espacios
            cleaned = str(contador_str).replace(',', '').replace(' ', '')
            return int(float(cleaned))
        except (ValueError, TypeError):
            return 0

    def _crear_historial_alquileres(self, reporte, maquina):
        """
        Crea registros del historial de alquileres para la máquina
        """
        # Buscar tickets de instalación y retiro para construir historial
        tickets_instalacion = self.env['ticket.alquiler'].search([
            ('product_alquiler', '=', maquina.id),
            ('tipo_servicio_id', '=', 'instalacion'),
            ('estado', '=', 'finalizado')
        ], order='agenda asc')
        
        for ticket in tickets_instalacion:
            # Buscar ticket de retiro correspondiente
            ticket_retiro = self.env['ticket.alquiler'].search([
                ('product_alquiler', '=', maquina.id),
                ('tipo_servicio_id', '=', 'retiro'),
                ('estado', '=', 'finalizado'),
                ('agenda', '>', ticket.agenda)
            ], order='agenda asc', limit=1)
            
            self.env['reporte.estado.maquina.alquiler'].create({
                'reporte_id': reporte.id,
                'cliente_id': ticket.partner_id.id if ticket.partner_id else None,
                'direccion': ticket.direccion_id_r,
                'fecha_instalacion': ticket.agenda.date() if ticket.agenda else None,
                'fecha_retiro': ticket_retiro.agenda.date() if ticket_retiro and ticket_retiro.agenda else None,
                'contador_bn_instalacion': self._limpiar_contador(ticket.contometrok_id),
                'contador_color_instalacion': self._limpiar_contador(ticket.contometroc_id),
                'contador_bn_retiro': self._limpiar_contador(ticket_retiro.contometrok_id) if ticket_retiro else 0,
                'contador_color_retiro': self._limpiar_contador(ticket_retiro.contometroc_id) if ticket_retiro else 0,
            })

    def _crear_registro_partes_retiradas(self, reporte, maquina):
        """
        Crea registros de partes retiradas para máquinas de partes o con problemas
        """
        solicitudes_partes = self.env['solicitud.partes'].search([
            ('maquina_origen_id', '=', maquina.id),
            ('state', 'in', ['completed', 'replaced'])
        ])

        for solicitud in solicitudes_partes:
            for linea in solicitud.parte_ids:

                # Solo registrar partes retiradas o reemplazadas
                if linea.estado not in ['retirado', 'reemplazado']:
                    continue

                self.env['reporte.estado.maquina.parte'].create({
                    'reporte_id': reporte.id,
                    'solicitud_partes_id': solicitud.id,
                    'nombre_parte': linea.parte,   # ← ESTE ES EL CAMBIO
                    'descripcion': linea.descripcion,
                    'estado_parte': linea.estado,
                    'condicion': linea.condicion,
                    'fecha_solicitud': solicitud.fecha_solicitud.date() if solicitud.fecha_solicitud else False,
                    'maquina_destino': solicitud.maquina_destino_id.serie if solicitud.maquina_destino_id else ''
                })


    @api.model
    def generar_reporte_partes_tecnicos(self):

        # limpiar reporte anterior
        self.search([]).unlink()

        lineas = self.env['solicitud.parte.tecnico.linea'].search([])

        for linea in lineas:

            origen = linea._get_origen_display()

            self.create({
                'fecha': linea.solicitud_id.fecha_solicitud,
                'solicitud_id': linea.solicitud_id.id,
                'tecnico_id': linea.solicitud_id.tecnico_id.id,
                'maquina_id': linea.solicitud_id.maquina_id.id,
                'parte': linea.parte,
                'estado': linea.state,
                'origen': origen
            })

    def _generar_pdf_reporte(self, fecha_reporte):
        """
        Genera el PDF del reporte semanal
        """
        # Aquí implementarías la lógica para generar el PDF
        # Por ahora solo logging
        reportes = self.search([('fecha_generacion', '=', fecha_reporte)])
        _logger.info(f"Generando PDF para {len(reportes)} máquinas del reporte {fecha_reporte}")
        
        # TODO: Implementar generación de PDF usando report de Odoo
        return True

    @api.model
    def limpiar_reportes_antiguos(self, dias_conservar=90):
        """
        Limpia reportes antiguos para no sobrecargar la base de datos.
        Se ejecutará mediante un cron job mensual.
        """
        fecha_limite = fields.Date.context_today(self) - timedelta(days=dias_conservar)
        reportes_antiguos = self.search([('fecha_generacion', '<', fecha_limite)])
        
        if reportes_antiguos:
            cantidad = len(reportes_antiguos)
            reportes_antiguos.unlink()
            _logger.info(f"Eliminados {cantidad} reportes anteriores a {fecha_limite}")
        
        return True


class ReporteEstadoMaquinaParte(models.Model):
    _name = 'reporte.estado.maquina.parte'
    _description = 'Partes Retiradas/Reemplazadas en Reporte de Máquinas'
    _order = 'fecha_solicitud desc'

    reporte_id = fields.Many2one(
        'reporte.estado.maquina',
        string='Reporte',
        required=True,
        ondelete='cascade'
    )
    
    solicitud_partes_id = fields.Many2one(
        'solicitud.partes',
        string='Solicitud de Partes',
        required=True
    )
    
    nombre_parte = fields.Char(string='Nombre de la Parte', required=True)
    descripcion = fields.Text(string='Descripción')
    
    estado_parte = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('retirado', 'Retirado'),
        ('reemplazado', 'Reemplazado')
    ], string='Estado de la Parte')
    
    condicion = fields.Selection([
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Condición')
    
    fecha_solicitud = fields.Date(string='Fecha de Solicitud', required=True)
    maquina_destino = fields.Char(string='Máquina Destino (Serie)')


class ReporteEstadoMaquinaAlquiler(models.Model):
    _name = 'reporte.estado.maquina.alquiler'
    _description = 'Historial de Alquileres en Reporte de Máquinas'
    _order = 'fecha_instalacion desc'

    reporte_id = fields.Many2one(
        'reporte.estado.maquina',
        string='Reporte',
        required=True,
        ondelete='cascade'
    )
    
    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True
    )
    
    direccion = fields.Text(string='Dirección')
    
    fecha_instalacion = fields.Date(string='Fecha de Instalación')
    fecha_retiro = fields.Date(string='Fecha de Retiro')
    
    # Contómetros al momento de instalación y retiro
    contador_bn_instalacion = fields.Integer(string='Contador B/N Instalación', default=0)
    contador_color_instalacion = fields.Integer(string='Contador Color Instalación', default=0)
    contador_bn_retiro = fields.Integer(string='Contador B/N Retiro', default=0)
    contador_color_retiro = fields.Integer(string='Contador Color Retiro', default=0)
    
    # Campos calculados para mostrar el uso durante el alquiler
    copias_bn_periodo = fields.Integer(
        string='Copias B/N en el Período',
        compute='_compute_copias_periodo',
        store=True
    )
    
    copias_color_periodo = fields.Integer(
        string='Copias Color en el Período',
        compute='_compute_copias_periodo',
        store=True
    )
    
    copias_total_periodo = fields.Integer(
        string='Total Copias en el Período',
        compute='_compute_copias_periodo',
        store=True
    )
    
    dias_alquiler = fields.Integer(
        string='Días de Alquiler',
        compute='_compute_dias_alquiler',
        store=True
    )

    @api.depends('contador_bn_instalacion', 'contador_color_instalacion', 
                 'contador_bn_retiro', 'contador_color_retiro')
    def _compute_copias_periodo(self):
        for record in self:
            record.copias_bn_periodo = max(0, record.contador_bn_retiro - record.contador_bn_instalacion)
            record.copias_color_periodo = max(0, record.contador_color_retiro - record.contador_color_instalacion)
            record.copias_total_periodo = record.copias_bn_periodo + record.copias_color_periodo

    @api.depends('fecha_instalacion', 'fecha_retiro')
    def _compute_dias_alquiler(self):
        for record in self:
            if record.fecha_instalacion and record.fecha_retiro:
                delta = record.fecha_retiro - record.fecha_instalacion
                record.dias_alquiler = delta.days
            else:
                record.dias_alquiler = 0


class ReporteEstadoMaquinaWizard(models.TransientModel):
    _name = 'reporte.estado.maquina.wizard'
    _description = 'Wizard para Generar Reporte de Estado de Máquinas'

    fecha_desde = fields.Date(
        string='Fecha Desde',
        default=lambda self: fields.Date.context_today(self) - timedelta(days=30)
    )
    
    fecha_hasta = fields.Date(
        string='Fecha Hasta',
        default=fields.Date.context_today
    )
    
    estados_maquina = fields.Selection([
        ('todos', 'Todos los Estados Relevantes'),
        ('sin_revisar', 'Solo Sin Revisar'),
        ('revisada', 'Solo Revisadas'),
        ('lista', 'Solo Listas'),
        ('con_problemas', 'Solo Con Problemas'),
        ('partes', 'Solo De Partes'),
        ('personalizado', 'Selección Personalizada')
    ], string='Estados a Incluir', default='todos', required=True)
    
    estados_personalizados = fields.Selection([
        ('sin_revisar', 'Sin Revisar'),
        ('revisada', 'Revisada'),
        ('lista', 'Lista'),
        ('con_problemas', 'Con Problemas'),
        ('partes', 'De Partes'),
        ('alquilada', 'Alquilada'),
        ('externo', 'Externo'),
        ('vendida', 'Vendida')
    ], string='Estado Personalizado',
       help='Seleccionar estado específico cuando se elige "Selección Personalizada"')
    
    incluir_historial = fields.Boolean(
        string='Incluir Historial de Alquileres',
        default=True
    )
    
    incluir_partes = fields.Boolean(
        string='Incluir Información de Partes',
        default=True
    )
    
    formato_salida = fields.Selection([
        ('pantalla', 'Ver en Pantalla'),
        ('pdf', 'Generar PDF'),
        ('excel', 'Exportar a Excel')
    ], string='Formato de Salida', default='pantalla', required=True)

    def action_generar_reporte(self):
        """
        Acción para generar el reporte según los filtros seleccionados
        """
        # Construir dominio de búsqueda
        domain = [
            ('fecha_generacion', '>=', self.fecha_desde),
            ('fecha_generacion', '<=', self.fecha_hasta)
        ]
        
        # Filtrar por estados
        if self.estados_maquina != 'todos':
            if self.estados_maquina == 'personalizado':
                if self.estados_personalizados:
                    domain.append(('estado_maquina', '=', self.estados_personalizados))
                else:
                    raise UserError(_('Debe seleccionar un estado cuando elige "Selección Personalizada".'))
            else:
                domain.append(('estado_maquina', '=', self.estados_maquina))
        else:
            # Estados relevantes por defecto
            domain.append(('estado_maquina', 'in', ['sin_revisar', 'revisada', 'lista', 'con_problemas', 'partes']))
        
        # Buscar reportes
        reportes = self.env['reporte.estado.maquina'].search(domain, order='estado_maquina, serie')
        
        if not reportes:
            raise UserError(_('No se encontraron datos para los filtros seleccionados.'))
        
        # Procesar según formato de salida
        if self.formato_salida == 'pantalla':
            return self._mostrar_en_pantalla(reportes)
        elif self.formato_salida == 'pdf':
            return self._generar_pdf(reportes)
        elif self.formato_salida == 'excel':
            return self._exportar_excel(reportes)

    def _mostrar_en_pantalla(self, reportes):
        """
        Muestra los reportes en una vista de árbol
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reporte de Estado de Máquinas',
            'res_model': 'reporte.estado.maquina',
            'view_mode': 'list,form',
            'view_type': 'form',
            'domain': [('id', 'in', reportes.ids)],
            'context': {
                'group_by': ['estado_maquina'],
            },
            'target': 'current',
        }

    def _generar_pdf(self, reportes):
        """
        Genera un PDF con el reporte
        """
        try:
            report_ref = self.env.ref('sat.action_reporte_estado_maquinas_pdf')
            return report_ref.report_action(reportes)
        except ValueError:
            raise UserError(_('El reporte PDF no está configurado. Por favor, configure el reporte PDF en el módulo.'))
    def _setup_palette(self, workbook):
        import xlwt
        # define todos tus colores personalizados una sola vez
        xlwt.add_palette_colour("dark_header", 0x21)
        workbook.set_colour_RGB(0x21, 47, 79, 79)

        xlwt.add_palette_colour("light_header", 0x22)
        workbook.set_colour_RGB(0x22, 240, 248, 255)

        xlwt.add_palette_colour("lista_color", 0x23)
        workbook.set_colour_RGB(0x23, 212, 237, 218)

        xlwt.add_palette_colour("revisada_color", 0x24)
        workbook.set_colour_RGB(0x24, 217, 237, 247)

        xlwt.add_palette_colour("sin_revisar_color", 0x25)
        workbook.set_colour_RGB(0x25, 248, 249, 250)

        xlwt.add_palette_colour("con_problemas_color", 0x26)
        workbook.set_colour_RGB(0x26, 255, 243, 205)

        xlwt.add_palette_colour("partes_color", 0x27)
        workbook.set_colour_RGB(0x27, 248, 215, 218)

        xlwt.add_palette_colour("alquilada_color", 0x28)
        workbook.set_colour_RGB(0x28, 230, 247, 255)

    def _exportar_excel(self, reportes):
        import xlwt
        import base64
        import re
        import uuid
        from io import BytesIO
        from unicodedata import normalize
        from urllib.parse import quote

        def _mes_es(dt):
            return [
                'enero','febrero','marzo','abril','mayo','junio',
                'julio','agosto','septiembre','octubre','noviembre','diciembre'
            ][dt.month - 1]

        def _slug_filename(text):
            # quita tildes -> ASCII
            text = normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
            # reemplaza todo lo raro por "_"
            text = re.sub(r'[^A-Za-z0-9._-]+', '_', text)
            text = re.sub(r'_{2,}', '_', text).strip('_')
            return text

        # === Workbook ===
        workbook = xlwt.Workbook(encoding='utf-8')
        self._setup_palette(workbook)
        self._crear_hoja_resumen(workbook, reportes)
        self._crear_hoja_detalle(workbook, reportes)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        excel_data = base64.b64encode(output.read()).decode('utf-8')

        # === Rango y mes/año ===
        fecha_desde = self.fecha_desde or fields.Date.context_today(self)
        fecha_hasta = self.fecha_hasta or fields.Date.context_today(self)
        mes_texto = _mes_es(fecha_hasta).capitalize()
        anio = fecha_hasta.year

        # === Secuencia (opcional) ===
        seq_raw = self.env['ir.sequence'].next_by_code('sat.reporte_estado_excel') or '0001'
        seq_safe = _slug_filename(seq_raw)

        # === Nombre final (ASCII y seguro) ===
        human_name = (
            f"{seq_safe}_Reporte_Estado_Maquinas_"
            f"{mes_texto}-{anio}_{fecha_desde.strftime('%Y%m%d')}_a_{fecha_hasta.strftime('%Y%m%d')}.xls"
        )
        safe_filename = _slug_filename(human_name)
        quoted_filename = quote(safe_filename)   # para ponerlo en la RUTA

        # === Crear adjunto ===
        attachment = self.env['ir.attachment'].create({
            'name': safe_filename,                 # tu nombre ya armado
            'type': 'binary',
            'datas': excel_data,
            # Forzar descarga en vez de previsualizar:
            'mimetype': 'application/octet-stream',
            'res_model': self._name,
            'res_id': self.id,
        })


        # === Asegurar access_token (para evitar 404 por ACLs) ===
        token = getattr(attachment, 'access_token', False)
        if not token:
            if hasattr(attachment, 'generate_access_token'):
                attachment.generate_access_token()
                token = attachment.access_token
        if not token:
            token = uuid.uuid4().hex
            attachment.write({'access_token': token})

        # === URL con nombre en la RUTA (no en query) ===
        url = f"/web/content/{attachment.id}/{quoted_filename}?download=1&access_token={token}"

        _logger.info("Descarga Excel -> id=%s name=%s url=%s", attachment.id, safe_filename, url)

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }


    def _crear_hoja_resumen(self, workbook, reportes):
        """
        Crea dashboard ejecutivo moderno con métricas visuales y KPIs
        """
        import xlwt
        from datetime import datetime
        
        worksheet = workbook.add_sheet('Dashboard Ejecutivo')
        
        # ESTILOS MODERNOS
        # Header principal - gradiente simulado
        title_style = xlwt.easyxf(
            'pattern: pattern solid, fore_colour dark_header;'
            'font: bold 1, height 500, colour white, name Arial;'
            'align: horiz center, vert center'
        )
        
        # Subtítulos con tipografía moderna
        subtitle_style = xlwt.easyxf(
            'font: bold 1, height 320, colour dark_header, name Arial;'
            'align: horiz center, vert center'
        )
        
        # Cards de métricas (estilo tarjetas)
        card_header = xlwt.easyxf(
            'pattern: pattern solid, fore_colour light_header;'
            'font: bold 1, height 280, name Arial;'
            'align: horiz center, vert center;'
            'borders: left medium, right medium, top medium, bottom thin'
        )
        
        card_value = xlwt.easyxf(
            'pattern: pattern solid, fore_colour light_header;'
            'font: bold 1, height 400, colour dark_header, name Arial;'
            'align: horiz center, vert center;'
            'borders: left medium, right medium, top thin, bottom medium',
            num_format_str='#,##0'
        )
        
        # Indicadores de estado (semáforo visual)
        status_excellent = xlwt.easyxf(
            'pattern: pattern solid, fore_colour lista_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )
        
        status_good = xlwt.easyxf(
            'pattern: pattern solid, fore_colour revisada_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )
        
        status_warning = xlwt.easyxf(
            'pattern: pattern solid, fore_colour con_problemas_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )
        
        status_critical = xlwt.easyxf(
            'pattern: pattern solid, fore_colour partes_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )
        
        # HEADER DEL DASHBOARD
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
        worksheet.write_merge(0, 1, 0, 8, '📊 DASHBOARD EJECUTIVO - INVENTARIO DE EQUIPOS', title_style)
        worksheet.write_merge(2, 2, 0, 8, f'Actualizado: {fecha_actual}', subtitle_style)
        
        # Establecer altura de filas para el header
        worksheet.row(0).height = 800
        worksheet.row(1).height = 400
        worksheet.row(2).height = 400
        
        # PROCESAR DATOS
        total_maquinas = len(reportes)
        estados_data = {}
        
        for reporte in reportes:
            estado = reporte.estado_maquina
            if estado not in estados_data:
                estados_data[estado] = {'cantidad': 0, 'contador_total': 0}
            estados_data[estado]['cantidad'] += 1
            estados_data[estado]['contador_total'] += reporte.contador_total or 0
        
        # SECCIÓN DE KPIs PRINCIPALES (Cards estilo dashboard)
        row = 4
        worksheet.write_merge(row, row, 0, 8, '🎯 MÉTRICAS CLAVE', subtitle_style)
        row += 2
        
        # Crear cards de KPIs
        equipos_operativos = (estados_data.get('lista', {}).get('cantidad', 0) + 
                            estados_data.get('alquilada', {}).get('cantidad', 0))
        equipos_problema = (estados_data.get('con_problemas', {}).get('cantidad', 0) + 
                        estados_data.get('partes', {}).get('cantidad', 0))
        sin_revisar = estados_data.get('sin_revisar', {}).get('cantidad', 0)
        
        # Card 1: Total Equipos
        worksheet.write_merge(row, row, 0, 1, 'TOTAL EQUIPOS', card_header)
        worksheet.write_merge(row+1, row+1, 0, 1, total_maquinas, card_value)
        
        # Card 2: Operativos
        worksheet.write_merge(row, row, 2, 3, 'OPERATIVOS', card_header)
        worksheet.write_merge(row+1, row+1, 2, 3, equipos_operativos, card_value)
        
        # Card 3: Con Problemas
        worksheet.write_merge(row, row, 4, 5, 'CON PROBLEMAS', card_header)
        worksheet.write_merge(row+1, row+1, 4, 5, equipos_problema, card_value)
        
        # Card 4: Sin Revisar
        worksheet.write_merge(row, row, 6, 7, 'SIN REVISAR', card_header)
        worksheet.write_merge(row+1, row+1, 6, 7, sin_revisar, card_value)
        
        row += 4
        
        # SEMÁFORO DE SALUD DEL INVENTARIO
        worksheet.write_merge(row, row, 0, 8, '🚦 INDICADOR DE SALUD', subtitle_style)
        row += 2
        
        # Calcular porcentajes para el semáforo
        pct_operativos = (equipos_operativos / total_maquinas * 100) if total_maquinas > 0 else 0
        pct_problemas = (equipos_problema / total_maquinas * 100) if total_maquinas > 0 else 0
        
        # Determinar estado general
        if pct_operativos >= 80:
            estado_general = "🟢 EXCELENTE"
            semaforo_style = status_excellent
        elif pct_operativos >= 60:
            estado_general = "🟡 BUENO" 
            semaforo_style = status_good
        elif pct_operativos >= 40:
            estado_general = "🟠 REGULAR"
            semaforo_style = status_warning
        else:
            estado_general = "🔴 CRÍTICO"
            semaforo_style = status_critical
        
        worksheet.write_merge(row, row+1, 0, 8, f'{estado_general} ({pct_operativos:.1f}% Operativo)', semaforo_style)
        worksheet.row(row).height = 600
        worksheet.row(row+1).height = 400
        
        row += 3
        
        # TABLA DE ESTADOS DETALLADA (Moderna)
        worksheet.write_merge(row, row, 0, 8, '📈 DISTRIBUCIÓN POR ESTADOS', subtitle_style)
        row += 2
        
        # Headers de la tabla moderna
        modern_header = xlwt.easyxf(
            'pattern: pattern solid, fore_colour dark_header;'
            'font: bold 1, colour white, height 260, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )
        
        headers_modernos = ['ESTADO', 'CANTIDAD', '%', 'CONTÓMETRO TOTAL', 'ESTADO VISUAL', 'ACCIÓN REQUERIDA']
        for col, header in enumerate(headers_modernos):
            worksheet.write(row, col, header, modern_header)
        row += 1
        
        # Mapeo de estilos modernos por estado
        estado_configs = {
            'lista': {
                'style': status_excellent,
                'visual': '🟢 LISTO',
                'accion': 'Disponible para alquiler'
            },
            'revisada': {
                'style': status_good,
                'visual': '🔵 REVISADO',
                'accion': 'Preparar para inventario'
            },
            'sin_revisar': {
                'style': status_warning,
                'visual': '⚪ PENDIENTE',
                'accion': 'Revisar técnicamente'
            },
            'con_problemas': {
                'style': status_warning,
                'visual': '🟠 ATENCIÓN',
                'accion': 'Reparación requerida'
            },
            'partes': {
                'style': status_critical,
                'visual': '🔴 CRÍTICO',
                'accion': 'Solo para repuestos'
            },
            'alquilada': {
                'style': status_good,
                'visual': '🔵 ACTIVO',
                'accion': 'En servicio'
            }
        }
        
        # Escribir datos de estados
        for estado, data in estados_data.items():
            config = estado_configs.get(estado, estado_configs['sin_revisar'])
            estado_label = dict(reportes._fields['estado_maquina'].selection).get(estado, estado)
            porcentaje = round((data['cantidad'] / total_maquinas) * 100, 1)
            
            worksheet.write(row, 0, estado_label, config['style'])
            worksheet.write(row, 1, data['cantidad'], config['style'])
            worksheet.write(row, 2, f"{porcentaje}%", config['style'])
            worksheet.write(row, 3, data['contador_total'], config['style'])
            worksheet.write(row, 4, config['visual'], config['style'])
            worksheet.write(row, 5, config['accion'], config['style'])
            row += 1
        
        # RESUMEN FINAL
        row += 2
        worksheet.write_merge(row, row, 0, 8, '💡 RECOMENDACIONES', subtitle_style)
        row += 1
        
        # Generar recomendaciones automáticas
        recomendaciones = []
        if sin_revisar > total_maquinas * 0.3:
            recomendaciones.append("🔍 Priorizar revisión técnica de equipos pendientes")
        if equipos_problema > 0:
            recomendaciones.append("🔧 Programar mantenimiento para equipos con problemas")
        if pct_operativos < 50:
            recomendaciones.append("⚠️ Nivel crítico: aumentar equipos operativos")
        if not recomendaciones:
            recomendaciones.append("✅ Inventario en buen estado general")
        
        for recomendacion in recomendaciones:
            worksheet.write_merge(row, row, 0, 8, recomendacion, status_good)
            row += 1
        
        # AUTO-AJUSTE DE COLUMNAS MODERNO
        column_data_analysis = [
            ['ESTADO'] + [dict(reportes._fields['estado_maquina'].selection).get(e, e) for e in estados_data.keys()],
            ['CANTIDAD'] + [str(d['cantidad']) for d in estados_data.values()],
            ['%'] + [f"{round((d['cantidad']/total_maquinas)*100, 1)}%" for d in estados_data.values()],
            ['CONTÓMETRO TOTAL'] + [str(d['contador_total']) for d in estados_data.values()],
            ['ESTADO VISUAL'] + ['🟢 ESTADO'],
            ['ACCIÓN REQUERIDA'] + ['Acción necesaria a realizar']
        ]
        
        for col_idx, col_data in enumerate(column_data_analysis):
            if col_idx < len(headers_modernos):
                max_length = max(len(str(item)) for item in col_data)
                optimal_width = max(2500, min(max_length * 280 + 800, 8000))
                worksheet.col(col_idx).width = optimal_width
        
        # Ajustar columnas restantes si las hay
        for remaining_col in range(len(headers_modernos), 9):
            worksheet.col(remaining_col).width = 2000

    def _crear_hoja_detalle(self, workbook, reportes):
        """
        Crea hoja con detalles simplificados - Solo los campos solicitados
        """
        import xlwt
        import re

        worksheet = workbook.add_sheet('Detalles Completos')

        # ESTILOS
        header_main = xlwt.easyxf(
            'pattern: pattern solid, fore_colour dark_header;'
            'font: bold 1, colour white, height 240;'
            'align: horiz center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        def get_row_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf('pattern: pattern solid, fore_colour lista_color; borders: left thin, right thin, top thin, bottom thin'),
                'revisada': xlwt.easyxf('pattern: pattern solid, fore_colour revisada_color; borders: left thin, right thin, top thin, bottom thin'),
                'sin_revisar': xlwt.easyxf('pattern: pattern solid, fore_colour sin_revisar_color; borders: left thin, right thin, top thin, bottom thin'),
                'con_problemas': xlwt.easyxf('pattern: pattern solid, fore_colour con_problemas_color; borders: left thin, right thin, top thin, bottom thin'),
                'partes': xlwt.easyxf('pattern: pattern solid, fore_colour partes_color; borders: left thin, right thin, top thin, bottom thin'),
                'alquilada': xlwt.easyxf('pattern: pattern solid, fore_colour alquilada_color; borders: left thin, right thin, top thin, bottom thin'),
            }
            return estado_styles.get(estado_maquina, xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin'))

        def get_number_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf('pattern: pattern solid, fore_colour lista_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'),
                'revisada': xlwt.easyxf('pattern: pattern solid, fore_colour revisada_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'),
                'sin_revisar': xlwt.easyxf('pattern: pattern solid, fore_colour sin_revisar_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'),
                'con_problemas': xlwt.easyxf('pattern: pattern solid, fore_colour con_problemas_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'),
                'partes': xlwt.easyxf('pattern: pattern solid, fore_colour partes_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'),
                'alquilada': xlwt.easyxf('pattern: pattern solid, fore_colour alquilada_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'),
            }
            return estado_styles.get(estado_maquina, xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0'))

        def get_date_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf('pattern: pattern solid, fore_colour lista_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'),
                'revisada': xlwt.easyxf('pattern: pattern solid, fore_colour revisada_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'),
                'sin_revisar': xlwt.easyxf('pattern: pattern solid, fore_colour sin_revisar_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'),
                'con_problemas': xlwt.easyxf('pattern: pattern solid, fore_colour con_problemas_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'),
                'partes': xlwt.easyxf('pattern: pattern solid, fore_colour partes_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'),
                'alquilada': xlwt.easyxf('pattern: pattern solid, fore_colour alquilada_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'),
            }
            return estado_styles.get(estado_maquina, xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY'))

        # ENCABEZADOS - Solo los 7 campos solicitados
        headers = [
            'Fecha', 
            'Marca', 
            'Modelo', 
            'Serie', 
            'Estado', 
            'Total Contómetro', 
            'Informe Técnico'
        ]

        # Escribir encabezados
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_main)

        # FILAS DE DATOS
        row = 1
        for reporte in reportes:
            estado = reporte.estado_maquina
            row_style = get_row_style(estado)
            number_style = get_number_style(estado)
            date_style = get_date_style(estado)

            col = 0

            # 1. Fecha
            worksheet.write(row, col, reporte.fecha_generacion or '', date_style)
            col += 1

            # 2. Marca
            worksheet.write(row, col, reporte.marca or '', row_style)
            col += 1

            # 3. Modelo
            worksheet.write(row, col, reporte.modelo or '', row_style)
            col += 1

            # 4. Serie
            worksheet.write(row, col, reporte.serie or '', row_style)
            col += 1

            # 5. Estado
            estado_display = dict(reporte._fields['estado_maquina'].selection).get(estado, '')
            worksheet.write(row, col, estado_display, row_style)
            col += 1

            # 6. Total Contómetro
            worksheet.write(row, col, reporte.contador_total or 0, number_style)
            col += 1

            # 7. Informe Técnico (limpiar HTML y limitar caracteres)
            informe_html = reporte.informe_tecnico or ''
            informe_limpio = re.sub('<.*?>', '', informe_html or '')
            informe_limpio = informe_limpio.replace('&nbsp;', ' ').strip()
            if len(informe_limpio) > 500:
                informe_limpio = informe_limpio[:497] + '...'
            worksheet.write(row, col, informe_limpio, row_style)

            row += 1

        # AUTO-AJUSTAR ANCHOS DE COLUMNA basado en contenido
        def auto_adjust_column_width(worksheet, col_index, header_text, data_values):
            """Calcula el ancho óptimo para una columna basado en su contenido"""
            # Calcular ancho basado en el encabezado
            header_width = len(header_text) * 256 + 500
            
            # Calcular ancho basado en el contenido más largo
            max_content_width = 0
            for value in data_values:
                if value:
                    # Para texto multilínea, tomar la línea más larga
                    if isinstance(value, str) and '\n' in value:
                        lines = value.split('\n')
                        content_width = max(len(line) for line in lines) * 256
                    else:
                        content_width = len(str(value)) * 256
                    max_content_width = max(max_content_width, content_width)
            
            # Usar el mayor entre encabezado y contenido, con límites
            optimal_width = max(header_width, max_content_width)
            
            # Establecer límites mínimos y máximos
            min_width = 2000   # Mínimo 2000 unidades
            max_width = 20000  # Máximo 20000 unidades (para evitar columnas demasiado anchas)
            
            return max(min_width, min(optimal_width, max_width))

        # Recopilar datos de cada columna para calcular anchos
        column_data = [[] for _ in range(len(headers))]
        
        # Llenar datos de cada columna (re-iterar reportes para recopilar datos)
        for reporte in reportes:
            estado = reporte.estado_maquina
            
            # Recopilar datos por columna
            column_data[0].append(str(reporte.fecha_generacion or ''))  # Fecha
            column_data[1].append(reporte.marca or '')                   # Marca
            column_data[2].append(reporte.modelo or '')                  # Modelo
            column_data[3].append(reporte.serie or '')                   # Serie
            column_data[4].append(dict(reporte._fields['estado_maquina'].selection).get(estado, ''))  # Estado
            column_data[5].append(str(reporte.contador_total or 0))      # Total Contómetro
            
            # Informe técnico procesado
            informe_html = reporte.informe_tecnico or ''
            informe_limpio = re.sub('<br[^>]*>', '\n', informe_html)
            informe_limpio = re.sub('<p[^>]*>', '\n', informe_limpio)
            informe_limpio = re.sub('</p>', '\n', informe_limpio)
            informe_limpio = re.sub('<div[^>]*>', '\n', informe_limpio)
            informe_limpio = re.sub('</div>', '\n', informe_limpio)
            informe_limpio = re.sub('<.*?>', '', informe_limpio)
            informe_limpio = informe_limpio.replace('&nbsp;', ' ').replace('&amp;', '&')
            lineas = [linea.strip() for linea in informe_limpio.split('\n') if linea.strip()]
            informe_organizado = '\n'.join(lineas)
            if len(informe_organizado) > 1000:
                informe_organizado = informe_organizado[:997] + '...'
            column_data[6].append(informe_organizado)                    # Informe Técnico
        
        # Aplicar auto-ajuste a cada columna
        for col_index, header in enumerate(headers):
            optimal_width = auto_adjust_column_width(worksheet, col_index, header, column_data[col_index])
            worksheet.col(col_index).width = optimal_width

        # CONGELAR PANELES PARA NAVEGACIÓN
        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(1)  # Congelar encabezado
        worksheet.set_vert_split_pos(4)  # Congelar primeras 4 columnas (hasta Serie)


    def action_generar_reporte_ahora(self):
        """
        Genera el reporte semanal inmediatamente (para testing)
        """
        try:
            self.env['reporte.estado.maquina'].generar_reporte_semanal()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reporte Generado'),
                    'message': _('El reporte semanal se ha generado exitosamente.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error(f"Error al generar reporte semanal: {str(e)}")
            raise UserError(_('Error al generar el reporte: %s') % str(e))

    @api.onchange('estados_maquina')
    def _onchange_estados_maquina(self):
        """
        Limpiar el estado personalizado cuando se cambia la selección principal
        """
        if self.estados_maquina != 'personalizado':
            self.estados_personalizados = False

class ReporteGestionPartesTecnico(models.Model):
    _name = 'reporte.gestion.partes.tecnico'
    _description = 'Reporte Gestión de Partes Técnicos'
    _order = 'fecha desc'

    fecha = fields.Datetime(string="Fecha")

    solicitud_id = fields.Many2one(
        'solicitud.parte.tecnico',
        string="Solicitud"
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string="Técnico"
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string="Máquina"
    )

    parte = fields.Char(string="Parte")

    estado = fields.Selection([
        ('buscando', 'Buscando'),
        ('encontrada', 'Encontrada'),
        ('por_conseguir', 'Por Conseguir'),
        ('entregada', 'Entregada'),
    ], string="Estado")

    origen = fields.Char(string="Origen")
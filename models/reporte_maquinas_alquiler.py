from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import xlwt
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
                self.env['reporte.estado.maquina.parte'].create({
                    'reporte_id': reporte.id,
                    'solicitud_partes_id': solicitud.id,
                    'nombre_parte': linea.nombre,
                    'descripcion': linea.descripcion,
                    'estado_parte': linea.estado,
                    'condicion': linea.condicion,
                    'fecha_solicitud': solicitud.fecha_solicitud.date(),
                    'maquina_destino': solicitud.maquina_destino_id.serie if solicitud.maquina_destino_id else ''
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
            'view_mode': 'tree,form',
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

    def _exportar_excel(self, reportes):
        """
        Exporta los datos a Excel directamente desde el wizard
        """
        import xlwt
        import base64
        from io import BytesIO
        
        # Crear workbook
        workbook = xlwt.Workbook(encoding='utf-8')
        
        # Crear hojas
        self._crear_hoja_resumen(workbook, reportes)
        self._crear_hoja_detalle(workbook, reportes)
        
        # Generar archivo
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        # Codificar en base64
        excel_data = base64.b64encode(output.read())
        
        # Generar nombre de archivo
        fecha_actual = fields.Date.context_today(self).strftime('%Y%m%d')
        filename = f'Reporte_Estado_Maquinas_{fecha_actual}.xls'
        
        # Crear attachment para descarga
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': excel_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.ms-excel'
        })
        
        # Retornar acción de descarga
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _crear_hoja_resumen(self, workbook, reportes):
        """
        Crea hoja de resumen ejecutivo con diseño profesional
        """
        import xlwt
        worksheet = workbook.add_sheet('Resumen Ejecutivo')
        
        # Usar los mismos colores personalizados definidos anteriormente
        
        # Estilos para el resumen
        title_style = xlwt.easyxf('font: bold 1, height 400, colour dark_header; align: horiz center')
        subtitle_style = xlwt.easyxf('font: bold 1, height 280; align: horiz center')
        header_resumen = xlwt.easyxf('pattern: pattern solid, fore_colour dark_header; font: bold 1, colour white; align: horiz center; borders: left thin, right thin, top thin, bottom thin')
        
        # Estilos específicos por estado para el resumen
        lista_summary = xlwt.easyxf('pattern: pattern solid, fore_colour lista_color; borders: left thin, right thin, top thin, bottom thin; align: horiz center')
        revisada_summary = xlwt.easyxf('pattern: pattern solid, fore_colour revisada_color; borders: left thin, right thin, top thin, bottom thin; align: horiz center')
        sin_revisar_summary = xlwt.easyxf('pattern: pattern solid, fore_colour sin_revisar_color; borders: left thin, right thin, top thin, bottom thin; align: horiz center')
        con_problemas_summary = xlwt.easyxf('pattern: pattern solid, fore_colour con_problemas_color; borders: left thin, right thin, top thin, bottom thin; align: horiz center')
        partes_summary = xlwt.easyxf('pattern: pattern solid, fore_colour partes_color; borders: left thin, right thin, top thin, bottom thin; align: horiz center')
        alquilada_summary = xlwt.easyxf('pattern: pattern solid, fore_colour alquilada_color; borders: left thin, right thin, top thin, bottom thin; align: horiz center')
        
        number_summary = xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
        
        # Título principal
        worksheet.write_merge(0, 0, 0, 6, 'REPORTE EJECUTIVO - ESTADO DE INVENTARIO', title_style)
        worksheet.write_merge(1, 1, 0, 6, f'Fecha de Generación: {fields.Date.context_today(self)}', subtitle_style)
        
        # Espacio
        row = 3
        
        # Encabezados del resumen
        worksheet.write(row, 0, 'ESTADO', header_resumen)
        worksheet.write(row, 1, 'CANTIDAD', header_resumen)
        worksheet.write(row, 2, 'PORCENTAJE', header_resumen)
        worksheet.write(row, 3, 'CONTADOR B/N', header_resumen)
        worksheet.write(row, 4, 'CONTADOR COLOR', header_resumen)
        worksheet.write(row, 5, 'CONTADOR SCANNER', header_resumen)
        worksheet.write(row, 6, 'OBSERVACIONES', header_resumen)
        row += 1
        
        # Agrupar datos por estado
        estados_data = {}
        total_maquinas = len(reportes)
        
        for reporte in reportes:
            estado = reporte.estado_maquina
            if estado not in estados_data:
                estados_data[estado] = {
                    'cantidad': 0,
                    'contador_bn': 0,
                    'contador_color': 0,
                    'contador_scanner': 0
                }
            estados_data[estado]['cantidad'] += 1
            estados_data[estado]['contador_bn'] += reporte.contador_bn or 0
            estados_data[estado]['contador_color'] += reporte.contador_color or 0
            estados_data[estado]['contador_scanner'] += reporte.contador_scanner or 0
        
        # Mapeo de estilos por estado
        estado_styles = {
            'lista': lista_summary,
            'revisada': revisada_summary, 
            'sin_revisar': sin_revisar_summary,
            'con_problemas': con_problemas_summary,
            'partes': partes_summary,
            'alquilada': alquilada_summary
        }
        
        # Observaciones por estado
        observaciones = {
            'lista': 'Listas para alquilar',
            'revisada': 'Revisadas, necesitan preparación',
            'sin_revisar': 'Requieren revisión técnica',
            'con_problemas': 'ATENCIÓN: Requieren reparación',
            'partes': 'CRÍTICO: Para repuestos',
            'alquilada': 'En servicio con clientes'
        }
        
        # Escribir datos del resumen
        for estado, data in estados_data.items():
            estado_label = dict(reportes._fields['estado_maquina'].selection).get(estado, estado)
            porcentaje = round((data['cantidad'] / total_maquinas) * 100, 1)
            style = estado_styles.get(estado, sin_revisar_summary)
            
            worksheet.write(row, 0, estado_label, style)
            worksheet.write(row, 1, data['cantidad'], style)
            worksheet.write(row, 2, f"{porcentaje}%", style)
            worksheet.write(row, 3, data['contador_bn'], number_summary)
            worksheet.write(row, 4, data['contador_color'], number_summary)
            worksheet.write(row, 5, data['contador_scanner'], number_summary)
            worksheet.write(row, 6, observaciones.get(estado, ''), style)
            row += 1
        
        # Total general
        row += 1
        worksheet.write(row, 0, 'TOTAL GENERAL', header_resumen)
        worksheet.write(row, 1, total_maquinas, header_resumen)
        worksheet.write(row, 2, '100%', header_resumen)
        worksheet.write(row, 3, sum(r.contador_bn or 0 for r in reportes), number_summary)
        worksheet.write(row, 4, sum(r.contador_color or 0 for r in reportes), number_summary)
        worksheet.write(row, 5, sum(r.contador_scanner or 0 for r in reportes), number_summary)
        worksheet.write(row, 6, f'{total_maquinas} equipos en inventario', header_resumen)
        
        # Indicadores clave (KPIs)
        row += 3
        worksheet.write_merge(row, row, 0, 6, 'INDICADORES CLAVE', title_style)
        row += 2
        
        # Calcular KPIs
        equipos_operativos = estados_data.get('lista', {}).get('cantidad', 0) + estados_data.get('alquilada', {}).get('cantidad', 0)
        equipos_problema = estados_data.get('con_problemas', {}).get('cantidad', 0) + estados_data.get('partes', {}).get('cantidad', 0)
        
        kpis = [
            ('Equipos Operativos', equipos_operativos, f"{round((equipos_operativos/total_maquinas)*100, 1)}%"),
            ('Equipos con Problemas', equipos_problema, f"{round((equipos_problema/total_maquinas)*100, 1)}%"),
            ('Equipos Sin Revisar', estados_data.get('sin_revisar', {}).get('cantidad', 0), f"{round((estados_data.get('sin_revisar', {}).get('cantidad', 0)/total_maquinas)*100, 1)}%"),
            ('Total Copias B/N', sum(r.contador_bn or 0 for r in reportes), 'Acumulado'),
            ('Total Copias Color', sum(r.contador_color or 0 for r in reportes), 'Acumulado')
        ]
        
        for kpi_name, kpi_value, kpi_percent in kpis:
            worksheet.write(row, 0, kpi_name, header_resumen)
            worksheet.write(row, 1, kpi_value, number_summary)
            worksheet.write(row, 2, kpi_percent, header_resumen)
            row += 1
        
        # Ajustar anchos de columna
        column_widths = [4500, 3000, 3000, 4000, 4000, 4000, 6000]
        for col, width in enumerate(column_widths):
            worksheet.col(col).width = width

    def _crear_hoja_detalle(self, workbook, reportes):
        """
        Crea hoja con detalles completos - Diseño profesional y minimalista
        """
        import xlwt
        worksheet = workbook.add_sheet('Detalles Completos')
        
        # PALETA DE COLORES PROFESIONAL MINIMALISTA
        # Definir colores personalizados
        xlwt.add_palette_colour("dark_header", 0x21)
        workbook.set_colour_RGB(0x21, 47, 79, 79)  # Verde oscuro profesional
        
        xlwt.add_palette_colour("light_header", 0x22) 
        workbook.set_colour_RGB(0x22, 240, 248, 255)  # Azul muy claro
        
        # ESTADOS DE MÁQUINA CON COLORES ESPECÍFICOS
        xlwt.add_palette_colour("lista_color", 0x23)
        workbook.set_colour_RGB(0x23, 212, 237, 218)  # Verde claro para "Lista"
        
        xlwt.add_palette_colour("revisada_color", 0x24)
        workbook.set_colour_RGB(0x24, 217, 237, 247)  # Azul claro para "Revisada"
        
        xlwt.add_palette_colour("sin_revisar_color", 0x25)
        workbook.set_colour_RGB(0x25, 248, 249, 250)  # Gris muy claro para "Sin Revisar"
        
        xlwt.add_palette_colour("con_problemas_color", 0x26)
        workbook.set_colour_RGB(0x26, 255, 243, 205)  # Amarillo claro para "Con Problemas"
        
        xlwt.add_palette_colour("partes_color", 0x27)
        workbook.set_colour_RGB(0x27, 248, 215, 218)  # Rojo claro para "De Partes"
        
        xlwt.add_palette_colour("alquilada_color", 0x28)
        workbook.set_colour_RGB(0x28, 230, 247, 255)  # Azul muy claro para "Alquilada"
        
        # ESTILOS PROFESIONALES
        header_main = xlwt.easyxf('pattern: pattern solid, fore_colour dark_header; font: bold 1, colour white, height 240; align: horiz center; borders: left thin, right thin, top thin, bottom thin')
        header_sub = xlwt.easyxf('pattern: pattern solid, fore_colour light_header; font: bold 1, height 200; align: horiz center; borders: left thin, right thin, top thin, bottom thin')
        
        # ESTILOS POR ESTADO DE MÁQUINA
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
        
        # Estilos especiales para números y fechas
        def get_number_style(estado_maquina):
            base_style = get_row_style(estado_maquina)
            if estado_maquina == 'lista':
                return xlwt.easyxf('pattern: pattern solid, fore_colour lista_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
            elif estado_maquina == 'revisada':
                return xlwt.easyxf('pattern: pattern solid, fore_colour revisada_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
            elif estado_maquina == 'sin_revisar':
                return xlwt.easyxf('pattern: pattern solid, fore_colour sin_revisar_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
            elif estado_maquina == 'con_problemas':
                return xlwt.easyxf('pattern: pattern solid, fore_colour con_problemas_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
            elif estado_maquina == 'partes':
                return xlwt.easyxf('pattern: pattern solid, fore_colour partes_color; borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
            else:
                return xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin; align: horiz right', num_format_str='#,##0')
        
        def get_date_style(estado_maquina):
            if estado_maquina == 'lista':
                return xlwt.easyxf('pattern: pattern solid, fore_colour lista_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY')
            elif estado_maquina == 'revisada':
                return xlwt.easyxf('pattern: pattern solid, fore_colour revisada_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY')
            elif estado_maquina == 'sin_revisar':
                return xlwt.easyxf('pattern: pattern solid, fore_colour sin_revisar_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY')
            elif estado_maquina == 'con_problemas':
                return xlwt.easyxf('pattern: pattern solid, fore_colour con_problemas_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY')
            elif estado_maquina == 'partes':
                return xlwt.easyxf('pattern: pattern solid, fore_colour partes_color; borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY')
            else:
                return xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin', num_format_str='DD/MM/YYYY')
        
        # ENCABEZADOS SIMPLIFICADOS Y PROFESIONALES
        headers = [
            # INFORMACIÓN ESENCIAL
            'Fecha', 'Serie', 'Modelo', 'Marca', 'Estado', 'Ubicación',
            
            # CONTÓMETROS
            'Contador B/N', 'Contador Color', 'Total', 'Scanner',
            
            # ÚLTIMO SERVICIO
            'Último Ticket', 'Fecha Servicio', 'Técnico',
            
            # CLIENTE ANTERIOR
            'Cliente Anterior', 'Fecha Retiro',
            
            # ACCESORIOS PRINCIPALES
            'Transformador', 'ADF', 'Finalizador', 'Panel', 'Wi-Fi',
            
            # FUNCIONES CRÍTICAS
            'Copia', 'Impresión', 'Scanner',
            
            # COMPONENTES CRÍTICOS
            'Tray 1', 'Fusora', 'Transfer', 'Óptico',
            
            # TONERS
            'Toner Black', 'Toner Color'
        ]
        
        # Escribir encabezados principales
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_main)
        
        # Escribir datos con colores por estado
        row = 1
        for reporte in reportes:
            estado = reporte.estado_maquina
            row_style = get_row_style(estado)
            number_style = get_number_style(estado)
            date_style = get_date_style(estado)
            
            col = 0
            
            # INFORMACIÓN ESENCIAL
            worksheet.write(row, col, reporte.fecha_generacion or '', date_style); col += 1
            worksheet.write(row, col, reporte.serie or '', row_style); col += 1
            worksheet.write(row, col, reporte.modelo or '', row_style); col += 1
            worksheet.write(row, col, reporte.marca or '', row_style); col += 1
            
            # Estado con estilo destacado
            estado_display = dict(reporte._fields['estado_maquina'].selection).get(estado, '')
            worksheet.write(row, col, estado_display, row_style); col += 1
            
            ubicacion_display = dict(reporte._fields['ubicacion_fisica'].selection).get(reporte.ubicacion_fisica, '') if reporte.ubicacion_fisica else ''
            worksheet.write(row, col, ubicacion_display, row_style); col += 1
            
            # CONTÓMETROS
            worksheet.write(row, col, reporte.contador_bn or 0, number_style); col += 1
            worksheet.write(row, col, reporte.contador_color or 0, number_style); col += 1
            worksheet.write(row, col, reporte.contador_total or 0, number_style); col += 1
            worksheet.write(row, col, reporte.contador_scanner or 0, number_style); col += 1
            
            # ÚLTIMO SERVICIO
            worksheet.write(row, col, reporte.ultimo_ticket_id.name if reporte.ultimo_ticket_id else '', row_style); col += 1
            worksheet.write(row, col, reporte.ultimo_ticket_fecha or '', date_style); col += 1
            worksheet.write(row, col, reporte.tecnico_responsable or '', row_style); col += 1
            
            # CLIENTE ANTERIOR
            worksheet.write(row, col, reporte.cliente_anterior_id.name if reporte.cliente_anterior_id else '', row_style); col += 1
            worksheet.write(row, col, reporte.fecha_ultimo_retiro or '', date_style); col += 1
            
            # ACCESORIOS PRINCIPALES (simplificado)
            worksheet.write(row, col, dict(reporte._fields['transformador'].selection).get(reporte.transformador, '') if reporte.transformador else '', row_style); col += 1
            
            # ADF (combinar simple y dual)
            adf_value = ''
            if reporte.adf_simple == 'si' or reporte.adf_dual == 'si':
                adf_value = 'Sí'
            elif reporte.adf_simple == 'no' and reporte.adf_dual == 'no':
                adf_value = 'No'
            worksheet.write(row, col, adf_value, row_style); col += 1
            
            # Finalizador (combinar interno y externo)
            fin_value = ''
            if reporte.finalizador_interno == 'si' or reporte.finalizador_externo == 'si':
                fin_value = 'Sí'
            elif reporte.finalizador_interno == 'no' and reporte.finalizador_externo == 'no':
                fin_value = 'No'
            worksheet.write(row, col, fin_value, row_style); col += 1
            
            # Panel (combinar smart y normal)
            panel_value = ''
            if reporte.panel_smart == 'si':
                panel_value = 'Smart'
            elif reporte.panel_normal == 'si':
                panel_value = 'Normal'
            worksheet.write(row, col, panel_value, row_style); col += 1
            
            worksheet.write(row, col, dict(reporte._fields['wifi'].selection).get(reporte.wifi, '') if reporte.wifi else '', row_style); col += 1
            
            # FUNCIONES CRÍTICAS
            worksheet.write(row, col, dict(reporte._fields['copia_estado'].selection).get(reporte.copia_estado, '') if reporte.copia_estado else '', row_style); col += 1
            worksheet.write(row, col, dict(reporte._fields['impresion_estado'].selection).get(reporte.impresion_estado, '') if reporte.impresion_estado else '', row_style); col += 1
            
            # Scanner (combinar SMB, USB, FTP)
            scanner_value = ''
            if any(getattr(reporte, f, '') == 'si' for f in ['scanner_smb_estado', 'scanner_usb_estado', 'scanner_ftp_estado']):
                scanner_value = 'Funciona'
            elif any(getattr(reporte, f, '') == 'no' for f in ['scanner_smb_estado', 'scanner_usb_estado', 'scanner_ftp_estado']):
                scanner_value = 'Con problemas'
            worksheet.write(row, col, scanner_value, row_style); col += 1
            
            # COMPONENTES CRÍTICOS
            worksheet.write(row, col, dict(reporte._fields['tray1_estado'].selection).get(reporte.tray1_estado, '') if reporte.tray1_estado else '', row_style); col += 1
            worksheet.write(row, col, dict(reporte._fields['fusora_estado'].selection).get(reporte.fusora_estado, '') if reporte.fusora_estado else '', row_style); col += 1
            worksheet.write(row, col, dict(reporte._fields['transfer_estado'].selection).get(reporte.transfer_estado, '') if reporte.transfer_estado else '', row_style); col += 1
            worksheet.write(row, col, dict(reporte._fields['optico_estado'].selection).get(reporte.optico_estado, '') if reporte.optico_estado else '', row_style); col += 1
            
            # TONERS
            worksheet.write(row, col, dict(reporte._fields['toner_black_nivel'].selection).get(reporte.toner_black_nivel, '') if reporte.toner_black_nivel else '', row_style); col += 1
            
            # Toner Color (combinar magenta, cyan, yellow)
            toner_color_value = ''
            if reporte.tipo_maquina == 'color':
                if any(getattr(reporte, f, '') == 'lleno' for f in ['toner_magenta_nivel', 'toner_cyan_nivel', 'toner_yellow_nivel']):
                    toner_color_value = 'Lleno'
                elif any(getattr(reporte, f, '') == 'vacio' for f in ['toner_magenta_nivel', 'toner_cyan_nivel', 'toner_yellow_nivel']):
                    toner_color_value = 'Vacío'
                elif any(getattr(reporte, f, '') == 'medio' for f in ['toner_magenta_nivel', 'toner_cyan_nivel', 'toner_yellow_nivel']):
                    toner_color_value = 'Medio'
            else:
                toner_color_value = 'N/A'
            worksheet.write(row, col, toner_color_value, row_style); col += 1
            
            row += 1
        
        # AJUSTAR ANCHOS DE COLUMNA PROFESIONALMENTE
        column_widths = [
            3000, 3500, 4000, 3000, 3500, 3000,  # Info básica
            3200, 3200, 3200, 3200,              # Contómetros
            3500, 3500, 4000,                    # Servicio
            4500, 3200,                          # Cliente anterior
            3000, 2500, 3000, 2500, 2500,       # Accesorios
            3000, 3000, 3000,                    # Funciones
            2800, 3000, 3000, 3000,             # Componentes
            3000, 3000                           # Toners
        ]
        
        for col, width in enumerate(column_widths):
            worksheet.col(col).width = width
        
        # CONGELAR PANELES PARA NAVEGACIÓN
        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(1)  # Congelar encabezado
        worksheet.set_vert_split_pos(2)  # Congelar serie y modeloicos
                import re
                informe_limpio = re.sub('<.*?>', '', informe)
                informe_limpio = informe_limpio.replace('&nbsp;', ' ').strip()
                # Limitar a 500 caracteres para Excel
                if len(informe_limpio) > 500:
                    informe_limpio = informe_limpio[:497] + '...'
            else:
                informe_limpio = ''
            worksheet.write(row, col, informe_limpio, base_style); col += 1
            
            row += 1
        
        # Ajustar ancho de columnas automáticamente
        for col in range(len(headers)):
            if col < 8:  # Información básica - más ancho
                worksheet.col(col).width = 4000
            elif col < 12:  # Contómetros - ancho medio
                worksheet.col(col).width = 3000
            elif headers[col] == 'Informe Técnico':  # Informe técnico - muy ancho
                worksheet.col(col).width = 8000
            else:  # Check lists y demás - ancho estándar
                worksheet.col(col).width = 2800
        
        # Congelar paneles para mejor navegación
        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(2)  # Congelar las 2 primeras filas
        worksheet.set_vert_split_pos(3)  # Congelar las 3 primeras columnas

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
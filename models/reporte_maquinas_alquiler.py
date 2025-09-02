from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class ReporteEstadoMaquina(models.Model):
    _name = 'reporte.estado.maquina'
    _description = 'Reporte de Estado de Máquinas'
    _order = 'fecha_generacion desc, estado_maquina, serie'
    _rec_name = 'display_name'

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
    
    estados_personalizados = fields.Many2many(
        'alquiler',
        string='Estados Personalizados',
        help='Seleccionar estados específicos cuando se elige "Selección Personalizada"'
    )
    
    marcas_incluir = fields.Many2many(
        'modelo.marca',
        string='Marcas a Incluir',
        help='Dejar vacío para incluir todas las marcas'
    )
    
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
                    estados = [e.estado_alquiler_id for e in self.estados_personalizados]
                    domain.append(('estado_maquina', 'in', estados))
            else:
                domain.append(('estado_maquina', '=', self.estados_maquina))
        else:
            # Estados relevantes por defecto
            domain.append(('estado_maquina', 'in', ['sin_revisar', 'revisada', 'lista', 'con_problemas', 'partes']))
        
        # Filtrar por marcas
        if self.marcas_incluir:
            marcas_nombres = [m.name for m in self.marcas_incluir]
            domain.append(('marca', 'in', marcas_nombres))
        
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
            'domain': [('id', 'in', reportes.ids)],
            'context': {
                'group_by': 'estado_maquina',
                'search_default_group_by_estado': 1,
            },
            'target': 'current',
        }

    def _generar_pdf(self, reportes):
        """
        Genera un PDF con el reporte
        """
        # Aquí se implementaría la generación del PDF
        # Por ahora retornamos el reporte estándar de Odoo
        return self.env.ref('sat.action_reporte_estado_maquinas_pdf').report_action(reportes)

    def _exportar_excel(self, reportes):
        """
        Exporta los datos a Excel
        """
        # Implementar exportación a Excel usando xlwt o similar
        raise UserError(_('La exportación a Excel estará disponible en una próxima versión.'))

    def action_generar_reporte_ahora(self):
        """
        Genera el reporte semanal inmediatamente (para testing)
        """
        self.env['reporte.estado.maquina'].generar_reporte_semanal()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
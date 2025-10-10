from odoo import _, models, fields, api, exceptions
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.http import request
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from pytz import timezone, UTC
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class ticket_alquiler(models.Model):

    _name = 'ticket.alquiler'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    

    name = fields.Char( 'TICKET N°', default='New', copy=False, required=True, readonly=True)
    
    url = fields.Char('URL', compute='_compute_url', store=True)
    calendar_event_id = fields.Many2one('calendar.event', string='Evento de Calendario')

    def _compute_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.url = f"{base_url}/web#id={record.id}&model=ticket.alquiler&view_type=form"

    @api.model
    def create(self, vals):
        # Generar el número del ticket utilizando la secuencia definida
        vals['name'] = self.env['ir.sequence'].next_by_code('ticket.alquiler') or 'New'
        
        # Asegurar que el nombre no es nulo
        if vals.get('name', 'New') == 'New':
            raise UserError(_("Error: No se pudo generar un número de ticket."))
        
        # Crear el registro
        record = super(ticket_alquiler, self).create(vals)
        
        # Calcular la URL del registro
        record._compute_url()
        
        return record
    def crear_evento_calendario(self):
        """
        Crea o actualiza un evento en el calendario para la visita técnica programada.
        Maneja valores predeterminados en caso de datos faltantes y agrega logs detallados.
        """
        import logging
        from datetime import timedelta
        _logger = logging.getLogger(__name__)

        self.ensure_one()
        CalendarEvent = self.env['calendar.event']

        _logger.info("Iniciando la creación/actualización del evento en el calendario para el registro ID: %s", self.id)

        if not self.agenda:
            _logger.warning("No se encontró una fecha en el campo 'agenda'. No se puede crear el evento.")
            return False

        try:
            # Calcular hora de fin (2 horas después por defecto)
            start_datetime = self.agenda
            stop_datetime = start_datetime + timedelta(hours=2)
            _logger.info("Fecha y hora de inicio: %s, Fecha y hora de fin: %s", start_datetime, stop_datetime)

            # Preparar participantes
            partner_ids = []
            if self.partner_id:
                partner_ids.append(self.partner_id.id)
            else:
                _logger.warning("El cliente no está asignado, se omitirá como participante.")

            if self.responsable and self.responsable.partner_id:
                partner_ids.append(self.responsable.partner_id.id)
            else:
                _logger.warning("El responsable técnico no está asignado, se omitirá como participante.")

            # Construir los valores del evento
            event_vals = {
                'name': f"Visita Técnica - {self.name or 'NA'} - {self.partner_id.name or 'NA'}",
                'start': start_datetime,
                'stop': stop_datetime,
                'partner_ids': [(6, 0, partner_ids)],
                'user_id': self.responsable.id if self.responsable else None,
                'description': """
                    Ticket: {}
                    Cliente: {}
                    Dirección: {}
                    Contacto: {}
                    Equipo: {}
                    Serie: {}
                    Problema: {}
                    Tipo de servicio: {}
                """.format(
                    self.name or 'NA',
                    self.partner_id.name or 'NA',
                    self.direccion_id_r or 'NA',
                    self.contacto_id_r or 'NA',
                    self.product_alquiler.name.name if self.product_alquiler.name else 'NA',
                    self.serie_id_r or 'NA',
                    self.description or 'NA',
                    dict(self._fields['tipo_servicio_id'].selection).get(self.tipo_servicio_id, 'NA')
                ),
                'location': self.direccion_id_r or 'NA',
                'allday': False,
            }
            _logger.debug("Valores preparados para el evento: %s", event_vals)

            # Crear o actualizar el evento
            if self.calendar_event_id:
                _logger.info("Actualizando evento existente con ID: %s", self.calendar_event_id.id)
                self.calendar_event_id.write(event_vals)
            else:
                _logger.info("Creando un nuevo evento en el calendario.")
                calendar_event = CalendarEvent.create(event_vals)
                self.calendar_event_id = calendar_event.id
                _logger.info("Nuevo evento creado con ID: %s", calendar_event.id)

            return True

        except Exception as e:
            _logger.error("Error al gestionar evento de calendario para el registro ID: %s. Detalles: %s", self.id, str(e))
            self.message_post(body=f"Error al gestionar evento de calendario: {str(e)}")
            return False


          

    reporter_name = fields.Char(string="Nombre de quien reporta")
    reporter_phone = fields.Char(string="Numero de quien reporto")
    problem_photo = fields.Binary(string="Foto del problema")

    responsable = fields.Many2one("res.users", string="Técnico", tracking=True, index=True)
    nombre_responsable = fields.Char(string="Nombre del Técnico", related="responsable.name", store=True)
    
    priority = fields.Selection([("0", ("Low")),("1", ("Medium")),("2", ("High")),("3", ("Very High"))],string="Prioridad",default="1")
    partner_id = fields.Many2one("res.partner", string="Empresa", tracking=True 
    )
    nombre_cliente  = fields.Char(related='partner_id.name', 
    string='Nombre de cliente', store=True
    )
    
    
    description = fields.Text(tracking=True
    )
    informe_id = fields.Html(string='Notas de reparación')   

    estado = fields.Selection(string='Estado', selection=[('nuevo', 'Nuevo'),
    ('proceso','En Proceso'),('finalizado','Finalizado')],  tracking=True,
    default='nuevo'
    )
    codigo_id = fields.Many2one('sale.order', string="Código")

    product_alquiler = fields.Many2one('alquiler', string='Modelo', tracking=True)
    
    tipo_id = fields.Selection([('color', 'Color'),('monocromatica','Monocromatica')], 
     string='Tipo de maquina', related='product_alquiler.tipo_maquina_id')
    serie_id_r = fields.Char(related='product_alquiler.serie', string="Serie", store=True, readonly=False)    
    marca_id_r = fields.Char(related='product_alquiler.marca', string="Marca", store=True)
    modelo_id_r  = fields.Char(related='product_alquiler.name.name',string='Modelo', store=True)
    direccion_id_r = fields.Char(string="Dirección")
    contacto_id_r = fields.Char(string="Contacto")
    celular_id_r = fields.Char(string="Celular")
    corre_id_r = fields.Char(string="Correo")
    piso_id_r = fields.Char(string="Piso")
    oficina_id_r = fields.Char(string="Oficina")
    area_id_r = fields.Char(string="Área")
    estern_id_r = fields.Boolean( string="Cliente externo", tracking=True)
    tray_id = fields.Char("Caseteras N°", tracking=True)
    adf_simple_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="ADF Simple", tracking=True)
    transformador_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Transformador", tracking=True)
    estabilizador = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Estabilizador", tracking=True)
    adf_dual_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="ADF Dual scan", tracking=True)
    finalizador_interno_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Finalizador Interno", tracking=True)
    finalizador_externo_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Finalizador Externo", tracking=True)
    mueble_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Mueble", tracking=True)
    panel_smart_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Panel Smart", tracking=True)
    panel_normal_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Panel Normal", tracking=True)
    wi_fi_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Wi-Fi", tracking=True)
    bluetooth_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Bluetooth", tracking=True)
    cable_usb_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Cable USB de impresión", tracking=True)
    cable_red_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Cable de red", tracking=True)
    
    toner_black_id = fields.Selection([("lleno", "Lleno"), ("medio", "Medio"), ("vacio", "Vacío"), ("sin_botella", "Sin botella")],
        string="Toner Black", tracking=True)
    toner_magenta_id = fields.Selection(
        [("lleno", "Lleno"),
    ("medio", "Medio"),
    ("vacio", "Vacío"),
    ("sin_botella", "Sin botella"),
    ("no_aplica", "No aplica")],
        string="Toner Magenta", tracking=True)
    toner_cyan_id = fields.Selection(
        [("lleno", "Lleno"),
    ("medio", "Medio"),
    ("vacio", "Vacío"),
    ("sin_botella", "Sin botella"),
    ("no_aplica", "No aplica")],
        string="Toner Cyan", tracking=True)
    toner_yellow_id = fields.Selection(
        [("lleno", "Lleno"),
    ("medio", "Medio"),
    ("vacio", "Vacío"),
    ("sin_botella", "Sin botella"),
    ("no_aplica", "No aplica")],
        string="Toner Yellow", tracking=True)
    copia_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")], string="Copia", tracking=True)
    impresion_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Impresión", tracking=True)
    impresion_usb_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Impresión USB", tracking=True)
    scaner_smb_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Scanner SMB", tracking=True)
    scaner_usb_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Scanner USB", tracking=True)
    scaner_ftp_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Scanner FTP", tracking=True)
    scaner_mail_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Scanner Mail", tracking=True)
    adf_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
        string="ADF", tracking=True)
    tray1_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                string="Tray 1", tracking=True)
    tray2_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                string="Tray 2", tracking=True)
    tray3_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                string="Tray 3", tracking=True)
    tray4_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                string="Tray 4", tracking=True)
    bypass_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                 string="Bypass", tracking=True)
    finalizador_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Requiere cambio de repuestos"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                      string="Finalizador", tracking=True)

    tacho_id = fields.Selection(
        [("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
        string="Tacho residual", tracking=True)
    fusora_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                 string="Unidad Fusora", tracking=True)
    transfer_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                   string="Faja de Transferencia", tracking=True)
    optico_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                 string="Unidad Optica", tracking=True)
    black_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                string="Unidad Imagen Black", tracking=True)
    magenta_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                  string="Unidad Imagen Magenta", tracking=True)
    cyan_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                               string="Unidad Imagen Cyan", tracking=True)
    yellow_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("desgaste", "Revisado - Con Desgaste"), ("cambio", "Revisado - Requiere Cambio"), ("no_aplica", "No Aplica para esta Máquina")],
                                 string="Unidad Imagen Yellow", tracking=True) 
    codigo_id  = fields.Char(string='Referencia id')     
    contometros_id = fields.Char(string="Contometro Scanner", tracking=True)
    contometrok_id = fields.Char(string="Contometro K", tracking=True)
    contometroc_id = fields.Char(string="Contometro Color", tracking=True)
    total_copias_id = fields.Char(string="Contometro Total P+C", compute="sumar_field")

    @api.depends('contometrok_id', 'contometroc_id')
    def sumar_field(self):
        for record in self:
            # Convertir los valores a enteros si existen, de lo contrario, usar 0
            contometrok_value = int(record.contometrok_id) if record.contometrok_id else 0
            contometroc_value = int(record.contometroc_id) if record.contometroc_id else 0
            # Sumar los valores y convertir de nuevo a cadena para almacenarlos en total_copias_id
            record.total_copias_id = str(contometrok_value + contometroc_value)


    @api.constrains('contometrok_id', 'contometroc_id', 'contometros_id')
    def _check_contometro_values(self):
        # ⏭️ Permitir saltar validaciones cuando se cargan valores en bloque
        if self.env.context.get('skip_constraints'):
            _logger.info("⏭️ Saltando validaciones por contexto skip_constraints")
            return

        for record in self:
            # Agregar logs para debug
            _logger.info(f"🔍 VALIDANDO CONTADORES - Ticket ID: {record.id}")
            _logger.info(f"🔍 Serie: {record.product_alquiler.serie if record.product_alquiler else 'NA'}")
            
            previous_record = self.search(
                [('product_alquiler', '=', record.product_alquiler.id), ('id', '<', record.id)],
                limit=1,
                order='id desc'
            )
            
            if previous_record:
                _logger.info(f"🔍 TICKET ANTERIOR: {previous_record.id} - {previous_record.name}")
            else:
                _logger.info(f"🔍 NO se encontró ticket anterior")

            # FUNCIÓN AUXILIAR para limpiar y convertir valores
            def clean_and_convert(value_str):
                """
                Limpia y convierte string a entero manejando comas y puntos
                """
                if not value_str:
                    return 0
                
                value_str = str(value_str).strip()
                if not value_str:
                    return 0
                
                try:
                    cleaned = value_str.replace(',', '')
                    if '.' in cleaned:
                        parts = cleaned.split('.')
                        if len(parts) == 2:
                            # 123.456 -> 123456 (si la parte final son 3 dígitos)
                            if len(parts[1]) == 3 and parts[1].isdigit():
                                cleaned = parts[0] + parts[1]
                            else:
                                cleaned = parts[0]  # 123.45 -> 123
                    result = int(float(cleaned))
                    _logger.info(f"🔧 Conversión: '{value_str}' → {result}")
                    return result
                except (ValueError, TypeError) as e:
                    _logger.error(f"❌ Error convirtiendo '{value_str}': {e}")
                    return 0

            # Convertir valores actuales usando la función de limpieza
            current_k = clean_and_convert(record.contometrok_id)
            current_color = clean_and_convert(record.contometroc_id)
            current_scanner = clean_and_convert(record.contometros_id)

            # Convertir valores anteriores
            prev_k = clean_and_convert(previous_record.contometrok_id) if previous_record else 0
            prev_color = clean_and_convert(previous_record.contometroc_id) if previous_record else 0
            prev_scanner = clean_and_convert(previous_record.contometros_id) if previous_record else 0

            # Debug: mostrar valores convertidos
            _logger.info(f"📊 VALORES ACTUALES: K={current_k}, Color={current_color}, Scanner={current_scanner}")
            if previous_record:
                _logger.info(f"📊 VALORES ANTERIORES: K={prev_k}, Color={prev_color}, Scanner={prev_scanner}")

            # VALIDAR CONTÓMETRO K (estricto mayor)
            if previous_record and current_k <= prev_k:
                _logger.error(f"❌ VALIDACIÓN K FALLÓ: {current_k} <= {prev_k}")
                raise ValidationError(
                    _("❗ ERROR: EL VALOR DEL CONTÓMETRO K ES INCORRECTO\n\n"
                    "Debe ingresar un valor MAYOR que el último valor registrado para esta máquina.\n"
                    f"Valor actual: {current_k:,}\n"
                    f"Valor anterior: {prev_k:,}\n"
                    f"Ticket anterior: {previous_record.name}")
                )

            # VALIDAR CONTÓMETRO COLOR (solo para máquinas a color)
            if record.tipo_id == 'color':
                if previous_record and current_color <= prev_color:
                    _logger.error(f"❌ VALIDACIÓN COLOR FALLÓ: {current_color} <= {prev_color}")
                    raise ValidationError(
                        _("❗ ERROR: EL VALOR DEL CONTÓMETRO COLOR ES INCORRECTO\n\n"
                        "Debe ingresar un valor MAYOR que el último valor registrado para esta máquina.\n"
                        f"Valor actual: {current_color:,}\n"
                        f"Valor anterior: {prev_color:,}\n"
                        f"Ticket anterior: {previous_record.name}")
                    )
                if current_color == 0:
                    _logger.error("❌ VALIDACIÓN COLOR: valor es 0")
                    raise ValidationError(
                        _("❗ ERROR: EL VALOR DEL CONTÓMETRO COLOR NO PUEDE SER 0\n\n"
                        "Debe ingresar el valor ACTUAL del contómetro.")
                    )

            # VALIDAR CONTÓMETRO SCANNER (permitir igual o mayor)
            if previous_record and current_scanner < prev_scanner:
                _logger.error(f"❌ VALIDACIÓN SCANNER FALLÓ: {current_scanner} < {prev_scanner}")
                raise ValidationError(
                    _("❗ ERROR: EL VALOR DEL CONTÓMETRO SCANNER ES INCORRECTO\n\n"
                    "Debe ingresar un valor IGUAL O MAYOR que el último valor registrado para esta máquina.\n"
                    f"Valor actual: {current_scanner:,}\n"
                    f"Valor anterior: {prev_scanner:,}\n"
                    f"Ticket anterior: {previous_record.name}")
                )

            # VALIDACIÓN adicional: evitar ambos en 0
            if current_k == 0 and current_scanner == 0:
                _logger.error("❌ VALIDACIÓN: Ambos contadores son 0")
                raise ValidationError(
                    _("❗ ERROR: LOS CONTÓMETROS NO PUEDEN SER 0\n\n"
                    "Debe ingresar los valores ACTUALES de los contómetros.")
                )

            _logger.info(f"✅ VALIDACIÓN EXITOSA para ticket {record.id}")
            _logger.info(f"✅ Valores finales: K={current_k:,}, Color={current_color:,}, Scanner={current_scanner:,}")

    
    tipo_servicio_id = fields.Selection([("instalacion", "Instalación"), ("retiro", "Retiro de maquina"),
                                         ("mantenimiento_preventivo", "Mantenimiento preventivo"), (
                                             "mantenimiento_correctivo", "Mantenimiento correctivo"),
                                         ("cambio_repuestos", "Cambio de repuestos"), ("remoto", "Asistencia remoto"),
                                         ("revision", "Revisión"), ("alquiler", "Preparar para alquiler")],
                                        string="Tipo de servicio", default="revision", tracking=True)
    retorno_id = fields.Selection([("si", "Si"), ("no", "No")], string="Retorno", default="si", tracking=True)

    asistencia_id = fields.Selection([("no", "No"), ("si", "Si")], string="Asistencia Directa", default="no", tracking=True)
    calidad_id = fields.Selection([("buena", "Buena"), ("regular", "Regular"), ("mala", "Mala")], string="Calidad", tracking=True)
    agenda = fields.Datetime(string='Fecha de visita', tracking=True)
    agenda_local = fields.Char(string='Fecha y Hora Local', compute='_compute_agenda_local')

    @api.depends('agenda')
    def _compute_agenda_local(self):
        user_tz = self.env.user.tz or 'UTC'
        local_tz = timezone(user_tz)
        for record in self:
            if record.agenda:
                utc_dt = UTC.localize(record.agenda)
                local_dt = utc_dt.astimezone(local_tz)
                record.agenda_local = local_dt.strftime('%d/%m/%Y %I:%M:%S %p')
            else:
                record.agenda_local = ''
    mensaje  = fields.Text(
    default='Se le asigno un Ticket de  servicio, lea atentamente se le indica todos los detalles del servicio.'
    )

    pedidos_count = fields.Integer(compute='compute_count_pedidos')
    def compute_count_pedidos(self):
        for record in self:
            record.pedidos_count = self.env['sale.order'].search_count([('equipo_id', '=', record.product_alquiler.id)])

    def get_pedidos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedidos',
            'view_mode': 'list,form',
            'res_model': 'sale.order',
            'domain': [('equipo_id', '=', self.product_alquiler.id)],
            'context': "{'create': True}"
        }

    

    sale_order_line_ids = fields.One2many(
        'sale.order.line',  # Modelo de las líneas de pedido de venta
        'ticket_ref_id',  # Campo Many2one en 'sale.order.line' que hace referencia al ticket
        string='Productos Solicitados',
        tracking=True
    )
    line_ids = fields.One2many(
        'ticket.alquiler.line',
        'ticket_id',
        string='Líneas de Productos',
        copy=True,
        required=True
    )

    def action_add_product_line(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agregar Producto',
            'res_model': 'ticket.alquiler.line',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }


    def action_view_lines(self):
        """ Método para ver las líneas de productos del ticket. """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Líneas de Productos',
            'res_model': 'ticket.alquiler.line',
            'view_mode': 'tree,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'create': False}
        }

    def create_sale_order(self):
        self.ensure_one()  # Asegúrate de estar trabajando con un único ticket

        # Crear el pedido de venta
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'equipo_id' :self.product_alquiler.id,
            'ticket_id' :self.id,
            'solicitante_id':self.responsable.id,
            'origin': self.name,  # Usar el nombre del ticket como referencia
        })

        # Recopilar líneas de productos
        sale_order_lines = []
        for line in self.line_ids:
            sale_order_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'price_unit': line.price_unit,
            }))

        # Agregar las líneas al pedido de venta
        sale_order.write({'order_line': sale_order_lines})

        return {
            'name': 'Pedido de Venta',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    # Nuevo campo para controlar cuando se envió la última notificación
    last_pending_notification = fields.Datetime(string="Última notificación de pendiente", readonly=True)
    
    # Método programado para ejecutarse diariamente (se configura en data XML)
    @api.model
    def _cron_notificar_tickets_pendientes(self):
        """
        Método cron para notificar a los técnicos sobre tickets pendientes por finalizar.
        Se ejecuta automáticamente según la programación definida.
        """
        _logger.info("Iniciando verificación de tickets pendientes por finalizar")
        
        # Agrupar tickets pendientes por técnico
        tecnicos_con_tickets = {}
        
        # Buscar todos los tickets en proceso
        tickets_pendientes = self.search([
            ('estado', '=', 'proceso'),
            ('agenda', '<', fields.Datetime.now())  # Solo tickets cuya fecha de visita ya pasó
        ])
        
        # Agrupar por técnico
        for ticket in tickets_pendientes:
            if not ticket.responsable:
                continue
                
            tech_id = ticket.responsable.id
            if tech_id not in tecnicos_con_tickets:
                tecnicos_con_tickets[tech_id] = {
                    'tecnico': ticket.responsable,
                    'tickets': []
                }
            
            tecnicos_con_tickets[tech_id]['tickets'].append(ticket)
        
        # Enviar notificaciones a cada técnico
        for tech_data in tecnicos_con_tickets.values():
            self._enviar_notificacion_pendientes(tech_data['tecnico'], tech_data['tickets'])
            
        return True
    
   
    def action_finalizar(self):
        _logger.info("=== Iniciando action_finalizar para tickets %s ===", self.ids)
        tickets = self.sudo()
        today = fields.Datetime.now().date()
        _logger.debug("Fecha actual: %s", today)

        for ticket in tickets:
            _logger.info("Procesando ticket ID %s (estado=%s)", ticket.id, ticket.estado)

            # VALIDACIONES DE CAMPOS REQUERIDOS SEGÚN LA LÓGICA DE LA VISTA
            errors = []
            
            # Campos requeridos cuando estado == 'nuevo'
            if ticket.estado == 'nuevo':
                if not ticket.agenda:
                    errors.append("• Agenda es requerida cuando el ticket está en estado 'nuevo'")
                if not ticket.responsable:
                    errors.append("• Responsable es requerido cuando el ticket está en estado 'nuevo'")
                if not ticket.description:
                    errors.append("• Descripción del problema es requerida cuando el ticket está en estado 'nuevo'")
            
            # Campos requeridos cuando estado == 'proceso' (para finalizar debe estar en proceso)
            if ticket.estado == 'proceso':
                # Contómetros requeridos en proceso
                if not ticket.contometrok_id:
                    errors.append("• Contador K es requerido cuando el ticket está en proceso")
                
                if not ticket.contometros_id:
                    errors.append("• Contador S es requerido cuando el ticket está en proceso")
                
                # Contador color requerido solo para equipos color en proceso
                if ticket.tipo_id == 'color' and not ticket.contometroc_id:
                    errors.append("• Contador Color es requerido para equipos a color cuando el ticket está en proceso")
                
                # Informe técnico requerido en proceso
                if not ticket.informe_id:
                    errors.append("• Informe Técnico es requerido cuando el ticket está en proceso")
                
                # Campos del Check List requeridos en proceso
                checklist_fields = [
                    ('calidad_id', 'Calidad'),
                    ('copia_id', 'Copia'),
                    ('impresion_id', 'Impresión'),
                    ('impresion_usb_id', 'Impresión USB'),
                    ('scaner_smb_id', 'Scanner SMB'),
                    ('scaner_usb_id', 'Scanner USB'),
                    ('scaner_ftp_id', 'Scanner FTP'),
                    ('scaner_mail_id', 'Scanner Mail'),
                    ('toner_black_id', 'Toner Black'),
                    ('bypass_id', 'Bypass'),
                    ('tray1_id', 'Tray 1'),
                    ('tray2_id', 'Tray 2'),
                    ('tray3_id', 'Tray 3'),
                    ('tray4_id', 'Tray 4'),
                    ('adf_id', 'ADF'),
                    ('finalizador_id', 'Finalizador'),
                    ('tacho_id', 'Tacho'),
                    ('fusora_id', 'Fusora'),
                    ('transfer_id', 'Transfer'),
                    ('optico_id', 'Óptico'),
                    ('black_id', 'Black'),
                ]
                
                # Validar campos generales del checklist cuando estado == 'proceso'
                for field_name, field_label in checklist_fields:
                    if not getattr(ticket, field_name, None):
                        errors.append(f"• {field_label} es requerido en el Check List cuando el ticket está en proceso")
                
                # Campos específicos para equipos color cuando estado == 'proceso' y tipo_id == 'color'
                if ticket.tipo_id == 'color':
                    color_fields = [
                        ('toner_magenta_id', 'Toner Magenta'),
                        ('toner_cyan_id', 'Toner Cyan'),
                        ('toner_yellow_id', 'Toner Yellow'),
                        ('magenta_id', 'Magenta'),
                        ('cyan_id', 'Cyan'),
                        ('yellow_id', 'Yellow'),
                    ]
                    
                    for field_name, field_label in color_fields:
                        if not getattr(ticket, field_name, None):
                            errors.append(f"• {field_label} es requerido para equipos a color cuando el ticket está en proceso")
            
            # Validar que el ticket esté en el estado correcto para finalizar
            if ticket.estado != 'proceso':
                errors.append(f"• El ticket debe estar en estado 'proceso' para poder finalizarlo. Estado actual: '{ticket.estado}'")
            
            # Si hay errores, mostrar mensaje detallado y no continuar
            if errors:
                error_message = "No se puede finalizar el ticket. Se encontraron los siguientes problemas:\n\n" + "\n".join(errors)
                error_message += "\n\nPor favor, complete todos los campos requeridos antes de intentar finalizar el ticket."
                raise UserError(error_message)

            unidad = ticket.product_alquiler
            
            # 1) Validar valores de contómetros (lanza error si no pasa)
            _logger.info("Validando contómetros del ticket %s...", ticket.id)
            try:
                ticket._check_contometro_values()
                _logger.info("Validación exitosa contómetros para ticket %s", ticket.id)
            except Exception:
                _logger.exception("Error en validación de contómetros para ticket %s", ticket.id)
                raise

            # 2) Crear pedido de venta si hay líneas
            if ticket.line_ids:
                _logger.info("Ticket %s tiene %d línea(s), creando pedido de venta", ticket.id, len(ticket.line_ids))
                ticket.create_sale_order()
                _logger.info("Pedido de venta creado para ticket %s", ticket.id)
            else:
                _logger.debug("Ticket %s no tiene líneas, se omite create_sale_order", ticket.id)

            # 3) Enviar correo de finalización
            _logger.info("Enviando correo de finalización para ticket %s", ticket.id)
            tmpl_fin = ticket.env.ref('sat.email_template_ticket_cliente_finalizacion')
            tmpl_fin.send_mail(ticket.id, force_send=True)
            _logger.info("Correo de finalización enviado para ticket %s", ticket.id)

            if ticket.retorno_id == 'no':
                _logger.info("ticket.retorno_id='no', enviando mail_template_retorno para ticket %s", ticket.id)
                ticket.env.ref('sat.mail_template_retorno').send_mail(ticket.id, force_send=True)
                _logger.info("Correo de retorno enviado para ticket %s", ticket.id)

            # 4) Actualizar estado de la unidad según tipo de servicio
            if unidad:
                _logger.info(
                    "Actualizando estado de UnidadAlquiler %s según tipo_servicio_id=%s",
                    unidad.id, ticket.tipo_servicio_id
                )
                if ticket.tipo_servicio_id == 'alquiler' and unidad.estado_alquiler_id == 'sin_revisar':
                    unidad.write({'estado_alquiler_id': 'revisada'})
                    _logger.info("Unidad %s pasada a 'revisada'", unidad.id)
                elif ticket.tipo_servicio_id == 'cambio_repuestos' and unidad.estado_alquiler_id == 'revisada':
                    prev = ticket.search([
                        ('product_alquiler', '=', unidad.id),
                        ('tipo_servicio_id', '=', 'alquiler')
                    ], order="create_date desc", limit=1)
                    if prev:
                        unidad.write({'estado_alquiler_id': 'lista'})
                        _logger.info("Unidad %s pasada a 'lista' (ticket previo %s)", unidad.id, prev.id)
                elif ticket.tipo_servicio_id == 'retiro':
                    unidad.write({
                        'estado_alquiler_id': 'sin_revisar',
                        'direccion': 'AV Angelica Gamarra 2156',
                        'contacto_id': 'Isidro',
                        'celular': '975399303',
                        'correo_': 'soporte@andescopiers.com.pe',
                        'cliente_id': 1,
                        'fecha_inicio': False,
                    })
                    _logger.info("Unidad %s reseteada por 'retiro'", unidad.id)

            # 5) Marcar ticket como finalizado y resetear notificación
            _logger.info("Marcando ticket %s como 'finalizado'", ticket.id)
            ticket.write({
                'estado': 'finalizado',
                'last_pending_notification': False,
            })

        _logger.info("=== action_finalizar completado para tickets %s ===", self.ids)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'view_id': False,
            'target': 'main',
        }
    
            

    def create_ticket_wizard(self):
        return {
            'name': 'Crear ticket',
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.alquiler',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(self.env.ref('sat.view_ticket_wizard').id, 'form')],
            'target': 'new',
        }
    
    
    responsable_mobile_clean = fields.Char(string='Número de celular (limpio)',  compute='_compute_responsable_mobile_clean', store=True )

    cliente_phones_clean = fields.Char(string='Números de contacto limpios', compute='_compute_cliente_phones_clean',  store=True
    )

    @api.depends('responsable.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            if record.responsable.mobile_phone:
                phone = record.responsable.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_mobile_clean = phone
            else:
                record.responsable_mobile_clean = 'NA'

    @api.depends('product_alquiler.celular')
    def _compute_cliente_phones_clean(self):
        for record in self:
            if record.product_alquiler.celular:
                phones = record.product_alquiler.celular.split('/')
                cleaned_phones = []
                for phone in phones:
                    phone = ''.join(phone.split())
                    if not phone.startswith('51'):
                        phone = '51' + phone
                    cleaned_phones.append(phone)
                record.cliente_phones_clean = ','.join(cleaned_phones)
            else:
                record.cliente_phones_clean = 'NA'

    

    def _generate_report_url(self):
        """Genera la URL del informe técnico en formato PDF."""
        report = self.env.ref('sat.report_template_id')
        pdf_content, _ = report.sudo().render_qweb_pdf([self.id])
        report_name = 'Informe_Tecnico_{}.pdf'.format(self.name)
        attachment = self.env['ir.attachment'].create({
            'name': report_name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'store_fname': report_name,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf'
        })
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return '{}/web/content/{}?download=true'.format(base_url, attachment.id)

    
         
    repuestos_count_ticket = fields.Integer(compute='compute_count_repuestos_ticket')

    def compute_count_repuestos_ticket(self):
         for record in self:
            record.repuestos_count_ticket = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', self.product_alquiler.id)])

    def get_repuestos_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos_ticket',
            'view_mode': 'list,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.product_alquiler.id)],
            'context': "{'create': False}"
        }  

    repuestos_count_ticket = fields.Integer(compute='compute_count_repuestos_ticket')

    def compute_count_repuestos_ticket(self):
         for record in self:
            record.repuestos_count_ticket = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', self.product_alquiler.id)])

    def get_repuestos_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos_ticket',
            'view_mode': 'list,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.product_alquiler.id)],
            'context': "{'create': False}"
        }  

      
    

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
                    selection_labels[field_name] = 'NA'  # Retorna 'NA' si no hay valor seleccionado
        _logger.info('Selection labels for %s: %s', self.name, selection_labels)
        return selection_labels


       
    
    # MODIFICA: action_asignar_masivo
    def action_asignar_masivo(self):
        _logger.info("🎯 [asignar_masivo] records=%s ids=%s", len(self), self.ids)

        # Validación
        tickets_no_nuevos = self.filtered(lambda t: t.estado != 'nuevo')
        if tickets_no_nuevos:
            raise UserError(
                "No se pueden asignar tickets que no están en estado 'nuevo'.\n"
                f"Diferentes: {', '.join(tickets_no_nuevos.mapped('name'))}"
            )

        Wizard = self.env['whatsapp.notification.wizard']
        view = self.env.ref('sat.view_whatsapp_notification_wizard_form_massive')

        wizard = Wizard.create({
            'es_asignacion_masiva': True,
            'tickets_masivos_ids': [(6, 0, self.ids)],
            'notificar_grupos': False,
        })
        _logger.info("✅ [asignar_masivo] wizard=%s es_asignacion_masiva=%s tickets=%s",
                    wizard.id, wizard.es_asignacion_masiva, len(wizard.tickets_masivos_ids))

        return {
            'type': 'ir.actions.act_window',
            'name': f'Asignación Masiva - {len(self)} Tickets',
            'res_model': 'whatsapp.notification.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': view.id,
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': {
                'default_es_asignacion_masiva': True,
                'default_tickets_masivos_ids': [(6, 0, self.ids)],
            },
        }


    def action_asignar_ticket(self):
        """
        Método modificado para manejar tanto asignación individual como masiva
        """
        if len(self) > 1:
            # Si son múltiples tickets, usar asignación masiva
            return self.action_asignar_masivo()
        
        # Para un solo ticket, usar el proceso original con wizard
        self.ensure_one()
        
        _logger.info(f"🎯 Iniciando proceso de asignación individual para ticket {self.name}")
        
        wizard = self.env['whatsapp.notification.wizard'].create({
            'ticket_id': self.id,
            'es_asignacion_masiva': False,
            'notificar_grupos': False,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmar Asignación de Ticket',
            'res_model': 'whatsapp.notification.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_es_asignacion_masiva': False,
                'default_notificar_grupos': False
            }
        }

    def _procesar_asignacion_masiva(self, wizard_data):
        """
        Procesa la asignación masiva agrupando por cliente y técnico
        """
        _logger.info(f"📋 Procesando asignación masiva de {len(self)} tickets")
        
        # Aplicar valores comunes del wizard a todos los tickets
        valores_comunes = {
            'responsable': wizard_data.get('tecnico_asignado').id if wizard_data.get('tecnico_asignado') else False,
            'agenda': wizard_data.get('fecha_visita'),
            'asistencia_id': wizard_data.get('asistencia_directa', 'no'),
        }
        
        # Aplicar valores individuales de tipo de servicio
        for ticket_data in wizard_data.get('ticket_lines', []):
            ticket = self.browse(ticket_data['ticket_id'])
            valores_ticket = valores_comunes.copy()
            valores_ticket['tipo_servicio_id'] = ticket_data['tipo_servicio_id']
            ticket.write(valores_ticket)
        
        # Agrupar tickets por cliente y técnico para envío consolidado
        grupos = {}
        for ticket in self:
            key = (ticket.partner_id.id if ticket.partner_id else 0, 
                ticket.responsable.id if ticket.responsable else 0)
            
            if key not in grupos:
                grupos[key] = {
                    'cliente': ticket.partner_id,
                    'tecnico': ticket.responsable,
                    'tickets': self.env['ticket.alquiler']
                }
            grupos[key]['tickets'] |= ticket
        
        _logger.info(f"📊 Se crearon {len(grupos)} grupos para notificación")
        
        # Procesar cada grupo
        for grupo_data in grupos.values():
            try:
                self._procesar_grupo_tickets_consolidado(grupo_data, wizard_data)
            except Exception as e:
                _logger.error(f"Error procesando grupo: {e}")
                raise
        
        # Cambiar estado de todos los tickets a 'proceso'
        self.write({'estado': 'proceso'})
        
        return True

    def _procesar_grupo_tickets_consolidado(self, grupo_data, wizard_data):
        """
        Procesa un grupo de tickets del mismo cliente/técnico con mensajes consolidados
        """
        tickets = grupo_data['tickets']
        cliente = grupo_data['cliente']
        tecnico = grupo_data['tecnico']
        
        _logger.info(f"🔄 Procesando grupo consolidado: Cliente={cliente.name if cliente else 'NA'}, "
                    f"Técnico={tecnico.name if tecnico else 'NA'}, "
                    f"Tickets={len(tickets)}")
        
        try:
            # 1. Crear eventos de calendario para todos los tickets
            for ticket in tickets:
                try:
                    ticket.crear_evento_calendario()
                except Exception as e:
                    _logger.warning(f"Error creando evento para ticket {ticket.name}: {e}")
            
            # 2. Enviar notificación a grupos si está habilitada
            if wizard_data.get('notificar_grupos') and wizard_data.get('grupo_seleccionado'):
                self._enviar_notificacion_grupo_consolidada(tickets, wizard_data)
            
            # 3. Generar y enviar mensajes WhatsApp consolidados
            self._enviar_whatsapp_consolidado(tickets, cliente, tecnico)
            
            # 4. Enviar correos consolidados
            self._enviar_correos_consolidados(tickets, cliente, tecnico)
            
            # 5. Verificar asistencia directa y notificar gerente si es necesario
            tickets_directos = tickets.filtered(lambda t: t.asistencia_id == 'si')
            if tickets_directos:
                self._notificar_gerente_asistencia_directa_consolidada(tickets_directos)
            
            _logger.info(f"✅ Grupo procesado exitosamente: {len(tickets)} tickets")
            
        except Exception as e:
            _logger.error(f"❌ Error procesando grupo consolidado: {e}")
            raise

    
    def _agrupar_tickets_por_tipo_servicio(self, tickets):
        """
        Agrupa tickets por tipo de servicio para usar en templates
        """
        agrupados = {}
        for ticket in tickets:
            tipo = ticket.tipo_servicio_id
            if tipo not in agrupados:
                agrupados[tipo] = []
            agrupados[tipo].append(ticket)
        return agrupados

    
    def action_proceso(self):
        self.estado='proceso'
        
    def action_nuevo(self):
        self.estado='nuevo'
    def action_crear_evaluacion(self):
        """Genera una evaluación para el ticket seleccionado."""
        self.ensure_one()  # Asegúrate de que solo se está trabajando con un registro
        _logger.info(f"Iniciando creación de evaluación para el ticket: {self.name}")
        
        # Verificar si el ticket cumple con las condiciones
        if self.estado != 'finalizado':
            raise ValidationError(_("El ticket no está finalizado. No se puede generar la evaluación."))
        
        if not self.agenda or self.agenda.date() != datetime.now(timezone(self.env.user.tz or 'UTC')).date():
            raise ValidationError(_("La fecha de agenda no coincide con la fecha actual. No se puede generar la evaluación."))
        
        # Verificar si ya existe una evaluación para el ticket
        evaluation_model = self.env['client.service.evaluation']
        existing_eval = evaluation_model.search([('ticket_id', '=', self.id)], limit=1)
        if existing_eval:
            raise ValidationError(_("Ya existe una evaluación para este ticket."))

        # Crear la evaluación
        try:
            evaluation = evaluation_model.create({
                'ticket_id': self.id,
                'state': 'draft'
            })
            _logger.info(f"Evaluación creada para el ticket: {self.name}")
            
            # Enviar correo con la evaluación creada
            template = self.env.ref('sat.email_template_service_evaluation', raise_if_not_found=False)
            if template:
                template.send_mail(evaluation.id, force_send=True)
                _logger.info(f"Correo enviado para la evaluación del ticket: {self.name}")

            return {
                'type': 'ir.actions.act_window',
                'name': 'Evaluación',
                'view_mode': 'form',
                'res_model': 'client.service.evaluation',
                'res_id': evaluation.id,
                'target': 'current',
            }

        except Exception as e:
            _logger.error(f"Error al crear evaluación para el ticket {self.name}: {e}")
            raise ValidationError(_("Error al crear la evaluación: {}").format(str(e)))

    
        
    

    color = fields.Integer(string='Índice de Color', default=0)
    
    @api.depends('estado')
    def _compute_color(self):
        """Calcula el color del ticket basado en su estado"""
        for record in self:
            if record.estado == 'borrador':
                record.color = 0  # Gris - Para tickets en borrador
            elif record.estado == 'asignado':
                record.color = 4  # Azul - Para tickets asignados
            elif record.estado == 'en_proceso':
                record.color = 3  # Amarillo - Para tickets en proceso
            elif record.estado == 'finalizado':
                record.color = 10  # Verde - Para tickets finalizados
            elif record.estado == 'cancelado':
                record.color = 1  # Rojo - Para tickets cancelados
            else:
                record.color = 0  # Color por defecto
    # ===========================
    #  INFORME TÉCNICO AUTOMÁTICO
    # ===========================

    # (1) Mapa de checklist (campo -> (etiqueta visible, peso de severidad))
    _CHECKLIST_MAP = {
        # Módulos / transporte papel
        'adf_id': ('ADF', 2),
        'bypass_id': ('Bypass', 2),
        'finalizador_id': ('Finalizador', 2),
        'tray1_id': ('Bandeja 1', 1),
        'tray2_id': ('Bandeja 2', 1),
        'tray3_id': ('Bandeja 3', 1),
        'tray4_id': ('Bandeja 4', 1),
        # Consumibles y proceso
        'tacho_id': ('Tacho residual', 1),
        'fusora_id': ('Unidad fusora', 3),
        'transfer_id': ('Faja de transferencia', 3),
        'optico_id': ('Unidad óptica', 3),
        'black_id': ('Unidad de imagen negro', 3),
        'magenta_id': ('Unidad de imagen magenta', 3),
        'cyan_id': ('Unidad de imagen cian', 3),
        'yellow_id': ('Unidad de imagen amarillo', 3),
    }

    # (2) Funciones (para detectar solo las que NO operan)
    _FUNCIONES = [
        ('copia_id', 'Copia'),
        ('impresion_id', 'Impresión'),
        ('impresion_usb_id', 'Impresión USB'),
        ('scaner_smb_id', 'Scanner SMB'),
        ('scaner_usb_id', 'Scanner USB'),
        ('scaner_ftp_id', 'Scanner FTP'),
        ('scaner_mail_id', 'Scanner Mail'),
    ]

    # (3) Tóner (solo se reporta si está vacío o sin botella)
    _TONERS = [
        ('toner_black_id', 'Tóner negro'),
        ('toner_cyan_id', 'Tóner cian'),
        ('toner_magenta_id', 'Tóner magenta'),
        ('toner_yellow_id', 'Tóner amarillo'),
    ]

    # (4) Mensaje base natural por tipo de servicio
    _SERVICIO_MSG = {
        'instalacion': (
            "Se realizó la instalación, configuración inicial y pruebas de copia, impresión y escaneo. "
            "El equipo queda operativo para su uso."
        ),
        'retiro': (
            "Se efectuó el retiro del equipo y la desconexión de sus accesorios, dejando el área ordenada."
        ),
        'mantenimiento_preventivo': (
            "Se realizó un mantenimiento preventivo integral: limpieza interna y externa, "
            "ajustes menores y verificación general de funcionamiento."
        ),
        'mantenimiento_correctivo': (
            "Se realizó mantenimiento correctivo sobre las unidades reportadas, "
            "con pruebas de validación al cierre."
        ),
        'cambio_repuestos': (
            "Se reemplazaron los repuestos indicados y se efectuaron pruebas funcionales de cierre."
        ),
        'remoto': (
            "Se brindó asistencia remota y se verificó el correcto funcionamiento posterior."
        ),
        'revision': (
            "Se efectuó revisión general, limpieza básica y diagnóstico de funcionamiento."
        ),
        'alquiler': (
            "Se preparó el equipo para alquiler con limpieza, configuración básica y pruebas iniciales."
        ),
    }

    # -------------------------
    # Utilidades de autogenerado
    # -------------------------

    def _is_autogen_informe(self):
        """True si el informe actual fue autogenerado (no editado manualmente)."""
        html = (self.informe_id or '').lower()
        return 'data-autogen="1"' in html

    def _collect_findings(self):
        """
        Reúne hallazgos del checklist por severidad:
        - con_falla: módulos marcados 'no'
        - desgaste: módulos marcados 'desgaste'
        - requiere_cambio: módulos marcados 'cambio'
        - score: severidad acumulada (para conclusión/calidad)
        """
        con_falla, desgaste, requiere_cambio, no_aplica = [], [], [], []
        severidad_total = 0

        for field_name, (etiqueta, peso) in self._CHECKLIST_MAP.items():
            val = getattr(self, field_name, False)
            if not val or val == 'si':
                continue
            if val == 'no':
                con_falla.append(etiqueta)
                severidad_total += 1 * peso
            elif val == 'desgaste':
                desgaste.append(etiqueta)
                severidad_total += 2 * peso
            elif val == 'cambio':
                requiere_cambio.append(etiqueta)
                severidad_total += 3 * peso
            elif val == 'no_aplica':
                no_aplica.append(etiqueta)

        return {
            'con_falla': con_falla,
            'desgaste': desgaste,
            'requiere_cambio': requiere_cambio,
            'no_aplica': no_aplica,
            'score': severidad_total,
        }

    def _calc_calidad(self, findings):
        """Devuelve 'buena' / 'regular' / 'mala' según los hallazgos del checklist."""
        if findings['requiere_cambio'] or findings['con_falla']:
            return 'mala'
        if findings['desgaste']:
            return 'regular'
        return 'buena'

    def _get_funciones_no_operativas(self):
        """Lista de funciones que salieron 'no' (no operativas)."""
        etiquetas = []
        for fname, label in self._FUNCIONES:
            if getattr(self, fname, False) == 'no':
                etiquetas.append(label)
        return etiquetas

    def _get_toners_criticos(self):
        """
        Devuelve tóneres críticos solo si están 'vacío' o 'sin_botella'.
        En monocromo solo considera negro.
        """
        criticos = []
        for fname, label in self._TONERS:
            if self.tipo_id != 'color' and fname != 'toner_black_id':
                continue
            val = getattr(self, fname, False)
            if val in ('vacio', 'sin_botella'):
                criticos.append(label)
        return criticos

    def _service_message(self):
        """Texto base natural según el tipo de servicio."""
        return self._SERVICIO_MSG.get(
            self.tipo_servicio_id or 'revision',
            "Se realizó atención técnica y verificación general de funcionamiento."
        )

    def _build_informe_html(self):
        """
        Genera un informe RESUMIDO y PROFESIONAL:
        • Siempre: texto base según el tipo de servicio (natural).
        • Solo si corresponde: bloque “Observaciones” con EXCEPCIONES
            - funciones que NO operan
            - módulos con DESGASTE o que REQUIEREN CAMBIO
            - tóneres críticos (vacío / sin botella)
        • Conclusión breve según severidad.
        • No muestra encabezados de equipo ni “Problema reportado”.
        """
        f = self._collect_findings()
        funciones_no = self._get_funciones_no_operativas()
        toners_crit = self._get_toners_criticos()

        # Conclusión dinámica según severidad
        calidad = self._calc_calidad(f)
        if calidad == 'mala':
            concl = (
                "Condición general: *mala*. Requiere intervención inmediata para evitar "
                "paradas no planificadas."
            )
        elif calidad == 'regular':
            concl = (
                "Condición general: *regular*. Equipo operativo con desgaste; "
                "se recomienda programar cambio preventivo."
            )
        else:
            concl = "Condición general: *buena*. Mantener el plan de mantenimiento preventivo."

        def _ul(items):
            return '' if not items else '<ul>' + ''.join(f'<li>{it}</li>' for it in items) + '</ul>'

        # Construir solo las observaciones necesarias
        bloques = []
        if funciones_no:
            bloques.append(f"<p><strong>Funciones no operativas</strong></p>{_ul(funciones_no)}")
        if f['requiere_cambio']:
            bloques.append(f"<p><strong>Requiere cambio inmediato</strong></p>{_ul(f['requiere_cambio'])}")
        if f['desgaste']:
            bloques.append(f"<p><strong>Componentes con desgaste</strong></p>{_ul(f['desgaste'])}")
        # Si hay módulos “con falla” y aún no se listaron por funciones, muéstralos
        if f['con_falla'] and not funciones_no:
            bloques.append(f"<p><strong>Con falla</strong></p>{_ul(f['con_falla'])}")
        if toners_crit:
            bloques.append(f"<p><strong>Consumibles críticos</strong></p>{_ul(toners_crit)}")

        excepciones_html = ''.join(bloques)

        # Texto base por tipo de servicio (siempre)
        texto_base = self._service_message()

        # Cuerpo: siempre texto base; Observaciones solo si existen
        cuerpo_html = (
            f"<p>{texto_base}</p>"
            if not excepciones_html else
            f"<p>{texto_base}</p><h5 style='margin:12px 0 6px;'>Observaciones</h5>{excepciones_html}"
        )

        # Si NO hay observaciones y la calidad es "buena", mantenemos el tono sobrio
        # y evitamos redundancias.
        if not excepciones_html and calidad == 'buena':
            concl = "Equipo en buen estado tras la intervención. Mantener plan de mantenimiento."

        html = f"""
    <div data-autogen="1" style="font-family: Arial; line-height:1.5;">
    {cuerpo_html}
    <h5 style="margin:12px 0 6px;">Conclusión</h5>
    <p>{concl}</p>
    <p style="color:#888; font-size:12px; margin-top:10px;">
        *Informe generado automáticamente a partir del checklist.*
    </p>
    </div>
    """
        return html, calidad

    def _autofill_informe_si_corresponde(self):
        """
        Genera/actualiza el informe automáticamente si:
        - está vacío, o
        - el informe actual fue autogenerado (data-autogen="1")
        Respeta la edición manual del técnico.
        """
        if self.informe_id and not self._is_autogen_informe():
            return
        html, calidad = self._build_informe_html()
        self.update({'informe_id': html, 'calidad_id': calidad})

    # (onchange) Regenerar automáticamente cuando cambie servicio o checklist
    @api.onchange(
        'tipo_servicio_id',           # <- asegura el mensaje base correcto
        'tipo_id',
        # funciones
        'copia_id', 'impresion_id', 'impresion_usb_id',
        'scaner_smb_id', 'scaner_usb_id', 'scaner_ftp_id', 'scaner_mail_id',
        # checklist módulos
        'adf_id', 'bypass_id', 'finalizador_id',
        'tray1_id', 'tray2_id', 'tray3_id', 'tray4_id',
        'tacho_id', 'fusora_id', 'transfer_id', 'optico_id',
        'black_id', 'magenta_id', 'cyan_id', 'yellow_id',
        # tóner
        'toner_black_id', 'toner_cyan_id', 'toner_magenta_id', 'toner_yellow_id',
    )
    def _onchange_autoinforme(self):
        for rec in self:
            rec._autofill_informe_si_corresponde()

    # Botón opcional en formulario para “Regenerar informe”
    def action_regenerar_informe(self):
        for rec in self:
            html, calidad = rec._build_informe_html()
            rec.write({'informe_id': html, 'calidad_id': calidad})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informe técnico'),
                'message': _('Informe regenerado automáticamente desde el checklist.'),
                'type': 'success',
            }
        }

            
class ReportTicketAlquiler(models.AbstractModel):
    _name = 'report.sat.ticket_alquiler'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['ticket.alquiler'].browse(docids)
        selection_labels = {}
        for doc in docs:
            # Llama al método get_selection_labels() para poblar selection_labels
            selection_labels[doc.id] = doc.get_selection_labels() if doc else {}
        return {
            'doc_ids': docids,
            'doc_model': 'ticket.alquiler',
            'docs': docs,
            'selection_labels': selection_labels,
        }



class TicketAlquilerLine(models.Model):
    _name = 'ticket.alquiler.line'
    _description = 'Línea de Ticket de Alquiler'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket', required=True )
    product_id = fields.Many2one('product.product', string='Producto', required=True )
    product_uom_qty = fields.Float(string='Cantidad', required=True, default=1.0 )
    price_unit = fields.Float(string='Precio Unitario', required=True)
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_price_subtotal', store=True )

    @api.depends('product_uom_qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_uom_qty * line.price_unit
    def action_add_product_line(self):
        # Redirigir al método de ticket.alquiler
        return self.env['ticket.alquiler'].browse(self.ticket_id.id).action_add_product_line()
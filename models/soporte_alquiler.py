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
        for record in self:
            previous_record = self.search(
                [('product_alquiler', '=', record.product_alquiler.id), ('id', '<', record.id)],
                limit=1,
                order='id desc'
            )

            # Convertir los valores a enteros (si no tienen valor, se asume 0)
            current_k = int(record.contometrok_id) if record.contometrok_id else 0
            current_color = int(record.contometroc_id) if record.contometroc_id else 0
            current_scanner = int(record.contometros_id) if record.contometros_id else 0

            prev_k = int(previous_record.contometrok_id) if previous_record and previous_record.contometrok_id else 0
            prev_color = int(previous_record.contometroc_id) if previous_record and previous_record.contometroc_id else 0
            prev_scanner = int(previous_record.contometros_id) if previous_record and previous_record.contometros_id else 0

            # Validar contómetro K
            if previous_record and current_k <= prev_k:
                raise ValidationError(
                    _("❗ ERROR: EL VALOR DEL CONTÓMETRO K ES INCORRECTO\n\n"
                    "Debe ingresar un valor MAYOR que el último valor registrado ({}) para esta máquina."
                    .format(prev_k))
                )

            # Validar contómetro color solo si es máquina a color
            if record.tipo_id == 'color':
                if previous_record and current_color <= prev_color:
                    raise ValidationError(
                        _("❗ ERROR: EL VALOR DEL CONTÓMETRO COLOR ES INCORRECTO\n\n"
                        "Debe ingresar un valor MAYOR que el último valor registrado ({}) para esta máquina."
                        .format(prev_color))
                    )
                if current_color == 0:
                    raise ValidationError(
                        _("❗ ERROR: EL VALOR DEL CONTÓMETRO COLOR NO PUEDE SER 0\n\n"
                        "Debe ingresar el valor ACTUAL del contómetro.")
                    )

            # Validar contómetro scanner
            if previous_record and current_scanner <= prev_scanner:
                raise ValidationError(
                    _("❗ ERROR: EL VALOR DEL CONTÓMETRO SCANNER ES INCORRECTO\n\n"
                    "Debe ingresar un valor MAYOR que el último valor registrado ({}) para esta máquina."
                    .format(prev_scanner))
                )

            # Validar que ni K ni scanner sean 0
            if current_k == 0 or current_scanner == 0:
                raise ValidationError(
                    _("❗ ERROR: EL VALOR DEL CONTÓMETRO NO PUEDE SER 0\n\n"
                    "Debe ingresar el valor ACTUAL del contómetro.")
                )


    
    tipo_servicio_id = fields.Selection([("instalacion", "Instalación"), ("retiro", "Retiro de maquina"),
                                         ("mantenimiento_preventivo", "Mantenimeinto preventivo"), (
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

    def action_finalizar(self):
        # Deshabilitar las reglas de acceso temporalmente para evitar restricciones
        self = self.sudo()

        # Llamar manualmente a la función de validación para cada registro
        for record in self:
            record._check_contometro_values()

        # Realizar las acciones necesarias antes de cambiar el estado
        if self.line_ids:
            self.create_sale_order()

        # Enviar el correo con la plantilla de finalización
        template4 = self.env.ref('sat.email_template_ticket_cliente_finalizacion')
        template4.send_mail(self.id, force_send=True)

        # Verificar el valor de retorno_id
        if self.retorno_id == 'no':
            template5 = self.env.ref('sat.mail_template_retorno')
            template5.send_mail(self.id, force_send=True)

        # Condición 1: Cambiar estado en `alquiler` a 'revisada' si es 'preparar para alquiler' y está en 'sin revisar'
        if self.tipo_servicio_id == 'alquiler' and self.product_alquiler.estado_alquiler_id == 'sin_revisar':
            self.product_alquiler.write({'estado_alquiler_id': 'revisada'})

        # Condición 2: Cambiar estado en `alquiler` a 'lista' si es 'cambio de repuestos' y el ticket anterior era 'preparar para alquiler'
        elif self.tipo_servicio_id == 'cambio_repuestos' and self.product_alquiler.estado_alquiler_id == 'revisada':
            ticket_anterior = self.search([
                ('product_alquiler', '=', self.product_alquiler.id),
                ('tipo_servicio_id', '=', 'alquiler')
            ], order="create_date desc", limit=1)
            
            if ticket_anterior:
                self.product_alquiler.write({'estado_alquiler_id': 'lista'})

        # Condición 3: Si es 'retiro de máquina', actualizar los campos en `alquiler`
        elif self.tipo_servicio_id == 'retiro':
            self.product_alquiler.write({
                'estado_alquiler_id': 'sin_revisar',
                'direccion': 'AV Angelica Gamarra 2156',
                'contacto_id': 'Isidro',
                'celular': '975399303',
                'correo_': 'soporte@andescopiers.com.pe',
                'cliente_id': 1,
                'fecha_inicio': ''
            })

        # Cambiar el estado del ticket a 'finalizado'
        self.write({'estado': 'finalizado'})

        # Redirigir a la vista de lista de tickets después de finalizar
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

    def send_whatsapp_message(self, phone, message, file_url=None):
        """Envía un mensaje de WhatsApp con o sin archivo adjunto utilizando la API externa."""
        _logger.debug(f"Enviando mensaje a {phone} con contenido: {message} y archivo: {file_url}")
        
        url = 'https://whatsapp.andessolutioncopiers.com/api/message'
        data = {
            'phone': phone,
            'message': message
        }
        if file_url:
            data['file_url'] = file_url
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data)

        _logger.debug(f"Código de estado: {response.status_code}")
        _logger.debug(f"Respuesta de la API: {response.text}")

        try:
            response_json = response.json()
            _logger.debug(f"Respuesta JSON: {response_json}")
            return response_json
        except json.JSONDecodeError as e:
            error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
            _logger.error(error_msg)
            return {"error": error_msg}

    

    def enviar_mensaje_whatsapp_finalizacion(self):
        msg_cliente_finalizacion = "Hola, estimado cliente.\n\nQueremos informarle que hemos completado satisfactoriamente nuestra visita técnica programada. A continuación, le detallamos el trabajo realizado durante la visita:\n\n*Ticket #:* {}\n*Fecha de Visita:* {}\n*Tipo de servicio:* {}\n*Dirección:* {}\n*Técnico Asignado:* {}\n*DNI:* {}\n\n*ESPECIFICACIONES DEL EQUIPO*\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n*Contómetro K:* {}\n*Contómetro color:* {}\n*Contómetro scanner:* {}\n\n*PROBLEMA REPORTADO*\n{}\n\n*INFORME TÉCNICO*\n{}\n\nAgradecemos su confianza en nuestros servicios y productos. Si necesita más asistencia o tiene cualquier requerimiento adicional, no dude en comunicarse con nosotros.".format(
            self.name if self.name else 'NA',
            self.agenda.strftime('%d/%m/%Y') if self.agenda else 'NA',
            self.tipo_servicio_id if self.tipo_servicio_id else 'NA',
            self.direccion_id_r if self.direccion_id_r else 'NA',
            self.responsable.name if self.responsable and self.responsable.name else 'NA',
            self.responsable.vat if self.responsable and self.responsable.vat else 'NA',
            self.marca_id_r if self.marca_id_r else 'NA',
            self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
            self.serie_id_r if self.serie_id_r else 'NA',
            self.contometrok_id if self.contometrok_id else 'NA',
            self.contometroc_id if self.contometroc_id else 'NA',
            self.contometros_id if self.contometros_id else 'NA',
            self.description if self.description else 'NA',
            self.informe_id if self.informe_id else 'NA'
        )

        # Generar URL del informe
        file_url = self._generate_report_url()

        # Enviar mensaje al cliente
        if self.cliente_phones_clean:
            phone_numbers = self.cliente_phones_clean.split(',')
            for phone_number in phone_numbers:
                self.send_whatsapp_message(phone_number, msg_cliente_finalizacion, file_url)

        # Enviando el correo de finalización al cliente
        template4 = self.env.ref('sat.email_template_ticket_cliente_finalizacion')
        template4.send_mail(self.id, force_send=True)
        # Verificar el valor de asistencia_id
        if self.retorno_id == 'no':
            # Enviar el correo de retorno si asistencia_id es 'no'
            template5 = self.env.ref('sat.ticket_alquiler')
            template5.send_mail(self.id, force_send=True)

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


       
    def enviar_mensaje_whatsapp(self):
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info("Iniciando el proceso de envío de mensaje de WhatsApp para el registro ID: %s", self.id)

        # Crear evento en calendario
        try:
            _logger.info("Intentando crear un evento en el calendario...")
            evento_creado = self.crear_evento_calendario()
            if not evento_creado:
                _logger.warning("No se pudo crear el evento en el calendario para el registro ID: %s", self.id)
                self.message_post(body="No se pudo crear el evento en el calendario.")
            else:
                _logger.info("Evento creado/actualizado exitosamente para el registro ID: %s", self.id)
        except Exception as e:
            _logger.error("Error al intentar crear el evento en el calendario para el registro ID: %s. Detalles: %s", self.id, str(e))
            self.message_post(body=f"Error al intentar crear el evento en el calendario: {str(e)}")

        # Obtener etiquetas de selección
        try:
            selection_labels = self.get_selection_labels()
            _logger.debug("Etiquetas de selección obtenidas: %s", selection_labels)
        except Exception as e:
            _logger.error("Error al obtener etiquetas de selección para el registro ID: %s. Detalles: %s", self.id, str(e))
            selection_labels = {}

        # Mensaje para el técnico
        try:
            msg_tecnico = (
                f"Hola *{self.responsable.name if self.responsable and self.responsable.name else 'NA'}*,\n\n"
                "Se le ha asignado un Ticket de servicio. Lea atentamente los detalles del servicio:\n\n"
                f"*Cliente:* {self.partner_id.name if self.partner_id and self.partner_id.name else 'NA'}\n"
                f"*Dirección:* {self.direccion_id_r if self.direccion_id_r else 'NA'}\n"
                f"*Contacto:* {self.contacto_id_r if self.contacto_id_r else 'NA'}\n"
                f"*Modelo:* {self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA'}\n"
                f"*Serie:* {self.serie_id_r if self.serie_id_r else 'NA'}\n"
                f"*Problema:* {self.description if self.description else 'NA'}\n"
                f"*Fecha de visita:* {self.agenda_local if self.agenda_local else 'NA'}\n"
                f"*Tipo de servicio:* {dict(self._fields['tipo_servicio_id'].selection).get(self.tipo_servicio_id, 'NA')}\n"
                f"*Asistencia directa:* {dict(self._fields['asistencia_id'].selection).get(self.asistencia_id, 'NA')}\n\n"
                f"*URL del Ticket:* {self.url}"
            )
            _logger.debug("Mensaje para técnico generado: %s", msg_tecnico)
        except Exception as e:
            _logger.error("Error al generar mensaje para el técnico. Detalles: %s", str(e))
            msg_tecnico = ""

        # Mensaje para el cliente
        try:
            msg_cliente = "Estimado/a *{}*,\n\nLe informamos que hemos programado una visita técnica para atender su requerimiento. A continuación, le detallamos la información correspondiente:\n\n*Ticket #:* {}\n*Fecha de Visita:* {}\n*Tipo de servicio:* {}\n*Dirección:* {}\n*Técnico Asignado:* {}\n*DNI:* {}\n\n*ESPECIFICACIONES DEL EQUIPO*\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n\n*PROBLEMA REPORTADO*\n{}\n\n1. Dar autorización para el ingreso de nuestro personal a sus oficinas o el espacio donde se encuentre nuestro equipo.\n2. Disponibilidad de espacio y tiempo para que nuestro personal pueda desarrollar su labor.\n\nGracias por su atención.".format(
                self.partner_id.name if self.partner_id and self.partner_id.name else 'NA',
                self.name if self.name else 'NA',
                self.agenda_local if self.agenda_local else 'NA',
                selection_labels.get('tipo_servicio_id', 'NA'),
                self.direccion_id_r if self.direccion_id_r else 'NA',
                self.responsable.name if self.responsable and self.responsable.name else 'NA',
                self.responsable.vat if self.responsable and self.responsable.vat else 'NA',
                self.marca_id_r if self.marca_id_r else 'NA',
                self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
                self.serie_id_r if self.serie_id_r else 'NA',
                self.description if self.description else 'NA'
            )
            _logger.debug("Mensaje para cliente generado: %s", msg_cliente)
        except Exception as e:
            _logger.error("Error al generar mensaje para el cliente. Detalles: %s", str(e))
            msg_cliente = ""

        # Enviar mensaje al técnico
        if self.responsable and self.responsable_mobile_clean:
            try:
                phone_number = self.responsable_mobile_clean
                _logger.info("Enviando mensaje de WhatsApp al técnico: %s", phone_number)
                self.send_whatsapp_message(phone_number, msg_tecnico)
            except Exception as e:
                _logger.error("Error al enviar mensaje de WhatsApp al técnico. Detalles: %s", str(e))

        # Enviar mensaje al cliente
        if self.cliente_phones_clean:
            try:
                phone_numbers = self.cliente_phones_clean.split(',')
                for phone_number in phone_numbers:
                    _logger.info("Enviando mensaje de WhatsApp al cliente: %s", phone_number)
                    self.send_whatsapp_message(phone_number, msg_cliente)
            except Exception as e:
                _logger.error("Error al enviar mensaje de WhatsApp al cliente. Detalles: %s", str(e))
           # Añadir notificación al gerente si es asistencia directa
        if self.asistencia_id == 'si':
            msg_gerente = (
                f"⚠️ *VISITA TÉCNICA DIRECTA*\n\n"
                f"Técnico: {self.responsable.name if self.responsable and self.responsable.name else 'NA'}\n"
                f"Cliente: {self.partner_id.name if self.partner_id and self.partner_id.name else 'NA'}\n"
                f"Fecha y hora: {self.agenda_local if self.agenda_local else 'NA'}\n"
                f"Dirección: {self.direccion_id_r if self.direccion_id_r else 'NA'}"
            )
            try:
                _logger.info("Enviando notificación de visita directa al gerente")
                self.send_whatsapp_message('51922541085', msg_gerente)
            except Exception as e:
                _logger.error("Error al enviar mensaje al gerente. Detalles: %s", str(e))

        # Enviar correos electrónicos
        try:
            template1 = self.env.ref('sat.email_template_ticket_cliente')
            template1.with_context(selection_labels=selection_labels).send_mail(self.id, force_send=True)
            _logger.info("Correo enviado al cliente.")
            
            template2 = self.env.ref('sat.email_template_ticket_tecnico')
            template2.with_context(selection_labels=selection_labels).send_mail(self.id, force_send=True)
            _logger.info("Correo enviado al técnico.")
            
            if self.asistencia_id == 'si':
                template3 = self.env.ref('sat.mail_template_asistencia_directa')
                template3.with_context(selection_labels=selection_labels).send_mail(self.id, force_send=True)
                _logger.info("Correo adicional enviado por asistencia directa.")
        except Exception as e:
            _logger.error("Error al enviar correos electrónicos. Detalles: %s", str(e))

        # Cambiar estado
        self.estado = 'proceso'
        _logger.info("Estado del registro ID: %s cambiado a 'proceso'.", self.id)

        return {
            'type': 'ir.actions.act_window_close'  # Cerrar ventana tras completar la acción
        }


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

    
        
    def enviar_mensaje_whatsapp_reporter(self):
        """Enviar mensaje de WhatsApp con los datos proporcionados por el cliente."""
        if self.reporter_phone:
            # Datos del reporte del cliente
            message = (
                f"Estimado/a {self.reporter_name},\n\n"
                "Hemos recibido su reporte de incidente y agradecemos la información proporcionada. "
                "A continuación, detallamos los datos registrados:\n\n"
                f"Cliente: {self.partner_id.name if self.partner_id else 'No especificado'}\n"
                f"Dirección: {self.direccion_id_r if self.direccion_id_r else 'No especificada'}\n"
                f"Modelo: {self.modelo_id_r if self.modelo_id_r else 'No especificada'}\n"
                f"Serie: {self.serie_id_r if self.serie_id_r else 'No especificada'}\n"
                f"Descripción del problema: {self.description if self.description else 'No proporcionada'}\n"
            )

            if self.problem_photo:
                message += "Foto del problema: Se adjuntará en un correo."

            message += (
                "\nNuestro equipo de soporte programará la asistencia técnica en función de la disponibilidad. "
                "Nos pondremos en contacto con usted para confirmar la fecha y hora."
            )

            # Enviar mensaje de WhatsApp con los detalles del cliente
            self.send_whatsapp_message(self.reporter_phone, message)

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
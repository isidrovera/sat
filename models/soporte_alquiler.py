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
                
                # Convertir a string si no lo es
                value_str = str(value_str).strip()
                
                if not value_str:
                    return 0
                
                try:
                    # Remover comas (separadores de miles)
                    cleaned = value_str.replace(',', '')
                    
                    # Si tiene punto, verificar si es separador decimal o de miles
                    if '.' in cleaned:
                        parts = cleaned.split('.')
                        if len(parts) == 2:
                            # Si la parte después del punto tiene 3 dígitos, es separador de miles
                            if len(parts[1]) == 3 and parts[1].isdigit():
                                cleaned = parts[0] + parts[1]  # Ejemplo: 123.456 -> 123456
                            else:
                                # Es decimal, tomar solo la parte entera
                                cleaned = parts[0]  # Ejemplo: 123.45 -> 123
                    
                    # Convertir a entero
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

            # VALIDAR CONTÓMETRO K
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
                    _logger.error(f"❌ VALIDACIÓN COLOR: valor es 0")
                    raise ValidationError(
                        _("❗ ERROR: EL VALOR DEL CONTÓMETRO COLOR NO PUEDE SER 0\n\n"
                        "Debe ingresar el valor ACTUAL del contómetro.")
                    )

            # VALIDAR CONTÓMETRO SCANNER (permite valores iguales o mayores)
            if previous_record and current_scanner < prev_scanner:
                _logger.error(f"❌ VALIDACIÓN SCANNER FALLÓ: {current_scanner} < {prev_scanner}")
                raise ValidationError(
                    _("❗ ERROR: EL VALOR DEL CONTÓMETRO SCANNER ES INCORRECTO\n\n"
                    "Debe ingresar un valor IGUAL O MAYOR que el último valor registrado para esta máquina.\n"
                    f"Valor actual: {current_scanner:,}\n"
                    f"Valor anterior: {prev_scanner:,}\n"
                    f"Ticket anterior: {previous_record.name}")
                )

            # VALIDAR QUE K Y SCANNER NO SEAN 0 (excepto en casos especiales)
            if current_k == 0 and current_scanner == 0:
                _logger.error(f"❌ VALIDACIÓN: Ambos contadores son 0")
                raise ValidationError(
                    _("❗ ERROR: LOS CONTÓMETROS NO PUEDEN SER 0\n\n"
                    "Debe ingresar los valores ACTUALES de los contómetros.")
                )

            # Si llegamos aquí, todo está bien
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
    
    def _enviar_notificacion_pendientes(self, tecnico, tickets):
        """
        Envía notificación por WhatsApp al técnico sobre sus tickets pendientes.
        
        Args:
            tecnico: objeto res.users del técnico
            tickets: lista de tickets pendientes
        """
        if not tecnico or not tickets:
            return False
            
        # Verificar si el técnico tiene número de teléfono limpio
        phone_number = None
        for ticket in tickets:
            if ticket.responsable_mobile_clean and ticket.responsable_mobile_clean != 'NA':
                phone_number = ticket.responsable_mobile_clean
                break
                
        if not phone_number:
            _logger.warning(f"No se encontró número de teléfono válido para el técnico {tecnico.name}")
            return False
            
        # Construir mensaje
        cantidad_tickets = len(tickets)
        lista_tickets = "\n".join([
            f"• Ticket: {t.name} - Cliente: {t.partner_id.name or 'NA'} - Fecha: {t.agenda_local or 'NA'}"
            for t in tickets[:5]  # Mostrar máximo 5 tickets para no hacer el mensaje muy largo
        ])
        
        if cantidad_tickets > 5:
            lista_tickets += f"\n... y {cantidad_tickets - 5} tickets más."
        
        mensaje = f"""
⚠️ *ALERTA DE TICKETS PENDIENTES* ⚠️

Hola *{tecnico.name}*,

Tienes *{cantidad_tickets} tickets* en proceso que necesitan ser finalizados:

{lista_tickets}

Por favor, finaliza estos tickets lo antes posible. 
        
*IMPORTANTE:* Si no cierras estos tickets a tiempo, se notificará a gerencia y no podrás solicitar movilidad hasta regularizar tu situación.

Para finalizar rápidamente un ticket, ingresa a Odoo y usa la opción "Finalizar".
"""
        
        # Enviar mensaje por WhatsApp
        try:
            for ticket in tickets:
                # Usar el primer ticket para enviar el mensaje
                resultado = ticket.send_whatsapp_message(phone_number, mensaje)
                # Registrar la notificación en el log de los tickets
                for t in tickets:
                    t.write({'last_pending_notification': fields.Datetime.now()})
                    t.message_post(
                        body=f"Notificación automática enviada al técnico sobre tickets pendientes por finalizar. "
                             f"Total: {cantidad_tickets} ticket(s)."
                    )
                
                _logger.info(f"Mensaje de alerta enviado al técnico {tecnico.name} sobre {cantidad_tickets} tickets pendientes")
                break
                
            return True
        except Exception as e:
            _logger.error(f"Error al enviar notificación de tickets pendientes: {str(e)}")
            return False

    def action_finalizar(self):
        _logger.info("=== Iniciando action_finalizar para tickets %s ===", self.ids)
        tickets = self.sudo()
        today = fields.Datetime.now().date()
        _logger.debug("Fecha actual: %s", today)

        for ticket in tickets:
            _logger.info("Procesando ticket ID %s (estado=%s)", ticket.id, ticket.estado)

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
    # Campo computed para controlar la visibilidad del botón
    mostrar_boton_contadores = fields.Boolean(
        string='Mostrar Botón Contadores',
        compute='_compute_mostrar_boton_contadores',
        store=False,
        help='Controla si se muestra el botón para cargar contadores'
    )

    @api.depends('estado', 'agenda', 'product_alquiler')
    def _compute_mostrar_boton_contadores(self):
        """
        Computed field para mostrar/ocultar el botón de cargar contadores
        ACTUALIZADO: Busca en modelos de contadores por serie
        """
        for record in self:
            mostrar = False
            
            # Solo mostrar si está en proceso
            if record.estado == 'proceso' and record.product_alquiler:
                # Verificar si hay contadores disponibles desde diferentes fuentes
                tiene_contadores_disponibles = record._tiene_contadores_disponibles()
                mostrar = tiene_contadores_disponibles
            
            record.mostrar_boton_contadores = mostrar

    def _tiene_contadores_disponibles(self):
        """
        Verifica si hay contadores disponibles desde diferentes fuentes para cargar
        """
        if not self.product_alquiler or not self.product_alquiler.serie:
            return False
        
        serie = self.product_alquiler.serie
        _logger.info(f"🔍 Verificando contadores disponibles para serie: {serie}")
        
        # 1) Verificar en el propio equipo de alquiler
        if self._tiene_contadores_en_equipo():
            _logger.info("✅ Contadores encontrados en equipo de alquiler")
            return True
        
        # 2) Verificar en PrintTracker Daily Reading
        if self._tiene_contadores_en_printtracker():
            _logger.info("✅ Contadores encontrados en PrintTracker Daily Reading")
            return True
        
        # 3) Verificar en Contador Automático (correos)
        if self._tiene_contadores_en_correos():
            _logger.info("✅ Contadores encontrados en Contador Automático")
            return True
        
        _logger.info("❌ No se encontraron contadores disponibles")
        return False

    def _tiene_contadores_en_equipo(self):
        """
        Verifica si el equipo tiene contadores y fecha de actualización coincidente
        """
        try:
            unidad = self.product_alquiler
            if not unidad or not self.agenda or not unidad.fecha_ultima_actualizacion:
                return False
            
            fecha_agenda = self.agenda.date()
            fecha_actualizacion = unidad.fecha_ultima_actualizacion.date()
            
            if fecha_agenda == fecha_actualizacion:
                tiene_contadores = (
                    (unidad.contador_bn or 0) > 0 or 
                    (unidad.contador_color or 0) > 0 or 
                    (unidad.contador_scan or 0) > 0
                )
                if tiene_contadores:
                    _logger.info(f"✅ Equipo tiene contadores para fecha {fecha_agenda}")
                    return True
            
            return False
        except Exception as e:
            _logger.error(f"❌ Error verificando contadores en equipo: {e}")
            return False

    def _tiene_contadores_en_printtracker(self):
        """
        Verifica si hay lecturas de PrintTracker para la serie
        """
        try:
            serie = self.product_alquiler.serie
            fecha_agenda = self.agenda.date()
            
            # Buscar lectura exacta de la fecha de agenda
            lectura_exacta = self.env['printtracker.daily.reading'].search([
                ('serie', '=', serie),
                ('fecha', '=', fecha_agenda),
                ('estado', 'in', ['validado', 'aplicado'])
            ], limit=1)
            
            if lectura_exacta and self._lectura_tiene_contadores(lectura_exacta):
                _logger.info(f"✅ PrintTracker: lectura exacta para {fecha_agenda}")
                return True
            
            # Buscar la lectura más reciente (hasta 7 días antes)
            fecha_limite = fecha_agenda - timedelta(days=7)
            lectura_reciente = self.env['printtracker.daily.reading'].search([
                ('serie', '=', serie),
                ('fecha', '>=', fecha_limite),
                ('fecha', '<=', fecha_agenda),
                ('estado', 'in', ['validado', 'aplicado'])
            ], order='fecha desc', limit=1)
            
            if lectura_reciente and self._lectura_tiene_contadores(lectura_reciente):
                _logger.info(f"✅ PrintTracker: lectura reciente del {lectura_reciente.fecha}")
                return True
            
            return False
        except Exception as e:
            _logger.error(f"❌ Error verificando PrintTracker: {e}")
            return False

    def _tiene_contadores_en_correos(self):
        """
        Verifica si hay contadores procesados desde correos para la serie
        """
        try:
            serie = self.product_alquiler.serie
            fecha_agenda = self.agenda.date()
            
            # Buscar procesamiento exacto de la fecha de agenda
            contador_exacto = self.env['contador.automatico'].search([
                ('serie_detectada', '=', serie),
                ('fecha_procesamiento', '>=', fields.Datetime.combine(fecha_agenda, datetime.min.time())),
                ('fecha_procesamiento', '<', fields.Datetime.combine(fecha_agenda + timedelta(days=1), datetime.min.time())),
                ('estado', '=', 'procesado')
            ], limit=1)
            
            if contador_exacto and self._contador_automatico_tiene_datos(contador_exacto):
                _logger.info(f"✅ Correos: contador exacto para {fecha_agenda}")
                return True
            
            # Buscar el más reciente (hasta 7 días antes)
            fecha_limite = fecha_agenda - timedelta(days=7)
            contador_reciente = self.env['contador.automatico'].search([
                ('serie_detectada', '=', serie),
                ('fecha_procesamiento', '>=', fields.Datetime.combine(fecha_limite, datetime.min.time())),
                ('fecha_procesamiento', '<=', fields.Datetime.combine(fecha_agenda + timedelta(days=1), datetime.min.time())),
                ('estado', '=', 'procesado')
            ], order='fecha_procesamiento desc', limit=1)
            
            if contador_reciente and self._contador_automatico_tiene_datos(contador_reciente):
                fecha_proc = contador_reciente.fecha_procesamiento.date()
                _logger.info(f"✅ Correos: contador reciente del {fecha_proc}")
                return True
            
            return False
        except Exception as e:
            _logger.error(f"❌ Error verificando contadores automáticos: {e}")
            return False

    def _lectura_tiene_contadores(self, lectura):
        """Verifica si una lectura de PrintTracker tiene contadores válidos"""
        return (
            (lectura.contador_bn or 0) > 0 or 
            (lectura.contador_color or 0) > 0 or 
            (lectura.contador_scan or 0) > 0
        )

    def _contador_automatico_tiene_datos(self, contador):
        """Verifica si un contador automático tiene datos válidos"""
        return (
            (contador.contador_bn_detectado or 0) > 0 or 
            (contador.contador_color_detectado or 0) > 0 or 
            (contador.contador_scan_detectado or 0) > 0
        )

    def action_cargar_contadores(self):
        """
        Carga los contadores desde diferentes fuentes disponibles
        ACTUALIZADO: Busca en múltiples modelos por serie
        """
        self.ensure_one()
        _logger.info(f"=== Iniciando carga de contadores para ticket {self.name} ===")
        
        # Verificar que el ticket esté en proceso
        if self.estado != 'proceso':
            raise UserError(_("Esta función solo está disponible para tickets en proceso."))
        
        # Verificar que existe una unidad de alquiler asignada
        if not self.product_alquiler:
            raise UserError(_("No hay un equipo asignado a este ticket."))
        
        if not self.product_alquiler.serie:
            raise UserError(_("El equipo asignado no tiene número de serie."))
        
        serie = self.product_alquiler.serie
        _logger.info(f"🔍 Buscando contadores para serie: {serie}")
        
        # Buscar contadores en orden de prioridad
        contadores_encontrados, fuente_datos = self._buscar_contadores_por_prioridad(serie)
        
        # DEBUG - Agregar logs detallados
        _logger.info(f"🔍 DEBUG - Contadores encontrados: {contadores_encontrados}")
        _logger.info(f"🔍 DEBUG - Fuente: {fuente_datos}")
        
        if not contadores_encontrados:
            raise UserError(_(
                "No se encontraron contadores válidos para la serie %s.\n"
                "Verifique que existan lecturas de PrintTracker o correos procesados para este equipo."
            ) % serie)
        
        # CRÍTICO: Deshabilitar validación automática temporalmente
        _logger.info("🔧 Deshabilitando validación automática temporalmente...")
        
        # Crear un contexto sin validaciones
        self_no_constraints = self.with_context(skip_constraints=True)
        
        # Cargar los contadores encontrados SIN VALIDACIONES
        valores_cargados = []
        
        # Cargar contador B/N
        bn_valor = contadores_encontrados.get('contador_bn', 0)
        _logger.info(f"🔍 DEBUG BN - Valor: {bn_valor}, Condición: {bn_valor > 0}")
        if bn_valor > 0:
            self_no_constraints.contometrok_id = str(bn_valor)
            valores_cargados.append(f"Contador B/N: {bn_valor:,}")
            _logger.info(f"→ contometrok_id cargado: {self_no_constraints.contometrok_id}")
        else:
            _logger.warning(f"⚠️ DEBUG BN - NO SE CARGA porque valor es {bn_valor}")
        
        # Cargar contador color (solo para máquinas a color)  
        color_valor = contadores_encontrados.get('contador_color', 0)
        _logger.info(f"🔍 DEBUG COLOR - Tipo máquina: {self.tipo_id}, Valor: {color_valor}, Condición: {self.tipo_id == 'color' and color_valor > 0}")
        if self.tipo_id == 'color' and color_valor > 0:
            self_no_constraints.contometroc_id = str(color_valor)
            valores_cargados.append(f"Contador Color: {color_valor:,}")
            _logger.info(f"→ contometroc_id cargado: {self_no_constraints.contometroc_id}")
        else:
            _logger.info(f"ℹ️ DEBUG COLOR - NO SE CARGA (tipo: {self.tipo_id}, valor: {color_valor})")
        
        # Cargar contador scanner
        scan_valor = contadores_encontrados.get('contador_scan', 0)
        _logger.info(f"🔍 DEBUG SCANNER - Valor: {scan_valor}, Tipo: {type(scan_valor)}, Condición: {scan_valor > 0}")
        if scan_valor > 0:
            self_no_constraints.contometros_id = str(scan_valor)
            valores_cargados.append(f"Contador Scanner: {scan_valor:,}")
            _logger.info(f"→ contometros_id cargado: {self_no_constraints.contometros_id}")
        else:
            _logger.error(f"❌ DEBUG SCANNER - NO SE CARGA porque valor es {scan_valor} (tipo: {type(scan_valor)})")
        
        # VERIFICAR VALORES FINALES ANTES DE VALIDACIÓN
        _logger.info(f"🎯 DEBUG FINAL - Valores asignados a campos:")
        _logger.info(f"   contometrok_id: '{self.contometrok_id}' (tipo: {type(self.contometrok_id)})")
        _logger.info(f"   contometroc_id: '{self.contometroc_id}' (tipo: {type(self.contometroc_id)})")
        _logger.info(f"   contometros_id: '{self.contometros_id}' (tipo: {type(self.contometros_id)})")
        
        # Verificar que se cargó al menos un contador
        if not valores_cargados:
            _logger.error(f"❌ No se cargaron valores. contadores_encontrados: {contadores_encontrados}")
            raise UserError(_("Los contadores encontrados no son válidos para cargar."))
        
        _logger.info(f"✅ Valores cargados: {valores_cargados}")
        
        # AHORA SÍ: Ejecutar validación manual una sola vez con todos los valores
        _logger.info("🔍 Ejecutando validación manual final...")
        try:
            # Forzar recálculo de campos computed si es necesario
            self.invalidate_cache()
            # Validar manualmente solo UNA VEZ
            self._check_contometro_values()
            _logger.info("✅ Validación manual exitosa")
        except ValidationError as e:
            _logger.error(f"❌ Validación falló: {str(e)}")
            raise e
        
        # Mensaje de confirmación
        mensaje_exito = (
            f"✅ Contadores cargados exitosamente desde {fuente_datos}:\n\n"
            f"📋 {' • '.join(valores_cargados)}\n\n"
            f"📅 Serie: {serie}"
        )
        
        # Registrar en el log del ticket
        self.message_post(
            body=mensaje_exito,
            message_type='notification'
        )
        
        _logger.info(f"=== Contadores cargados exitosamente para ticket {self.name} ===")
        
        # Mostrar mensaje al usuario
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contadores Cargados'),
                'message': _('Los contadores se han cargado correctamente desde %s.') % fuente_datos,
                'type': 'success',
                'sticky': False,
            }
        }
    def _buscar_contadores_por_prioridad(self, serie):
        """
        Busca contadores en orden de prioridad:
        1. Equipo de alquiler (si fecha coincide)
        2. PrintTracker Daily Reading (más reciente)
        3. Contador Automático (más reciente)
        """
        fecha_agenda = self.agenda.date() if self.agenda else None
        
        # PRIORIDAD 1: Equipo de alquiler (solo si fecha coincide)
        _logger.info("🔍 Prioridad 1: Verificando equipo de alquiler...")
        contadores_equipo = self._obtener_contadores_equipo(fecha_agenda)
        if contadores_equipo:
            return contadores_equipo, "Equipo de Alquiler"
        
        # PRIORIDAD 2: PrintTracker Daily Reading
        _logger.info("🔍 Prioridad 2: Verificando PrintTracker Daily Reading...")
        contadores_pt = self._obtener_contadores_printtracker(serie, fecha_agenda)
        if contadores_pt:
            return contadores_pt, "PrintTracker Daily Reading"
        
        # PRIORIDAD 3: Contador Automático (correos)
        _logger.info("🔍 Prioridad 3: Verificando Contador Automático...")
        contadores_correo = self._obtener_contadores_correos(serie, fecha_agenda)
        if contadores_correo:
            return contadores_correo, "Procesamiento de Correos"
        
        _logger.warning("❌ No se encontraron contadores en ninguna fuente")
        return None, None

    def _obtener_contadores_equipo(self, fecha_agenda):
        """
        Obtiene contadores del equipo de alquiler si la fecha coincide
        """
        try:
            unidad = self.product_alquiler
            if not unidad or not fecha_agenda or not unidad.fecha_ultima_actualizacion:
                return None
            
            if fecha_agenda == unidad.fecha_ultima_actualizacion.date():
                contadores = {
                    'contador_bn': unidad.contador_bn or 0,
                    'contador_color': unidad.contador_color or 0,
                    'contador_scan': unidad.contador_scan or 0,
                }
                
                if any(v > 0 for v in contadores.values()):
                    _logger.info(f"✅ Contadores desde equipo: {contadores}")
                    return contadores
            
            return None
        except Exception as e:
            _logger.error(f"❌ Error obteniendo contadores del equipo: {e}")
            return None

    def _obtener_contadores_printtracker(self, serie, fecha_agenda):
        """
        Obtiene contadores desde PrintTracker Daily Reading
        """
        try:
            # Buscar lectura exacta de la fecha de agenda
            if fecha_agenda:
                lectura_exacta = self.env['printtracker.daily.reading'].search([
                    ('serie', '=', serie),
                    ('fecha', '=', fecha_agenda),
                    ('estado', 'in', ['validado', 'aplicado'])
                ], limit=1)
                
                if lectura_exacta:
                    contadores = self._extraer_contadores_printtracker(lectura_exacta)
                    if contadores:
                        _logger.info(f"✅ Contadores exactos desde PrintTracker ({fecha_agenda}): {contadores}")
                        return contadores
            
            # Buscar la lectura más reciente (hasta 30 días antes)
            fecha_limite = (fecha_agenda - timedelta(days=30)) if fecha_agenda else (datetime.now().date() - timedelta(days=30))
            fecha_max = fecha_agenda if fecha_agenda else datetime.now().date()
            
            lectura_reciente = self.env['printtracker.daily.reading'].search([
                ('serie', '=', serie),
                ('fecha', '>=', fecha_limite),
                ('fecha', '<=', fecha_max),
                ('estado', 'in', ['validado', 'aplicado'])
            ], order='fecha desc', limit=1)
            
            if lectura_reciente:
                contadores = self._extraer_contadores_printtracker(lectura_reciente)
                if contadores:
                    _logger.info(f"✅ Contadores recientes desde PrintTracker ({lectura_reciente.fecha}): {contadores}")
                    return contadores
            
            return None
        except Exception as e:
            _logger.error(f"❌ Error obteniendo contadores de PrintTracker: {e}")
            return None

    def _obtener_contadores_correos(self, serie, fecha_agenda):
        """
        Obtiene contadores desde Contador Automático (correos)
        """
        try:
            # Buscar procesamiento exacto de la fecha de agenda
            if fecha_agenda:
                contador_exacto = self.env['contador.automatico'].search([
                    ('serie_detectada', '=', serie),
                    ('fecha_procesamiento', '>=', fields.Datetime.combine(fecha_agenda, datetime.min.time())),
                    ('fecha_procesamiento', '<', fields.Datetime.combine(fecha_agenda + timedelta(days=1), datetime.min.time())),
                    ('estado', '=', 'procesado')
                ], limit=1)
                
                if contador_exacto:
                    contadores = self._extraer_contadores_correos(contador_exacto)
                    if contadores:
                        _logger.info(f"✅ Contadores exactos desde correos ({fecha_agenda}): {contadores}")
                        return contadores
            
            # Buscar el más reciente (hasta 30 días antes)
            fecha_limite = (fecha_agenda - timedelta(days=30)) if fecha_agenda else (datetime.now().date() - timedelta(days=30))
            fecha_max = (fecha_agenda + timedelta(days=1)) if fecha_agenda else datetime.now().date() + timedelta(days=1)
            
            contador_reciente = self.env['contador.automatico'].search([
                ('serie_detectada', '=', serie),
                ('fecha_procesamiento', '>=', fields.Datetime.combine(fecha_limite, datetime.min.time())),
                ('fecha_procesamiento', '<', fields.Datetime.combine(fecha_max, datetime.min.time())),
                ('estado', '=', 'procesado')
            ], order='fecha_procesamiento desc', limit=1)
            
            if contador_reciente:
                contadores = self._extraer_contadores_correos(contador_reciente)
                if contadores:
                    fecha_proc = contador_reciente.fecha_procesamiento.date()
                    _logger.info(f"✅ Contadores recientes desde correos ({fecha_proc}): {contadores}")
                    return contadores
            
            return None
        except Exception as e:
            _logger.error(f"❌ Error obteniendo contadores de correos: {e}")
            return None

    def _extraer_contadores_printtracker(self, lectura):
        """
        Extrae contadores de una lectura de PrintTracker
        """
        contadores = {
            'contador_bn': lectura.contador_bn or 0,
            'contador_color': lectura.contador_color or 0,
            'contador_scan': lectura.contador_scan or 0,
        }
        
        # Verificar que al menos uno sea mayor que 0
        if any(v > 0 for v in contadores.values()):
            return contadores
        
        return None

    def _extraer_contadores_correos(self, contador):
        """
        Extrae contadores de un registro de contador automático
        """
        contadores = {
            'contador_bn': contador.contador_bn_detectado or 0,
            'contador_color': contador.contador_color_detectado or 0,
            'contador_scan': contador.contador_scan_detectado or 0,
        }
        
        # Verificar que al menos uno sea mayor que 0
        if any(v > 0 for v in contadores.values()):
            return contadores
        
        return None
            

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


       
    def _enviar_mensaje_whatsapp_original(self):
        """
        Método original con tu código actual de envío de WhatsApp
        (Copia EXACTAMENTE tu método enviar_mensaje_whatsapp actual aquí)
        """
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
            'type': 'ir.actions.act_window_close'
        }

    def action_asignar_ticket(self):
        """
        Método que SIEMPRE muestra el wizard antes de proceder con la asignación
        """
        self.ensure_one()
        
        _logger.info(f"🎯 Iniciando proceso de asignación para ticket {self.name}")
        
        # SIEMPRE mostrar el wizard, sin importar si hay grupos configurados o no
        wizard = self.env['whatsapp.notification.wizard'].create({
            'ticket_id': self.id,
            'notificar_grupos': False,  # Por defecto NO notificar, que el usuario decida
        })
        
        _logger.info(f"🪄 Wizard creado con ID: {wizard.id}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmar Asignación de Ticket',
            'res_model': 'whatsapp.notification.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_notificar_grupos': False
            }
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
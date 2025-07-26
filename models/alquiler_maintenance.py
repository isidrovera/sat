import calendar
import requests
import uuid
from urllib.parse import urlencode
from odoo.exceptions import UserError, ValidationError
import io
import qrcode
import re
import base64
from io import BytesIO
import xlwt
from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)

class UnidadAlquiler(models.Model):
    _inherit = 'alquiler'

    control_mantenimiento = fields.Boolean(
        string="Mantenimiento mensual", default=True)
    fecha_inicio = fields.Date(
        string='Fecha de mantenimiento inicial',
        required=False,
        tracking=True,
        default=fields.Date.today,  # ← AGREGAR ESTA LÍNEA
        help="Fecha inicial del mantenimiento"
    )

    intervalo_meses = fields.Selection([
        ('1', 'Mensual'),
        ('2', 'Cada 2 meses'),
        ('3', 'Cada 3 meses'),
        ('6', 'Cada 6 meses'),
        ('12', 'Anual')
    ], string='Intervalo de mantenimiento',
        default='1',
        required=True,
        tracking=True,
        help="Frecuencia de mantenimiento"
    )
    patron_recurrencia = fields.Selection([
        ('fecha_exacta', 'Día específico del mes'),
        ('semana_dia', 'Día específico de la semana')
    ], string='Patrón de recurrencia',
        default='fecha_exacta',
        required=True,
        tracking=True,
        help="Determina cómo se calculará la próxima fecha de mantenimiento"
    )

    semana_mes = fields.Selection([
        ('1', 'Primera'),
        ('2', 'Segunda'),
        ('3', 'Tercera'),
        ('4', 'Cuarta'),
        ('-1', 'Última'),
        ('-2', 'Penúltima'),
        ('-3', 'Antepenúltima')
    ], string='Posición en el mes',
        tracking=True,
        help="Posición específica del día de la semana en el mes (ej. primer lunes, último viernes, etc.)"
    )

    dia_semana = fields.Selection([
        ('0', 'Lunes'),
        ('1', 'Martes'),
        ('2', 'Miércoles'),
        ('3', 'Jueves'),
        ('4', 'Viernes'),
        ('5', 'Sábado'),
        ('6', 'Domingo')
    ], string='Día de la semana',
        tracking=True,
        help="Qué día de la semana debe programarse el mantenimiento"
    )

    fecha_recurrente = fields.Date(
        string='Próxima fecha de mantenimiento',
        compute='_compute_fecha_recurrente',
        store=True,
        tracking=True,
        help="Próxima fecha de mantenimiento"
    )

    # Campo de estado de programación
    estado_programacion = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('confirmado', 'Confirmado'),
        ('reprogramado', 'Por Reprogramar')
    ], string='Estado de Programación',
        default='pendiente',
        tracking=True,
        help="Estado actual de la programación del mantenimiento"
    )

    # Campos adicionales para tracking
    fecha_confirmacion = fields.Datetime(
        string='Fecha de Confirmación',
        tracking=True,
        readonly=True,
        help="Fecha cuando se confirmó el mantenimiento"
    )

    motivo_reprogramacion = fields.Text(
        string='Motivo de Reprogramación',
        tracking=True,
        help="Razón por la que se solicita reprogramación"
    )
    usar_fecha_recurrente_como_base = fields.Boolean(
        string='Usar fecha recurrente como base',
        default=False,
        help="Si está activado, usará la fecha recurrente como base para calcular la próxima fecha. Si no, usará la fecha inicial."
    )
    @api.onchange('fecha_inicio', 'patron_recurrencia')
    def _onchange_fecha_inicio(self):
        """
        Cuando el usuario selecciona una fecha y el patrón 'día específico de la semana',
        este método detecta automáticamente qué día de la semana es y qué posición
        ocupa en el mes (primera, segunda, última, etc.)
        """
        if self.fecha_inicio and self.patron_recurrencia == 'semana_dia':
            # Detectar día de la semana (0-6 donde 0 es lunes)
            dia_semana = self.fecha_inicio.weekday()
            self.dia_semana = str(dia_semana)

            # Obtener todas las ocurrencias de este día de la semana en el mes
            ocurrencias = []
            year, month = self.fecha_inicio.year, self.fecha_inicio.month
            ultimo_dia = calendar.monthrange(year, month)[1]

            for dia in range(1, ultimo_dia + 1):
                fecha = datetime(year, month, dia).date()
                if fecha.weekday() == dia_semana:
                    ocurrencias.append(dia)

            # Encontrar la posición de la fecha actual en las ocurrencias
            posicion = None
            for i, dia in enumerate(ocurrencias):
                if dia == self.fecha_inicio.day:
                    posicion = i
                    break

            if posicion is not None:
                total_ocurrencias = len(ocurrencias)

                # Determinar si es mejor expresar desde el inicio o desde el final
                posicion_desde_final = -1 * (total_ocurrencias - posicion)

                # Si es una de las últimas 3 posiciones, usar expresión desde el final
                if posicion_desde_final >= -3:  # Última, penúltima o antepenúltima
                    self.semana_mes = str(posicion_desde_final)  # -1, -2 o -3
                else:
                    # Es mejor expresarlo desde el inicio
                    # +1 porque la posición empieza en 0
                    self.semana_mes = str(posicion + 1)

                # Loguear para depuración
                _logger.info(
                    f"DETECCIÓN DE PATRÓN: Fecha={self.fecha_inicio}, "
                    f"Día semana={dia_semana} ({['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana]}), "
                    f"Ocurrencias en mes={ocurrencias}, "
                    f"Posición={posicion+1} de {total_ocurrencias}, "
                    f"Posición asignada={self.semana_mes}"
                )



    
    @api.depends('fecha_inicio', 'intervalo_meses', 'patron_recurrencia', 'semana_mes', 'dia_semana', 'usar_fecha_recurrente_como_base')
    def _compute_fecha_recurrente(self):
        """
        Calcula la próxima fecha de mantenimiento basada en el patrón seleccionado,
        manteniendo la posición relativa correcta de los días en el mes.
        """
        for record in self:
            if not record.fecha_inicio:
                record.fecha_recurrente = False
                continue

            # Guardar fecha anterior para comparación
            fecha_anterior = record.fecha_recurrente

            # DETECCIÓN DE PROBLEMAS: Imprimir valores involucrados en el cálculo
            _logger.info(f"VALORES DE ENTRADA: fecha_inicio={record.fecha_inicio}, "
                        f"fecha_recurrente={record.fecha_recurrente}, "
                        f"intervalo_meses={record.intervalo_meses}, "
                        f"patron_recurrencia={record.patron_recurrencia}, "
                        f"semana_mes={record.semana_mes}, "
                        f"dia_semana={record.dia_semana}, "
                        f"usar_fecha_recurrente_como_base={record.usar_fecha_recurrente_como_base}")

            # ✅ CAMBIO PRINCIPAL: Determinar la fecha base para el cálculo
            # QUITAR la condición "record.fecha_recurrente > fields.Date.today()"
            if record.usar_fecha_recurrente_como_base and record.fecha_recurrente:
                base_date = record.fecha_recurrente  # ← Ahora SÍ usará fechas vencidas como base
                _logger.info(f"USANDO FECHA_RECURRENTE COMO BASE: {base_date}")
            else:
                base_date = record.fecha_inicio
                _logger.info(f"USANDO FECHA_INICIO COMO BASE: {base_date}")

            # Asegurarse que intervalo_meses sea un valor válido - IMPORTANTE
            intervalo_str = record.intervalo_meses or '1'
            try:
                meses = int(intervalo_str)
                # Verificación adicional para valores no válidos
                if meses <= 0 or meses > 12:
                    meses = 1  # Valor predeterminado seguro
                    _logger.warning(
                        f"Valor de intervalo no válido: {intervalo_str}, usando predeterminado: 1")
            except (ValueError, TypeError):
                meses = 1  # Valor predeterminado si hay error de conversión
                _logger.warning(
                    f"Error al convertir intervalo: {intervalo_str}, usando predeterminado: 1")

            # Determinar el mes objetivo sumando exactamente el número de meses del intervalo
            target_date = base_date + relativedelta(months=meses)
            target_year = target_date.year
            target_month = target_date.month

            # Calcular la nueva fecha según el patrón elegido
            if record.patron_recurrencia == 'fecha_exacta' or not record.patron_recurrencia:
                # Mantener el mismo día del mes
                day_of_month = base_date.day

                # Ajustar si el día no existe en el mes destino
                last_day = calendar.monthrange(target_year, target_month)[1]
                if day_of_month > last_day:
                    day_of_month = last_day

                siguiente_fecha = datetime(
                    target_year, target_month, day_of_month).date()
                record.fecha_recurrente = siguiente_fecha

            elif record.patron_recurrencia == 'semana_dia' and record.semana_mes and record.dia_semana:
                try:
                    weekday = int(record.dia_semana)  # 0=Lunes, 6=Domingo
                    # Posición (puede ser desde inicio o final)
                    position_str = record.semana_mes

                    # Encontrar todas las ocurrencias del día de la semana en el mes objetivo
                    ocurrencias = []
                    last_day = calendar.monthrange(
                        target_year, target_month)[1]

                    for dia in range(1, last_day + 1):
                        fecha = datetime(target_year, target_month, dia).date()
                        if fecha.weekday() == weekday:
                            ocurrencias.append(fecha)

                    # No hay ocurrencias de este día de la semana (raro, pero posible en teoría)
                    if not ocurrencias:
                        record.fecha_recurrente = base_date + \
                            relativedelta(months=meses)
                        _logger.warning(
                            f"No se encontraron ocurrencias de día {weekday} en {target_month}/{target_year}")
                        continue

                    # Determinar qué ocurrencia usar según la posición
                    position = int(position_str)
                    if position < 0:  # Posición desde el final (-1, -2, -3)
                        # Asegurarnos de que el índice esté dentro del rango
                        index = position
                        if abs(position) > len(ocurrencias):
                            # Usar la primera ocurrencia si no hay suficientes
                            index = -len(ocurrencias)
                        siguiente_fecha = ocurrencias[index]
                    else:  # Posición desde el inicio (1, 2, 3, 4)
                        # Ajustar el índice (position es 1-based, el índice es 0-based)
                        index = position - 1
                        if index >= len(ocurrencias):
                            # Usar la última si no hay suficientes
                            index = len(ocurrencias) - 1
                        siguiente_fecha = ocurrencias[index]

                    record.fecha_recurrente = siguiente_fecha

                except Exception as e:
                    # Si hay cualquier error en el cálculo, usar un método simple como fallback
                    _logger.error(
                        f"Error en cálculo de fecha recurrente: {str(e)}")
                    record.fecha_recurrente = base_date + \
                        relativedelta(months=meses)
            else:
                # Fallback simple
                record.fecha_recurrente = base_date + \
                    relativedelta(months=meses)

            # Log para depuración detallada
            dia_nombre = ['Lunes', 'Martes', 'Miércoles',
                        'Jueves', 'Viernes', 'Sábado', 'Domingo']
            dia_semana_nombre = ""
            if record.dia_semana:
                try:
                    dia_semana_nombre = dia_nombre[int(record.dia_semana)]
                except (IndexError, ValueError):
                    dia_semana_nombre = f"Día {record.dia_semana}"

            _logger.info(
                f"✅ CÁLCULO FECHA CORREGIDO: Base={base_date}, "
                f"Intervalo={meses} meses, "
                f"Mes objetivo={target_month}/{target_year}, "
                f"Patrón={record.patron_recurrencia}, "
                f"Posición={record.semana_mes}, "
                f"Día={dia_semana_nombre}, "
                f"Resultado={record.fecha_recurrente}"
            )

            # Verificación adicional del resultado
            diferencia_meses = (record.fecha_recurrente.year - base_date.year) * \
                12 + (record.fecha_recurrente.month - base_date.month)
            if diferencia_meses != meses:
                _logger.warning(
                    f"ALERTA: La diferencia de meses ({diferencia_meses}) no coincide con el intervalo ({meses}). "
                    f"Base={base_date}, Resultado={record.fecha_recurrente}"
                )

            # Actualizar estado si la fecha cambió
            if fecha_anterior and record.fecha_recurrente != fecha_anterior:
                if record.estado_programacion in ['confirmado', 'reprogramado']:
                    record.estado_programacion = 'pendiente'
                    record.message_post(
                        body=f"⚠️ Nueva fecha de mantenimiento calculada: {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                        message_type='notification'
                    )

    def iniciar_calculo_recurrente(self):
        """
        Activa el cálculo recurrente para calcular fechas futuras
        a partir de la fecha recurrente actual en vez de la fecha de inicio.
        """
        self.ensure_one()
        self.usar_fecha_recurrente_como_base = True
        self.message_post(
            body="🔄 Se ha iniciado el cálculo recurrente. Las próximas fechas se calcularán a partir de la fecha recurrente actual.",
            message_type='notification'
        )
        return True

    def reiniciar_configuracion(self):
        """
        Reinicia la configuración para volver a calcular la fecha recurrente
        a partir de la fecha de inicio original.
        """
        self.ensure_one()
        self.usar_fecha_recurrente_como_base = False
        self._compute_fecha_recurrente()  # Forzar recálculo
        self.message_post(
            body="🔄 Configuración reiniciada. La fecha recurrente se calculará a partir de la fecha de inicio.",
            message_type='notification'
        )
        return True
    @api.model
    def update_fecha_recurrente(self):
        """
        Actualiza la fecha de mantenimiento recurrente para registros con fechas pasadas.
        VERSIÓN CORREGIDA: Activa el uso de fecha_recurrente como base para cálculos futuros.
        """
        today = fields.Date.today()
        
        # Buscar registros con fechas vencidas
        records = self.search([
            ('fecha_recurrente', '<=', today),
            ('estado_programacion', 'in', ['confirmado', 'pendiente']),
            ('control_mantenimiento', '=', True)
        ])
        
        _logger.info(f"🔍 ENCONTRADOS {len(records)} registros con fechas vencidas para actualizar")

        for record in records:
            fecha_vencida = record.fecha_recurrente
            
            _logger.info(f"📅 PROCESANDO: {record.name or 'Sin nombre'} - Fecha vencida: {fecha_vencida}")
            
            # ✅ CAMBIO CLAVE: Activar el flag para usar fecha_recurrente como base
            record.write({
                'usar_fecha_recurrente_como_base': True,  # ← ESTO ES LO IMPORTANTE
                'estado_programacion': 'pendiente',
                'fecha_confirmacion': False
            })

            # Forzar recálculo de la fecha recurrente
            # Ahora usará la fecha vencida como base gracias al flag activado
            record._compute_fecha_recurrente()

            _logger.info(f"✅ ACTUALIZADO: Nueva fecha calculada: {record.fecha_recurrente}")
            
            record.message_post(
                body=f"🔄 Mantenimiento actualizado de {fecha_vencida.strftime('%d/%m/%Y')} → {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                message_type='notification'
            )

        _logger.info(f"🎯 ACTUALIZACIÓN COMPLETADA: {len(records)} registros procesados")


    @api.model
    def send_maintenance_reminders(self):
        """Envía recordatorios de mantenimiento a los clientes con equipos programados."""
        today = fields.Date.today()
        target_date = today + timedelta(days=3)
        _logger.info(
            f"Buscando registros con fecha_recurrente entre {target_date} y {target_date + timedelta(days=1)}")

        # Buscar registros con fecha_recurrente dentro del rango
        records = self.search([
            ('fecha_recurrente', '>=', target_date),
            ('fecha_recurrente', '<', target_date + timedelta(days=1)),
            ('control_mantenimiento', '=', True)
        ])
        _logger.info(
            f"Registros encontrados para enviar recordatorios: {len(records)}")

        if not records:
            _logger.warning(
                "No se encontraron registros para enviar recordatorios.")
            return

        # Agrupar registros por cliente
        grouped_records = {}
        for record in records:
            if record.cliente_id:
                cliente_id = record.cliente_id.id
                if cliente_id not in grouped_records:
                    grouped_records[cliente_id] = {
                        'cliente': record.cliente_id,
                        'correo': record.correo_,
                        'equipos': []
                    }
                grouped_records[cliente_id]['equipos'].append(record)

        # Enviar correos agrupados por cliente
        mail_template = self.env.ref(
            'sat.mail_template_maintenance_notification')
        for client_data in grouped_records.values():
            correo = client_data['correo']
            if not correo:
                _logger.warning(
                    f"Cliente {client_data['cliente'].name} no tiene correo. Saltando...")
                continue

            primer_equipo = client_data['equipos'][0]
            try:
                mail_template.with_context(
                    equipos=client_data['equipos'],
                    fecha_mantenimiento=target_date
                ).send_mail(primer_equipo.id, force_send=True)
                _logger.info(
                    f"Correo enviado a {correo} para cliente {client_data['cliente'].name}")
            except Exception as e:
                _logger.error(
                    f"Error al enviar correo a {correo} para cliente {client_data['cliente'].name}: {e}")
    def button_send_test_mail(self):
        """Función para probar el envío de correo desde la interfaz"""
        self.ensure_one()
        # Buscar todos los equipos del mismo cliente
        equipos_cliente = self.search([
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True)
        ])

        mail_template = self.env.ref(
            'sat.mail_template_maintenance_notification')
        mail_template.with_context(
            equipos=equipos_cliente,
            fecha_mantenimiento=self.fecha_recurrente
        ).send_mail(self.id, force_send=True)

    def aplicar_configuracion_a_todos(self):
        """
        Aplica la configuración de mantenimiento del registro actual a todos
        los otros equipos del mismo cliente.
        VERSIÓN CORREGIDA: Evita recálculos múltiples no deseados.
        """
        self.ensure_one()

        # Verificar que haya un cliente asignado
        if not self.cliente_id:
            raise UserError(
                _("Debe seleccionar un cliente antes de aplicar la configuración a todos los equipos."))

        # Verificar que la configuración de mantenimiento esté completa
        if not self.fecha_inicio or not self.intervalo_meses:
            raise UserError(
                _("Complete la configuración de mantenimiento antes de aplicarla a otros equipos."))

        # Buscar todos los otros equipos del mismo cliente que tienen mantenimiento activado
        otros_equipos = self.search([
            ('id', '!=', self.id),
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True)
        ])

        if not otros_equipos:
            raise UserError(
                _("No se encontraron otros equipos con mantenimiento activado para este cliente."))

        # ✅ CAMBIO PRINCIPAL: Resetear TODOS los equipos primero (sin recálculos)
        _logger.info(f"🔄 APLICANDO configuración a {len(otros_equipos)} equipos del cliente {self.cliente_id.name}")
        
        # Valores a copiar (SIN usar_fecha_recurrente_como_base para evitar problemas)
        valores_base = {
            'fecha_inicio': self.fecha_inicio,
            'intervalo_meses': self.intervalo_meses,
            'patron_recurrencia': self.patron_recurrencia,
            'usar_fecha_recurrente_como_base': False,  # ← RESETEAR a False
            'estado_programacion': 'pendiente',
            'fecha_confirmacion': False
        }

        # Si el patrón es "día específico de la semana", también copiar estos campos
        if self.patron_recurrencia == 'semana_dia':
            valores_base.update({
                'semana_mes': self.semana_mes,
                'dia_semana': self.dia_semana
            })

        # ✅ IMPORTANTE: Usar with_context para evitar triggers no deseados
        try:
            # Aplicar la configuración base a todos los equipos (esto forzará recálculo desde fecha_inicio)
            otros_equipos.with_context(skip_compute=True).write(valores_base)
            
            # Forzar recálculo manual UNA SOLA VEZ para cada equipo
            for equipo in otros_equipos:
                equipo._compute_fecha_recurrente()
                _logger.info(f"✅ Equipo {equipo.id}: Nueva fecha_recurrente = {equipo.fecha_recurrente}")

        except Exception as e:
            _logger.error(f"❌ Error aplicando configuración: {str(e)}")
            raise UserError(_(f"Error al aplicar configuración: {str(e)}"))

        # Mostrar mensaje de confirmación
        message = _(
            f"Configuración de mantenimiento aplicada a {len(otros_equipos)} equipo(s) del cliente {self.cliente_id.name}.")

        # Registrar la acción en el historial
        self.message_post(
            body=f"✅ {message}",
            message_type='notification'
        )

        _logger.info(f"🎯 CONFIGURACIÓN APLICADA EXITOSAMENTE a {len(otros_equipos)} equipos")

        # Mostrar mensaje al usuario
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración aplicada'),
                'message': message,
                'sticky': False,
                'type': 'success',
            }
        }


    def _create_maintenance_tickets(self):
        """Crear tickets de mantenimiento para todos los equipos del cliente"""
        try:
            equipos = self.search([
                ('cliente_id', '=', self.cliente_id.id),
                ('fecha_recurrente', '=', self.fecha_recurrente),
                ('control_mantenimiento', '=', True)
            ])

            for equipo in equipos:
                self.env['ticket.alquiler'].create({
                    'partner_id': equipo.cliente_id.id,
                    'product_alquiler': equipo.id,
                    'tipo_servicio_id': 'mantenimiento_preventivo',
                    'estado': 'nuevo',
                    'description': 'Mantenimiento preventivo programado',
                    'direccion_id_r': equipo.direccion,
                    'contacto_id_r': equipo.contacto_id,
                    'celular_id_r': equipo.celular,
                    'corre_id_r': equipo.correo_,
                })

            # ✅ CORREGIDO: Actualizar TODOS los equipos
            equipos.write({
                'estado_programacion': 'confirmado',
                'fecha_confirmacion': fields.Datetime.now()
            })

            # ✅ Opcional: enviar email solo una vez
            template = self.env.ref(
                'sat.mail_template_maintenance_confirmation')
            template.send_mail(self.id, force_send=True)

            # ✅ Opcional: log solo en el primer equipo
            self.message_post(
                body=f"✅ Mantenimiento confirmado para {self.fecha_recurrente.strftime('%d/%m/%Y')}",
                message_type='notification'
            )

            return True
        except Exception as e:
            _logger.error(
                "Error al crear tickets de mantenimiento: %s", str(e))
            return False

    def _send_reschedule_request(self):
        """Enviar solicitud de reprogramación"""
        try:
            self.write({
                'estado_programacion': 'reprogramado',
                'fecha_confirmacion': False
            })
            template = self.env.ref('sat.mail_template_maintenance_reschedule')
            template.send_mail(self.id, force_send=True)

            self.message_post(
                body="🔄 Solicitud de reprogramación recibida",
                message_type='notification'
            )

            return True
        except Exception as e:
            _logger.error(
                "Error al enviar solicitud de reprogramación: %s", str(e))
            return False

    def process_maintenance_response(self, response_type):
        """Procesa la respuesta del cliente desde el correo"""
        self.ensure_one()
        # Validaciones
        if self.estado_programacion == 'confirmado' and response_type == 'confirm':
            raise ValidationError(_("Este mantenimiento ya está confirmado"))
        if self.estado_programacion == 'reprogramado' and response_type == 'confirm':
            raise ValidationError(
                _("Este mantenimiento está pendiente de reprogramación"))

        if response_type == 'confirm':
            return self._create_maintenance_tickets()
        elif response_type == 'reschedule':
            return self._send_reschedule_request()
        return False


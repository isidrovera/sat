import hashlib
import hmac
import calendar
import requests
import uuid
from urllib.parse import urlencode
from pytz import timezone, UTC
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

    mantenimiento_aviso_ciclo = fields.Date(
        string='Ciclo del último aviso preventivo', readonly=True, copy=False, index=True)
    mantenimiento_aviso_cliente_id = fields.Many2one(
        'res.partner', string='Cliente del último aviso preventivo', readonly=True, copy=False)

    @api.model
    def _mantenimiento_ahora_local(self):
        """Datetime local de Lima, independiente de la zona horaria del usuario cron."""
        ahora = fields.Datetime.to_datetime(fields.Datetime.now())
        if not ahora.tzinfo:
            ahora = UTC.localize(ahora)
        return ahora.astimezone(timezone('America/Lima')).replace(tzinfo=None)

    @api.model
    def _mantenimiento_horario_abierto(self):
        ahora = self._mantenimiento_ahora_local()
        horario = self.env['whatsapp.calendar.event'].sudo().get_working_intervals(ahora.date())
        hora = ahora.hour + ahora.minute / 60.0 + ahora.second / 3600.0
        return bool(horario.get('disponible') and any(
            inicio <= hora < fin for inicio, fin in horario.get('intervalos', [])))

    control_mantenimiento = fields.Boolean(
        string="Mantenimiento mensual", default=False)
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
    fecha_ultimo_mantenimiento = fields.Date(
        string='Último mantenimiento realizado',
        tracking=True,
        readonly=True,
        help="Fecha del último mantenimiento completado"
    )
    @api.onchange('fecha_inicio', 'patron_recurrencia')
    def _onchange_fecha_inicio(self):
        """
        MEJORADO: Detección automática con mejor logging y verificación.
        """
        if self.fecha_inicio and self.patron_recurrencia == 'semana_dia':
            # Detectar día de la semana
            dia_semana_python = self.fecha_inicio.weekday()  # 0=Lunes, 6=Domingo
            self.dia_semana = str(dia_semana_python)
            
            # Nombres para logging
            nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            dia_nombre = nombres_dias[dia_semana_python]
            
            _logger.info(f"DETECCIÓN: {self.fecha_inicio} es un {dia_nombre} (código: {dia_semana_python})")

            # Obtener todas las ocurrencias de este día en el mes
            ocurrencias = []
            year, month = self.fecha_inicio.year, self.fecha_inicio.month
            ultimo_dia = calendar.monthrange(year, month)[1]

            for dia in range(1, ultimo_dia + 1):
                fecha = datetime(year, month, dia).date()
                if fecha.weekday() == dia_semana_python:
                    ocurrencias.append(dia)

            _logger.info(f"Todas las ocurrencias de {dia_nombre} en {month}/{year}: {ocurrencias}")

            # Encontrar posición de la fecha seleccionada
            posicion = None
            for i, dia in enumerate(ocurrencias):
                if dia == self.fecha_inicio.day:
                    posicion = i
                    break

            if posicion is not None:
                total_ocurrencias = len(ocurrencias)
                posicion_desde_inicio = posicion + 1
                posicion_desde_final = -1 * (total_ocurrencias - posicion)

                _logger.info(f"ANÁLISIS:")
                _logger.info(f"  Día seleccionado: {self.fecha_inicio.day}")
                _logger.info(f"  Posición desde inicio: {posicion_desde_inicio} de {total_ocurrencias}")
                _logger.info(f"  Posición desde final: {posicion_desde_final}")

                # Decidir si usar posición desde inicio o final
                if posicion_desde_final >= -3:  # Última, penúltima o antepenúltima
                    self.semana_mes = str(posicion_desde_final)
                    descripcion = f"{['Última','Penúltima','Antepenúltima'][abs(posicion_desde_final)-1]} {dia_nombre}"
                else:
                    # Expresar desde el inicio
                    self.semana_mes = str(posicion_desde_inicio)
                    descripcion = f"{['Primera','Segunda','Tercera','Cuarta'][posicion_desde_inicio-1]} {dia_nombre}"

                _logger.info(f"CONFIGURACIÓN DETECTADA: {descripcion}")
                _logger.info(f"  semana_mes = '{self.semana_mes}'")
                _logger.info(f"  dia_semana = '{self.dia_semana}'")


    # NUEVO MÉTODO: Para debugging y verificación
    def debug_cronograma_perpetuo(self):
        """
        Simula los próximos 12 meses de mantenimiento para verificar el patrón.
        """
        self.ensure_one()
        
        if not self.fecha_inicio:
            return {'warning': {'title': 'Error', 'message': 'Debe definir una fecha de inicio'}}
        
        # Simular 12 próximos mantenimientos
        record = self.new(self.copy_data()[0])
        fecha_simulada = self.fecha_inicio
        resultados = []
        
        for i in range(12):
            # Simular el cálculo
            old_fecha_inicio = record.fecha_inicio
            record.fecha_inicio = fecha_simulada
            record._compute_fecha_recurrente()
            
            resultado = {
                'mes': i + 1,
                'fecha_inicio': fecha_simulada,
                'fecha_recurrente': record.fecha_recurrente,
                'mes_nombre': fecha_simulada.strftime('%B %Y'),
                'dia_semana': fecha_simulada.strftime('%A')
            }
            resultados.append(resultado)
            
            # Preparar para siguiente iteración
            fecha_simulada = record.fecha_recurrente
        
        # Restaurar fecha original
        record.fecha_inicio = old_fecha_inicio
        record._compute_fecha_recurrente()
        
        # Mostrar resultados
        mensaje = "SIMULACIÓN DE 12 MESES:\\n\\n"
        for r in resultados:
            mensaje += f"{r['mes']:2d}. {r['fecha_recurrente'].strftime('%d/%m/%Y')} ({r['fecha_recurrente'].strftime('%A')})\\n"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Simulación de Cronograma',
                'message': mensaje,
                'sticky': True,
                'type': 'info',
            }
        }


    
    @api.depends('fecha_inicio', 'intervalo_meses', 'patron_recurrencia', 'semana_mes', 'dia_semana')
    def _compute_fecha_recurrente(self):
        """
        Calcula la próxima fecha de mantenimiento basada en fecha_inicio actualizable.
        NUEVO ENFOQUE: fecha_inicio se actualiza automáticamente y siempre es la base del cálculo.
        """
        for record in self:
            if not record.fecha_inicio:
                record.fecha_recurrente = False
                continue

            # Guardar fecha anterior para comparación
            fecha_anterior = record.fecha_recurrente
            today = fields.Date.today()

            _logger.info(f"CALCULANDO desde fecha_inicio: {record.fecha_inicio}, "
                        f"patron: {record.patron_recurrencia}, intervalo: {record.intervalo_meses} meses, "
                        f"hoy: {today}")

            # Validar intervalo
            intervalo_str = record.intervalo_meses or '1'
            try:
                meses = int(intervalo_str)
                if meses <= 0 or meses > 12:
                    meses = 1
            except (ValueError, TypeError):
                meses = 1

            if record.patron_recurrencia == 'fecha_exacta' or not record.patron_recurrencia:
                # PATRÓN: DÍA ESPECÍFICO DEL MES
                day_of_month = record.fecha_inicio.day
                siguiente_fecha = record.fecha_inicio + relativedelta(months=meses)
                
                # Ajustar si el día no existe en el mes destino
                last_day = calendar.monthrange(siguiente_fecha.year, siguiente_fecha.month)[1]
                if day_of_month > last_day:
                    final_day = last_day
                else:
                    final_day = day_of_month
                
                record.fecha_recurrente = siguiente_fecha.replace(day=final_day)
                
                _logger.info(f"FECHA_EXACTA: {record.fecha_inicio} + {meses} meses = {record.fecha_recurrente}")

            elif record.patron_recurrencia == 'semana_dia' and record.semana_mes and record.dia_semana:
                # PATRÓN: DÍA ESPECÍFICO DE LA SEMANA
                try:
                    weekday = int(record.dia_semana)
                    position = int(record.semana_mes)
                    
                    # Nombres para logging
                    dias_nombres = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
                    pos_nombres = {'1':'Primer','2':'Segundo','3':'Tercer','4':'Cuarto','-1':'Último','-2':'Penúltimo','-3':'Antepenúltimo'}
                    patron_desc = f"{pos_nombres.get(record.semana_mes, record.semana_mes)} {dias_nombres[weekday]}"
                    
                    # Calcular el mes objetivo
                    target_date = record.fecha_inicio + relativedelta(months=meses)
                    target_year = target_date.year
                    target_month = target_date.month
                    
                    _logger.info(f"SEMANA_DIA: Buscando {patron_desc} en {target_month}/{target_year}")
                    
                    # Encontrar todas las ocurrencias del día en el mes objetivo
                    ocurrencias = []
                    last_day = calendar.monthrange(target_year, target_month)[1]
                    
                    for dia in range(1, last_day + 1):
                        fecha = datetime(target_year, target_month, dia).date()
                        if fecha.weekday() == weekday:
                            ocurrencias.append(fecha)
                    
                    _logger.info(f"Ocurrencias encontradas: {[f.strftime('%d/%m') for f in ocurrencias]}")
                    
                    if ocurrencias:
                        # Seleccionar según posición
                        if position < 0:  # Desde el final (-1=último, -2=penúltimo, etc.)
                            if abs(position) <= len(ocurrencias):
                                record.fecha_recurrente = ocurrencias[position]
                            else:
                                record.fecha_recurrente = ocurrencias[0]
                        else:  # Desde el inicio (1=primer, 2=segundo, etc.)
                            index = position - 1
                            if index < len(ocurrencias):
                                record.fecha_recurrente = ocurrencias[index]
                            else:
                                record.fecha_recurrente = ocurrencias[-1]
                        
                        _logger.info(f"RESULTADO: {patron_desc} = {record.fecha_recurrente.strftime('%d/%m/%Y')}")
                    else:
                        # Fallback si no hay ocurrencias (muy raro)
                        record.fecha_recurrente = target_date
                        _logger.warning(f"Sin ocurrencias de {patron_desc} en {target_month}/{target_year}, usando fallback")
                        
                except Exception as e:
                    _logger.error(f"Error en cálculo semana_dia: {str(e)}")
                    record.fecha_recurrente = record.fecha_inicio + relativedelta(months=meses)
            else:
                # Fallback simple
                record.fecha_recurrente = record.fecha_inicio + relativedelta(months=meses)

            # Log final completo
            _logger.info(f"RESULTADO FINAL: {record.name} -> "
                        f"fecha_inicio: {record.fecha_inicio} -> "
                        f"fecha_recurrente: {record.fecha_recurrente} -> "
                        f"dias_diferencia: {(record.fecha_recurrente - today).days}")

            # Solo hacer message_post si el registro está guardado
            if (fecha_anterior and 
                record.fecha_recurrente != fecha_anterior and 
                record.id and 
                hasattr(record, '_origin') and 
                record._origin and 
                record._origin.id):
                
                if record.estado_programacion in ['confirmado', 'reprogramado']:
                    record.estado_programacion = 'pendiente'



    def iniciar_calculo_recurrente(self):
        """
        SIMPLIFICADO: Ya no necesario con el nuevo enfoque.
        Solo resetea el estado.
        """
        self.ensure_one()
        
        self.write({
            'estado_programacion': 'pendiente',
            'fecha_confirmacion': False
        })
        
        self.message_post(
            body="Cronograma de mantenimiento reiniciado",
            message_type='notification'
        )
        
        return True

    def corregir_patron_manualmente(self, nuevo_dia_semana=None, nueva_posicion=None):
        """
        Permite corregir manualmente la configuración de patrón.
        Útil cuando la detección automática falla.
        """
        self.ensure_one()
        
        if nuevo_dia_semana is not None:
            self.dia_semana = str(nuevo_dia_semana)
        
        if nueva_posicion is not None:
            self.semana_mes = str(nueva_posicion)
        
        # Recalcular con la nueva configuración
        self._compute_fecha_recurrente()
        
        # Determinar descripción del patrón
        if self.patron_recurrencia == 'semana_dia':
            dias_nombres = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
            pos_nombres = {'1':'Primer','2':'Segundo','3':'Tercer','4':'Cuarto','-1':'Último','-2':'Penúltimo','-3':'Antepenúltimo'}
            patron_desc = f"{pos_nombres.get(self.semana_mes)} {dias_nombres[int(self.dia_semana)]}"
        else:
            patron_desc = f"Día {self.fecha_inicio.day} del mes"
        
        mensaje = f"Patrón corregido a: {patron_desc}. Próximo mantenimiento: {self.fecha_recurrente.strftime('%d/%m/%Y')}"
        
        self.message_post(
            body=mensaje,
            message_type='notification'
        )
        
        _logger.info(f"PATRÓN CORREGIDO MANUALMENTE: {self.name} -> {patron_desc}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Patrón Corregido',
                'message': mensaje,
                'sticky': True,
                'type': 'success',
            }
        }


    def reiniciar_configuracion(self):
        """
        MODIFICADO: Reinicia solo el estado, mantiene fecha_inicio actual.
        """
        self.ensure_one()
        
        self.write({
            'estado_programacion': 'pendiente',
            'fecha_confirmacion': False
        })
        
        # Forzar recálculo desde fecha_inicio actual
        self._compute_fecha_recurrente()
        
        self.message_post(
            body=f"Configuración reiniciada. Próximo mantenimiento: {self.fecha_recurrente.strftime('%d/%m/%Y')}",
            message_type='notification'
        )
        
        return True
    @api.model
    def update_fecha_recurrente(self):
        """Conservar pendientes vencidos: vencer no equivale a completar."""
        today = fields.Date.context_today(self)
        records = self.search([
            ('fecha_recurrente', '<=', today),
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ])
        _logger.info("[MANTENIMIENTO] %s equipos con fecha alcanzada o vencida; no se avanza el ciclo sin ejecución.", len(records))
        return True

    def confirmar_mantenimiento_completado(self):
        """Cerrar manualmente el ciclo si su ticket vinculado está finalizado."""
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM alquiler WHERE id = %s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        self._validar_equipo_mantenimiento()
        if not self.fecha_recurrente:
            raise UserError(_("No hay fecha de mantenimiento programada."))
        ciclo = self.fecha_recurrente
        lineas = self._lineas_ciclo_mantenimiento()
        finalizadas = lineas.filtered(lambda l: l.ticket_id and
            l.ticket_id.estado == 'finalizado' and
            l.ticket_id.product_alquiler == self and
            l.ticket_id.tipo_servicio_id == 'mantenimiento_preventivo' and
            l.ticket_id.partner_id == self.cliente_id)
        if len(finalizadas) != 1:
            raise UserError(_("Debe existir exactamente un ticket finalizado vinculado a este ciclo. Revise la planificación."))
        if lineas.filtered(lambda l: l.ticket_id and l.ticket_id.estado != 'finalizado'):
            raise UserError(_("Existen tickets pendientes en este ciclo."))
        # No se conoce un campo de fecha real de ejecución en ticket.alquiler.
        # La fecha registrada corresponde a la confirmación manual del cierre.
        fecha_cierre = fields.Date.context_today(self)
        self.write({
            'fecha_inicio': ciclo,
            'fecha_ultimo_mantenimiento': fecha_cierre,
            'estado_programacion': 'pendiente',
            'fecha_confirmacion': False,
        })
        self.message_post(body=_("Ciclo %(ciclo)s cerrado mediante ticket %(ticket)s. Fecha de confirmación del cierre: %(fecha)s. Próximo ciclo: %(proximo)s.") % {
            'ciclo': ciclo, 'ticket': finalizadas.ticket_id.name,
            'fecha': fecha_cierre, 'proximo': self.fecha_recurrente,
        }, message_type='notification')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Mantenimiento completado'),
                           'message': _('Próximo mantenimiento: %s') % self.fecha_recurrente,
                           'type': 'success', 'sticky': False}}

    def debug_patron_cliente(self, cliente_id=None):
        """
        Método de debugging para verificar patrones de un cliente específico.
        Ejecutar manualmente para revisar la lógica.
        """
        if not cliente_id:
            # Usar el cliente actual del registro
            cliente_id = self.cliente_id.id if self.cliente_id else None
        
        if not cliente_id:
            _logger.error("No se proporcionó cliente_id")
            return
        
        today = fields.Date.today()
        equipos = self.search([
            ('cliente_id', '=', cliente_id),
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ])
        
        print(f"\n=== DEBUG CRONOGRAMA CLIENTE {equipos[0].cliente_id.name if equipos else 'N/A'} ===")
        print(f"Hoy: {today.strftime('%d/%m/%Y - %A')}")
        print(f"Total equipos: {len(equipos)}")
        
        for equipo in equipos:
            if equipo.patron_recurrencia == 'semana_dia':
                dias = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
                pos = {'1':'Primer','2':'Segundo','3':'Tercer','4':'Cuarto','-1':'Último','-2':'Penúltimo','-3':'Antepenúltimo'}
                patron = f"{pos.get(equipo.semana_mes)} {dias[int(equipo.dia_semana)]}"
            else:
                patron = f"Día {equipo.fecha_inicio.day} del mes"
            
            print(f"\nEquipo {equipo.id}:")
            print(f"  Patrón: {patron} cada {equipo.intervalo_meses} mes(es)")
            print(f"  Fecha inicio: {equipo.fecha_inicio}")
            print(f"  Fecha actual: {equipo.fecha_recurrente} ({'✅ FUTURO' if equipo.fecha_recurrente > today else '❌ VENCIDO'})")
            
            # Simular próximas 3 fechas
            old_fecha = equipo.fecha_recurrente
            old_usar_base = equipo.usar_fecha_recurrente_como_base
            
            print(f"  Próximas 3 fechas:")
            for i in range(1, 4):
                # Simular que vence y se recalcula
                equipo.fecha_recurrente = old_fecha
                equipo.usar_fecha_recurrente_como_base = True
                equipo._compute_fecha_recurrente()
                nueva_fecha = equipo.fecha_recurrente
                print(f"    {i}. {nueva_fecha.strftime('%d/%m/%Y - %A')}")
                old_fecha = nueva_fecha
            
            # Restaurar valores originales
            equipo.fecha_recurrente = equipo.fecha_recurrente  # Mantener la última calculada
            equipo.usar_fecha_recurrente_como_base = old_usar_base
    @api.model
    def send_maintenance_reminders(self):
        """Un aviso por cliente/ciclo; adelantar ante cierres y recuperar avisos pendientes.

        No proponer fechas vencidas o días cerrados. Esos casos quedan para
        coordinación operativa. El marcador es persistente y se escribe solo
        si Odoo no informa error de envío.
        """
        if not self._mantenimiento_horario_abierto():
            return False
        self.env.cr.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', (41971, 1))
        if not self.env.cr.fetchone()[0]:
            return False
        hoy = self._mantenimiento_ahora_local().date()
        calendario = self.env['whatsapp.calendar.event'].sudo()
        cache = {}
        def laborable(fecha):
            if fecha not in cache:
                cache[fecha] = bool(calendario.get_working_intervals(fecha).get('intervalos'))
            return cache[fecha]
        # Anticipación normal de tres días calendario. Si un cierre prolongado
        # impide avisar con esa anticipación, enviar en el último día hábil previo.
        limite = hoy + timedelta(days=30)
        registros = self.search([
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_programacion', '=', 'pendiente'),
            ('cliente_id', '!=', False),
            ('fecha_recurrente', '>=', hoy), ('fecha_recurrente', '<=', limite),
        ], order='fecha_recurrente, cliente_id, id')
        grupos = {}
        for equipo in registros:
            grupos.setdefault((equipo.cliente_id.id, equipo.fecha_recurrente), equipo)
        plantilla = self.env.ref('sat.mail_template_maintenance_notification')
        for (cliente, ciclo), equipo in grupos.items():
            if not self._mantenimiento_horario_abierto():
                break
            if not laborable(ciclo):
                continue
            objetivo = ciclo - timedelta(days=3)
            if hoy < objetivo:
                # Hay un día hábil posterior a hoy y hasta el día objetivo:
                # todavía no corresponde anticipar el envío.
                if any(laborable(hoy + timedelta(days=i))
                       for i in range(1, (objetivo - hoy).days + 1)):
                    continue
            try:
                with self.env.cr.savepoint():
                    equipos = equipo._equipos_ciclo_cliente()
                    self.env.cr.execute('SELECT id FROM alquiler WHERE id IN %s ORDER BY id FOR UPDATE',
                                        (tuple(equipos.ids),))
                    equipos.invalidate_recordset()
                    if any(e.cliente_id.id != cliente or e.fecha_recurrente != ciclo or
                           not e.control_mantenimiento or e.estado_alquiler_id != 'alquilada'
                           for e in equipos):
                        continue
                    if any(e.estado_programacion != 'pendiente' for e in equipos):
                        continue
                    if any(e.mantenimiento_aviso_ciclo == ciclo and
                           e.mantenimiento_aviso_cliente_id.id == cliente for e in equipos):
                        continue
                    destino = equipos.filtered(lambda e: bool(e.correo_))[:1]
                    if not destino:
                        _logger.warning('[MANT] Cliente %s sin correo para ciclo %s', cliente, ciclo)
                        continue
                    if not self._mantenimiento_horario_abierto():
                        break
                    mail_id = plantilla.with_context(equipos=equipos, fecha_mantenimiento=ciclo).send_mail(
                        destino.id, force_send=True, raise_exception=True)
                    if not mail_id:
                        raise UserError(_('No se generó el correo de mantenimiento.'))
                    equipos.write({'mantenimiento_aviso_ciclo': ciclo,
                                   'mantenimiento_aviso_cliente_id': cliente})
            except Exception:
                _logger.exception('[MANT] Error de aviso cliente=%s ciclo=%s', cliente, ciclo)
        return True

    def _validar_equipo_mantenimiento(self):
        self.ensure_one()
        if not self.control_mantenimiento:
            raise UserError("El equipo no tiene activado el mantenimiento preventivo.")
        if self.estado_alquiler_id != 'alquilada':
            raise UserError("El equipo debe encontrarse en estado Alquilada.")
        if not self.cliente_id:
            raise UserError("El equipo no tiene un cliente asignado.")

    def button_send_test_mail(self):
        """Función para probar el envío de correo desde la interfaz"""
        self.ensure_one()
        self._validar_equipo_mantenimiento()
        if not self.fecha_recurrente:
            raise UserError("No hay fecha de mantenimiento programada.")
        # Buscar equipos del mismo cliente y fecha
        equipos_cliente = self.search([
            ('cliente_id', '=', self.cliente_id.id),
            ('fecha_recurrente', '=', self.fecha_recurrente),
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ])

        mail_template = self.env.ref(
            'sat.mail_template_maintenance_notification')
        mail_template.with_context(
            equipos=equipos_cliente,
            fecha_mantenimiento=self.fecha_recurrente
        ).send_mail(self.id, force_send=True)

    def aplicar_configuracion_a_todos(self):
        """
        MODIFICADO: Aplica configuración sin el campo usar_fecha_recurrente_como_base.
        """
        self.ensure_one()
        self._validar_equipo_mantenimiento()

        # Verificaciones
        if not self.cliente_id:
            raise UserError("Debe seleccionar un cliente antes de aplicar la configuración")

        if not self.fecha_inicio or not self.intervalo_meses:
            raise UserError("Complete la configuración de mantenimiento antes de aplicarla")

        # Buscar otros equipos del mismo cliente
        otros_equipos = self.search([
            ('id', '!=', self.id),
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ])

        if not otros_equipos:
            raise UserError("No se encontraron otros equipos con mantenimiento activado para este cliente")

        _logger.info(f"APLICANDO configuración a {len(otros_equipos)} equipos del cliente {self.cliente_id.name}")
        
        # Valores a copiar (sin usar_fecha_recurrente_como_base)
        valores_base = {
            'fecha_inicio': self.fecha_inicio,
            'intervalo_meses': self.intervalo_meses,
            'patron_recurrencia': self.patron_recurrencia,
            'estado_programacion': 'pendiente',
            'fecha_confirmacion': False
        }

        # Si el patrón es "día específico de la semana", copiar estos campos
        if self.patron_recurrencia == 'semana_dia':
            valores_base.update({
                'semana_mes': self.semana_mes,
                'dia_semana': self.dia_semana
            })

        try:
            # Aplicar configuración
            otros_equipos.write(valores_base)
            
            # Forzar recálculo para cada equipo
            for equipo in otros_equipos:
                equipo._compute_fecha_recurrente()
                _logger.info(f"Equipo {equipo.id}: fecha_recurrente = {equipo.fecha_recurrente}")

            # Mensaje de confirmación
            message = f"Configuración aplicada a {len(otros_equipos)} equipo(s) del cliente {self.cliente_id.name}"
            
            self.message_post(
                body=message,
                message_type='notification'
            )

            _logger.info(f"CONFIGURACIÓN APLICADA EXITOSAMENTE a {len(otros_equipos)} equipos")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Configuración aplicada',
                    'message': message,
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error(f"Error aplicando configuración: {str(e)}")
            raise UserError(f"Error al aplicar configuración: {str(e)}")



    def _lineas_ciclo_mantenimiento(self):
        self.ensure_one()
        return self.env['mantenimiento.planificador.linea'].search([
            ('equipo_id', '=', self.id),
            ('cliente_id', '=', self.cliente_id.id),
            ('fecha_ideal', '=', self.fecha_recurrente),
            ('estado', '!=', 'cancelado'),
            ('planificador_id.estado', '!=', 'cancelado'),
        ])

    def get_maintenance_action_url(self, accion):
        """Genera un enlace firmado compatible con MaintenanceController."""
        self.ensure_one()
        self._validar_equipo_mantenimiento()
        if not self.fecha_recurrente or accion not in ('confirm', 'reschedule'):
            raise UserError(_("Acción o ciclo de mantenimiento inválido."))
        params = self.env['ir.config_parameter'].sudo()
        secreto = params.get_param('database.secret')
        base_url = params.get_param('web.base.url')
        if not secreto or not base_url:
            raise UserError(_("Falta configurar la seguridad o URL base de Odoo."))
        cliente = str(self.cliente_id.id)
        ciclo = str(self.fecha_recurrente)
        mensaje = f'mantenimiento:v1:{accion}:{self.id}:{cliente}:{ciclo}'
        firma = hmac.new(secreto.encode('utf-8'), mensaje.encode('utf-8'), hashlib.sha256).hexdigest()
        ruta = 'confirmar' if accion == 'confirm' else 'reprogramar'
        query = urlencode({'ciclo': ciclo, 'cliente': cliente, 'firma': firma})
        return f"{base_url.rstrip('/')}/mantenimiento/{ruta}/{self.id}?{query}"

    def _equipos_ciclo_cliente(self):
        self.ensure_one()
        self._validar_equipo_mantenimiento()
        if not self.fecha_recurrente:
            raise UserError(_("No hay fecha de mantenimiento programada."))
        return self.search([
            ('cliente_id', '=', self.cliente_id.id),
            ('fecha_recurrente', '=', self.fecha_recurrente),
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ], order='id')

    def _create_maintenance_tickets(self):
        """Nombre histórico conservado: confirmar sin crear tickets paralelos."""
        equipos = self._equipos_ciclo_cliente()
        ciclo = self.fecha_recurrente
        cliente = self.cliente_id
        with self.env.cr.savepoint():
            for equipo in equipos:
                self.env.cr.execute('SELECT id FROM alquiler WHERE id = %s FOR UPDATE', (equipo.id,))
            equipos.invalidate_recordset()
            for equipo in equipos:
                equipo._validar_equipo_mantenimiento()
                if equipo.cliente_id != cliente or equipo.fecha_recurrente != ciclo:
                    raise UserError(_("Cambió el cliente o ciclo durante la confirmación."))
            if any(e.estado_programacion == 'reprogramado' for e in equipos):
                raise UserError(_('Existe una reprogramación pendiente de coordinación.'))
            pendientes = equipos.filtered(lambda e: e.estado_programacion != 'confirmado')
            if not pendientes:
                return True
            if ciclo < self._mantenimiento_ahora_local().date() or not self.env['whatsapp.calendar.event'].sudo().get_working_intervals(ciclo).get('intervalos'):
                raise UserError(_('La fecha propuesta ya venció o no tiene horario laboral. Solicite reprogramación.'))
            for equipo in pendientes:
                if equipo.estado_programacion == 'reprogramado':
                    continue
                lineas = equipo._lineas_ciclo_mantenimiento()
                if len(lineas) > 1:
                    raise UserError(_("Hay más de una línea activa para el mismo ciclo."))
                if lineas:
                    if lineas.fecha_confirmada and lineas.fecha_confirmada != ciclo:
                        raise UserError(_("La línea ya tiene otra fecha confirmada."))
                    if lineas.ticket_id and lineas.fecha_programada != ciclo:
                        raise UserError(_("Existe un ticket con otra fecha; revise la planificación."))
                    if lineas.fecha_programada and lineas.fecha_programada != ciclo:
                        lineas.write({'fecha_confirmada': ciclo, 'estado': 'reasignar',
                                      'fecha_programada': False, 'hora_inicio': 0.0, 'hora_fin': 0.0,
                                      'tecnico_id': False, 'tecnico_apoyo_ids': [(5, 0, 0)],
                                      'nota': _('Cliente confirmó la fecha recurrente; revisar asignación.')})
                    else:
                        vals = {'fecha_confirmada': ciclo}
                        if not lineas.ticket_id and lineas.estado != 'programado':
                            vals['estado'] = 'confirmado'
                        lineas.write(vals)
                equipo.write({'estado_programacion': 'confirmado',
                              'fecha_confirmacion': fields.Datetime.now()})
            self.env.ref('sat.mail_template_maintenance_confirmation').send_mail(self.id, force_send=True)
            self.message_post(body=_("Mantenimiento confirmado para %s. La creación de tickets corresponde al planificador.") % ciclo,
                              message_type='notification')
        return True

    def _send_reschedule_request(self):
        """Registrar solicitud sin cancelar ni modificar tickets existentes."""
        equipos = self._equipos_ciclo_cliente()
        with self.env.cr.savepoint():
            for equipo in equipos:
                self.env.cr.execute('SELECT id FROM alquiler WHERE id = %s FOR UPDATE', (equipo.id,))
            equipos.invalidate_recordset()
            for equipo in equipos:
                equipo._validar_equipo_mantenimiento()
                if equipo.cliente_id != self.cliente_id or equipo.fecha_recurrente != self.fecha_recurrente:
                    raise UserError(_("Cambió el cliente o ciclo durante la reprogramación."))
                for linea in equipo._lineas_ciclo_mantenimiento():
                    if linea.ticket_id:
                        linea.write({'nota': _('Cliente solicita reprogramar; revisar el ticket existente.')})
                    else:
                        linea.write({'estado': 'reasignar', 'fecha_confirmada': False,
                                     'hora_confirmada': 0.0, 'fecha_programada': False,
                                     'hora_inicio': 0.0, 'hora_fin': 0.0, 'tecnico_id': False,
                                     'tecnico_apoyo_ids': [(5, 0, 0)],
                                     'nota': _('Cliente solicita reprogramar; pendiente de nueva confirmación.')})
            if all(e.estado_programacion == 'reprogramado' for e in equipos):
                return True
            equipos.write({'estado_programacion': 'reprogramado', 'fecha_confirmacion': False})
            self.env.ref('sat.mail_template_maintenance_reschedule').send_mail(self.id, force_send=True)
            self.message_post(body=_("Solicitud de reprogramación recibida."), message_type='notification')
        return True

    def process_maintenance_response(self, response_type):
        """Procesa la respuesta del cliente desde el correo"""
        self.ensure_one()
        self._validar_equipo_mantenimiento()
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


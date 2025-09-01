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
        Calcula la próxima fecha de mantenimiento para cronogramas perpetuos.
        VERSIÓN FINAL CORREGIDA: Siempre encuentra fechas FUTURAS respetando el patrón original.
        """
        for record in self:
            if not record.fecha_inicio:
                record.fecha_recurrente = False
                continue

            # Guardar fecha anterior para comparación
            fecha_anterior = record.fecha_recurrente
            today = fields.Date.today()

            _logger.info(f"🔍 CALCULANDO para {record.name}: fecha_inicio={record.fecha_inicio}, "
                        f"fecha_recurrente_actual={record.fecha_recurrente}, "
                        f"hoy={today}, patrón={record.patron_recurrencia}")

            # Validar intervalo
            intervalo_str = record.intervalo_meses or '1'
            try:
                meses = int(intervalo_str)
                if meses <= 0 or meses > 12:
                    meses = 1
            except (ValueError, TypeError):
                meses = 1

            if record.patron_recurrencia == 'fecha_exacta' or not record.patron_recurrencia:
                # ========== PATRÓN: DÍA ESPECÍFICO DEL MES ==========
                day_of_month = record.fecha_inicio.day
                
                # ✅ LÓGICA CORREGIDA: Buscar desde HOY hacia adelante
                candidate_date = today
                found = False
                
                # Buscar hasta 24 meses en el futuro
                for month_offset in range(1, 25):
                    test_date = today + relativedelta(months=month_offset)
                    
                    # Solo considerar meses que coincidan con el intervalo
                    if month_offset % meses == 0:
                        # Ajustar el día si no existe en el mes destino
                        last_day = calendar.monthrange(test_date.year, test_date.month)[1]
                        if day_of_month > last_day:
                            final_day = last_day
                        else:
                            final_day = day_of_month
                        
                        fecha_calculada = test_date.replace(day=final_day)
                        
                        if fecha_calculada > today:
                            record.fecha_recurrente = fecha_calculada
                            found = True
                            _logger.info(f"✅ FECHA EXACTA ENCONTRADA: {fecha_calculada}")
                            break
                
                if not found:
                    # Fallback simple
                    record.fecha_recurrente = today + relativedelta(months=meses, day=day_of_month)

            elif record.patron_recurrencia == 'semana_dia' and record.semana_mes and record.dia_semana:
                # ========== PATRÓN: DÍA ESPECÍFICO DE LA SEMANA ==========
                try:
                    weekday = int(record.dia_semana)  # 0=Lunes, 6=Domingo
                    position = int(record.semana_mes)  # 1,2,3,4 o -1,-2,-3
                    
                    dias_nombres = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
                    pos_nombres = {'1':'Primer','2':'Segundo','3':'Tercer','4':'Cuarto','-1':'Último','-2':'Penúltimo','-3':'Antepenúltimo'}
                    patron_desc = f"{pos_nombres.get(record.semana_mes, record.semana_mes)} {dias_nombres[weekday]}"
                    
                    _logger.info(f"🎯 BUSCANDO PATRÓN: {patron_desc} cada {meses} mes(es) desde HOY ({today})")
                    
                    def encontrar_fecha_en_mes(year, month):
                        """Encuentra la fecha del patrón en un mes específico"""
                        ocurrencias = []
                        last_day = calendar.monthrange(year, month)[1]
                        
                        # Encontrar todas las ocurrencias del día de la semana
                        for dia in range(1, last_day + 1):
                            fecha = datetime(year, month, dia).date()
                            if fecha.weekday() == weekday:
                                ocurrencias.append(fecha)
                        
                        if not ocurrencias:
                            return None
                        
                        # Seleccionar según posición
                        if position < 0:  # Desde el final (-1=último, -2=penúltimo, etc.)
                            if abs(position) <= len(ocurrencias):
                                return ocurrencias[position]  # position ya es negativo
                            else:
                                return ocurrencias[0]  # Primera si no hay suficientes
                        else:  # Desde el inicio (1=primer, 2=segundo, etc.)
                            index = position - 1  # Convertir a índice 0-based
                            if index < len(ocurrencias):
                                return ocurrencias[index]
                            else:
                                return ocurrencias[-1]  # Última si no hay suficientes
                    
                    # ✅ NUEVA LÓGICA: Buscar desde HOY hacia adelante en intervalos correctos
                    found = False
                    
                    # Buscar hasta 24 meses en el futuro
                    for month_offset in range(1, 25):
                        # Solo buscar en meses que coincidan con el intervalo
                        if month_offset % meses == 0:
                            target_date = today + relativedelta(months=month_offset)
                            fecha_candidata = encontrar_fecha_en_mes(target_date.year, target_date.month)
                            
                            if fecha_candidata and fecha_candidata > today:
                                record.fecha_recurrente = fecha_candidata
                                found = True
                                _logger.info(f"✅ PATRÓN ENCONTRADO: {patron_desc} en {fecha_candidata.strftime('%d/%m/%Y')} "
                                            f"(mes +{month_offset} desde hoy)")
                                break
                            else:
                                _logger.info(f"⏭️ Mes +{month_offset}: {target_date.strftime('%m/%Y')} → "
                                            f"{'Sin ocurrencias' if not fecha_candidata else f'Fecha {fecha_candidata} ya pasó'}")
                    
                    if not found:
                        # Fallback: buscar sin restricción de intervalo
                        _logger.warning("🔍 FALLBACK: Buscando sin restricción de intervalo...")
                        for month_offset in range(1, 12):
                            target_date = today + relativedelta(months=month_offset)
                            fecha_candidata = encontrar_fecha_en_mes(target_date.year, target_date.month)
                            
                            if fecha_candidata and fecha_candidata > today:
                                record.fecha_recurrente = fecha_candidata
                                found = True
                                _logger.info(f"✅ FALLBACK ENCONTRADO: {patron_desc} en {fecha_candidata.strftime('%d/%m/%Y')}")
                                break
                    
                    if not found:
                        _logger.error(f"❌ NO SE PUDO ENCONTRAR {patron_desc}, usando fallback simple")
                        record.fecha_recurrente = today + relativedelta(months=meses)

                except Exception as e:
                    _logger.error(f"❌ Error en cálculo de patrón semana_dia: {str(e)}")
                    record.fecha_recurrente = today + relativedelta(months=meses)
            else:
                # Fallback para casos no contemplados
                record.fecha_recurrente = today + relativedelta(months=meses)

            # Log final detallado
            if record.dia_semana and record.semana_mes:
                dia_nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                posicion_nombres = {
                    '1': 'Primer', '2': 'Segundo', '3': 'Tercer', '4': 'Cuarto',
                    '-1': 'Último', '-2': 'Penúltimo', '-3': 'Antepenúltimo'
                }
                dia_semana_nombre = dia_nombres[int(record.dia_semana)]
                posicion_nombre = posicion_nombres.get(record.semana_mes, record.semana_mes)
                patron_desc = f"{posicion_nombre} {dia_semana_nombre}"
            else:
                patron_desc = f"Día {record.fecha_inicio.day} del mes"

            # Verificar que la fecha esté en el futuro
            if record.fecha_recurrente <= today:
                _logger.error(f"❌ ERROR: Fecha calculada {record.fecha_recurrente} NO está en el futuro (hoy={today})")
                # Forzar una fecha futura
                record.fecha_recurrente = today + relativedelta(months=meses)
            
            _logger.info(
                f"🎯 RESULTADO FINAL: {record.name} → {patron_desc} cada {meses} mes(es) "
                f"→ PRÓXIMA FECHA: {record.fecha_recurrente.strftime('%d/%m/%Y')} "
                f"(hoy es {today.strftime('%d/%m/%Y')} - "
                f"{'✅ FUTURO' if record.fecha_recurrente > today else '❌ PASADO'})"
            )

            # Solo hacer message_post si el registro está guardado y hay cambio
            if (fecha_anterior and 
                record.fecha_recurrente != fecha_anterior and 
                record.id and 
                hasattr(record, '_origin') and 
                record._origin and 
                record._origin.id):
                
                if record.estado_programacion in ['confirmado', 'reprogramado']:
                    record.estado_programacion = 'pendiente'
                    try:
                        record.message_post(
                            body=f"Nueva fecha de mantenimiento: {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                            message_type='notification'
                        )
                    except Exception as e:
                        _logger.warning(f"No se pudo enviar mensaje: {str(e)}")




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
        Actualiza fechas de mantenimiento vencidas.
        VERSIÓN FINAL CORREGIDA: Calcula fechas futuras correctamente.
        """
        today = fields.Date.today()
        
        # Buscar registros con fechas vencidas
        records = self.search([
            ('fecha_recurrente', '<=', today),
            ('control_mantenimiento', '=', True)
        ])
        
        _logger.info(f"🔍 CRON: Encontrados {len(records)} registros con fechas vencidas (hoy={today})")

        for record in records:
            fecha_vencida = record.fecha_recurrente
            
            _logger.info(f"📅 PROCESANDO: {record.name} - Fecha vencida: {fecha_vencida} - Patrón: {record.patron_recurrencia}")
            
            # ✅ ACTIVAR el uso de fecha_recurrente como base
            record.write({
                'usar_fecha_recurrente_como_base': True,
                'estado_programacion': 'pendiente',
                'fecha_confirmacion': False
            })

            # Forzar recálculo (la nueva lógica calculará desde HOY hacia adelante)
            record._compute_fecha_recurrente()

            # Verificar que el resultado sea correcto
            if record.fecha_recurrente <= today:
                _logger.error(f"❌ ERROR: {record.name} - Fecha calculada {record.fecha_recurrente} aún está en el pasado")
                # Forzar una fecha futura simple
                record.fecha_recurrente = today + relativedelta(months=int(record.intervalo_meses or '1'))

            _logger.info(f"✅ ACTUALIZADO: {record.name} → {fecha_vencida} → {record.fecha_recurrente} "
                        f"({'✅ FUTURO' if record.fecha_recurrente > today else '❌ PASADO'})")
            
            # Enviar notificación solo si el registro existe
            if record.id and hasattr(record, '_origin') and record._origin and record._origin.id:
                try:
                    record.message_post(
                        body=f"Mantenimiento actualizado: {fecha_vencida.strftime('%d/%m/%Y')} → {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                        message_type='notification'
                    )
                except Exception as e:
                    _logger.warning(f"No se pudo enviar notificación: {str(e)}")

        _logger.info(f"🎯 CRON COMPLETADO: {len(records)} registros actualizados")
        return True


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
            ('control_mantenimiento', '=', True)
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


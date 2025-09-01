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
        """
        Actualiza fechas vencidas moviendo fecha_inicio hacia adelante.
        NUEVO ENFOQUE: Actualiza fecha_inicio para simplificar cálculos futuros.
        """
        today = fields.Date.today()
        
        # Buscar registros con fechas vencidas
        records = self.search([
            ('fecha_recurrente', '<=', today),
            ('control_mantenimiento', '=', True)
        ])
        
        _logger.info(f"CRON: Encontrados {len(records)} registros con fechas vencidas (hoy: {today})")

        for record in records:
            fecha_vencida = record.fecha_recurrente
            fecha_inicio_anterior = record.fecha_inicio
            
            # Determinar descripción del patrón para logs
            if record.patron_recurrencia == 'semana_dia' and record.semana_mes and record.dia_semana:
                dias_nombres = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
                pos_nombres = {'1':'Primer','2':'Segundo','3':'Tercer','4':'Cuarto','-1':'Último','-2':'Penúltimo','-3':'Antepenúltimo'}
                patron_desc = f"{pos_nombres.get(record.semana_mes, record.semana_mes)} {dias_nombres[int(record.dia_semana)]}"
            else:
                patron_desc = f"Día {record.fecha_inicio.day} del mes"
            
            _logger.info(f"PROCESANDO: {record.name} - Patrón: {patron_desc}")
            _logger.info(f"  fecha_inicio anterior: {fecha_inicio_anterior}")
            _logger.info(f"  fecha_recurrente vencida: {fecha_vencida}")
            
            # ACTUALIZAR fecha_inicio a la fecha vencida
            record.write({
                'fecha_inicio': fecha_vencida,
                'fecha_ultimo_mantenimiento': fecha_vencida,  # Registrar el último mantenimiento
                'estado_programacion': 'pendiente',
                'fecha_confirmacion': False
            })

            # Forzar recálculo desde la nueva fecha_inicio
            record._compute_fecha_recurrente()

            _logger.info(f"ACTUALIZADO: {record.name}")
            _logger.info(f"  nueva fecha_inicio: {record.fecha_inicio}")
            _logger.info(f"  nueva fecha_recurrente: {record.fecha_recurrente}")
            _logger.info(f"  patrón mantenido: {patron_desc}")
            
            # Verificar que el patrón se respete
            if record.patron_recurrencia == 'semana_dia':
                dia_calculado = record.fecha_recurrente.weekday()
                dia_esperado = int(record.dia_semana)
                if dia_calculado == dia_esperado:
                    _logger.info(f"  PATRÓN VERIFICADO: {patron_desc} respetado correctamente")
                else:
                    _logger.error(f"  ERROR PATRÓN: Esperado {dias_nombres[dia_esperado]}, calculado {dias_nombres[dia_calculado]}")
            
            # Enviar notificación
            if record.id and hasattr(record, '_origin') and record._origin and record._origin.id:
                try:
                    record.message_post(
                        body=f"Mantenimiento actualizado: {fecha_vencida.strftime('%d/%m/%Y')} → {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                        message_type='notification'
                    )
                except Exception as e:
                    _logger.warning(f"No se pudo enviar notificación: {str(e)}")

        _logger.info(f"CRON COMPLETADO: {len(records)} registros actualizados")
        return True
    def confirmar_mantenimiento_completado(self):
        """
        Confirma que el mantenimiento fue completado y avanza fecha_inicio.
        Método para usar cuando el técnico completa el mantenimiento.
        """
        self.ensure_one()
        
        if not self.fecha_recurrente:
            raise UserError("No hay fecha de mantenimiento programada")
        
        fecha_completada = self.fecha_recurrente
        
        # Actualizar fecha_inicio para el próximo cálculo
        self.write({
            'fecha_inicio': fecha_completada,
            'fecha_ultimo_mantenimiento': fecha_completada,
            'estado_programacion': 'pendiente',
            'fecha_confirmacion': fields.Datetime.now()
        })
        
        # Recalcular automáticamente la próxima fecha
        self._compute_fecha_recurrente()
        
        # Log del cambio
        self.message_post(
            body=f"Mantenimiento completado el {fecha_completada.strftime('%d/%m/%Y')}. Próximo: {self.fecha_recurrente.strftime('%d/%m/%Y')}",
            message_type='notification'
        )
        
        _logger.info(f"MANTENIMIENTO COMPLETADO: {self.name} - Nueva secuencia iniciada desde {self.fecha_inicio}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mantenimiento Completado',
                'message': f'Próximo mantenimiento programado para {self.fecha_recurrente.strftime("%d/%m/%Y")}',
                'sticky': False,
                'type': 'success',
            }
        }



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
        MODIFICADO: Aplica configuración sin el campo usar_fecha_recurrente_como_base.
        """
        self.ensure_one()

        # Verificaciones
        if not self.cliente_id:
            raise UserError("Debe seleccionar un cliente antes de aplicar la configuración")

        if not self.fecha_inicio or not self.intervalo_meses:
            raise UserError("Complete la configuración de mantenimiento antes de aplicarla")

        # Buscar otros equipos del mismo cliente
        otros_equipos = self.search([
            ('id', '!=', self.id),
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True)
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


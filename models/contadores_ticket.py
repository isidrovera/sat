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

class ContadoresTicket(models.Model):
    
    _inherit = 'ticket.alquiler'
    _description = 'Contadores Ticket'

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
        Carga los contadores desde diferentes fuentes disponibles.
        Solo carga contadores que estén máximo 3 días anteriores a la fecha de agenda.
        Escribe todos los campos en una sola operación y valida al final.
        """
        self.ensure_one()
        _logger.info(f"=== Iniciando carga de contadores para ticket {self.name} ===")
        
        # Verificaciones básicas
        ESTADOS_TRABAJO = ('proceso', 'en_revision', 'en_sitio', 'en_ruta')

        if self.estado not in ESTADOS_TRABAJO:
            estados_legibles = ", ".join(ESTADOS_TRABAJO)
            raise UserError(_(
                "Esta función solo está disponible en los siguientes estados: %s\n"
                "Estado actual: %s"
            ) % (estados_legibles, self.estado))
        if not self.product_alquiler:
            raise UserError(_("No hay un equipo asignado a este ticket."))
        if not self.product_alquiler.serie:
            raise UserError(_("El equipo asignado no tiene número de serie."))
        if not self.agenda:
            raise UserError(_("El ticket debe tener una fecha de agenda asignada."))
        
        serie = self.product_alquiler.serie
        fecha_agenda = self.agenda.date()
        fecha_limite_minima = fecha_agenda - timedelta(days=3)
        
        _logger.info(f"🔍 Buscando contadores para serie: {serie}")
        _logger.info(f"📅 Fecha agenda: {fecha_agenda}")
        _logger.info(f"📅 Fecha límite mínima (3 días antes): {fecha_limite_minima}")
        
        # Buscar contadores con validación de fecha
        contadores_encontrados, fuente_datos, fecha_contador = self._buscar_contadores_con_limite_fecha(serie, fecha_agenda, fecha_limite_minima)
        
        # DEBUG - Agregar logs detallados
        _logger.info(f"🔍 DEBUG - Contadores encontrados: {contadores_encontrados}")
        _logger.info(f"🔍 DEBUG - Fuente: {fuente_datos}")
        _logger.info(f"🔍 DEBUG - Fecha contador: {fecha_contador}")
        
        if not contadores_encontrados:
            raise UserError(_(
                "No se encontraron contadores válidos para la serie %s dentro del rango de fechas permitido.\n\n"
                "📅 Fecha de agenda: %s\n"
                "📅 Fecha límite (3 días antes): %s\n\n"
                "Verifique que existan lecturas de PrintTracker o correos procesados para este equipo "
                "entre estas fechas."
            ) % (serie, fecha_agenda.strftime('%d/%m/%Y'), fecha_limite_minima.strftime('%d/%m/%Y')))
        
        # Armar payload de actualización en una sola operación
        _logger.info("🔧 Preparando actualización masiva de campos...")
        updates = {}
        valores_cargados = []
        fecha_contador_str = fecha_contador.strftime('%d/%m/%Y') if fecha_contador else 'fecha desconocida'

        # B/N
        bn_valor = contadores_encontrados.get('contador_bn', 0)
        _logger.info(f"🔍 DEBUG BN - Valor: {bn_valor}, Fecha: {fecha_contador_str}")
        if bn_valor > 0:
            updates['contometrok_id'] = str(bn_valor)
            valores_cargados.append(f"Contador B/N: {bn_valor:,} (del {fecha_contador_str})")
        else:
            _logger.warning(f"⚠️ DEBUG BN - NO SE CARGA porque valor es {bn_valor}")

        # Color (solo para máquinas a color)
        color_valor = contadores_encontrados.get('contador_color', 0)
        _logger.info(f"🔍 DEBUG COLOR - Tipo máquina: {self.tipo_id}, Valor: {color_valor}, Fecha: {fecha_contador_str}")
        if self.tipo_id == 'color' and color_valor > 0:
            updates['contometroc_id'] = str(color_valor)
            valores_cargados.append(f"Contador Color: {color_valor:,} (del {fecha_contador_str})")
        else:
            _logger.info(f"ℹ️ DEBUG COLOR - NO SE CARGA (tipo: {self.tipo_id}, valor: {color_valor})")

        # Scanner
        scan_valor = contadores_encontrados.get('contador_scan', 0)
        _logger.info(f"🔍 DEBUG SCANNER - Valor: {scan_valor}, Fecha: {fecha_contador_str}")
        if scan_valor > 0:
            updates['contometros_id'] = str(scan_valor)
            valores_cargados.append(f"Contador Scanner: {scan_valor:,} (del {fecha_contador_str})")
        else:
            _logger.error(f"❌ DEBUG SCANNER - NO SE CARGA porque valor es {scan_valor}")

        # Verificación previa
        if not updates:
            _logger.error(f"❌ No se cargaron valores. contadores_encontrados: {contadores_encontrados}")
            raise UserError(_("Los contadores encontrados no son válidos para cargar."))

        # 🔒 Escribir TODO de una vez, deshabilitando validaciones
        _logger.info("🔧 Deshabilitando validación automática temporalmente con skip_constraints...")
        self.with_context(skip_constraints=True).write(updates)

        # (Opcional) invalidar caché de este recordset si tu versión lo expone
        try:
            self.invalidate_recordset()
        except Exception:
            # No es crítico; write() ya deja el cache coherente para validaciones inmediatas
            pass

        # ✅ Validación manual final (ahora sin saltos)
        _logger.info("🔍 Ejecutando validación manual final...")
        try:
            self._check_contometro_values()
            _logger.info("✅ Validación manual exitosa")
        except ValidationError as e:
            _logger.error(f"❌ Validación falló: {str(e)}")
            raise

        # Mensajes detallados
        dias_diferencia = (fecha_agenda - fecha_contador).days if fecha_contador else 0
        mensaje_diferencia = ""
        if dias_diferencia > 0:
            mensaje_diferencia = f" ({dias_diferencia} días antes de la agenda)"
        
        mensaje_exito = (
            f"✅ Contadores cargados exitosamente desde {fuente_datos}:\n\n"
            f"📋 Contadores cargados:\n"
            f"{'• ' + chr(10) + '• '.join(valores_cargados)}\n\n"
            f"📅 Fecha de los contadores: {fecha_contador_str}{mensaje_diferencia}\n"
            f"📅 Fecha de agenda: {fecha_agenda.strftime('%d/%m/%Y')}\n"
            f"🔧 Serie: {serie}"
        )

        # Registrar en el chatter
        self.message_post(body=mensaje_exito, message_type='notification')
        _logger.info(f"=== Contadores cargados exitosamente para ticket {self.name} ===")
        
        # Refrescar la página y mostrar notificación
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',  # Esto refresca la página completa
            'params': {
                'message': {
                    'title': _('Contadores Cargados'),
                    'message': _('Los contadores se han cargado correctamente desde %s del %s.') % (
                        fuente_datos or 'fuente desconocida', 
                        fecha_contador_str
                    ),
                    'type': 'success',
                    'sticky': True,  # Mantener visible más tiempo
                }
            }
        }

    def _buscar_contadores_con_limite_fecha(self, serie, fecha_agenda, fecha_limite_minima):
        """
        Busca contadores en orden de prioridad con validación de fecha límite:
        Solo acepta contadores entre fecha_limite_minima y fecha_agenda
        """
        # PRIORIDAD 1: Equipo de alquiler (solo si fecha está en rango)
        _logger.info("🔍 Prioridad 1: Verificando equipo de alquiler...")
        contadores_equipo, fecha_equipo = self._obtener_contadores_equipo_con_fecha(fecha_agenda, fecha_limite_minima)
        if contadores_equipo:
            return contadores_equipo, "Equipo de Alquiler", fecha_equipo
        
        # PRIORIDAD 2: PrintTracker Daily Reading
        _logger.info("🔍 Prioridad 2: Verificando PrintTracker Daily Reading...")
        contadores_pt, fecha_pt = self._obtener_contadores_printtracker_con_limite(serie, fecha_agenda, fecha_limite_minima)
        if contadores_pt:
            return contadores_pt, "PrintTracker Daily Reading", fecha_pt
        
        # PRIORIDAD 3: Contador Automático (correos)
        _logger.info("🔍 Prioridad 3: Verificando Contador Automático...")
        contadores_correo, fecha_correo = self._obtener_contadores_correos_con_limite(serie, fecha_agenda, fecha_limite_minima)
        if contadores_correo:
            return contadores_correo, "Procesamiento de Correos", fecha_correo
        
        _logger.warning("❌ No se encontraron contadores en el rango de fechas permitido")
        return None, None, None

    def _obtener_contadores_equipo_con_fecha(self, fecha_agenda, fecha_limite_minima):
        """
        Obtiene contadores del equipo de alquiler si la fecha está en rango permitido
        """
        try:
            unidad = self.product_alquiler
            if not unidad or not unidad.fecha_ultima_actualizacion:
                return None, None
            
            fecha_equipo = unidad.fecha_ultima_actualizacion.date()
            
            # Verificar que esté en el rango permitido
            if fecha_limite_minima <= fecha_equipo <= fecha_agenda:
                contadores = {
                    'contador_bn': unidad.contador_bn or 0,
                    'contador_color': unidad.contador_color or 0,
                    'contador_scan': unidad.contador_scan or 0,
                }
                
                if any(v > 0 for v in contadores.values()):
                    _logger.info(f"✅ Contadores desde equipo del {fecha_equipo}: {contadores}")
                    return contadores, fecha_equipo
            else:
                _logger.info(f"❌ Fecha equipo ({fecha_equipo}) fuera del rango permitido")
            
            return None, None
        except Exception as e:
            _logger.error(f"❌ Error obteniendo contadores del equipo: {e}")
            return None, None

    def _obtener_contadores_printtracker_con_limite(self, serie, fecha_agenda, fecha_limite_minima):
        """
        Obtiene contadores desde PrintTracker Daily Reading con límite de fecha
        """
        try:
            # Buscar la lectura más reciente dentro del rango permitido
            lectura_reciente = self.env['printtracker.daily.reading'].search([
                ('serie', '=', serie),
                ('fecha', '>=', fecha_limite_minima),
                ('fecha', '<=', fecha_agenda),
                ('estado', 'in', ['validado', 'aplicado'])
            ], order='fecha desc', limit=1)
            
            if lectura_reciente:
                contadores = self._extraer_contadores_printtracker(lectura_reciente)
                if contadores:
                    _logger.info(f"✅ Contadores desde PrintTracker del {lectura_reciente.fecha}: {contadores}")
                    return contadores, lectura_reciente.fecha
            else:
                _logger.info(f"❌ No hay lecturas PrintTracker entre {fecha_limite_minima} y {fecha_agenda}")
            
            return None, None
        except Exception as e:
            _logger.error(f"❌ Error obteniendo contadores de PrintTracker: {e}")
            return None, None

    def _obtener_contadores_correos_con_limite(self, serie, fecha_agenda, fecha_limite_minima):
        """
        Obtiene contadores desde Contador Automático (correos) con límite de fecha
        """
        try:
            # Buscar el más reciente dentro del rango permitido
            contador_reciente = self.env['contador.automatico'].search([
                ('serie_detectada', '=', serie),
                ('fecha_procesamiento', '>=', fields.Datetime.combine(fecha_limite_minima, datetime.min.time())),
                ('fecha_procesamiento', '<=', fields.Datetime.combine(fecha_agenda + timedelta(days=1), datetime.min.time())),
                ('estado', '=', 'procesado')
            ], order='fecha_procesamiento desc', limit=1)
            
            if contador_reciente:
                contadores = self._extraer_contadores_correos(contador_reciente)
                if contadores:
                    fecha_proc = contador_reciente.fecha_procesamiento.date()
                    _logger.info(f"✅ Contadores desde correos del {fecha_proc}: {contadores}")
                    return contadores, fecha_proc
            else:
                _logger.info(f"❌ No hay contadores de correos entre {fecha_limite_minima} y {fecha_agenda}")
            
            return None, None
        except Exception as e:
            _logger.error(f"❌ Error obteniendo contadores de correos: {e}")
            return None, None

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
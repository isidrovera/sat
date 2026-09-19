# ================================================================================================
# MODELO: printtracker_alert.py - Sistema de Alertas PrintTracker
# Email configurable vía ir.config_parameter: printtracker.alert.email_destino
# Timestamps naive para Odoo, campos alineados con API real PrintTracker
# ================================================================================================

from odoo import models, fields, api
import logging
import traceback
from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser
import json
import re

_logger = logging.getLogger(__name__)


class PrintTrackerAlert(models.Model):
    _name = 'printtracker.alert'
    _description = 'Alertas PrintTracker'
    _order = 'fecha_creacion desc, prioridad desc'
    _rec_name = 'display_name'

    # ==========================================
    # IDENTIFICACIÓN
    # ==========================================
    serie_equipo = fields.Char('Serie del Equipo', required=True, index=True)
    equipo_id = fields.Many2one('alquiler', string='Equipo',
                                compute='_compute_equipo_id', store=True, index=True)

    # ==========================================
    # TIPO Y PRIORIDAD
    # ==========================================
    tipo_alerta = fields.Selection([
        ('suministro_bajo', 'Suministro Bajo'),
        ('suministro_critico', 'Suministro Crítico'),
        ('suministro_vacio', 'Suministro Vacío'),
        ('equipo_offline', 'Equipo Offline'),
        ('sin_lecturas', 'Sin Lecturas Recientes'),
        ('uso_anomalo_alto', 'Uso Anómalamente Alto'),
        ('uso_anomalo_bajo', 'Uso Anómalamente Bajo'),
        ('contador_decrece', 'Contador Decreció'),
        ('mantenimiento_debido', 'Mantenimiento Requerido'),
        ('error_sincronizacion', 'Error de Sincronización'),
        ('conflicto_datos', 'Conflicto en Datos'),
        ('paper_jam', 'Atasco de Papel'),
        ('device_error', 'Error de Dispositivo'),
        ('supply_replaced', 'Suministro Reemplazado'),
        ('supply_event', 'Evento de Suministro'),
        ('cover_open', 'Cubierta Abierta'),
        ('connectivity_issue', 'Problema de Conectividad'),
        ('device_event', 'Evento de Dispositivo'),
        ('custom', 'Personalizada'),
    ], string='Tipo de Alerta', required=True, index=True)

    prioridad = fields.Selection([
        ('baja', 'Baja'), ('media', 'Media'), ('alta', 'Alta'),
        ('critica', 'Crítica'), ('urgente', 'Urgente'),
    ], string='Prioridad', required=True, default='media', index=True)

    # ==========================================
    # CONTENIDO
    # ==========================================
    titulo = fields.Char('Título', required=True)
    descripcion = fields.Text('Descripción')
    mensaje_detallado = fields.Html('Mensaje Detallado')

    # ==========================================
    # FECHAS
    # ==========================================
    fecha_creacion = fields.Datetime('Fecha Creación', default=fields.Datetime.now, readonly=True)
    fecha_deteccion = fields.Datetime('Fecha Detección')
    fecha_vencimiento = fields.Datetime('Fecha Vencimiento')

    # ==========================================
    # ESTADO
    # ==========================================
    estado = fields.Selection([
        ('nueva', 'Nueva'), ('notificada', 'Notificada'),
        ('en_proceso', 'En Proceso'), ('resuelta', 'Resuelta'),
        ('cerrada', 'Cerrada'), ('ignorada', 'Ignorada'),
    ], string='Estado', default='nueva', index=True)

    # ==========================================
    # GESTIÓN
    # ==========================================
    asignado_a = fields.Many2one('res.users', string='Asignado A')
    resuelto_por = fields.Many2one('res.users', string='Resuelto Por')
    fecha_resolucion = fields.Datetime('Fecha Resolución')
    notas_resolucion = fields.Text('Notas de Resolución')

    # ==========================================
    # DATOS ESPECÍFICOS
    # ==========================================
    suministro_id = fields.Many2one('printtracker.supply', string='Suministro Relacionado')
    porcentaje_suministro = fields.Float('Porcentaje Suministro (%)')
    dias_sin_lecturas = fields.Integer('Días sin Lecturas')
    ultima_lectura = fields.Datetime('Última Lectura')
    contador_actual = fields.Integer('Contador Actual')
    contador_anterior = fields.Integer('Contador Anterior')
    diferencia_contador = fields.Integer('Diferencia Contador')

    # ==========================================
    # INTEGRACIÓN NORMALIZADA DE TÓNER
    # ==========================================

    def _is_toner_event(self):
        """
        Indica si la alerta corresponde a un evento que debe ser enviado
        al sistema central de gestión de tóner.
        """
        self.ensure_one()
        return self.tipo_alerta in (
            'suministro_bajo',
            'suministro_critico',
            'suministro_vacio',
            'supply_replaced',
            'supply_event',
        )

    def _map_toner_event_type(self, event_data=None):
        """
        Convierte el tipo de alerta PrintTracker al estándar
        toner.monitoring.event.

        REGLA IMPORTANTE:
        ------------------
        alertType / tipo_alerta define el tipo principal del evento.

        Una descripción como:
            "The black toner estimated depletion September 16, 2026"

        NO reemplaza un "Low supply" por otro tipo.
        La fecha estimada se guarda adicionalmente en
        estimated_depletion_date.
        """
        self.ensure_one()
        event_data = event_data or {}

        mapping = {
            'suministro_bajo': 'low',
            'suministro_critico': 'critical',
            'suministro_vacio': 'empty',
            'supply_replaced': 'replaced',
        }

        if self.tipo_alerta in mapping:
            return mapping[self.tipo_alerta]

        # Evento genérico de suministro.
        # Solo se considera lectura de nivel si el payload realmente
        # contiene una lectura explícita para el supply relacionado.
        if self.tipo_alerta == 'supply_event':
            if self._event_has_explicit_level(event_data):
                return 'level'
            return 'supply_event'

        return 'unknown'

    def _get_event_supply_payload(self, event_data):
        """
        Devuelve el suministro exacto relacionado al event de PrintTracker.

        PrintTracker puede entregar los datos del suministro en distintas
        posiciones según el tipo de event / dispositivo:

            1. event.supplies
            2. event.meterRead.supplies   <- estructura observada en /events
            3. event.attributes           <- atributos del supply del event

        REGLAS:
        - supplyKey identifica el suministro exacto cuando está presente.
        - nunca se toma un supply de otro equipo.
        - si supplyKey no existe, solo se usa un fallback cuando hay una
          única opción inequívoca.
        - soporta toner, ink, drum, waste y otros supplies sin descartarlos;
          únicamente los toner se envían al flujo especializado de tóner.
        """
        self.ensure_one()
        event_data = event_data or {}

        supply_key = (
            self.api_supply_key
            or event_data.get('supplyKey')
            or event_data.get('supply_key')
        )

        # --------------------------------------------------------
        # 1. supplies directamente en el event
        # --------------------------------------------------------
        supplies = event_data.get('supplies')

        # --------------------------------------------------------
        # 2. estructura real observada en GET /events:
        #    event.meterRead.supplies
        # --------------------------------------------------------
        if not isinstance(supplies, dict):
            meter_read = event_data.get('meterRead') or {}
            if isinstance(meter_read, dict):
                supplies = meter_read.get('supplies')

        if isinstance(supplies, dict):
            if supply_key and supply_key in supplies:
                payload = supplies.get(supply_key)
                if isinstance(payload, dict):
                    return supply_key, payload

            # Sin supplyKey, solo aceptar una única opción claramente
            # identificada. No adivinar entre varios consumibles.
            candidates = [
                (key, payload)
                for key, payload in supplies.items()
                if isinstance(payload, dict)
            ]

            if len(candidates) == 1:
                return candidates[0]

            # Compatibilidad histórica: si existe exactamente un toner,
            # puede utilizarse para eventos antiguos sin supplyKey.
            toner_candidates = []
            for key, payload in candidates:
                raw_type = self._nested_value(payload, 'type')
                if str(raw_type or '').strip().lower() == 'toner':
                    toner_candidates.append((key, payload))

            if len(toner_candidates) == 1:
                return toner_candidates[0]

        # --------------------------------------------------------
        # 3. El event también puede traer attributes correspondientes
        #    específicamente al supply indicado por supplyKey.
        # --------------------------------------------------------
        attributes = event_data.get('attributes')
        if supply_key and isinstance(attributes, dict):
            return supply_key, attributes

        return supply_key or False, False

    @staticmethod
    def _nested_value(container, key):
        """
        Extrae valores de estructuras PrintTracker del tipo:
            {"displayName": "...", "value": "123"}
        o devuelve directamente el valor simple.
        """
        if not isinstance(container, dict):
            return False

        value = container.get(key)

        if isinstance(value, dict):
            return value.get('value')

        return value

    def _event_has_explicit_level(self, event_data):
        """
        True únicamente cuando el supply relacionado contiene un nivel
        explícito. Un nivel 0 es válido si PrintTracker lo envió.
        """
        self.ensure_one()

        _key, supply_payload = self._get_event_supply_payload(
            event_data or {}
        )

        if not supply_payload:
            return False

        for key in (
            'pctRemaining',
            'percentRemaining',
            'percentageRemaining',
            'currentLevel',
        ):
            raw = self._nested_value(supply_payload, key)
            if raw not in (None, False, ''):
                return True

        return False

    def _extract_explicit_level(self, event_data):
        """
        Devuelve:
            (
                porcentaje,
                valor_bruto,
                máximo,
                disponible,
                supply_key,
                supply_payload,
            )

        Lee la estructura REAL del payload PrintTracker:

            supplies.blackToner.currentLevel.value
            supplies.blackToner.maxLevel.value
            supplies.blackToner.pctRemaining.value

        La ausencia de datos nunca se convierte en 0%.
        """
        self.ensure_one()
        event_data = event_data or {}

        supply_key, supply_payload = self._get_event_supply_payload(
            event_data
        )

        if not supply_payload:
            return False, 0, 0, False, supply_key, False

        raw_current = self._nested_value(
            supply_payload,
            'currentLevel',
        )
        raw_max = self._nested_value(
            supply_payload,
            'maxLevel',
        )

        raw_percent = self._nested_value(
            supply_payload,
            'pctRemaining',
        )

        if raw_percent in (None, False, ''):
            raw_percent = self._nested_value(
                supply_payload,
                'percentRemaining',
            )

        if raw_percent in (None, False, ''):
            raw_percent = self._nested_value(
                supply_payload,
                'percentageRemaining',
            )

        level_value = 0
        level_max = 0
        percent = False
        available = False

        if raw_current not in (None, False, ''):
            try:
                level_value = int(float(raw_current))
            except (TypeError, ValueError):
                level_value = 0

        if raw_max not in (None, False, ''):
            try:
                level_max = int(float(raw_max))
            except (TypeError, ValueError):
                level_max = 0

        if raw_percent not in (None, False, ''):
            try:
                percent = float(raw_percent)
                if 0.0 <= percent <= 100.0:
                    available = True
                else:
                    percent = False
            except (TypeError, ValueError):
                percent = False

        if not available and level_max > 0:
            try:
                percent = max(
                    0.0,
                    min(
                        100.0,
                        (float(level_value) / float(level_max)) * 100.0,
                    ),
                )
                available = True
            except (TypeError, ValueError, ZeroDivisionError):
                percent = False
                available = False

        return (
            percent if available else False,
            level_value,
            level_max,
            available,
            supply_key,
            supply_payload,
        )

    @staticmethod
    def _extract_estimated_depletion_date(event_data, description=''):
        """
        Extrae una fecha de agotamiento estimado.

        Prioriza campos estructurados del payload y luego usa la descripción.
        """
        event_data = event_data or {}

        structured_keys = (
            'estimatedDepletionDate',
            'estimatedDepletion',
            'depletionDate',
            'estimatedEmptyDate',
        )

        for key in structured_keys:
            raw = event_data.get(key)
            if not raw:
                continue
            try:
                parsed = dateutil_parser.parse(str(raw), fuzzy=True)
                return parsed.date()
            except (TypeError, ValueError, OverflowError):
                pass

        text = description or event_data.get('description') or ''
        lowered = text.lower()
        if not any(
            phrase in lowered
            for phrase in (
                'estimated depletion',
                'estimated to deplete',
                'estimated empty',
                'depletion estimate',
                'agotamiento estimado',
                'se agotará',
                'se agotara',
            )
        ):
            return False

        try:
            parsed = dateutil_parser.parse(text, fuzzy=True)
            return parsed.date()
        except (TypeError, ValueError, OverflowError):
            return False

    def _get_printtracker_supply(self):
        """
        Obtiene el suministro PrintTracker correspondiente al MISMO equipo.

        supply_key (por ejemplo blackToner) se repite en cientos de equipos,
        por lo que nunca debe buscarse únicamente por esa clave cuando ya
        conocemos el equipo.

        Prioridad:
        1. suministro_id ya enlazado;
        2. equipment + api_supply_key;
        3. si no hay equipo, aceptar supply_key solo cuando la coincidencia
           global sea única.
        """
        self.ensure_one()

        Supply = self.env['printtracker.supply'].sudo()

        if self.suministro_id:
            return self.suministro_id

        if not self.api_supply_key:
            return Supply.browse()

        if self.equipo_id:
            return Supply.search([
                ('device_id', '=', self.equipo_id.id),
                ('supply_key', '=', self.api_supply_key),
            ], limit=1)

        matches = Supply.search([
            ('supply_key', '=', self.api_supply_key),
        ], limit=2)

        if len(matches) == 1:
            return matches

        return Supply.browse()

    def _normalize_toner_color(self, supply=False):
        """
        Determina el color del tóner.
        Para un equipo monocromático, si no llega color, se infiere negro.
        En equipos color no se adivina el color.
        """
        self.ensure_one()
        supply = supply or self._get_printtracker_supply()

        valid_colors = ('black', 'cyan', 'magenta', 'yellow')
        if supply and supply.supply_color in valid_colors:
            return supply.supply_color

        if self.equipo_id and self.equipo_id.tipo_maquina_id != 'color':
            return 'black'

        return 'unknown'

    @staticmethod
    def _extract_meter_value(raw_value):
        """
        Extrae un entero no negativo de un valor simple o estructura común.
        No inventa ni convierte estructuras ambiguas en contadores.
        """
        if raw_value in (None, False, ''):
            return 0

        if isinstance(raw_value, bool):
            return 0

        if isinstance(raw_value, (int, float)):
            return max(0, int(raw_value))

        if isinstance(raw_value, dict):
            for key in ('value', 'reading', 'meterRead', 'count', 'counter', 'total'):
                value = raw_value.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return max(0, int(value))

        try:
            return max(0, int(float(str(raw_value).strip())))
        except (TypeError, ValueError):
            return 0

    def _get_meter_counter_value(self, meter, color=False):
        """
        Busca un contador en printtracker.meter usando nombres de campo
        compatibles con distintas versiones del conector.
        """
        self.ensure_one()
        if not meter:
            return 0

        if color:
            candidates = [
                'color_pages',
                'color_pages_life',
                'total_color',
                'total_color_pages',
                'counter_color',
                'color_counter',
            ]
        else:
            candidates = [
                'black_pages',
                'mono_pages',
                'bw_pages',
                'black_pages_life',
                'mono_pages_life',
                'total_bw',
                'total_black',
                'counter_bn',
                'mono_counter',
            ]

        for field_name in candidates:
            if field_name not in meter._fields:
                continue
            try:
                value = int(getattr(meter, field_name, 0) or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value

        # En equipos monocromáticos total_pages_life es una referencia válida
        # si no existe un contador B/N más específico.
        if (
            not color
            and self.equipo_id
            and self.equipo_id.tipo_maquina_id != 'color'
            and 'total_pages_life' in meter._fields
        ):
            try:
                return max(0, int(meter.total_pages_life or 0))
            except (TypeError, ValueError):
                return 0

        return 0

    def _get_event_counters(self, event_data=None):
        """
        Obtiene los contadores del evento PrintTracker.

        Estructura real observada:

            meterRead
                pageCounts
                    default
                        totalBlack
                            value = "529800"
                        total
                            value = "529800"

        REGLAS:
        -------
        - Para B/N se prioriza totalBlack.
        - Si no existe totalBlack y el equipo es monocromático, se puede usar
          total como respaldo.
        - Para color se aceptan únicamente claves explícitas de total color.
        - Nunca se interpreta ausencia como contador 0 válido.
        """
        self.ensure_one()
        event_data = event_data or {}

        counter_bn = 0
        counter_color = 0
        bn_available = False
        color_available = False
        indirect = False

        meter_read = event_data.get('meterRead')

        def parse_counter(node):
            if node in (None, False, ''):
                return 0, False

            if isinstance(node, dict):
                node = node.get('value')

            if node in (None, False, ''):
                return 0, False

            try:
                value = int(float(node))
            except (TypeError, ValueError):
                return 0, False

            return max(0, value), True

        if isinstance(meter_read, dict):
            page_counts = meter_read.get('pageCounts')

            if isinstance(page_counts, dict):
                default_counts = page_counts.get('default')

                if isinstance(default_counts, dict):
                    # B/N
                    counter_bn, bn_available = parse_counter(
                        default_counts.get('totalBlack')
                    )

                    if (
                        not bn_available
                        and self.equipo_id
                        and self.equipo_id.tipo_maquina_id != 'color'
                    ):
                        counter_bn, bn_available = parse_counter(
                            default_counts.get('total')
                        )

                    # COLOR
                    for key in (
                        'totalColor',
                        'totalColour',
                        'totalFullColor',
                        'totalFullColour',
                    ):
                        if key not in default_counts:
                            continue

                        (
                            counter_color,
                            color_available,
                        ) = parse_counter(
                            default_counts.get(key)
                        )

                        if color_available:
                            break

        # Respaldo: contadores consolidados confiables del equipo.
        if self.equipo_id:
            has_auto = bool(
                getattr(
                    self.equipo_id,
                    'has_auto_counters',
                    False,
                )
            )

            if has_auto and not bn_available:
                raw_bn = getattr(
                    self.equipo_id,
                    'contador_bn',
                    None,
                )

                if raw_bn not in (None, False, ''):
                    try:
                        counter_bn = max(
                            0,
                            int(raw_bn),
                        )
                        bn_available = True
                        indirect = True
                    except (TypeError, ValueError):
                        pass

            if (
                has_auto
                and self.equipo_id.tipo_maquina_id == 'color'
                and not color_available
            ):
                raw_color = getattr(
                    self.equipo_id,
                    'contador_color',
                    None,
                )

                if raw_color not in (None, False, ''):
                    try:
                        counter_color = max(
                            0,
                            int(raw_color),
                        )
                        color_available = True
                        indirect = True
                    except (TypeError, ValueError):
                        pass

        return {
            'bn': int(counter_bn or 0),
            'color': int(counter_color or 0),
            'bn_available': bool(bn_available),
            'color_available': bool(color_available),
            'indirect': bool(indirect),
        }

    def _prepare_toner_monitoring_values(self, event_data=None):
        """
        Prepara toner.monitoring.event utilizando el payload real
        PrintTracker sin inventar datos.
        """
        self.ensure_one()
        event_data = event_data or {}

        # Reprocesar debe funcionar también para alerts ya existentes.
        # Cuando no se recibe event_data explícitamente, recuperar el JSON
        # bruto que se guardó al crear la alerta desde PrintTracker.
        if not event_data and self.api_raw_data:
            try:
                raw_event = json.loads(self.api_raw_data)
                if isinstance(raw_event, dict):
                    event_data = raw_event
            except (TypeError, ValueError, json.JSONDecodeError):
                _logger.warning(
                    '[TONER/PT] No se pudo reconstruir api_raw_data alerta=%s',
                    self.id,
                )

        supply_record = self._get_printtracker_supply()

        (
            explicit_percent,
            explicit_value,
            explicit_max,
            explicit_available,
            payload_supply_key,
            payload_supply,
        ) = self._extract_explicit_level(
            event_data
        )

        color = self._normalize_toner_color(
            supply=supply_record
        )

        # Si no existe printtracker.supply relacionado, obtener color
        # directamente del payload del suministro.
        if payload_supply:
            raw_color = self._nested_value(
                payload_supply,
                'color',
            )

            normalized_payload_color = (
                str(raw_color or '')
                .strip()
                .lower()
            )

            if normalized_payload_color in (
                'black',
                'cyan',
                'magenta',
                'yellow',
            ):
                color = normalized_payload_color

        counters = self._get_event_counters(
            event_data=event_data
        )

        # El tipo principal lo define la alerta PrintTracker.
        event_type = self._map_toner_event_type(
            event_data=event_data
        )

        level_percent = False
        level_value = 0
        level_max = 0
        level_available = False

        if explicit_available:
            level_percent = explicit_percent
            level_value = explicit_value
            level_max = explicit_max
            level_available = True

        # Si el evento es EMPTY, semánticamente existe un 0%.
        # No se usa esta regla para LOW.
        if event_type == 'empty' and not level_available:
            level_percent = 0.0
            level_available = True

        description = (
            event_data.get('description')
            or self.descripcion
            or ''
        )

        # La predicción de agotamiento es INFORMACIÓN ADICIONAL.
        # No reemplaza el tipo LOW/CRITICAL.
        estimated_depletion_date = (
            self._extract_estimated_depletion_date(
                event_data,
                description=description,
            )
        )

        raw_payload = self.api_raw_data

        if not raw_payload and event_data:
            raw_payload = json.dumps(
                event_data,
                ensure_ascii=False,
                default=str,
                indent=2,
            )

        external_event_id = (
            self.api_event_id
            or event_data.get('id')
        )

        if not external_event_id and self.id:
            external_event_id = (
                'printtracker-alert-%s-%s-%s'
                % (
                    self.id,
                    self.contador_repeticiones or 1,
                    self.tipo_alerta or 'event',
                )
            )

        # --------------------------------------------------------
        # Metadata del supply
        # --------------------------------------------------------

        supply_key = (
            self.api_supply_key
            or event_data.get('supplyKey')
            or payload_supply_key
            or (
                supply_record.supply_key
                if supply_record
                else False
            )
        )

        payload_supply_type = (
            self._nested_value(
                payload_supply,
                'type',
            )
            if payload_supply
            else False
        )

        payload_supply_name = (
            self._nested_value(
                payload_supply,
                'displayableName',
            )
            if payload_supply
            else False
        )

        payload_supply_description = (
            self._nested_value(
                payload_supply,
                'description',
            )
            if payload_supply
            else False
        )

        payload_part_number = (
            self._nested_value(
                payload_supply,
                'partNumber',
            )
            if payload_supply
            else False
        )

        return {
            'equipment_id': (
                self.equipo_id.id
                if self.equipo_id
                else False
            ),
            'source': 'printtracker',
            'external_event_id': external_event_id,
            'source_reference': supply_key,

            'printtracker_alert_id': self.id,
            'printtracker_supply_id': (
                supply_record.id
                if supply_record
                else False
            ),

            'event_type': event_type,
            'color': color,

            'event_date': (
                self.api_event_timestamp
                or self.fecha_deteccion
                or self.fecha_creacion
                or fields.Datetime.now()
            ),

            'level_percent': (
                float(level_percent)
                if level_available
                else 0.0
            ),
            'level_value': int(level_value or 0),
            'level_max': int(level_max or 0),
            'level_available': bool(level_available),

            'estimated_depletion_date': (
                estimated_depletion_date
            ),

            'counter_bn': int(
                counters.get('bn', 0)
                or 0
            ),
            'counter_color': int(
                counters.get('color', 0)
                or 0
            ),
            'counter_bn_available': bool(
                counters.get('bn_available')
            ),
            'counter_color_available': bool(
                counters.get('color_available')
            ),
            'counter_is_estimated': bool(
                counters.get('indirect')
            ),

            'supply_key': supply_key,

            'supply_type': (
                str(payload_supply_type)
                if payload_supply_type
                else (
                    supply_record.supply_type
                    if supply_record
                    else False
                )
            ),

            'supply_name': (
                payload_supply_name
                or payload_supply_description
                or (
                    supply_record.displayable_name
                    or supply_record.description
                    or supply_record.display_name
                    if supply_record
                    else False
                )
            ),

            'part_number': (
                payload_part_number
                or (
                    supply_record.part_number
                    if supply_record
                    else False
                )
            ),

            'raw_description': (
                description
                or False
            ),
            'raw_subject': (
                self.titulo
                or False
            ),
            'raw_payload': raw_payload,
        }

    def _create_toner_monitoring_event(self, event_data=None):
        """
        Crea o recupera toner.monitoring.event y enlaza ambas capas.

        Es idempotente:
        - si ya está enlazado, reutiliza el registro;
        - si existe source + external_event_id, reutiliza el existente;
        - el modelo normalizado controla su propio procesamiento.
        """
        self.ensure_one()

        if not self._is_toner_event():
            return self.env['toner.monitoring.event']

        if not self.equipo_id:
            self.write({
                'toner_event_processed': False,
                'toner_event_processing_error': (
                    'No se pudo identificar el equipo para procesar '
                    'el evento de tóner.'
                ),
            })
            _logger.warning(
                '[TONER/PT] Alerta %s sin equipo. Serie=%s',
                self.id,
                self.serie_equipo,
            )
            return self.env['toner.monitoring.event']

        if self.toner_monitoring_event_id:
            return self.toner_monitoring_event_id

        MonitoringEvent = self.env['toner.monitoring.event'].sudo()
        vals = self._prepare_toner_monitoring_values(event_data=event_data)

        try:
            event = MonitoringEvent.create_normalized_event(vals)

            self.write({
                'toner_monitoring_event_id': event.id,
                'toner_event_processed': True,
                'toner_event_processing_error': False,
            })

            _logger.info(
                '[TONER/PT] Evento normalizado enlazado '
                'alert=%s event=%s type=%s equipment=%s color=%s state=%s',
                self.id,
                event.id,
                event.event_type,
                self.equipo_id.id,
                event.color,
                event.processing_state,
            )
            return event

        except Exception as error:
            _logger.exception(
                '[TONER/PT] Error normalizando alerta=%s serie=%s',
                self.id,
                self.serie_equipo,
            )
            self.write({
                'toner_event_processed': False,
                'toner_event_processing_error': str(error),
            })
            return self.env['toner.monitoring.event']

    def action_retry_toner_processing(self):
        """
        Reintenta la integración después de corregir datos del equipo,
        color, supplyKey o contadores.
        """
        for alert in self:
            if not alert._is_toner_event():
                continue

            if not alert.toner_monitoring_event_id:
                alert._create_toner_monitoring_event()
                continue

            event = alert.toner_monitoring_event_id
            prepared = alert._prepare_toner_monitoring_values()

            safe_fields = (
                'equipment_id',
                'printtracker_supply_id',
                'color',
                'level_percent',
                'level_value',
                'level_max',
                'level_available',
                'estimated_depletion_date',
                'counter_bn',
                'counter_color',
                'counter_bn_available',
                'counter_color_available',
                'counter_is_estimated',
                'supply_key',
                'supply_type',
                'supply_name',
                'part_number',
                'raw_description',
                'raw_subject',
                'raw_payload',
            )
            vals = {
                field_name: prepared.get(field_name)
                for field_name in safe_fields
                if field_name in prepared
            }

            event.write(vals)
            event.action_retry_processing()

            alert.write({
                'toner_event_processed': True,
                'toner_event_processing_error': (
                    event.processing_error or False
                ),
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Gestión de tóner',
                'message': 'Procesamiento de tóner reintentado.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_view_toner_monitoring_event(self):
        """Abre el evento normalizado relacionado."""
        self.ensure_one()

        if not self.toner_monitoring_event_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Esta alerta no tiene un evento de tóner relacionado.',
                    'type': 'warning',
                    'sticky': False,
                },
            }

        return {
            'type': 'ir.actions.act_window',
            'name': 'Evento de Tóner',
            'res_model': 'toner.monitoring.event',
            'res_id': self.toner_monitoring_event_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==========================================
    # NOTIFICACIONES
    # ==========================================
    notificar_email = fields.Boolean('Notificar por Email', default=True)
    notificar_chatter = fields.Boolean('Notificar en Chatter', default=True)
    email_enviado = fields.Boolean('Email Enviado', readonly=True)
    chatter_enviado = fields.Boolean('Chatter Enviado', readonly=True)

    # ==========================================
    # REPETICIÓN Y CONTROL
    # ==========================================
    es_recurrente = fields.Boolean('Es Recurrente', default=False)
    frecuencia_revision = fields.Integer('Frecuencia Revisión (min)', default=60)
    ultima_revision = fields.Datetime('Última Revisión')
    contador_repeticiones = fields.Integer('Repeticiones', default=1)
    max_repeticiones = fields.Integer('Máximo Repeticiones', default=5)

    # ==========================================
    # ORIGEN
    # ==========================================
    origen_datos = fields.Selection([
        ('interno', 'Generado Internamente'),
        ('api_events', 'Event de PrintTracker API'),
    ], string='Origen', default='interno', required=True, index=True)

    # ==========================================
    # CAMPOS DE API EVENTS (PrintTracker real)
    # ==========================================
    api_event_id = fields.Char('Event ID API', index=True)
    api_event_type = fields.Char('Tipo Event API')
    api_resolution_status = fields.Char('Estado Resolución API')
    api_event_timestamp = fields.Datetime('Timestamp Event API')
    api_supply_key = fields.Char('Supply Key API')
    api_device_key = fields.Char('Device Key API')
    api_raw_data = fields.Text('Datos Crudos API')

    # ==========================================
    # INTEGRACIÓN CON GESTIÓN CENTRAL DE TÓNER
    # ==========================================
    toner_monitoring_event_id = fields.Many2one(
        'toner.monitoring.event',
        string='Evento de Tóner',
        readonly=True,
        copy=False,
        index=True,
        ondelete='set null',
    )
    toner_event_processed = fields.Boolean(
        string='Evento de Tóner Procesado',
        default=False,
        readonly=True,
        copy=False,
        index=True,
    )
    toner_event_processing_error = fields.Text(
        string='Error Procesamiento Tóner',
        readonly=True,
        copy=False,
    )

    # ==========================================
    # INFO EQUIPO (cache)
    # ==========================================
    cliente_nombre = fields.Char('Cliente', compute='_compute_equipo_info', store=True)
    modelo_equipo = fields.Char('Modelo', compute='_compute_equipo_info', store=True)
    ubicacion_equipo = fields.Char('Ubicación', compute='_compute_equipo_info', store=True)

    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)

    # ==========================================
    # ACCIÓN AUTOMÁTICA
    # ==========================================
    accion_automatica = fields.Selection([
        ('ninguna', 'Ninguna'),
        ('crear_orden_compra', 'Crear Orden de Compra'),
        ('crear_tarea', 'Crear Tarea'),
        ('notificar_tecnico', 'Notificar Técnico'),
    ], string='Acción Automática', default='ninguna')
    accion_ejecutada = fields.Boolean('Acción Ejecutada', default=False)
    resultado_accion = fields.Text('Resultado de Acción')

    # ==========================================
    # CONSTRAINTS
    # ==========================================
    _sql_constraints = [
        ('positive_percentage', 'CHECK(porcentaje_suministro >= 0 AND porcentaje_suministro <= 100)',
         'Porcentaje debe estar entre 0 y 100'),
        ('positive_days', 'CHECK(dias_sin_lecturas >= 0)',
         'Días sin lecturas debe ser positivo'),
        ('unique_api_event', 'UNIQUE(api_event_id)',
         'Event de API ya procesado'),
    ]

    # ==========================================
    # COMPUTED FIELDS
    # ==========================================

    @api.depends('serie_equipo')
    def _compute_equipo_id(self):
        for alert in self:
            if alert.serie_equipo:
                equipo = self.env['alquiler'].search([('serie', '=', alert.serie_equipo)], limit=1)
                alert.equipo_id = equipo.id if equipo else False
            else:
                alert.equipo_id = False

    @api.depends('equipo_id')
    def _compute_equipo_info(self):
        for alert in self:
            if alert.equipo_id:
                eq = alert.equipo_id
                alert.cliente_nombre = eq.cliente_id.name if hasattr(eq, 'cliente_id') and eq.cliente_id else ''
                alert.modelo_equipo = eq.name.name if hasattr(eq, 'name') and eq.name else ''
                alert.ubicacion_equipo = getattr(eq, 'ubicacion', '') or getattr(eq, 'custom_location', '') or ''
            else:
                alert.cliente_nombre = ''
                alert.modelo_equipo = ''
                alert.ubicacion_equipo = ''

    @api.depends('serie_equipo', 'tipo_alerta', 'prioridad')
    def _compute_display_name(self):
        tipo_labels = dict(self._fields['tipo_alerta'].selection)
        prio_labels = dict(self._fields['prioridad'].selection)
        for alert in self:
            serie = alert.serie_equipo or 'N/A'
            tipo = tipo_labels.get(alert.tipo_alerta, alert.tipo_alerta or '')
            prio = prio_labels.get(alert.prioridad, alert.prioridad or '')
            alert.display_name = f"[{prio}] {serie} - {tipo}"

    # ==========================================
    # HELPER: EMAIL SOPORTE (configurable)
    # ==========================================
    def _get_email_soporte(self):
        """Obtiene email de soporte desde parámetro del sistema."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'printtracker.alert.email_destino', 'soporte@andescopiers.com.pe'
        )

    # ==========================================
    # HELPER: PARSE TIMESTAMP API → naive datetime
    # ==========================================
    @staticmethod
    def _parse_api_timestamp(timestamp_str):
        """
        Convierte timestamp de API a datetime naive (Odoo requiere naive UTC).
        Ejemplos API: '2024-01-15T10:30:00Z', '2024-01-15T10:30:00.000Z'
        """
        if not timestamp_str:
            return None
        try:
            dt = dateutil_parser.parse(timestamp_str)
            # Odoo requiere naive datetime (asume UTC)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            return None

    # ==========================================
    # CREAR ALERTAS - SUMINISTRO BAJO
    # ==========================================
    def crear_alerta_suministro_bajo(self, suministro):
        """
        Crea o actualiza alerta de suministro bajo.
        Si ya existe una activa para el mismo suministro, actualiza y escala.
        """
        try:
            serie = suministro.device_id.serie if suministro.device_id else None
            if not serie:
                return None

            percent = suministro.percent_remaining or 0

            # Determinar tipo y prioridad según porcentaje
            if percent <= 0:
                tipo = 'suministro_vacio'
                prioridad = 'urgente'
            elif percent < 5:
                tipo = 'suministro_critico'
                prioridad = 'critica'
            else:
                tipo = 'suministro_bajo'
                prioridad = 'alta'

            # Buscar alerta existente activa para este suministro
            existente = self.search([
                ('serie_equipo', '=', serie),
                ('suministro_id', '=', suministro.id),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                # Actualizar: incrementar repeticiones, escalar si empeoró
                vals = {
                    'ultima_revision': fields.Datetime.now(),
                    'porcentaje_suministro': percent,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                }

                # Escalar prioridad si empeoró
                prioridades = ['baja', 'media', 'alta', 'critica', 'urgente']
                if prioridades.index(prioridad) > prioridades.index(existente.prioridad):
                    vals['prioridad'] = prioridad
                    vals['tipo_alerta'] = tipo

                # Si llegó al máximo repeticiones → en_proceso
                if existente.contador_repeticiones + 1 >= existente.max_repeticiones:
                    vals['estado'] = 'en_proceso'

                existente.write(vals)
                _logger.debug(f"📝 Actualizada alerta suministro {serie} ({percent:.1f}%)")
                return existente

            # Crear nueva
            tipo_supply = dict(suministro._fields['supply_type'].selection).get(
                suministro.supply_type, suministro.supply_type)
            color_supply = dict(suministro._fields['supply_color'].selection).get(
                suministro.supply_color, '') if suministro.supply_color else ''

            titulo = f"Suministro {tipo} - {serie}"
            desc = (f"{tipo_supply} {color_supply} al {percent:.1f}% "
                    f"en equipo {serie}")

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': tipo,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': desc,
                'suministro_id': suministro.id,
                'porcentaje_suministro': percent,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
                # La reposición de tóner se gestiona mediante
                # toner.counter.submission; nunca crear una OC directa.
                'accion_automatica': 'ninguna',
            })

            _logger.info(f"🆕 Alerta suministro: {serie} - {tipo_supply} {color_supply} ({percent:.1f}%)")

            # Integrar con el flujo central de tóner.
            try:
                nueva._create_toner_monitoring_event()
            except Exception:
                _logger.exception(
                    "[TONER/PT] Error integrando alerta interna de suministro id=%s",
                    nueva.id,
                )

            return nueva

        except Exception as e:
            _logger.error(f"❌ Error crear alerta suministro: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - EQUIPO OFFLINE
    # ==========================================
    def crear_alerta_equipo_offline(self, serie, dias_offline, ultima_lectura):
        """
        Crea o actualiza alerta de equipo offline.
        Escala: 3+ días = alta, 7+ = crítica, 14+ = urgente
        """
        try:
            if not serie:
                return None

            # Prioridad por días
            if dias_offline >= 14:
                prioridad = 'urgente'
            elif dias_offline >= 7:
                prioridad = 'critica'
            else:
                prioridad = 'alta'

            existente = self.search([
                ('serie_equipo', '=', serie),
                ('tipo_alerta', '=', 'equipo_offline'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                vals = {
                    'ultima_revision': fields.Datetime.now(),
                    'dias_sin_lecturas': dias_offline,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                }
                prioridades = ['baja', 'media', 'alta', 'critica', 'urgente']
                if prioridades.index(prioridad) > prioridades.index(existente.prioridad):
                    vals['prioridad'] = prioridad

                if existente.contador_repeticiones + 1 >= existente.max_repeticiones:
                    vals['estado'] = 'en_proceso'

                existente.write(vals)
                return existente

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': 'equipo_offline',
                'prioridad': prioridad,
                'titulo': f"Equipo offline - {serie} ({dias_offline} días)",
                'descripcion': f"Equipo {serie} sin reportar hace {dias_offline} días. Última lectura: {ultima_lectura}",
                'dias_sin_lecturas': dias_offline,
                'ultima_lectura': ultima_lectura if isinstance(ultima_lectura, datetime) else None,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
            })

            _logger.info(f"🆕 Alerta offline: {serie} ({dias_offline} días)")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta offline: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - USO ANÓMALO
    # ==========================================
    def crear_alerta_uso_anomalo(self, serie, tipo_anomalia, contador_actual, contador_anterior):
        """tipo_anomalia: 'alto' o 'bajo'"""
        try:
            if not serie:
                return None

            tipo = f"uso_anomalo_{tipo_anomalia}"
            prioridad = 'alta' if tipo_anomalia == 'alto' else 'media'
            diferencia = abs(contador_actual - contador_anterior)

            existente = self.search([
                ('serie_equipo', '=', serie),
                ('tipo_alerta', '=', tipo),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                existente.write({
                    'ultima_revision': fields.Datetime.now(),
                    'contador_actual': contador_actual,
                    'contador_anterior': contador_anterior,
                    'diferencia_contador': diferencia,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                })
                return existente

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': tipo,
                'prioridad': prioridad,
                'titulo': f"Uso {tipo_anomalia} - {serie}",
                'descripcion': f"Incremento {'excesivo' if tipo_anomalia == 'alto' else 'muy bajo'}: "
                               f"{diferencia:,} páginas en equipo {serie}",
                'contador_actual': contador_actual,
                'contador_anterior': contador_anterior,
                'diferencia_contador': diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
            })

            _logger.info(f"🆕 Alerta uso {tipo_anomalia}: {serie} ({diferencia:,} págs)")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta uso anómalo: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - CONTADOR DECRECE
    # ==========================================
    def crear_alerta_contador_decrece(self, serie, tipo_contador, valor_actual, valor_anterior):
        """tipo_contador: 'B/N', 'Color', 'Scan'"""
        try:
            if not serie:
                return None

            diferencia = valor_anterior - valor_actual

            existente = self.search([
                ('serie_equipo', '=', serie),
                ('tipo_alerta', '=', 'contador_decrece'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                existente.write({
                    'ultima_revision': fields.Datetime.now(),
                    'contador_actual': valor_actual,
                    'contador_anterior': valor_anterior,
                    'diferencia_contador': diferencia,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                })
                return existente

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': 'contador_decrece',
                'prioridad': 'critica' if diferencia > 10000 else 'alta',
                'titulo': f"Contador {tipo_contador} decreció - {serie}",
                'descripcion': f"Contador {tipo_contador} bajó de {valor_anterior:,} a {valor_actual:,} "
                               f"(dif: {diferencia:,}) en equipo {serie}",
                'contador_actual': valor_actual,
                'contador_anterior': valor_anterior,
                'diferencia_contador': diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
            })

            _logger.info(f"🆕 Alerta contador decrece: {serie} {tipo_contador} ({diferencia:,})")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta contador: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - DESDE API EVENT
    # ==========================================
    def crear_alerta_desde_api_event(self, event_data, device_serial):
        """
        Crea alerta desde un event de la API de PrintTracker.
        Campos del event: id, createdDate, modifiedDate, entityKey, installKey,
        deviceKey, deviceSerialNumber, timestamp, description, alertType,
        supplyKey, resolutionStatus, acknowledged, meterRead
        """
        try:
            event_id = event_data.get('id')
            device_serial = str(device_serial or '').strip()
            if not event_id or not device_serial:
                return None

            # Verificar duplicado
            if self.search([('api_event_id', '=', event_id)], limit=1):
                return None

            # Clasificar event
            clasificacion = self._clasificar_event_api(event_data)

            # Parse timestamp
            ts_raw = event_data.get('timestamp') or event_data.get('createdDate')
            ts = self._parse_api_timestamp(ts_raw)

            nueva = self.create({
                'serie_equipo': device_serial,
                'tipo_alerta': clasificacion['tipo'],
                'prioridad': clasificacion['prioridad'],
                'titulo': f"{clasificacion['titulo']} - {device_serial}",
                'descripcion': event_data.get('description', 'Evento de PrintTracker API'),
                'fecha_deteccion': ts or fields.Datetime.now(),
                'origen_datos': 'api_events',
                'api_event_id': event_id,
                'api_event_type': event_data.get('alertType', ''),
                'api_resolution_status': event_data.get('resolutionStatus', ''),
                'api_event_timestamp': ts,
                'api_supply_key': event_data.get('supplyKey', ''),
                'api_device_key': event_data.get('deviceKey', ''),
                'api_raw_data': json.dumps(event_data, default=str)[:5000],
                'max_repeticiones': 9999,  # API events no tienen límite
            })

            _logger.info(f"🆕 Alerta API: {device_serial} - {clasificacion['tipo']} (event {event_id})")

            # Los eventos de suministro se normalizan y se envían al
            # flujo oficial de gestión de tóner.
            try:
                nueva._create_toner_monitoring_event(event_data=event_data)
            except Exception:
                _logger.exception(
                    "[TONER/PT] Error integrando API event=%s alerta=%s",
                    event_id,
                    nueva.id,
                )

            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta API event: {e}\n{traceback.format_exc()}")
            return None

    def _clasificar_event_api(self, event_data):
        """
        Clasifica cualquier event recibido desde PrintTracker.

        La API documenta que un event puede incluir:
        id, deviceSerialNumber, timestamp, description, alertType,
        supplyKey, resolutionStatus, meterRead y supplies.

        REGLAS:
        - Nunca descartar un event desconocido.
        - Priorizar alertType cuando tenga contenido útil.
        - Usar supplyKey para reconocer eventos de suministros.
        - Usar description como respaldo.
        - Todo lo no reconocido se conserva como device_event.
        """
        event_data = event_data or {}

        desc = str(event_data.get('description') or '').strip().lower()
        alert_type = str(event_data.get('alertType') or '').strip().lower()
        supply_key = str(event_data.get('supplyKey') or '').strip()

        combined = " ".join(
            value for value in (alert_type, desc)
            if value
        )

        # ----------------------------------------------------------
        # ATASCO DE PAPEL
        # ----------------------------------------------------------
        if any(term in combined for term in (
            'paper jam',
            'jammed',
            'paperjam',
            'atasco',
        )):
            return {
                'tipo': 'paper_jam',
                'prioridad': 'alta',
                'titulo': 'Atasco de Papel',
            }

        # ----------------------------------------------------------
        # SUMINISTROS
        # supplyKey es una señal fuerte de que el event pertenece
        # a un consumible. La descripción/alertType define la acción.
        # ----------------------------------------------------------
        supply_words = (
            'toner',
            'ink',
            'drum',
            'supply',
            'cartridge',
            'developer',
            'waste',
            'imaging unit',
            'fuser',
        )
        is_supply_event = bool(supply_key) or any(
            term in combined for term in supply_words
        )

        if is_supply_event:
            # Reemplazo confirmado / instalación.
            if any(term in combined for term in (
                'replaced',
                'replacement',
                'was replaced',
                'installed',
                'replacement detected',
                'reemplaz',
                'sustituid',
                'instalad',
            )):
                return {
                    'tipo': 'supply_replaced',
                    'prioridad': 'media',
                    'titulo': 'Suministro Reemplazado',
                }

            # Vacío / agotado.
            if any(term in combined for term in (
                'empty',
                'depleted',
                'out of toner',
                'out of ink',
                'agotado',
                'agotada',
                'vacío',
                'vacio',
                'vacía',
                'vacia',
                '0%',
            )):
                return {
                    'tipo': 'suministro_vacio',
                    'prioridad': 'urgente',
                    'titulo': 'Suministro Vacío',
                }

            # Crítico.
            if any(term in combined for term in (
                'critical',
                'very low',
                'critically low',
                'crítico',
                'critico',
            )):
                return {
                    'tipo': 'suministro_critico',
                    'prioridad': 'critica',
                    'titulo': 'Suministro Crítico',
                }

            # Bajo.
            if any(term in combined for term in (
                'low supply',
                'supply low',
                'low toner',
                'toner low',
                'low ink',
                'ink low',
                'low',
                'bajo',
                'baja',
            )):
                return {
                    'tipo': 'suministro_bajo',
                    'prioridad': 'alta',
                    'titulo': 'Suministro Bajo',
                }

            # Event de suministro sin semántica suficiente.
            return {
                'tipo': 'supply_event',
                'prioridad': 'media',
                'titulo': 'Evento de Suministro',
            }

        # ----------------------------------------------------------
        # ERRORES DEL DISPOSITIVO
        # ----------------------------------------------------------
        if any(term in combined for term in (
            'device error',
            'error code',
            'service call',
            'fault',
            'failure',
            'malfunction',
            'error',
            'fallo',
            'código',
            'codigo',
        )):
            return {
                'tipo': 'device_error',
                'prioridad': 'critica',
                'titulo': 'Error de Dispositivo',
            }

        # ----------------------------------------------------------
        # CUBIERTA / PUERTA ABIERTA
        # No se usa solamente "open" para evitar falsos positivos con
        # resolutionStatus=Open u otras descripciones.
        # ----------------------------------------------------------
        if any(term in combined for term in (
            'cover open',
            'door open',
            'cover is open',
            'door is open',
            'tapa abierta',
            'cubierta abierta',
            'puerta abierta',
        )):
            return {
                'tipo': 'cover_open',
                'prioridad': 'baja',
                'titulo': 'Cubierta Abierta',
            }

        # ----------------------------------------------------------
        # CONECTIVIDAD
        # ----------------------------------------------------------
        if any(term in combined for term in (
            'offline',
            'connectivity',
            'connection lost',
            'communication lost',
            'not responding',
            'unreachable',
            'desconect',
            'sin conexión',
            'sin conexion',
        )):
            return {
                'tipo': 'connectivity_issue',
                'prioridad': 'alta',
                'titulo': 'Problema de Conectividad',
            }

        # ----------------------------------------------------------
        # MANTENIMIENTO
        # ----------------------------------------------------------
        if any(term in combined for term in (
            'maintenance required',
            'maintenance due',
            'service required',
            'maintenance',
            'mantenimiento',
        )):
            return {
                'tipo': 'mantenimiento_debido',
                'prioridad': 'alta',
                'titulo': 'Mantenimiento Requerido',
            }

        # ----------------------------------------------------------
        # FALLBACK SEGURO
        # Nunca perder un event porque PrintTracker agregue un nuevo
        # alertType que todavía no conocemos.
        # ----------------------------------------------------------
        return {
            'tipo': 'device_event',
            'prioridad': 'media',
            'titulo': 'Evento de Dispositivo',
        }

    def procesar_notificaciones(self):
        """
        Envía email a soporte + chatter en equipo.

        Una alerta solo pasa de 'nueva' a 'notificada' cuando todos los
        canales configurados que correspondan fueron procesados con éxito.
        Si el correo falla, permanece pendiente para que el cron lo reintente.
        """
        resultado = True

        for alert in self:
            try:
                email_ok = True
                chatter_ok = True

                if alert.notificar_email and not alert.email_enviado:
                    email_ok = bool(alert._enviar_notificacion_email())

                if alert.notificar_chatter and not alert.chatter_enviado:
                    chatter_ok = bool(alert._enviar_notificacion_chatter())

                # Ejecutar acción automática
                if alert.accion_automatica != 'ninguna' and not alert.accion_ejecutada:
                    alert._ejecutar_accion_automatica()

                email_completo = (
                    not alert.notificar_email
                    or alert.email_enviado
                    or email_ok
                )
                chatter_completo = (
                    not alert.notificar_chatter
                    or alert.chatter_enviado
                    or chatter_ok
                )

                if alert.estado == 'nueva' and email_completo and chatter_completo:
                    alert.estado = 'notificada'

                if not (email_completo and chatter_completo):
                    resultado = False
                    _logger.warning(
                        "⚠️ Alerta pendiente de notificación id=%s serie=%s "
                        "email_ok=%s chatter_ok=%s",
                        alert.id,
                        alert.serie_equipo,
                        email_completo,
                        chatter_completo,
                    )

            except Exception as e:
                resultado = False
                _logger.error(
                    f"❌ Error notificación {alert.display_name}: "
                    f"{e}\n{traceback.format_exc()}"
                )

        return resultado

    def _enviar_notificacion_email(self):
        """
        Envía email a soporte (configurable).
        SIEMPRE a soporte, NUNCA al cliente/entidad.

        Retorna True únicamente cuando Odoo pudo ejecutar el envío.
        """
        self.ensure_one()

        try:
            email_destino = self._get_email_soporte()
            if not email_destino:
                _logger.warning(
                    "⚠️ Email soporte no configurado para alerta=%s serie=%s",
                    self.id,
                    self.serie_equipo,
                )
                return False

            # Construir HTML del email
            html_body = self._construir_email_html()

            prioridad_label = dict(
                self._fields['prioridad'].selection
            ).get(
                self.prioridad,
                self.prioridad,
            )
            tipo_label = dict(
                self._fields['tipo_alerta'].selection
            ).get(
                self.tipo_alerta,
                self.tipo_alerta,
            )

            mail_values = {
                'subject': (
                    f"[{prioridad_label.upper()}] Alerta PrintTracker - "
                    f"{self.serie_equipo} - {tipo_label}"
                ),
                'body_html': html_body,
                'email_from': (
                    self.env.company.email
                    or 'noreply@andescopiers.com.pe'
                ),
                'email_to': email_destino,
                'auto_delete': False,
            }

            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()

            self.write({
                'email_enviado': True,
                'ultima_revision': fields.Datetime.now(),
            })

            _logger.info(
                "📧 Email enviado a %s para %s alerta=%s",
                email_destino,
                self.serie_equipo,
                self.id,
            )
            return True

        except Exception as e:
            _logger.error(
                f"❌ Error email alerta={self.id} serie={self.serie_equipo}: "
                f"{e}\n{traceback.format_exc()}"
            )
            return False

    def _construir_email_html(self):
        """Construye HTML profesional para email."""
        self.ensure_one()
        prioridad_label = dict(self._fields['prioridad'].selection).get(self.prioridad, self.prioridad)
        tipo_label = dict(self._fields['tipo_alerta'].selection).get(self.tipo_alerta, self.tipo_alerta)

        # Color según prioridad
        colores = {
            'urgente': '#dc3545', 'critica': '#e74c3c',
            'alta': '#fd7e14', 'media': '#ffc107', 'baja': '#28a745',
        }
        color = colores.get(self.prioridad, '#6c757d')

        # Info adicional según tipo
        info_extra = ''
        if self.porcentaje_suministro:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Nivel Suministro</td><td style="padding:8px;border:1px solid #ddd;">{self.porcentaje_suministro:.1f}%</td></tr>'
        if self.dias_sin_lecturas:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Días Offline</td><td style="padding:8px;border:1px solid #ddd;">{self.dias_sin_lecturas}</td></tr>'
        if self.diferencia_contador:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Diferencia Contador</td><td style="padding:8px;border:1px solid #ddd;">{self.diferencia_contador:,}</td></tr>'
        if self.api_event_id:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Event ID</td><td style="padding:8px;border:1px solid #ddd;">{self.api_event_id}</td></tr>'
        if self.api_resolution_status:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Estado API</td><td style="padding:8px;border:1px solid #ddd;">{self.api_resolution_status}</td></tr>'

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:{color};color:white;padding:15px;border-radius:8px 8px 0 0;">
                <h2 style="margin:0;">🚨 Alerta PrintTracker - {prioridad_label.upper()}</h2>
            </div>
            <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
                <table style="width:100%;border-collapse:collapse;margin-bottom:15px;">
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;width:35%;">Equipo (Serie)</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.serie_equipo}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Cliente</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.cliente_nombre or 'N/A'}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Modelo</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.modelo_equipo or 'N/A'}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Ubicación</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.ubicacion_equipo or 'N/A'}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Tipo Alerta</td>
                        <td style="padding:8px;border:1px solid #ddd;">{tipo_label}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Prioridad</td>
                        <td style="padding:8px;border:1px solid #ddd;color:{color};font-weight:bold;">{prioridad_label}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Fecha Detección</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.fecha_deteccion or self.fecha_creacion}</td></tr>
                    {info_extra}
                </table>
                <div style="background:#f8f9fa;padding:12px;border-radius:4px;margin-top:10px;">
                    <strong>Descripción:</strong><br/>{self.descripcion or 'Sin descripción adicional'}
                </div>
                <p style="color:#6c757d;font-size:12px;margin-top:15px;">
                    Origen: {self.origen_datos} | Alerta #{self.id or 'nueva'} |
                    Generado automáticamente por PrintTracker Alert System
                </p>
            </div>
        </div>
        """
        return html

    def _enviar_notificacion_chatter(self):
        """Publica notificación en el chatter del equipo."""
        self.ensure_one()
        try:
            if not self.equipo_id:
                return

            prioridad_label = dict(self._fields['prioridad'].selection).get(self.prioridad, self.prioridad)
            tipo_label = dict(self._fields['tipo_alerta'].selection).get(self.tipo_alerta, self.tipo_alerta)

            body = f"""
            <p><strong>🚨 Alerta PrintTracker [{prioridad_label}]</strong></p>
            <p><strong>Tipo:</strong> {tipo_label}</p>
            <p>{self.descripcion or ''}</p>
            """

            self.equipo_id.message_post(
                body=body,
                subject=f"Alerta: {tipo_label}",
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            self.chatter_enviado = True
            _logger.info(f"💬 Chatter en equipo {self.serie_equipo}")

        except Exception as e:
            _logger.error(f"❌ Error chatter: {e}")

    # ==========================================
    # ACCIONES AUTOMÁTICAS
    # ==========================================
    def _ejecutar_accion_automatica(self):
        """Ejecuta acción automática según configuración."""
        self.ensure_one()
        try:
            if self.accion_automatica == 'crear_orden_compra':
                if self._is_toner_event():
                    self._create_toner_monitoring_event()
                    self.accion_ejecutada = True
                    self.resultado_accion = (
                        'Evento enviado al flujo oficial de solicitud de tóner'
                    )
                else:
                    self._accion_crear_orden_compra()
            elif self.accion_automatica == 'crear_tarea':
                self._accion_crear_tarea()
            elif self.accion_automatica == 'notificar_tecnico':
                self._accion_notificar_tecnico()
        except Exception as e:
            self.resultado_accion = f"Error: {e}"
            _logger.error(f"❌ Error acción automática: {e}")

    def _accion_crear_orden_compra(self):
        """Crea orden de compra si hay suministro y producto asociados."""
        self.ensure_one()
        if not self.suministro_id or not self.suministro_id.product_id:
            self.resultado_accion = "Sin suministro/producto asociado"
            return

        try:
            supply = self.suministro_id
            po = self.env['purchase.order'].create({
                'origin': f'Alerta PrintTracker - {self.serie_equipo}',
                'order_line': [(0, 0, {
                    'product_id': supply.product_id.id,
                    'name': f'{supply.product_id.name} - {self.serie_equipo}',
                    'product_qty': 1,
                    'price_unit': supply.supply_cost or supply.product_id.standard_price or 0,
                    'date_planned': fields.Datetime.now(),
                })],
            })
            self.accion_ejecutada = True
            self.resultado_accion = f"OC creada: {po.name}"
            _logger.info(f"📦 OC {po.name} creada para {self.serie_equipo}")
        except Exception as e:
            self.resultado_accion = f"Error OC: {e}"

    def _accion_crear_tarea(self):
        """Crea tarea en proyecto si está disponible."""
        self.ensure_one()
        try:
            if not hasattr(self.env, 'project.task'):
                self.resultado_accion = "Módulo project no instalado"
                return

            task = self.env['project.task'].create({
                'name': self.titulo,
                'description': self.descripcion or '',
            })
            self.accion_ejecutada = True
            self.resultado_accion = f"Tarea creada: {task.name}"
        except Exception as e:
            self.resultado_accion = f"Error tarea: {e}"

    def _accion_notificar_tecnico(self):
        """Envía email al equipo de soporte (no a todos los usuarios)."""
        self.ensure_one()
        try:
            email_soporte = self._get_email_soporte()
            if email_soporte:
                self._enviar_notificacion_email()
                self.accion_ejecutada = True
                self.resultado_accion = f"Notificación enviada a {email_soporte}"
        except Exception as e:
            self.resultado_accion = f"Error notificación: {e}"

    # ==========================================
    # ACCIONES MANUALES
    # ==========================================
    def action_marcar_resuelta(self):
        for alert in self:
            alert.write({
                'estado': 'resuelta',
                'resuelto_por': self.env.uid,
                'fecha_resolucion': fields.Datetime.now(),
            })
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': 'Alerta(s) marcada(s) como resuelta(s)', 'type': 'success'}}

    def action_marcar_en_proceso(self):
        for alert in self:
            alert.estado = 'en_proceso'

    def action_ignorar(self):
        for alert in self:
            alert.estado = 'ignorada'

    def action_reenviar_email(self):
        self.ensure_one()
        self.email_enviado = False
        self._enviar_notificacion_email()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': f'Email reenviado a {self._get_email_soporte()}', 'type': 'success'}}

    def action_resolver(self):
        """Botón 'Resolver' en la vista form."""
        return self.action_marcar_resuelta()

    def action_asignar(self):
        """Botón 'Asignar' en la vista form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar Alerta',
            'res_model': 'printtracker.alert',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_view_equipo(self):
        """Botón 'Ver Equipo' en la vista form."""
        self.ensure_one()
        if not self.equipo_id:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'message': 'No hay equipo vinculado', 'type': 'warning'}}
        return {
            'type': 'ir.actions.act_window',
            'name': f'Equipo - {self.serie_equipo}',
            'res_model': 'alquiler',
            'res_id': self.equipo_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==========================================
    # UTILIDADES
    # ==========================================
    @api.model
    def limpiar_alertas_antiguas(self, dias=30):
        """Elimina alertas resueltas/cerradas más antiguas que N días."""
        try:
            fecha_corte = datetime.now() - timedelta(days=dias)
            antiguas = self.search([
                ('estado', 'in', ['resuelta', 'cerrada', 'ignorada']),
                ('fecha_creacion', '<', fecha_corte),
            ])
            count = len(antiguas)
            antiguas.unlink()
            _logger.info(f"🗑️ {count} alertas antiguas eliminadas")
            return count
        except Exception as e:
            _logger.error(f"❌ Error limpieza: {e}")
            return 0

    @api.model
    def obtener_estadisticas_alertas(self):
        """Estadísticas generales de alertas."""
        try:
            activas = self.search([('estado', 'in', ['nueva', 'notificada', 'en_proceso'])])
            return {
                'total_activas': len(activas),
                'por_prioridad': {
                    p: len(activas.filtered(lambda a, pr=p: a.prioridad == pr))
                    for p in ['urgente', 'critica', 'alta', 'media', 'baja']
                },
                'por_tipo': {
                    t: len(activas.filtered(lambda a, tp=t: a.tipo_alerta == tp))
                    for t in set(activas.mapped('tipo_alerta'))
                },
                'por_origen': {
                    'interno': len(activas.filtered(lambda a: a.origen_datos == 'interno')),
                    'api_events': len(activas.filtered(lambda a: a.origen_datos == 'api_events')),
                },
                'equipos_afectados': len(set(activas.mapped('serie_equipo'))),
            }
        except Exception:
            return {}
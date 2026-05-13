# -*- coding: utf-8 -*-
import logging
import json
import base64
from datetime import datetime, date

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class LeaveRequestController(http.Controller):
    """
    Controlador para solicitudes de permiso usando el modelo personalizado:

        mantenimiento.tecnico.ausencia

    Este controlador NO usa:
        - hr.leave
        - hr.leave.type
        - hr.leave.allocation

    Solo maneja lógica:
        - Cargar datos para el formulario
        - Validar datos recibidos
        - Procesar adjunto
        - Crear mantenimiento.tecnico.ausencia
        - Enviar a aprobación
        - Retornar JSON
    """

    # ============================================================
    # FORMULARIO WEB
    # ============================================================

    @http.route('/leave/request', type='http', auth='user', website=True)
    def leave_request_form(self, **kwargs):
        """
        Renderiza el formulario web.

        El HTML, CSS y JS deben estar en:
            - views/permisos_templates.xml
            - static/src/css/permisos.css
            - static/src/js/permisos.js
        """

        _logger.info("=" * 80)
        _logger.info("🚀 [PERMISOS] CARGANDO FORMULARIO PERSONALIZADO")
        _logger.info("=" * 80)

        try:
            user = request.env.user
            Ausencia = request.env['mantenimiento.tecnico.ausencia'].sudo()

            _logger.info("👤 [PERMISOS] Usuario actual:")
            _logger.info("   - ID: %s", user.id)
            _logger.info("   - Nombre: %s", user.name)
            _logger.info("   - Login: %s", user.login)

            employee = user.employee_id

            if employee:
                _logger.info("✅ [PERMISOS] Empleado relacionado:")
                _logger.info("   - ID: %s", employee.id)
                _logger.info("   - Nombre: %s", employee.name)
                _logger.info(
                    "   - Departamento: %s",
                    employee.department_id.name if employee.department_id else "Sin departamento"
                )
                _logger.info(
                    "   - Compañía: %s",
                    employee.company_id.name if employee.company_id else "Sin compañía"
                )
            else:
                _logger.warning(
                    "⚠️ [PERMISOS] Usuario sin empleado relacionado. "
                    "Se permite continuar porque el modelo usa res.users como técnico."
                )

            # Tipos desde el selection real del modelo personalizado
            absence_types = self._get_absence_types()

            values = {
                'user': user,
                'employee': employee,
                'absence_types': absence_types,
                'today': fields.Date.today(),
                'user_tz': user.tz or 'UTC',
            }

            _logger.info("📋 [PERMISOS] Tipos enviados al template:")
            for item in absence_types:
                _logger.info("   - %s: %s", item.get('key'), item.get('name'))

            _logger.info("🎨 [PERMISOS] Renderizando template: sat.leave_request_template")

            return request.render('sat.leave_request_template', values)

        except Exception as e:
            _logger.error("=" * 80)
            _logger.error("💥 [PERMISOS] ERROR CARGANDO FORMULARIO")
            _logger.error("=" * 80)
            _logger.error("❌ Error: %s", str(e), exc_info=True)
            return request.render('website.500')

    # ============================================================
    # SUBMIT FORMULARIO
    # ============================================================

    @http.route(
        '/leave/request/submit',
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
        csrf=True
    )
    def submit_leave_request(self, **post):
        """
        Recibe el formulario y crea un registro en mantenimiento.tecnico.ausencia.
        """

        _logger.info("=" * 80)
        _logger.info("🚀 [PERMISOS] PROCESANDO SOLICITUD PERSONALIZADA")
        _logger.info("=" * 80)

        user = request.env.user

        try:
            _logger.info("👤 [PERMISOS] Usuario solicitante:")
            _logger.info("   - ID: %s", user.id)
            _logger.info("   - Nombre: %s", user.name)
            _logger.info("   - Login: %s", user.login)

            self._log_post_data(post)

            # ------------------------------------------------------------
            # Validación básica
            # ------------------------------------------------------------
            validation = self._validate_form_data(post)

            if not validation.get('valid'):
                return self._json_error(
                    error_code='VALIDATION_ERROR',
                    message=validation.get('message'),
                    suggestion='Verifica los campos requeridos y vuelve a intentar.',
                    details=validation.get('details')
                )

            # ------------------------------------------------------------
            # Preparar valores para mantenimiento.tecnico.ausencia
            # ------------------------------------------------------------
            vals = self._prepare_absence_values(post, user)

            _logger.info("⚙️ [PERMISOS] Valores finales para crear ausencia:")
            for key, value in vals.items():
                if key == 'adjunto':
                    _logger.info("   - adjunto: archivo base64")
                else:
                    _logger.info("   - %s: %s", key, value)

            # ------------------------------------------------------------
            # Validar solapamiento antes de crear
            # ------------------------------------------------------------
            overlap = self._check_overlap(
                tecnico_id=vals.get('tecnico_id'),
                fecha_inicio=vals.get('fecha_inicio'),
                fecha_fin=vals.get('fecha_fin') or vals.get('fecha_inicio'),
            )

            if overlap.get('has_overlap'):
                return self._json_error(
                    error_code='DATE_OVERLAP',
                    message=overlap.get('message'),
                    suggestion='Ya existe una ausencia o permiso activo para este trabajador en ese rango.',
                    details=overlap.get('details')
                )

            # ------------------------------------------------------------
            # Crear registro personalizado
            # ------------------------------------------------------------
            ausencia = self._create_custom_absence(vals)

            # ------------------------------------------------------------
            # Enviar a aprobación
            # ------------------------------------------------------------
            self._send_to_approval(ausencia)

            # ------------------------------------------------------------
            # Registrar mensaje en chatter
            # ------------------------------------------------------------
            self._post_chatter_message(ausencia, user)

            _logger.info("=" * 80)
            _logger.info("🎉 [PERMISOS] SOLICITUD CREADA CORRECTAMENTE")
            _logger.info("=" * 80)
            _logger.info("   - ID: %s", ausencia.id)
            _logger.info("   - Referencia: %s", ausencia.name)
            _logger.info("   - Técnico: %s", ausencia.tecnico_id.name)
            _logger.info("   - Tipo: %s", ausencia.tipo)
            _logger.info("   - Estado: %s", ausencia.estado)
            _logger.info("   - Fechas: %s a %s", ausencia.fecha_inicio, ausencia.fecha_fin)

            return self._json_success(
                message='Solicitud de permiso enviada correctamente.',
                record_id=ausencia.id,
                reference=ausencia.name,
                redirect_url='/web#id=%s&model=mantenimiento.tecnico.ausencia&view_type=form' % ausencia.id,
            )

        except ValidationError as e:
            _logger.error("❌ [PERMISOS] ValidationError: %s", str(e), exc_info=True)
            return self._json_error(
                error_code='VALIDATION_ERROR',
                message=str(e),
                suggestion='Verifica los datos ingresados.'
            )

        except UserError as e:
            _logger.error("❌ [PERMISOS] UserError: %s", str(e), exc_info=True)
            return self._json_error(
                error_code='USER_ERROR',
                message=str(e),
                suggestion='Verifica la configuración del técnico o del permiso.'
            )

        except Exception as e:
            _logger.error("=" * 80)
            _logger.error("💥 [PERMISOS] ERROR GENERAL EN SUBMIT")
            _logger.error("=" * 80)
            _logger.error("❌ Error: %s", str(e), exc_info=True)
            return self._json_error(
                error_code='INTERNAL_ERROR',
                message='No se pudo procesar la solicitud de permiso.',
                suggestion='Intenta nuevamente. Si el problema persiste, contacta al administrador.',
                details=str(e)
            )

    # ============================================================
    # API AJAX
    # ============================================================

    @http.route('/leave/request/get_leave_types', type='json', auth='user')
    def get_available_leave_types(self):
        """
        Retorna tipos de ausencia del modelo personalizado.
        """

        _logger.info("🔌 [PERMISOS] API get_leave_types")

        try:
            absence_types = self._get_absence_types()

            return {
                'success': True,
                'leave_types': absence_types,
                'absence_types': absence_types,
            }

        except Exception as e:
            _logger.error("💥 [PERMISOS] Error get_leave_types: %s", str(e), exc_info=True)
            return {
                'success': False,
                'error': str(e),
            }

    @http.route('/leave/request/validate_dates', type='json', auth='user')
    def validate_leave_dates(self, date_from=None, date_to=None, tipo=None):
        """
        Valida fechas desde JS antes de enviar el formulario.
        """

        _logger.info("🔍 [PERMISOS] API validate_dates")
        _logger.info("   - date_from: %s", date_from)
        _logger.info("   - date_to: %s", date_to)
        _logger.info("   - tipo: %s", tipo)

        try:
            if not date_from:
                return {
                    'success': False,
                    'valid': False,
                    'error': 'La fecha de inicio es requerida.',
                }

            fecha_inicio = self._parse_date(date_from)
            fecha_fin = self._parse_date(date_to) if date_to else fecha_inicio

            if fecha_inicio < date.today():
                return {
                    'success': True,
                    'valid': False,
                    'error': 'No se pueden solicitar permisos para fechas pasadas.',
                }

            if fecha_fin < fecha_inicio:
                return {
                    'success': True,
                    'valid': False,
                    'error': 'La fecha fin no puede ser menor que la fecha de inicio.',
                }

            return {
                'success': True,
                'valid': True,
            }

        except Exception as e:
            _logger.error("💥 [PERMISOS] Error validate_dates: %s", str(e), exc_info=True)
            return {
                'success': False,
                'valid': False,
                'error': 'Las fechas ingresadas no son válidas.',
            }

    @http.route('/leave/request/check_overlap', type='json', auth='user')
    def check_leave_overlap(self, date_from=None, date_to=None):
        """
        Verifica solapamiento desde JS.
        """

        _logger.info("🔍 [PERMISOS] API check_overlap")
        _logger.info("   - date_from: %s", date_from)
        _logger.info("   - date_to: %s", date_to)

        try:
            user = request.env.user

            if not date_from:
                return {
                    'success': False,
                    'has_overlap': False,
                    'error': 'La fecha de inicio es requerida.',
                }

            fecha_inicio = date_from
            fecha_fin = date_to or date_from

            overlap = self._check_overlap(
                tecnico_id=user.id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

            overlap['success'] = True
            return overlap

        except Exception as e:
            _logger.error("💥 [PERMISOS] Error check_overlap: %s", str(e), exc_info=True)
            return {
                'success': False,
                'has_overlap': False,
                'error': str(e),
            }

    # ============================================================
    # VALIDACIONES
    # ============================================================

    def _validate_form_data(self, post):
        """
        Valida los campos requeridos.

        Campos esperados desde el XML:
            - tipo
            - fecha_inicio
            - fecha_fin
            - motivo
            - dia_completo
            - hora_inicio
            - hora_fin
            - adjunto
        """

        _logger.info("🔍 [PERMISOS] Validando datos del formulario")

        tipo = post.get('tipo')
        fecha_inicio = post.get('fecha_inicio')
        fecha_fin = post.get('fecha_fin') or fecha_inicio
        motivo = post.get('motivo')

        missing = []

        if not tipo:
            missing.append('Tipo de permiso')

        if not fecha_inicio:
            missing.append('Fecha de inicio')

        if not motivo or not str(motivo).strip():
            missing.append('Motivo')

        if missing:
            return {
                'valid': False,
                'message': 'Campos requeridos faltantes: %s' % ', '.join(missing),
                'details': {
                    'missing_fields': missing,
                }
            }

        # Validar tipo contra selection real
        valid_types = self._get_valid_type_keys()

        if tipo not in valid_types:
            return {
                'valid': False,
                'message': 'Tipo de permiso no válido: %s' % tipo,
                'details': {
                    'valid_types': valid_types,
                }
            }

        # Validar fechas
        try:
            fecha_inicio_date = self._parse_date(fecha_inicio)
            fecha_fin_date = self._parse_date(fecha_fin)
        except Exception:
            return {
                'valid': False,
                'message': 'Las fechas ingresadas no tienen un formato válido.',
            }

        if fecha_fin_date < fecha_inicio_date:
            return {
                'valid': False,
                'message': 'La fecha fin no puede ser menor que la fecha de inicio.',
            }

        # Validar horas si no es día completo
        dia_completo = self._to_bool(post.get('dia_completo'), default=True)

        if not dia_completo:
            hora_inicio = post.get('hora_inicio')
            hora_fin = post.get('hora_fin')

            if not hora_inicio:
                return {
                    'valid': False,
                    'message': 'Debe ingresar la hora de inicio.',
                }

            if not hora_fin:
                return {
                    'valid': False,
                    'message': 'Debe ingresar la hora de fin.',
                }

            hora_inicio_float = self._hour_to_float(hora_inicio)
            hora_fin_float = self._hour_to_float(hora_fin)

            if hora_inicio_float < 0 or hora_inicio_float > 24:
                return {
                    'valid': False,
                    'message': 'La hora de inicio debe estar entre 0 y 24.',
                }

            if hora_fin_float < 0 or hora_fin_float > 24:
                return {
                    'valid': False,
                    'message': 'La hora de fin debe estar entre 0 y 24.',
                }

            if hora_fin_float <= hora_inicio_float:
                return {
                    'valid': False,
                    'message': 'La hora fin debe ser mayor que la hora inicio.',
                }

        _logger.info("✅ [PERMISOS] Validación correcta")
        return {'valid': True}

    def _check_overlap(self, tecnico_id, fecha_inicio, fecha_fin):
        """
        Verifica si ya existe ausencia activa o pendiente para el técnico.
        """

        _logger.info("🔍 [PERMISOS] Verificando solapamiento")
        _logger.info("   - tecnico_id: %s", tecnico_id)
        _logger.info("   - fecha_inicio: %s", fecha_inicio)
        _logger.info("   - fecha_fin: %s", fecha_fin)

        Ausencia = request.env['mantenimiento.tecnico.ausencia'].sudo()

        domain = [
            ('tecnico_id', '=', tecnico_id),
            ('estado', 'not in', ['rechazado', 'cancelado', 'cerrado']),
            ('fecha_inicio', '<=', fecha_fin),
            '|',
            ('fecha_fin', '=', False),
            ('fecha_fin', '>=', fecha_inicio),
        ]

        _logger.info("🔎 [PERMISOS] Dominio overlap: %s", domain)

        records = Ausencia.search(domain)

        if not records:
            _logger.info("✅ [PERMISOS] Sin solapamiento")
            return {
                'has_overlap': False,
            }

        details = []

        for rec in records:
            tipo_label = dict(rec._fields['tipo'].selection).get(rec.tipo, rec.tipo)
            estado_label = dict(rec._fields['estado'].selection).get(rec.estado, rec.estado)

            details.append({
                'id': rec.id,
                'name': rec.name,
                'tipo': tipo_label,
                'estado': estado_label,
                'fecha_inicio': rec.fecha_inicio.strftime('%d/%m/%Y') if rec.fecha_inicio else '',
                'fecha_fin': rec.fecha_fin.strftime('%d/%m/%Y') if rec.fecha_fin else 'Sin fecha fin',
            })

            _logger.warning(
                "⚠️ [PERMISOS] Solapamiento encontrado: %s | %s | %s - %s",
                rec.name,
                tipo_label,
                rec.fecha_inicio,
                rec.fecha_fin,
            )

        return {
            'has_overlap': True,
            'message': 'Ya existe una ausencia o permiso registrado para este trabajador en el rango seleccionado.',
            'details': details,
        }

    # ============================================================
    # PREPARACIÓN Y CREACIÓN
    # ============================================================

    def _prepare_absence_values(self, post, user):
        """
        Prepara valores para crear mantenimiento.tecnico.ausencia.
        """

        _logger.info("⚙️ [PERMISOS] Preparando valores para modelo personalizado")

        tipo = post.get('tipo')
        fecha_inicio = post.get('fecha_inicio')
        fecha_fin = post.get('fecha_fin') or fecha_inicio
        motivo = (post.get('motivo') or '').strip()

        dia_completo = self._to_bool(post.get('dia_completo'), default=True)

        hora_inicio = 0.0
        hora_fin = 24.0

        if not dia_completo:
            hora_inicio = self._hour_to_float(post.get('hora_inicio'))
            hora_fin = self._hour_to_float(post.get('hora_fin'))

        vals = {
            'tecnico_id': user.id,
            'tipo': tipo,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'dia_completo': dia_completo,
            'hora_inicio': 0.0 if dia_completo else hora_inicio,
            'hora_fin': 24.0 if dia_completo else hora_fin,
            'motivo': motivo,
            'estado': 'borrador',
            'notificar_contabilidad': True,
        }

        # Procesar adjunto si viene del formulario
        attachment_vals = self._prepare_attachment(post)

        if attachment_vals:
            vals.update(attachment_vals)

        return vals

    def _create_custom_absence(self, vals):
        """
        Crea el registro en mantenimiento.tecnico.ausencia.
        """

        _logger.info("💾 [PERMISOS] Creando mantenimiento.tecnico.ausencia")

        Ausencia = request.env['mantenimiento.tecnico.ausencia'].sudo()

        ausencia = Ausencia.create(vals)

        _logger.info("✅ [PERMISOS] Ausencia creada")
        _logger.info("   - ID: %s", ausencia.id)
        _logger.info("   - Referencia: %s", ausencia.name)
        _logger.info("   - Estado: %s", ausencia.estado)

        return ausencia

    def _send_to_approval(self, ausencia):
        """
        Envía la ausencia a aprobación si está en borrador.
        """

        _logger.info("📨 [PERMISOS] Enviando a aprobación")

        if ausencia.estado != 'borrador':
            _logger.info(
                "ℹ️ [PERMISOS] No se envía a aprobación porque el estado actual es: %s",
                ausencia.estado
            )
            return False

        ausencia.action_enviar_aprobacion()

        _logger.info("✅ [PERMISOS] Enviada a aprobación")
        _logger.info("   - Estado actual: %s", ausencia.estado)

        return True

    def _post_chatter_message(self, ausencia, user):
        """
        Publica mensaje en chatter.
        """

        try:
            ausencia.message_post(
                body=_("Solicitud registrada desde el formulario web por %s.") % user.name,
                message_type='notification'
            )
            return True

        except Exception as e:
            _logger.warning(
                "⚠️ [PERMISOS] No se pudo publicar mensaje en chatter: %s",
                str(e)
            )
            return False

    # ============================================================
    # ADJUNTOS
    # ============================================================

    def _prepare_attachment(self, post):
        """
        Procesa un archivo adjunto y lo guarda en los campos:
            - adjunto
            - adjunto_filename

        El input del XML debe tener:
            name="adjunto"
        """

        _logger.info("📎 [PERMISOS] Revisando archivo adjunto")

        file_obj = post.get('adjunto')

        # Fallback por si el template usa otro nombre
        if not file_obj:
            file_obj = post.get('file_input')

        if not file_obj:
            _logger.info("ℹ️ [PERMISOS] No se recibió archivo adjunto")
            return {}

        if not hasattr(file_obj, 'read') or not hasattr(file_obj, 'filename'):
            _logger.info("ℹ️ [PERMISOS] El campo adjunto no es un archivo válido")
            return {}

        if not file_obj.filename:
            _logger.info("ℹ️ [PERMISOS] Archivo sin nombre, se omite")
            return {}

        _logger.info("📁 [PERMISOS] Archivo recibido:")
        _logger.info("   - Nombre: %s", file_obj.filename)
        _logger.info("   - Tipo MIME: %s", getattr(file_obj, 'content_type', 'unknown'))

        content = file_obj.read()

        if not content:
            _logger.warning("⚠️ [PERMISOS] Archivo vacío, se omite")
            return {}

        size = len(content)

        _logger.info("   - Tamaño: %.2f KB", size / 1024)

        max_size = 10 * 1024 * 1024

        if size > max_size:
            raise ValidationError(
                _("El archivo adjunto supera los 10 MB. Adjunta un archivo más pequeño.")
            )

        return {
            'adjunto': base64.b64encode(content),
            'adjunto_filename': file_obj.filename,
        }

    # ============================================================
    # HELPERS
    # ============================================================

    def _get_absence_types(self):
        """
        Obtiene los tipos desde el selection del modelo personalizado.
        """

        Ausencia = request.env['mantenimiento.tecnico.ausencia'].sudo()

        selection = Ausencia._fields['tipo'].selection

        return [
            {
                'id': key,
                'key': key,
                'name': label,
            }
            for key, label in selection
        ]

    def _get_valid_type_keys(self):
        """
        Retorna solo las claves válidas del selection tipo.
        """

        return [item['key'] for item in self._get_absence_types()]

    def _parse_date(self, value):
        """
        Convierte YYYY-MM-DD a date.
        """

        if isinstance(value, date):
            return value

        if not value:
            raise ValidationError(_("Fecha vacía."))

        return datetime.strptime(str(value), '%Y-%m-%d').date()

    def _to_bool(self, value, default=False):
        """
        Convierte valores de formulario a boolean.
        """

        if value is None:
            return default

        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in (
            'true',
            '1',
            'on',
            'yes',
            'si',
            'sí',
        )

    def _hour_to_float(self, value):
        """
        Convierte hora a float.

        Ejemplos:
            "08:00" -> 8.0
            "08:30" -> 8.5
            "13.5"  -> 13.5
        """

        if value is None or value == '':
            return 0.0

        if isinstance(value, (int, float)):
            return float(value)

        value = str(value).strip()

        try:
            if ':' in value:
                hour, minute = value.split(':', 1)
                return float(hour) + (float(minute) / 60.0)

            return float(value)

        except Exception:
            raise ValidationError(
                _("La hora ingresada no es válida: %s") % value
            )

    def _log_post_data(self, post):
        """
        Log controlado de datos recibidos.
        """

        _logger.info("📦 [PERMISOS] Datos recibidos:")

        for key, value in post.items():
            if hasattr(value, 'filename'):
                _logger.info(
                    "   📎 %s: %s (%s)",
                    key,
                    value.filename,
                    getattr(value, 'content_type', 'unknown')
                )
            else:
                _logger.info("   📋 %s: %s", key, value)

    # ============================================================
    # RESPUESTAS JSON
    # ============================================================

    def _json_success(self, message, record_id, reference, redirect_url):
        """
        Respuesta JSON exitosa.
        """

        data = {
            'success': True,
            'message': message,
            'record_id': record_id,
            'absence_id': record_id,
            'reference': reference,
            'redirect_url': redirect_url,
            'timestamp': datetime.now().isoformat(),
        }

        return request.make_response(
            json.dumps(data, ensure_ascii=False),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            status=200
        )

    def _json_error(self, error_code, message, suggestion=None, details=None):
        """
        Respuesta JSON de error.
        """

        _logger.error("❌ [PERMISOS] Retornando error JSON")
        _logger.error("   - Código: %s", error_code)
        _logger.error("   - Mensaje: %s", message)
        _logger.error("   - Sugerencia: %s", suggestion)
        _logger.error("   - Detalles: %s", details)

        data = {
            'success': False,
            'error_code': error_code,
            'error': message,
            'suggestion': suggestion or 'Verifica los datos ingresados.',
            'timestamp': datetime.now().isoformat(),
        }

        if details:
            data['details'] = details

        return request.make_response(
            json.dumps(data, ensure_ascii=False),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            status=400
        )
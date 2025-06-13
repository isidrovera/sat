# -*- coding: utf-8 -*-
import logging
import json
import base64
from datetime import datetime, timedelta
from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

class LeaveRequestController(http.Controller):

    @http.route('/leave/request', type='http', auth='user', website=True)
    def leave_request_form(self, **kwargs):
        """Mostrar el formulario de solicitud de permiso"""
        
        _logger.info("=" * 60)
        _logger.info("🚀 INICIO FORMULARIO PERMISO")
        _logger.info("=" * 60)
        
        try:
            # Obtener el empleado actual
            _logger.info("📋 Verificando empleado del usuario...")
            employee = request.env.user.employee_id
            if not employee:
                _logger.error(f"❌ Usuario {request.env.user.name} no tiene empleado asociado")
                _logger.error(f"   - Usuario ID: {request.env.user.id}")
                _logger.error(f"   - Usuario login: {request.env.user.login}")
                return request.render('website.404')
            
            _logger.info(f"✅ Empleado encontrado: {employee.name}")
            _logger.info(f"   - Empleado ID: {employee.id}")
            _logger.info(f"   - Departamento: {employee.department_id.name if employee.department_id else 'Sin departamento'}")
            _logger.info(f"   - Compañía: {employee.company_id.name}")
            
            # Obtener tipos de permiso disponibles
            _logger.info("📝 Buscando tipos de permiso disponibles...")
            leave_types = request.env['hr.leave.type'].search([
                ('company_id', 'in', [employee.company_id.id, False]),
                ('active', '=', True)
            ])
            
            _logger.info(f"✅ Tipos de permiso encontrados: {len(leave_types)}")
            for lt in leave_types:
                _logger.info(f"   📌 {lt.name}")
                _logger.info(f"      - ID: {lt.id}")
                _logger.info(f"      - Requiere asignación: {lt.requires_allocation}")
                _logger.info(f"      - Unidad de solicitud: {lt.request_unit}")
                _logger.info(f"      - Requiere documento: {lt.support_document}")
            
            # Datos para el template
            values = {
                'employee': employee,
                'leave_types': leave_types,
                'today': fields.Date.today(),
                'user_tz': request.env.user.tz or 'UTC',
            }
            
            _logger.info("🎨 Renderizando template...")
            _logger.info(f"   - Template: sat.leave_request_template")
            _logger.info(f"   - Empleado: {employee.name}")
            _logger.info(f"   - Tipos disponibles: {len(leave_types)}")
            _logger.info(f"   - Fecha actual: {values['today']}")
            
            _logger.info("=" * 60)
            _logger.info("✅ FORMULARIO CARGADO EXITOSAMENTE")
            _logger.info("=" * 60)
            
            return request.render('sat.leave_request_template', values)
            
        except Exception as e:
            _logger.error("=" * 60)
            _logger.error("💥 ERROR AL CARGAR FORMULARIO")
            _logger.error("=" * 60)
            _logger.error(f"❌ Error: {str(e)}", exc_info=True)
            _logger.error(f"   - Tipo de error: {type(e).__name__}")
            _logger.error(f"   - Usuario: {request.env.user.name if request.env.user else 'N/A'}")
            return request.render('website.500')

    @http.route('/leave/request/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit_leave_request(self, **post):
        """Procesar la solicitud de permiso enviada"""
        
        _logger.info("=" * 60)
        _logger.info("🚀 INICIO PROCESAMIENTO SOLICITUD")
        _logger.info("=" * 60)
        _logger.info(f"📦 Datos recibidos:")
        for key, value in post.items():
            if hasattr(value, 'filename'):
                _logger.info(f"   📎 {key}: {value.filename} ({getattr(value, 'content_type', 'unknown')})")
            else:
                _logger.info(f"   📋 {key}: {value}")
        
        _logger.info(f"🌐 Headers de solicitud:")
        for key, value in dict(request.httprequest.headers).items():
            _logger.info(f"   🔗 {key}: {value}")
        
        try:
            # Verificar empleado
            _logger.info("👤 Verificando empleado...")
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("❌ No se encontró empleado asociado al usuario")
                _logger.error(f"   - Usuario: {request.env.user.name}")
                _logger.error(f"   - Usuario ID: {request.env.user.id}")
                return self._return_error_response(
                    'EMPLOYEE_NOT_FOUND',
                    'No se encontró empleado asociado al usuario',
                    'Por favor contacta al administrador del sistema para configurar tu perfil de empleado.'
                )

            _logger.info(f"✅ Empleado verificado: {employee.name} (ID: {employee.id})")

            # Validar datos requeridos
            _logger.info("🔍 Validando campos requeridos...")
            validation_result = self._validate_form_data(post)
            if not validation_result['valid']:
                return self._return_error_response(
                    'VALIDATION_ERROR',
                    validation_result['message'],
                    'Verifica que todos los campos requeridos estén completados correctamente.'
                )

            # Obtener tipo de permiso
            _logger.info("📝 Obteniendo tipo de permiso...")
            leave_type = self._get_leave_type(post.get('holiday_status_id'))
            if not leave_type:
                return self._return_error_response(
                    'INVALID_LEAVE_TYPE',
                    'Tipo de permiso no válido',
                    'Selecciona un tipo de permiso válido de la lista.'
                )
            
            _logger.info(f"✅ Tipo de permiso encontrado: {leave_type.name}")
            _logger.info(f"   - ID: {leave_type.id}")
            _logger.info(f"   - Requiere asignación: {leave_type.requires_allocation}")
            _logger.info(f"   - Requiere documento: {leave_type.support_document}")
            _logger.info(f"   - Unidad: {leave_type.request_unit}")

            # Verificar solapamiento ANTES de crear
            overlap_result = self._check_date_overlap_detailed(post, employee)
            if overlap_result['has_overlap']:
                _logger.error("❌ SOLAPAMIENTO DETECTADO")
                _logger.error(f"   - Solicitudes en conflicto: {len(overlap_result['overlapping_leaves'])}")
                for leave in overlap_result['overlapping_leaves']:
                    _logger.error(f"   ⚠️  {leave['type']}: {leave['date_from']} - {leave['date_to']} ({leave['state']})")
                
                return self._return_error_response(
                    'DATE_OVERLAP',
                    f'Ya tienes {len(overlap_result["overlapping_leaves"])} solicitud(es) de permiso en este período',
                    'Selecciona fechas diferentes o cancela las solicitudes existentes.',
                    overlap_result['overlapping_leaves']
                )

            _logger.info("✅ No se detectaron conflictos de fechas")

            # Validar disponibilidad de días/horas ANTES de crear
            _logger.info("⏱️ Verificando disponibilidad de horas/días...")
            availability_result = self._validate_leave_availability(employee, leave_type, post)
            if not availability_result['valid']:
                _logger.error("❌ DISPONIBILIDAD INSUFICIENTE")
                _logger.error(f"   - Mensaje: {availability_result['message']}")
                
                return self._return_error_response(
                    'INSUFFICIENT_BALANCE',
                    availability_result['message'],
                    'Contacta a Recursos Humanos para verificar tu saldo de permisos.'
                )

            _logger.info("✅ Disponibilidad verificada correctamente")

            # Preparar valores para crear la solicitud
            _logger.info("⚙️ Preparando valores para la solicitud...")
            vals = self._prepare_leave_values(post, employee, leave_type)
            
            _logger.info("📎 Manejando archivos adjuntos...")
            attachment_ids = self._handle_attachments(post)
            if attachment_ids:
                _logger.info(f"✅ Archivos procesados: {len(attachment_ids)}")
            else:
                _logger.info("ℹ️ No se encontraron archivos adjuntos")

            # Crear la solicitud CON MANEJO DE ERRORES
            _logger.info("💾 Creando solicitud de permiso...")
            _logger.info(f"   - Valores finales: {vals}")
            
            try:
                leave = request.env['hr.leave'].sudo().create(vals)
                _logger.info(f"✅ Solicitud creada exitosamente")
                _logger.info(f"   - ID de solicitud: {leave.id}")
                _logger.info(f"   - Nombre: {leave.display_name}")
                _logger.info(f"   - Estado: {leave.state}")
                _logger.info(f"   - Duración: {leave.number_of_days} días")
                
            except ValidationError as create_error:
                _logger.error("❌ ERROR AL CREAR SOLICITUD (ValidationError)")
                _logger.error(f"   - Error: {str(create_error)}")
                
                # Convertir errores técnicos a mensajes amigables
                friendly_message = self._get_friendly_error_message(str(create_error))
                return self._return_error_response(
                    'VALIDATION_ERROR',
                    friendly_message,
                    'Verifica los datos ingresados y vuelve a intentar.'
                )
                
            except Exception as create_error:
                _logger.error("❌ ERROR AL CREAR SOLICITUD (Exception)")
                _logger.error(f"   - Error: {str(create_error)}")
                _logger.error(f"   - Tipo: {type(create_error).__name__}")
                
                friendly_message = self._get_friendly_error_message(str(create_error))
                return self._return_error_response(
                    'INTERNAL_ERROR',
                    'Error interno del sistema',
                    'Por favor intenta nuevamente. Si el problema persiste, contacta al administrador.',
                    str(create_error)
                )

            # Asociar adjuntos a la solicitud creada
            if attachment_ids:
                _logger.info("🔗 Asociando archivos adjuntos...")
                request.env['ir.attachment'].sudo().browse(attachment_ids).write({
                    'res_id': leave.id
                })
                _logger.info(f"✅ {len(attachment_ids)} archivos asociados a la solicitud {leave.id}")

            # Enviar correo de notificación usando plantillas XML
            _logger.info("📧 Enviando notificación por correo...")
            self._send_notification_email(leave, employee, leave_type)

            _logger.info("=" * 60)
            _logger.info("🎉 SOLICITUD PROCESADA EXITOSAMENTE")
            _logger.info("=" * 60)
            _logger.info(f"   - ID final: {leave.id}")
            _logger.info(f"   - Empleado: {employee.name}")
            _logger.info(f"   - Tipo: {leave_type.name}")
            _logger.info(f"   - Fechas: {leave.request_date_from} a {leave.request_date_to}")
            
            # Respuesta JSON exitosa
            return self._return_success_response(
                'Solicitud de permiso enviada correctamente',
                leave.id,
                f'/web#id={leave.id}&model=hr.leave&view_type=form'
            )

        except ValidationError as e:
            _logger.error("=" * 60)
            _logger.error("💥 ERROR DE VALIDACIÓN")
            _logger.error("=" * 60)
            _logger.error(f"❌ Error de validación: {str(e)}")
            _logger.error(f"   - Tipo: ValidationError")
            _logger.error(f"   - Empleado: {employee.name if 'employee' in locals() else 'N/A'}")
            return self._return_error_response(
                'VALIDATION_ERROR',
                str(e),
                'Verifica los datos ingresados y vuelve a intentar.'
            )
            
        except Exception as e:
            _logger.error("=" * 60)
            _logger.error("💥 ERROR INTERNO")
            _logger.error("=" * 60)
            _logger.error(f"❌ Error interno: {str(e)}", exc_info=True)
            _logger.error(f"   - Tipo: {type(e).__name__}")
            _logger.error(f"   - Empleado: {employee.name if 'employee' in locals() else 'N/A'}")
            _logger.error(f"   - Datos POST: {dict(post)}")
            return self._return_error_response(
                'INTERNAL_ERROR',
                'Error interno del sistema',
                'Por favor intenta nuevamente. Si el problema persiste, contacta al administrador.',
                str(e)
            )

    def _validate_form_data(self, post):
        """Validar datos del formulario"""
        
        _logger.info("🔍 Validando campos requeridos...")
        
        required_fields = {
            'holiday_status_id': 'Tipo de permiso',
            'request_date_from': 'Fecha de inicio',
            'private_name': 'Descripción'
        }
        
        missing_fields = []
        for field, name in required_fields.items():
            if not post.get(field):
                missing_fields.append(name)
                _logger.error(f"❌ Campo requerido faltante: {field}")
            else:
                _logger.info(f"✅ Campo {field}: {post.get(field)}")
        
        if missing_fields:
            error_msg = f'Campos requeridos faltantes: {", ".join(missing_fields)}'
            _logger.error(f"❌ Validación fallida: {error_msg}")
            return {
                'valid': False,
                'message': error_msg
            }
        
        # Validar descripción no esté vacía
        if not post.get('private_name', '').strip():
            return {
                'valid': False,
                'message': 'La descripción no puede estar vacía'
            }
        
        return {'valid': True}

    def _get_leave_type(self, leave_type_id):
        """Obtener tipo de permiso"""
        
        try:
            leave_type_id = int(leave_type_id)
            leave_type = request.env['hr.leave.type'].browse(leave_type_id)
            if leave_type.exists():
                return leave_type
        except (ValueError, TypeError):
            pass
        
        return False

    def _check_date_overlap_detailed(self, post, employee):
        """Verificar solapamiento con logs detallados"""
        
        _logger.info("🔍 === VERIFICACIÓN DETALLADA DE SOLAPAMIENTO ===")
        
        try:
            date_from = post.get('request_date_from')
            date_to = post.get('request_date_to', date_from)
            
            _logger.info(f"📅 Fechas a verificar:")
            _logger.info(f"   - Desde: {date_from}")
            _logger.info(f"   - Hasta: {date_to}")
            _logger.info(f"   - Empleado: {employee.name} (ID: {employee.id})")

            # Buscar solicitudes que se solapan
            domain = [
                ('employee_id', '=', employee.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '<=', date_to),
                ('request_date_to', '>=', date_from),
            ]
            
            _logger.info(f"🔎 Buscando con dominio: {domain}")
            
            overlapping_leaves = request.env['hr.leave'].search(domain)
            
            _logger.info(f"📊 Resultado de búsqueda: {len(overlapping_leaves)} solicitud(es) encontrada(s)")

            if overlapping_leaves:
                _logger.warning("⚠️ SOLAPAMIENTO DETECTADO:")
                overlap_info = []
                
                for i, leave in enumerate(overlapping_leaves, 1):
                    _logger.warning(f"   {i}. ID: {leave.id}")
                    _logger.warning(f"      - Tipo: {leave.holiday_status_id.name}")
                    _logger.warning(f"      - Fechas: {leave.request_date_from} - {leave.request_date_to}")
                    _logger.warning(f"      - Estado: {leave.state}")
                    _logger.warning(f"      - Nombre: {leave.display_name}")
                    
                    overlap_info.append({
                        'id': leave.id,
                        'name': leave.display_name,
                        'date_from': leave.request_date_from.strftime('%d/%m/%Y'),
                        'date_to': leave.request_date_to.strftime('%d/%m/%Y'),
                        'state': leave.state,
                        'type': leave.holiday_status_id.name
                    })
                
                return {
                    'has_overlap': True,
                    'overlapping_leaves': overlap_info,
                    'message': f'Ya tiene {len(overlapping_leaves)} solicitud(es) en este período'
                }
            else:
                _logger.info("✅ No se encontraron solapamientos")
                return {'has_overlap': False}

        except Exception as e:
            _logger.error(f"💥 Error verificando solapamiento: {str(e)}", exc_info=True)
            return {'has_overlap': False, 'error': str(e)}

    def _validate_leave_availability(self, employee, leave_type, post):
        """Validar disponibilidad de días/horas para el empleado - CORREGIDO"""
        
        _logger.info("⏱️ === VALIDANDO DISPONIBILIDAD ===")
        _logger.info(f"   - Empleado: {employee.name} (ID: {employee.id})")
        _logger.info(f"   - Tipo: {leave_type.name} (ID: {leave_type.id})")
        _logger.info(f"   - Requiere asignación: {leave_type.requires_allocation}")
        
        try:
            # CORRECCIÓN: Verificar correctamente si no requiere asignación
            if leave_type.requires_allocation == 'no':  # ← CORREGIDO AQUÍ
                _logger.info(f"✅ Tipo {leave_type.name} no requiere asignación - VÁLIDO")
                return {'valid': True}
            
            _logger.info(f"🔍 Tipo {leave_type.name} requiere asignación, verificando...")
            
            # Calcular días solicitados
            date_from = post.get('request_date_from')
            date_to = post.get('request_date_to', date_from)
            
            _logger.info(f"📅 Período solicitado: {date_from} - {date_to}")
            
            # Crear un leave temporal para calcular duración
            temp_vals = {
                'employee_id': employee.id,
                'holiday_status_id': leave_type.id,
                'request_date_from': date_from,
                'request_date_to': date_to,
            }
            
            # Configurar tipo de unidad
            if post.get('request_unit_half') == 'true':
                temp_vals['request_unit_half'] = True
                temp_vals['request_date_from_period'] = post.get('request_date_from_period', 'am')
                _logger.info(f"⏰ Modo: Medio día ({temp_vals['request_date_from_period']})")
                
            elif post.get('request_unit_hours') == 'true':
                temp_vals['request_unit_hours'] = True
                hour_from = post.get('request_hour_from', '8:00')
                hour_to = post.get('request_hour_to', '17:00')
                
                _logger.info(f"⏰ Modo: Horas específicas ({hour_from} - {hour_to})")
                
                if ':' in str(hour_from):
                    h, m = str(hour_from).split(':')
                    temp_vals['request_hour_from'] = float(h) + float(m)/60
                else:
                    temp_vals['request_hour_from'] = float(hour_from)
                    
                if ':' in str(hour_to):
                    h, m = str(hour_to).split(':')
                    temp_vals['request_hour_to'] = float(h) + float(m)/60
                else:
                    temp_vals['request_hour_to'] = float(hour_to)
            else:
                _logger.info("⏰ Modo: Día completo")
            
            # Crear leave temporal sin guardarlo para calcular duración
            _logger.info("🧮 Calculando duración de la solicitud...")
            temp_leave = request.env['hr.leave'].new(temp_vals)
            requested_days = temp_leave.number_of_days
            
            _logger.info(f"📊 Días/horas solicitados: {requested_days}")
            
            # Buscar asignación disponible
            _logger.info("🔍 Buscando asignaciones disponibles...")
            allocation = request.env['hr.leave.allocation'].search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', date_from),
                ('date_to', '>=', date_to)
            ], limit=1)
            
            if not allocation:
                _logger.error(f"❌ No se encontró asignación válida para {leave_type.name}")
                return {
                    'valid': False,
                    'message': f'No tienes una asignación válida para {leave_type.name}. Contacta a Recursos Humanos para solicitar una asignación.'
                }
            
            _logger.info(f"✅ Asignación encontrada: {allocation.display_name}")
            _logger.info(f"   - Días asignados: {allocation.number_of_days}")
            _logger.info(f"   - Días tomados: {allocation.leaves_taken}")
            
            # Verificar días disponibles
            available_days = allocation.number_of_days - allocation.leaves_taken
            _logger.info(f"📊 Días disponibles: {available_days}")
            
            if requested_days > available_days:
                _logger.error(f"❌ Días insuficientes: solicita {requested_days}, disponible {available_days}")
                return {
                    'valid': False,
                    'message': f'Saldo insuficiente. Solicitas: {requested_days} días, Disponible: {available_days} días para {leave_type.name}.'
                }
            
            _logger.info("✅ Validación de disponibilidad exitosa")
            return {
                'valid': True,
                'requested_days': requested_days,
                'available_days': available_days,
                'allocation_id': allocation.id
            }
            
        except Exception as e:
            _logger.error(f"💥 Error validando disponibilidad: {str(e)}", exc_info=True)
            return {
                'valid': False,
                'message': f'Error al verificar disponibilidad. Contacta al administrador del sistema.'
            }

    def _prepare_leave_values(self, post, employee, leave_type):
        """Preparar valores para crear la solicitud de permiso"""
        
        _logger.info("⚙️ === PREPARANDO VALORES PARA SOLICITUD ===")
        
        # Valores base
        vals = {
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': post.get('request_date_from'),
            'request_date_to': post.get('request_date_to', post.get('request_date_from')),
            'private_name': post.get('private_name').strip(),
            'notes': post.get('notes', '').strip(),
        }
        
        _logger.info(f"📋 Valores base preparados:")
        for key, value in vals.items():
            _logger.info(f"   - {key}: {value}")
        
        _logger.info(f"🔧 Configurando tipo de unidad:")
        _logger.info(f"   - request_unit_half: '{post.get('request_unit_half')}'")
        _logger.info(f"   - request_unit_hours: '{post.get('request_unit_hours')}'")

        # Configurar según el tipo de unidad
        if post.get('request_unit_half') == 'true':
            vals['request_unit_half'] = True
            vals['request_date_from_period'] = post.get('request_date_from_period', 'am')
            vals['request_date_to'] = vals['request_date_from']
            _logger.info(f"✅ Configurado como MEDIO DÍA:")
            _logger.info(f"   - Período: {vals['request_date_from_period']}")
            _logger.info(f"   - Fecha unificada: {vals['request_date_to']}")
            
        elif post.get('request_unit_hours') == 'true':
            vals['request_unit_hours'] = True
            
            # Convertir horas "08:00" a float 8.0
            hour_from = post.get('request_hour_from', '8:00')
            hour_to = post.get('request_hour_to', '17:00')
            
            _logger.info(f"⏰ Procesando horas personalizadas:")
            _logger.info(f"   - Hora desde (raw): '{hour_from}'")
            _logger.info(f"   - Hora hasta (raw): '{hour_to}'")
            
            try:
                # Convertir hora de inicio
                if ':' in str(hour_from):
                    h, m = str(hour_from).split(':')
                    vals['request_hour_from'] = float(h) + float(m)/60
                    _logger.info(f"   - Hora desde convertida: {h}:{m} → {vals['request_hour_from']}")
                else:
                    vals['request_hour_from'] = float(hour_from)
                    _logger.info(f"   - Hora desde (directa): {vals['request_hour_from']}")
                    
                # Convertir hora de fin
                if ':' in str(hour_to):
                    h, m = str(hour_to).split(':')
                    vals['request_hour_to'] = float(h) + float(m)/60
                    _logger.info(f"   - Hora hasta convertida: {h}:{m} → {vals['request_hour_to']}")
                else:
                    vals['request_hour_to'] = float(hour_to)
                    _logger.info(f"   - Hora hasta (directa): {vals['request_hour_to']}")
                    
            except (ValueError, TypeError) as e:
                _logger.error(f"❌ Error convirtiendo horas: {e}")
                _logger.error(f"   - hour_from: {hour_from} (tipo: {type(hour_from)})")
                _logger.error(f"   - hour_to: {hour_to} (tipo: {type(hour_to)})")
                vals['request_hour_from'] = 8.0
                vals['request_hour_to'] = 17.0
                _logger.warning(f"⚠️ Usando valores por defecto: 8.0 - 17.0")
                
            vals['request_date_to'] = vals['request_date_from']
            _logger.info(f"✅ Configurado como HORAS ESPECÍFICAS:")
            _logger.info(f"   - De: {vals['request_hour_from']} a {vals['request_hour_to']}")
            _logger.info(f"   - Fecha unificada: {vals['request_date_to']}")
            
        else:
            # Día completo
            vals['request_unit_half'] = False
            vals['request_unit_hours'] = False
            _logger.info("✅ Configurado como DÍA COMPLETO")

        # Validar fechas
        if not vals['request_date_from']:
            _logger.error("❌ Fecha de inicio requerida")
            raise ValidationError("La fecha de inicio es requerida")
            
        if not vals['request_date_to']:
            vals['request_date_to'] = vals['request_date_from']
            _logger.info(f"ℹ️ Fecha fin ajustada a fecha inicio: {vals['request_date_to']}")

        _logger.info("✅ === VALORES FINALES PREPARADOS ===")
        for key, value in vals.items():
            _logger.info(f"   🔹 {key}: {value}")
            
        return vals

    def _handle_attachments(self, post):
        """Manejar archivos adjuntos"""
        attachment_ids = []
        
        _logger.info("📎 === PROCESANDO ARCHIVOS ADJUNTOS ===")
        
        try:
            # Buscar archivos en el post
            file_fields = [key for key in post.keys() if key.startswith('attachment_') or key == 'file_input']
            _logger.info(f"🔍 Campos de archivo encontrados: {file_fields}")
            
            file_count = 0
            for key in post:
                file_obj = post[key]
                
                # Verificar si es un archivo
                if hasattr(file_obj, 'read') and hasattr(file_obj, 'filename'):
                    if file_obj.filename:  # Asegurar que tenga nombre
                        file_count += 1
                        _logger.info(f"📁 Procesando archivo #{file_count}: {key}")
                        _logger.info(f"   - Nombre: {file_obj.filename}")
                        _logger.info(f"   - Tipo MIME: {getattr(file_obj, 'content_type', 'unknown')}")
                        
                        try:
                            file_content = file_obj.read()
                            file_size = len(file_content)
                            _logger.info(f"   - Tamaño: {file_size} bytes ({file_size/1024:.2f} KB)")
                            
                            if file_size == 0:
                                _logger.warning(f"⚠️ Archivo vacío, omitiendo: {file_obj.filename}")
                                continue
                            
                            if file_size > 5 * 1024 * 1024:  # 5MB
                                _logger.warning(f"⚠️ Archivo muy grande (>{file_size/1024/1024:.2f}MB): {file_obj.filename}")
                            
                            # Crear adjunto
                            _logger.info(f"💾 Creando adjunto en base de datos...")
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': file_obj.filename,
                                'datas': base64.b64encode(file_content),
                                'res_model': 'hr.leave',
                                'res_id': 0,  # Se actualizará después de crear el leave
                                'type': 'binary',
                                'mimetype': getattr(file_obj, 'content_type', 'application/octet-stream')
                            })
                            
                            attachment_ids.append(attachment.id)
                            _logger.info(f"✅ Archivo guardado exitosamente:")
                            _logger.info(f"   - Attachment ID: {attachment.id}")
                            _logger.info(f"   - Nombre: {attachment.name}")
                            _logger.info(f"   - Tamaño: {len(attachment.datas)} caracteres (base64)")
                            
                        except Exception as file_error:
                            _logger.error(f"❌ Error procesando archivo {file_obj.filename}:")
                            _logger.error(f"   - Error: {str(file_error)}")
                            _logger.error(f"   - Tipo: {type(file_error).__name__}")
                            continue
                    else:
                        _logger.info(f"ℹ️ Campo {key} sin nombre de archivo, omitiendo")
                else:
                    # No es un archivo, es un campo normal
                    if not isinstance(file_obj, str) or len(str(file_obj)) > 50:
                        continue  # Skip para no llenar logs con datos largos
                    
        except Exception as e:
            _logger.error(f"💥 Error general procesando adjuntos: {str(e)}", exc_info=True)
            
        _logger.info(f"📊 RESUMEN DE ARCHIVOS:")
        _logger.info(f"   - Total procesados: {len(attachment_ids)}")
        _logger.info(f"   - IDs generados: {attachment_ids}")
        
        return attachment_ids

    def _send_notification_email(self, leave, employee, leave_type):
        """Enviar correo de notificación usando plantillas XML"""
        
        _logger.info("📧 === ENVIANDO CORREOS CON PLANTILLAS XML ===")
        
        try:
            # Verificar que las plantillas existan antes de enviar
            self._verify_email_templates()
            
            # 1. Enviar correo a administradores/supervisores
            admin_sent = self._send_admin_notification(leave, employee, leave_type)
            
            # 2. Enviar confirmación al empleado
            employee_sent = self._send_employee_confirmation(leave, employee, leave_type)
            
            if admin_sent or employee_sent:
                _logger.info("✅ Al menos un correo enviado exitosamente")
                return True
            else:
                _logger.warning("⚠️ No se pudo enviar ningún correo")
                return False
            
        except Exception as e:
            _logger.error(f"💥 Error general enviando correos: {str(e)}", exc_info=True)
            return False

    def _verify_email_templates(self):
        """Verificar que las plantillas de correo estén disponibles"""
        
        _logger.info("🔍 === VERIFICANDO PLANTILLAS DE CORREO ===")
        
        try:
            # Verificar plantilla para administradores
            admin_template = request.env.ref('sat.email_template_leave_request', raise_if_not_found=False)
            if admin_template:
                _logger.info(f"✅ Plantilla admin encontrada: {admin_template.name}")
            else:
                _logger.error("❌ Plantilla 'sat.email_template_leave_request' no encontrada")
            
            # Verificar plantilla para empleados
            employee_template = request.env.ref('sat.email_template_leave_request_employee', raise_if_not_found=False)
            if employee_template:
                _logger.info(f"✅ Plantilla empleado encontrada: {employee_template.name}")
            else:
                _logger.error("❌ Plantilla 'sat.email_template_leave_request_employee' no encontrada")
            
            return admin_template and employee_template
            
        except Exception as e:
            _logger.error(f"💥 Error verificando plantillas: {str(e)}")
            return False

    def _send_admin_notification(self, leave, employee, leave_type):
        """Enviar notificación a administradores usando plantilla XML"""
        
        _logger.info("📧 Enviando notificación a administradores...")
        
        try:
            # Buscar plantilla para administradores
            template = request.env.ref('sat.email_template_leave_request', raise_if_not_found=False)
            
            if not template:
                _logger.error("❌ Plantilla 'sat.email_template_leave_request' no encontrada")
                return False
            
            _logger.info(f"✅ Plantilla admin encontrada: {template.name} (ID: {template.id})")
            
            # Verificar/configurar servidor de correo
            mail_server = self._ensure_mail_server(template)
            
            # Preparar contexto para envío
            email_context = {
                'default_mail_server_id': mail_server.id if mail_server else False,
                'mail_server_id': mail_server.id if mail_server else False,
                'force_send': True,
                'mail_notify_author': False,
                'mail_create_nosubscribe': True,
                'mail_auto_delete': True,
            }
            
            _logger.info(f"📤 Enviando correo administrativo:")
            _logger.info(f"   - Leave ID: {leave.id}")
            _logger.info(f"   - Template: {template.name}")
            _logger.info(f"   - Servidor: {mail_server.name if mail_server else 'Default'}")
            
            # Enviar correo
            mail_id = template.with_context(**email_context).send_mail(
                leave.id,
                force_send=True,
                raise_exception=False  # No romper si falla
            )
            
            if mail_id:
                mail_record = request.env['mail.mail'].browse(mail_id)
                _logger.info(f"✅ Correo administrativo enviado:")
                _logger.info(f"   - Mail ID: {mail_id}")
                _logger.info(f"   - Estado: {mail_record.state}")
                _logger.info(f"   - Para: {mail_record.email_to}")
                _logger.info(f"   - Desde: {mail_record.email_from}")
                return True
            else:
                _logger.error("❌ No se generó mail_id para correo administrativo")
                return False
                
        except Exception as e:
            _logger.error(f"💥 Error enviando correo administrativo: {str(e)}", exc_info=True)
            return False

    def _send_employee_confirmation(self, leave, employee, leave_type):
        """Enviar confirmación al empleado usando plantilla XML"""
        
        _logger.info("📧 Enviando confirmación al empleado...")
        
        try:
            # Verificar que el empleado tenga email
            employee_email = employee.work_email or (employee.user_id.email if employee.user_id else None)
            if not employee_email:
                _logger.warning(f"⚠️ Empleado {employee.name} no tiene email configurado")
                return False
            
            _logger.info(f"📬 Email del empleado: {employee_email}")
            
            # Buscar plantilla para empleados
            template = request.env.ref('sat.email_template_leave_request_employee', raise_if_not_found=False)
            
            if not template:
                _logger.error("❌ Plantilla 'sat.email_template_leave_request_employee' no encontrada")
                return False
            
            _logger.info(f"✅ Plantilla empleado encontrada: {template.name} (ID: {template.id})")
            
            # Verificar/configurar servidor de correo
            mail_server = self._ensure_mail_server(template)
            
            # Preparar contexto para envío
            email_context = {
                'default_mail_server_id': mail_server.id if mail_server else False,
                'mail_server_id': mail_server.id if mail_server else False,
                'force_send': True,
                'mail_notify_author': False,
                'mail_create_nosubscribe': True,
                'mail_auto_delete': True,
            }
            
            _logger.info(f"📤 Enviando confirmación al empleado:")
            _logger.info(f"   - Leave ID: {leave.id}")
            _logger.info(f"   - Template: {template.name}")
            _logger.info(f"   - Para: {employee_email}")
            _logger.info(f"   - Servidor: {mail_server.name if mail_server else 'Default'}")
            
            # Enviar correo
            mail_id = template.with_context(**email_context).send_mail(
                leave.id,
                force_send=True,
                raise_exception=False  # No romper si falla
            )
            
            if mail_id:
                mail_record = request.env['mail.mail'].browse(mail_id)
                _logger.info(f"✅ Confirmación enviada al empleado:")
                _logger.info(f"   - Mail ID: {mail_id}")
                _logger.info(f"   - Estado: {mail_record.state}")
                _logger.info(f"   - Para: {mail_record.email_to}")
                _logger.info(f"   - Desde: {mail_record.email_from}")
                return True
            else:
                _logger.error("❌ No se generó mail_id para confirmación de empleado")
                return False
                
        except Exception as e:
            _logger.error(f"💥 Error enviando confirmación al empleado: {str(e)}", exc_info=True)
            return False

    def _ensure_mail_server(self, template):
        """Asegurar que la plantilla tenga servidor de correo configurado"""
        
        _logger.info("🔧 === CONFIGURANDO SERVIDOR DE CORREO ===")
        
        try:
            # Si la plantilla ya tiene servidor, usarlo
            if template.mail_server_id:
                _logger.info(f"✅ Plantilla ya tiene servidor: {template.mail_server_id.name}")
                return template.mail_server_id
            
            # Buscar servidor específico para soporte@andescopiers.com.pe
            mail_server = request.env['ir.mail_server'].search([
                ('smtp_user', '=', 'soporte@andescopiers.com.pe'),
                ('active', '=', True)
            ], limit=1)
            
            if not mail_server:
                _logger.warning("⚠️ No se encontró servidor específico, buscando cualquier servidor activo...")
                mail_server = request.env['ir.mail_server'].search([
                    ('active', '=', True)
                ], limit=1, order='sequence asc')
            
            if mail_server:
                _logger.info(f"🔧 Asignando servidor a plantilla:")
                _logger.info(f"   - Servidor: {mail_server.name}")
                _logger.info(f"   - Host: {mail_server.smtp_host}")
                _logger.info(f"   - Usuario: {mail_server.smtp_user}")
                
                # Asignar servidor a la plantilla
                template.sudo().write({'mail_server_id': mail_server.id})
                return mail_server
            else:
                _logger.error("❌ No se encontraron servidores de correo activos")
                return False
                
        except Exception as e:
            _logger.error(f"💥 Error configurando servidor: {str(e)}")
            return False

    def _get_friendly_error_message(self, technical_error):
        """Convertir errores técnicos a mensajes amigables para el usuario"""
        
        _logger.info(f"🔄 Convirtiendo error técnico: {technical_error}")
        
        error_lower = str(technical_error).lower()
        
        # Mapeo de errores comunes a mensajes amigables
        if 'suficientes horas' in error_lower or 'sufficient hours' in error_lower:
            return "No tienes suficientes horas disponibles para este tipo de permiso. Contacta a Recursos Humanos para verificar tu saldo."
            
        elif 'asignación' in error_lower or 'allocation' in error_lower:
            return "No tienes una asignación válida para este tipo de permiso. Contacta a Recursos Humanos."
            
        elif 'período' in error_lower or 'period' in error_lower:
            return "Las fechas seleccionadas no son válidas para este tipo de permiso."
            
        elif 'solapamiento' in error_lower or 'overlap' in error_lower:
            return "Ya tienes una solicitud de permiso en el período seleccionado. Por favor selecciona fechas diferentes."
            
        elif 'estado' in error_lower or 'state' in error_lower:
            return "No se puede crear la solicitud en el estado actual. Contacta a tu supervisor."
            
        elif 'empleado' in error_lower or 'employee' in error_lower:
            return "Error con los datos del empleado. Contacta al administrador del sistema."
            
        elif 'fecha' in error_lower or 'date' in error_lower:
            return "Las fechas ingresadas no son válidas. Verifica que la fecha de inicio sea anterior o igual a la fecha de fin."
            
        elif 'documento' in error_lower or 'document' in error_lower:
            return "Este tipo de permiso requiere documentación de soporte. Por favor adjunta los documentos necesarios."
            
        elif 'balance' in error_lower or 'saldo' in error_lower:
            return "No tienes suficiente saldo disponible para este tipo de permiso."
            
        elif 'aprobación' in error_lower or 'approval' in error_lower:
            return "Error en el proceso de aprobación. Contacta a tu supervisor."
            
        else:
            # Error genérico pero amigable
            return "No se pudo procesar tu solicitud en este momento. Por favor verifica los datos ingresados o contacta a Recursos Humanos para asistencia."

    def _return_error_response(self, error_code, message, suggestion=None, details=None):
        """Retornar respuesta de error estructurada"""
        
        _logger.error("❌ === RETORNANDO RESPUESTA DE ERROR ===")
        _logger.error(f"   - Código: {error_code}")
        _logger.error(f"   - Mensaje: {message}")
        _logger.error(f"   - Timestamp: {datetime.now()}")
        _logger.error(f"   - Usuario: {request.env.user.name if request.env.user else 'N/A'}")
        
        response_data = {
            'success': False,
            'error': message,
            'error_code': error_code,
            'suggestion': suggestion or 'Verifica los datos ingresados o contacta a Recursos Humanos.',
            'timestamp': datetime.now().isoformat()
        }
        
        if details:
            response_data['details'] = details
        
        _logger.error(f"   - Respuesta JSON: {response_data}")
        
        return request.make_response(
            json.dumps(response_data),
            headers={'Content-Type': 'application/json'},
            status=400
        )

    def _return_success_response(self, message, leave_id, redirect_url):
        """Retornar respuesta de éxito estructurada"""
        
        response_data = {
            'success': True,
            'message': message,
            'leave_id': leave_id,
            'redirect_url': redirect_url,
            'timestamp': datetime.now().isoformat()
        }
        
        return request.make_response(
            json.dumps(response_data),
            headers={'Content-Type': 'application/json'}
        )

    @http.route('/leave/request/get_leave_types', type='json', auth='user')
    def get_available_leave_types(self):
        """API para obtener tipos de permiso disponibles via AJAX"""
        
        _logger.info("🔌 === API: OBTENER TIPOS DE PERMISO ===")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("❌ No se encontró empleado para API")
                return {'error': 'No employee found'}

            _logger.info(f"👤 Empleado: {employee.name} (ID: {employee.id})")

            leave_types = request.env['hr.leave.type'].search([
                ('company_id', 'in', [employee.company_id.id, False]),
                ('active', '=', True)
            ])

            _logger.info(f"📝 Tipos encontrados: {len(leave_types)}")

            result = {
                'leave_types': [{
                    'id': lt.id,
                    'name': lt.name,
                    'request_unit': lt.request_unit,
                    'support_document': lt.support_document,
                    'color': lt.color,
                    'validation_type': lt.leave_validation_type,
                    'requires_allocation': lt.requires_allocation,
                } for lt in leave_types]
            }
            
            _logger.info(f"✅ Retornando {len(leave_types)} tipos via API")
            return result

        except Exception as e:
            _logger.error(f"💥 Error en API tipos de permiso: {str(e)}", exc_info=True)
            return {'error': str(e)}

    @http.route('/leave/request/validate_dates', type='json', auth='user')
    def validate_leave_dates(self, date_from, date_to=None, holiday_status_id=None):
        """Validar fechas de solicitud"""
        
        _logger.info("🔍 === API: VALIDAR FECHAS ===")
        _logger.info(f"📅 Fechas recibidas: {date_from} - {date_to}")
        _logger.info(f"📝 Tipo de permiso ID: {holiday_status_id}")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("❌ No se encontró empleado para validación")
                return {'error': 'No employee found'}

            _logger.info(f"👤 Validando para empleado: {employee.name}")

            # Validaciones básicas
            if not date_from:
                _logger.error("❌ Fecha de inicio requerida")
                return {'valid': False, 'error': 'Fecha de inicio requerida'}

            # Validar que la fecha no sea pasada
            from datetime import date
            today = date.today()
            request_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            
            if request_date < today:
                _logger.warning(f"⚠️ Fecha en el pasado: {request_date} < {today}")
                return {
                    'valid': False, 
                    'error': 'No se pueden solicitar permisos para fechas pasadas'
                }

            _logger.info("✅ Fechas validadas correctamente")
            return {'valid': True}
            
        except Exception as e:
            _logger.error(f"💥 Error validando fechas: {str(e)}", exc_info=True)
            return {'error': str(e)}

    @http.route('/leave/request/check_overlap', type='json', auth='user')
    def check_leave_overlap(self, date_from, date_to=None):
        """Verificar si hay solapamiento con solicitudes existentes"""
        
        _logger.info("🔍 === API: VERIFICAR SOLAPAMIENTO ===")
        _logger.info(f"📅 Verificando overlap para: {date_from} - {date_to}")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("❌ No se encontró empleado")
                return {'error': 'No employee found'}

            if not date_to:
                date_to = date_from
                _logger.info(f"ℹ️ Fecha fin ajustada a: {date_to}")

            _logger.info(f"👤 Verificando para empleado: {employee.name} (ID: {employee.id})")

            # Buscar solicitudes que se solapan
            domain = [
                ('employee_id', '=', employee.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '<=', date_to),
                ('request_date_to', '>=', date_from),
            ]
            
            _logger.info(f"🔎 Dominio de búsqueda: {domain}")
            
            overlapping_leaves = request.env['hr.leave'].search(domain)
            
            _logger.info(f"📊 Solicitudes encontradas: {len(overlapping_leaves)}")

            if overlapping_leaves:
                _logger.warning("⚠️ SOLAPAMIENTO DETECTADO EN API:")
                overlap_info = []
                
                for i, leave in enumerate(overlapping_leaves, 1):
                    _logger.warning(f"   {i}. {leave.holiday_status_id.name}: {leave.request_date_from} - {leave.request_date_to} ({leave.state})")
                    
                    overlap_info.append({
                        'id': leave.id,
                        'name': leave.display_name,
                        'date_from': leave.request_date_from.strftime('%d/%m/%Y'),
                        'date_to': leave.request_date_to.strftime('%d/%m/%Y'),
                        'state': leave.state,
                'type': leave.holiday_status_id.name
                    })
                
                result = {
                    'has_overlap': True,
                    'overlapping_leaves': overlap_info,
                    'message': f'Ya tiene {len(overlapping_leaves)} solicitud(es) en este período'
                }
                
                _logger.warning(f"⚠️ Retornando solapamiento: {len(overlap_info)} conflictos")
                return result
            
            _logger.info("✅ No se encontraron solapamientos")
            return {'has_overlap': False}

        except Exception as e:
            _logger.error(f"💥 Error verificando solapamiento: {str(e)}", exc_info=True)
            return {'error': str(e)}
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
            employee = request.env.user.employee_id
            if not employee:
                _logger.error(f"❌ Usuario {request.env.user.name} no tiene empleado asociado")
                return request.render('website.404')
            
            _logger.info(f"✅ Empleado encontrado: {employee.name}")
            
            # Obtener tipos de permiso disponibles
            leave_types = request.env['hr.leave.type'].search([
                ('company_id', 'in', [employee.company_id.id, False]),
                ('active', '=', True)
            ])
            
            _logger.info(f"✅ Tipos de permiso encontrados: {len(leave_types)}")
            
            # Datos para el template
            values = {
                'employee': employee,
                'leave_types': leave_types,
                'today': fields.Date.today(),
                'user_tz': request.env.user.tz or 'UTC',
            }
            
            return request.render('sat.leave_request_template', values)
            
        except Exception as e:
            _logger.error("💥 ERROR AL CARGAR FORMULARIO", exc_info=True)
            return request.render('website.500')

    @http.route('/leave/request/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit_leave_request(self, **post):
        """Procesar la solicitud de permiso enviada"""
        
        _logger.info("=" * 60)
        _logger.info("🚀 INICIO PROCESAMIENTO SOLICITUD")
        _logger.info("=" * 60)
        
        try:
            # Verificar empleado
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("❌ No se encontró empleado asociado al usuario")
                return self._return_error_response(
                    'EMPLOYEE_NOT_FOUND',
                    'No se encontró empleado asociado al usuario',
                    'Por favor contacta al administrador del sistema para configurar tu perfil de empleado.'
                )

            _logger.info(f"✅ Empleado verificado: {employee.name}")

            # Validar datos requeridos
            validation_result = self._validate_form_data(post)
            if not validation_result['valid']:
                return self._return_error_response(
                    'VALIDATION_ERROR',
                    validation_result['message'],
                    'Verifica que todos los campos requeridos estén completados correctamente.'
                )

            # Obtener tipo de permiso
            leave_type = self._get_leave_type(post.get('holiday_status_id'))
            if not leave_type:
                return self._return_error_response(
                    'INVALID_LEAVE_TYPE',
                    'Tipo de permiso no válido',
                    'Selecciona un tipo de permiso válido de la lista.'
                )

            # Verificar solapamiento ANTES de crear
            overlap_result = self._check_date_overlap_detailed(post, employee)
            if overlap_result['has_overlap']:
                _logger.error("❌ SOLAPAMIENTO DETECTADO")
                return self._return_error_response(
                    'DATE_OVERLAP',
                    f'Ya tienes {len(overlap_result["overlapping_leaves"])} solicitud(es) de permiso en este período',
                    'Selecciona fechas diferentes o cancela las solicitudes existentes.',
                    overlap_result['overlapping_leaves']
                )

            # Validar disponibilidad de días/horas
            availability_result = self._validate_leave_availability(employee, leave_type, post)
            if not availability_result['valid']:
                _logger.error("❌ DISPONIBILIDAD INSUFICIENTE")
                return self._return_error_response(
                    'INSUFFICIENT_BALANCE',
                    availability_result['message'],
                    'Contacta a Recursos Humanos para verificar tu saldo de permisos.'
                )

            # Preparar valores para crear la solicitud
            vals = self._prepare_leave_values(post, employee, leave_type)
            
            # Manejar archivos adjuntos
            attachment_ids = self._handle_attachments(post)

            # Crear la solicitud
            leave = request.env['hr.leave'].sudo().create(vals)
            _logger.info(f"✅ Solicitud creada exitosamente: {leave.id}")

            # Asociar adjuntos a la solicitud creada
            if attachment_ids:
                request.env['ir.attachment'].sudo().browse(attachment_ids).write({
                    'res_id': leave.id
                })

            # Enviar correo de notificación
            self._send_notification_email(leave, employee, leave_type)

            _logger.info("🎉 SOLICITUD PROCESADA EXITOSAMENTE")
            
            # Respuesta JSON exitosa
            return self._return_success_response(
                'Solicitud de permiso enviada correctamente',
                leave.id,
                f'/web#id={leave.id}&model=hr.leave&view_type=form'
            )

        except ValidationError as e:
            _logger.error("💥 ERROR DE VALIDACIÓN", exc_info=True)
            return self._return_error_response(
                'VALIDATION_ERROR',
                str(e),
                'Verifica los datos ingresados y vuelve a intentar.'
            )
            
        except Exception as e:
            _logger.error("💥 ERROR INTERNO", exc_info=True)
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
        
        if missing_fields:
            return {
                'valid': False,
                'message': f'Campos requeridos faltantes: {", ".join(missing_fields)}'
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
        
        _logger.info("🔍 Verificando solapamiento de fechas...")
        
        try:
            date_from = post.get('request_date_from')
            date_to = post.get('request_date_to', date_from)

            # Buscar solicitudes que se solapan
            domain = [
                ('employee_id', '=', employee.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '<=', date_to),
                ('request_date_to', '>=', date_from),
            ]
            
            overlapping_leaves = request.env['hr.leave'].search(domain)

            if overlapping_leaves:
                _logger.warning("⚠️ SOLAPAMIENTO DETECTADO")
                overlap_info = []
                
                for leave in overlapping_leaves:
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
                    'overlapping_leaves': overlap_info
                }
            else:
                return {'has_overlap': False}

        except Exception as e:
            _logger.error(f"💥 Error verificando solapamiento: {str(e)}", exc_info=True)
            return {'has_overlap': False, 'error': str(e)}

    def _validate_leave_availability(self, employee, leave_type, post):
        """Validar disponibilidad de días/horas para el empleado"""
        
        _logger.info("⏱️ Validando disponibilidad...")
        
        try:
            # Si no requiere asignación, es válido
            if not leave_type.requires_allocation:
                _logger.info(f"✅ Tipo {leave_type.name} no requiere asignación")
                return {'valid': True}
            
            # Calcular días solicitados
            date_from = post.get('request_date_from')
            date_to = post.get('request_date_to', date_from)
            
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
                
            elif post.get('request_unit_hours') == 'true':
                temp_vals['request_unit_hours'] = True
                hour_from = post.get('request_hour_from', '8:00')
                hour_to = post.get('request_hour_to', '17:00')
                
                # Convertir horas
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
            
            # Crear leave temporal para calcular duración
            temp_leave = request.env['hr.leave'].new(temp_vals)
            requested_days = temp_leave.number_of_days
            
            # Buscar asignación disponible
            allocation = request.env['hr.leave.allocation'].search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', date_from),
                ('date_to', '>=', date_to)
            ], limit=1)
            
            if not allocation:
                return {
                    'valid': False,
                    'message': f'No tienes una asignación válida para {leave_type.name}. Contacta a Recursos Humanos para solicitar una asignación.'
                }
            
            # Verificar días disponibles
            available_days = allocation.number_of_days - allocation.leaves_taken
            
            if requested_days > available_days:
                return {
                    'valid': False,
                    'message': f'Saldo insuficiente. Solicitas: {requested_days} días, Disponible: {available_days} días para {leave_type.name}.'
                }
            
            return {'valid': True}
            
        except Exception as e:
            _logger.error(f"💥 Error validando disponibilidad: {str(e)}", exc_info=True)
            return {
                'valid': False,
                'message': 'Error al verificar disponibilidad. Contacta al administrador del sistema.'
            }

    def _prepare_leave_values(self, post, employee, leave_type):
        """Preparar valores para crear la solicitud de permiso"""
        
        # Valores base
        vals = {
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': post.get('request_date_from'),
            'request_date_to': post.get('request_date_to', post.get('request_date_from')),
            'private_name': post.get('private_name').strip(),
            'notes': post.get('notes', '').strip(),
        }
        
        # Configurar según el tipo de unidad
        if post.get('request_unit_half') == 'true':
            vals['request_unit_half'] = True
            vals['request_date_from_period'] = post.get('request_date_from_period', 'am')
            vals['request_date_to'] = vals['request_date_from']
            
        elif post.get('request_unit_hours') == 'true':
            vals['request_unit_hours'] = True
            
            hour_from = post.get('request_hour_from', '8:00')
            hour_to = post.get('request_hour_to', '17:00')
            
            try:
                # Convertir horas
                if ':' in str(hour_from):
                    h, m = str(hour_from).split(':')
                    vals['request_hour_from'] = float(h) + float(m)/60
                else:
                    vals['request_hour_from'] = float(hour_from)
                    
                if ':' in str(hour_to):
                    h, m = str(hour_to).split(':')
                    vals['request_hour_to'] = float(h) + float(m)/60
                else:
                    vals['request_hour_to'] = float(hour_to)
                    
            except (ValueError, TypeError):
                vals['request_hour_from'] = 8.0
                vals['request_hour_to'] = 17.0
                
            vals['request_date_to'] = vals['request_date_from']
            
        else:
            # Día completo
            vals['request_unit_half'] = False
            vals['request_unit_hours'] = False

        return vals

    def _handle_attachments(self, post):
        """Manejar archivos adjuntos"""
        attachment_ids = []
        
        _logger.info("📎 Procesando archivos adjuntos...")
        
        try:
            for key in post:
                file_obj = post[key]
                
                # Verificar si es un archivo
                if hasattr(file_obj, 'read') and hasattr(file_obj, 'filename'):
                    if file_obj.filename:
                        try:
                            file_content = file_obj.read()
                            file_size = len(file_content)
                            
                            if file_size == 0:
                                continue
                            
                            if file_size > 5 * 1024 * 1024:  # 5MB
                                _logger.warning(f"⚠️ Archivo muy grande: {file_obj.filename}")
                                continue
                            
                            # Crear adjunto
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': file_obj.filename,
                                'datas': base64.b64encode(file_content),
                                'res_model': 'hr.leave',
                                'res_id': 0,  # Se actualizará después
                                'type': 'binary',
                                'mimetype': getattr(file_obj, 'content_type', 'application/octet-stream')
                            })
                            
                            attachment_ids.append(attachment.id)
                            _logger.info(f"✅ Archivo guardado: {attachment.name}")
                            
                        except Exception as file_error:
                            _logger.error(f"❌ Error procesando archivo {file_obj.filename}: {str(file_error)}")
                            continue
                            
        except Exception as e:
            _logger.error(f"💥 Error general procesando adjuntos: {str(e)}")
            
        return attachment_ids

    def _send_notification_email(self, leave, employee, leave_type):
        """Enviar correo de notificación"""
        
        _logger.info("📧 Enviando correo de notificación...")
        
        try:
            # Destinatarios
            recipients = ['verapolo@icloud.com']
            cc_recipients = ['verapolo@icloud.com']

            # Preparar datos para el template
            email_data = {
                'employee_name': employee.name,
                'employee_code': employee.barcode or 'No asignado',
                'department': employee.department_id.name if employee.department_id else 'No asignado',
                'leave_type': leave_type.name,
                'date_from': leave.request_date_from.strftime('%d/%m/%Y'),
                'date_to': leave.request_date_to.strftime('%d/%m/%Y'),
                'duration': leave.number_of_days,
                'request_date': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'notes': leave.notes or 'Sin observaciones',
                'leave_id': leave.id,
            }

            # Determinar tipo de período
            if leave.request_unit_half:
                period_type = "Medio día - " + ("Mañana" if leave.request_date_from_period == 'am' else "Tarde")
            elif leave.request_unit_hours:
                period_type = f"Horas específicas ({leave.request_hour_from:.1f} - {leave.request_hour_to:.1f})"
            else:
                period_type = "Día completo"
            
            email_data['period_type'] = period_type

            # Crear y enviar correo
            email_body = self._create_email_template(email_data)

            mail_values = {
                'subject': f'Solicitud de Permiso - {employee.name} - {leave_type.name}',
                'body_html': email_body,
                'email_to': ', '.join(recipients),
                'email_cc': ', '.join(cc_recipients),
                'auto_delete': False,
                'email_from': request.env.user.email or 'noreply@corapsac.com.pe',
            }

            # Adjuntar archivos si existen
            attachments = request.env['ir.attachment'].search([
                ('res_model', '=', 'hr.leave'),
                ('res_id', '=', leave.id)
            ])
            
            if attachments:
                mail_values['attachment_ids'] = [(6, 0, attachments.ids)]

            mail = request.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            _logger.info(f"✅ Correo enviado exitosamente")

        except Exception as e:
            _logger.error("💥 ERROR AL ENVIAR CORREO:", exc_info=True)

    def _create_email_template(self, data):
        """Crear template HTML para el correo"""
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .info-table th, .info-table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                .info-table th {{ background-color: #f2f2f2; font-weight: bold; }}
                .footer {{ background: #ecf0f1; padding: 15px; text-align: center; font-size: 12px; }}
                .important {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>📋 Nueva Solicitud de Permiso</h2>
                <p>Sistema de Gestión de Tiempo Personal - CORAPSAC</p>
            </div>
            
            <div class="content">
                <div class="important">
                    <strong>⚠️ Atención:</strong> Se ha recibido una nueva solicitud de permiso que requiere consideración.
                </div>
                
                <h3>📊 Detalles de la Solicitud</h3>
                <table class="info-table">
                    <tr>
                        <th>👤 Trabajador</th>
                        <td>{data['employee_name']}</td>
                    </tr>
                    <tr>
                        <th>🆔 Código Empleado</th>
                        <td>{data['employee_code']}</td>
                    </tr>
                    <tr>
                        <th>🏢 Departamento</th>
                        <td>{data['department']}</td>
                    </tr>
                    <tr>
                        <th>📝 Tipo de Permiso</th>
                        <td>{data['leave_type']}</td>
                    </tr>
                    <tr>
                        <th>📅 Fecha de Inicio</th>
                        <td>{data['date_from']}</td>
                    </tr>
                    <tr>
                        <th>📅 Fecha de Fin</th>
                        <td>{data['date_to']}</td>
                    </tr>
                    <tr>
                        <th>⏱️ Tipo de Período</th>
                        <td>{data['period_type']}</td>
                    </tr>
                    <tr>
                        <th>📊 Duración</th>
                        <td>{data['duration']} día(s)</td>
                    </tr>
                    <tr>
                        <th>🕒 Fecha de Solicitud</th>
                        <td>{data['request_date']}</td>
                    </tr>
                    <tr>
                        <th>📋 Observaciones</th>
                        <td>{html_escape(data['notes'])}</td>
                    </tr>
                </table>
                
                <div style="margin: 30px 0; padding: 20px; background: #e8f4fd; border-left: 4px solid #3498db;">
                    <h4>🔗 Acciones Requeridas</h4>
                    <p>Para revisar y aprobar esta solicitud, ingrese al sistema:</p>
                    <p><strong>URL:</strong> <a href="https://andessolutioncopiers.com/odoo/web#id={data['leave_id']}&model=hr.leave&view_type=form">Ver Solicitud en el Sistema</a></p>
                </div>
            </div>
            
            <div class="footer">
                <p>Este es un correo automático generado por el Sistema de Gestión de RRHH de CORAPSAC</p>
                <p>Por favor no responda a este correo</p>
            </div>
        </body>
        </html>
        """

    def _return_error_response(self, error_code, message, suggestion=None, details=None):
        """Retornar respuesta de error estructurada"""
        
        _logger.error("❌ Retornando respuesta de error")
        _logger.error(f"   - Código: {error_code}")
        _logger.error(f"   - Mensaje: {message}")
        
        response_data = {
            'success': False,
            'error': message,
            'error_code': error_code,
            'suggestion': suggestion or 'Verifica los datos ingresados o contacta a Recursos Humanos.',
            'timestamp': datetime.now().isoformat()
        }
        
        if details:
            response_data['details'] = details
        
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
        
        _logger.info("🔌 API: Obtener tipos de permiso")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'error': 'No employee found'}

            leave_types = request.env['hr.leave.type'].search([
                ('company_id', 'in', [employee.company_id.id, False]),
                ('active', '=', True)
            ])

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
            
            return result

        except Exception as e:
            _logger.error(f"💥 Error en API tipos de permiso: {str(e)}", exc_info=True)
            return {'error': str(e)}

    @http.route('/leave/request/validate_dates', type='json', auth='user')
    def validate_leave_dates(self, date_from, date_to=None, holiday_status_id=None):
        """Validar fechas de solicitud"""
        
        _logger.info("🔍 API: Validar fechas")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'error': 'No employee found'}

            # Validaciones básicas
            if not date_from:
                return {'valid': False, 'error': 'Fecha de inicio requerida'}

            # Validar que la fecha no sea pasada
            from datetime import date
            today = date.today()
            request_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            
            if request_date < today:
                return {
                    'valid': False, 
                    'error': 'No se pueden solicitar permisos para fechas pasadas'
                }

            return {'valid': True}
            
        except Exception as e:
            _logger.error(f"💥 Error validando fechas: {str(e)}", exc_info=True)
            return {'error': str(e)}

    @http.route('/leave/request/check_overlap', type='json', auth='user')
    def check_leave_overlap(self, date_from, date_to=None):
        """Verificar si hay solapamiento con solicitudes existentes"""
        
        _logger.info("🔍 API: Verificar solapamiento")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'error': 'No employee found'}

            if not date_to:
                date_to = date_from

            # Buscar solicitudes que se solapan
            domain = [
                ('employee_id', '=', employee.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '<=', date_to),
                ('request_date_to', '>=', date_from),
            ]
            
            overlapping_leaves = request.env['hr.leave'].search(domain)

            if overlapping_leaves:
                overlap_info = []
                
                for leave in overlapping_leaves:
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
            
            return {'has_overlap': False}

        except Exception as e:
            _logger.error(f"💥 Error verificando solapamiento: {str(e)}", exc_info=True)
            return {'error': str(e)}
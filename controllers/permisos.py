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
        
        _logger.info("=== INICIO FORMULARIO PERMISO ===")
        
        try:
            # Obtener el empleado actual
            employee = request.env.user.employee_id
            if not employee:
                _logger.error(f"Usuario {request.env.user.name} no tiene empleado asociado")
                return request.render('website.404')
            
            _logger.info(f"Empleado accediendo al formulario: {employee.name} (ID: {employee.id})")
            
            # Obtener tipos de permiso disponibles
            leave_types = request.env['hr.leave.type'].search([
                ('company_id', 'in', [employee.company_id.id, False]),
                ('active', '=', True)
            ])
            
            _logger.info(f"Tipos de permiso disponibles: {len(leave_types)} tipos")
            for lt in leave_types:
                _logger.debug(f"  - {lt.name} (ID: {lt.id}, Requiere asignación: {lt.requires_allocation})")
            
            # Datos para el template
            values = {
                'employee': employee,
                'leave_types': leave_types,
                'today': fields.Date.today(),
                'user_tz': request.env.user.tz or 'UTC',
            }
            
            _logger.info("Template de formulario cargado correctamente")
            return request.render('sat.leave_request_template', values)
            
        except Exception as e:
            _logger.error(f"Error al cargar formulario de permiso: {str(e)}", exc_info=True)
            return request.render('website.500')

    @http.route('/leave/request/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit_leave_request(self, **post):
        """Procesar la solicitud de permiso enviada"""
        
        _logger.info("=== INICIO PROCESAMIENTO SOLICITUD ===")
        _logger.info(f"Datos recibidos: {post}")
        _logger.info(f"Headers: {dict(request.httprequest.headers)}")
        
        try:
            # Verificar empleado
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("No se encontró empleado asociado al usuario")
                return request.render('website.500', {
                    'message': 'No se encontró empleado asociado al usuario'
                })

            _logger.info(f"Procesando solicitud para empleado: {employee.name} (ID: {employee.id})")

            # Validar datos requeridos
            required_fields = ['holiday_status_id', 'request_date_from']
            missing_fields = []
            
            for field in required_fields:
                if not post.get(field):
                    missing_fields.append(field)
                    _logger.error(f"Campo requerido faltante: {field}")
            
            if missing_fields:
                return self._return_error_response(f'Campos requeridos faltantes: {", ".join(missing_fields)}')

            # Obtener tipo de permiso
            try:
                leave_type_id = int(post.get('holiday_status_id'))
                leave_type = request.env['hr.leave.type'].browse(leave_type_id)
                if not leave_type.exists():
                    _logger.error(f"Tipo de permiso no encontrado: {leave_type_id}")
                    return self._return_error_response('Tipo de permiso no válido')
            except (ValueError, TypeError) as e:
                _logger.error(f"Error al convertir holiday_status_id: {e}")
                return self._return_error_response('Tipo de permiso inválido')

            _logger.info(f"Tipo de permiso seleccionado: {leave_type.name}")

            # Preparar valores para crear la solicitud
            vals = self._prepare_leave_values(post, employee, leave_type)
            _logger.info(f"Valores preparados para crear solicitud: {vals}")

            # Manejar archivos adjuntos
            attachment_ids = self._handle_attachments(post)
            if attachment_ids:
                _logger.info(f"Archivos adjuntos procesados: {len(attachment_ids)} archivos")

            # Crear la solicitud
            _logger.info("Creando solicitud de permiso...")
            leave = request.env['hr.leave'].sudo().create(vals)
            _logger.info(f"Solicitud creada exitosamente con ID: {leave.id}")

            # Asociar adjuntos a la solicitud creada
            if attachment_ids:
                request.env['ir.attachment'].sudo().browse(attachment_ids).write({
                    'res_id': leave.id
                })
                _logger.info(f"Adjuntos asociados a la solicitud {leave.id}")

            # Enviar correo de notificación
            self._send_notification_email(leave, employee, leave_type)

            _logger.info("=== SOLICITUD PROCESADA EXITOSAMENTE ===")
            
            # Respuesta JSON exitosa
            return request.make_response(
                json.dumps({
                    'success': True,
                    'message': 'Solicitud de permiso enviada correctamente',
                    'leave_id': leave.id,
                    'redirect_url': f'/web#id={leave.id}&model=hr.leave&view_type=form'
                }),
                headers={'Content-Type': 'application/json'}
            )

        except ValidationError as e:
            _logger.error(f"Error de validación: {str(e)}")
            return self._return_error_response(str(e))
        except Exception as e:
            _logger.error(f"Error interno al procesar solicitud: {str(e)}", exc_info=True)
            return self._return_error_response(f'Error interno: {str(e)}')

    def _prepare_leave_values(self, post, employee, leave_type):
        """Preparar valores para crear la solicitud de permiso"""
        
        _logger.info("=== PREPARANDO VALORES PARA SOLICITUD ===")
        
        # Valores base
        vals = {
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': post.get('request_date_from'),
            'request_date_to': post.get('request_date_to', post.get('request_date_from')),
            'private_name': post.get('private_name') or f"{employee.name} - {leave_type.name}",
            'notes': post.get('notes', ''),
        }
        
        _logger.info(f"Valores base: {vals}")
        _logger.info(f"request_unit_half recibido: '{post.get('request_unit_half')}'")
        _logger.info(f"request_unit_hours recibido: '{post.get('request_unit_hours')}'")

        # Configurar según el tipo de unidad
        if post.get('request_unit_half') == 'true':
            vals['request_unit_half'] = True
            vals['request_date_from_period'] = post.get('request_date_from_period', 'am')
            vals['request_date_to'] = vals['request_date_from']
            _logger.info(f"Configurado como medio día: {vals['request_date_from_period']}")
            
        elif post.get('request_unit_hours') == 'true':
            vals['request_unit_hours'] = True
            
            # Convertir horas "08:00" a float 8.0
            hour_from = post.get('request_hour_from', '8:00')
            hour_to = post.get('request_hour_to', '17:00')
            
            _logger.info(f"Horas recibidas - Desde: '{hour_from}', Hasta: '{hour_to}'")
            
            try:
                # Convertir hora de inicio
                if ':' in str(hour_from):
                    h, m = str(hour_from).split(':')
                    vals['request_hour_from'] = float(h) + float(m)/60
                else:
                    vals['request_hour_from'] = float(hour_from)
                    
                # Convertir hora de fin
                if ':' in str(hour_to):
                    h, m = str(hour_to).split(':')
                    vals['request_hour_to'] = float(h) + float(m)/60
                else:
                    vals['request_hour_to'] = float(hour_to)
                    
            except (ValueError, TypeError) as e:
                _logger.error(f"Error al convertir horas: {e}")
                vals['request_hour_from'] = 8.0
                vals['request_hour_to'] = 17.0
                
            vals['request_date_to'] = vals['request_date_from']
            _logger.info(f"Configurado como horas: {vals['request_hour_from']} - {vals['request_hour_to']}")
            
        else:
            # Día completo
            vals['request_unit_half'] = False
            vals['request_unit_hours'] = False
            _logger.info("Configurado como día completo")

        # Validar fechas
        if not vals['request_date_from']:
            raise ValidationError("La fecha de inicio es requerida")
            
        if not vals['request_date_to']:
            vals['request_date_to'] = vals['request_date_from']

        _logger.info(f"Valores finales preparados: {vals}")
        return vals

    def _handle_attachments(self, post):
        """Manejar archivos adjuntos"""
        attachment_ids = []
        
        _logger.info("=== PROCESANDO ARCHIVOS ADJUNTOS ===")
        
        try:
            # Buscar archivos en el post
            file_fields = [key for key in post.keys() if key.startswith('attachment_') or key == 'file_input']
            _logger.info(f"Campos de archivo encontrados: {file_fields}")
            
            for key in post:
                file_obj = post[key]
                
                # Verificar si es un archivo
                if hasattr(file_obj, 'read') and hasattr(file_obj, 'filename'):
                    if file_obj.filename:  # Asegurar que tenga nombre
                        try:
                            file_content = file_obj.read()
                            file_name = file_obj.filename
                            
                            _logger.info(f"Procesando archivo: {file_name} ({len(file_content)} bytes)")
                            
                            # Crear adjunto
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': file_name,
                                'datas': base64.b64encode(file_content),
                                'res_model': 'hr.leave',
                                'res_id': 0,  # Se actualizará después de crear el leave
                                'type': 'binary',
                                'mimetype': getattr(file_obj, 'content_type', 'application/octet-stream')
                            })
                            attachment_ids.append(attachment.id)
                            _logger.info(f"Archivo {file_name} guardado con ID: {attachment.id}")
                            
                        except Exception as file_error:
                            _logger.error(f"Error procesando archivo {file_obj.filename}: {str(file_error)}")
                            continue
                    
        except Exception as e:
            _logger.error(f"Error general al procesar adjuntos: {str(e)}")
            
        _logger.info(f"Total de archivos procesados: {len(attachment_ids)}")
        return attachment_ids

    def _send_notification_email(self, leave, employee, leave_type):
        """Enviar correo de notificación"""
        
        _logger.info("=== ENVIANDO CORREO DE NOTIFICACIÓN ===")
        
        try:
            # Destinatarios
            recipients = ['verapolo@icloud.com']
            cc_recipients = ['verapolo@icloud.com']  # Ajusta el email de Lincoln
            
            _logger.info(f"Destinatarios: {recipients}")
            _logger.info(f"Con copia: {cc_recipients}")

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

            # Crear el cuerpo del correo
            email_body = self._create_email_template(email_data)

            # Enviar correo
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
                _logger.info(f"Adjuntando {len(attachments)} archivos al correo")

            mail = request.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            _logger.info(f"Correo enviado exitosamente con ID: {mail.id}")

        except Exception as e:
            _logger.error(f"Error al enviar correo de notificación: {str(e)}", exc_info=True)
            # No fallar la solicitud por problemas de correo

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

    def _return_error_response(self, message):
        """Retornar respuesta de error"""
        _logger.error(f"Retornando error: {message}")
        return request.make_response(
            json.dumps({
                'success': False,
                'error': message
            }),
            headers={'Content-Type': 'application/json'},
            status=400
        )

    @http.route('/leave/request/get_leave_types', type='json', auth='user')
    def get_available_leave_types(self):
        """API para obtener tipos de permiso disponibles via AJAX"""
        
        _logger.info("Solicitando tipos de permiso disponibles via AJAX")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                _logger.error("No se encontró empleado para obtener tipos de permiso")
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
            
            _logger.info(f"Retornando {len(leave_types)} tipos de permiso")
            return result

        except Exception as e:
            _logger.error(f"Error al obtener tipos de permiso: {str(e)}")
            return {'error': str(e)}

    @http.route('/leave/request/validate_dates', type='json', auth='user')
    def validate_leave_dates(self, date_from, date_to=None, holiday_status_id=None):
        """Validar fechas de solicitud"""
        
        _logger.info(f"Validando fechas: {date_from} - {date_to}")
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'error': 'No employee found'}

            # Aquí podrías agregar validaciones adicionales
            # Por ejemplo: verificar conflictos, días laborables, etc.
            
            _logger.info("Fechas validadas correctamente")
            return {'valid': True}
            
        except Exception as e:
            _logger.error(f"Error al validar fechas: {str(e)}")
            return {'error': str(e)}

    @http.route('/leave/request/check_overlap', type='json', auth='user')
    def check_leave_overlap(self, date_from, date_to=None):
        """Verificar si hay solapamiento con solicitudes existentes"""
        
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'error': 'No employee found'}

            if not date_to:
                date_to = date_from

            # Buscar solicitudes que se solapan
            overlapping_leaves = request.env['hr.leave'].search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),  # Estados activos
                ('request_date_from', '&lt;=', date_to),
                ('request_date_to', '&gt;=', date_from),
            ])

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
            _logger.error(f"Error al verificar solapamiento: {str(e)}")
            return {'error': str(e)}
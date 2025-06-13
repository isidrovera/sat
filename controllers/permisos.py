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
                return self._return_error_response('No se encontró empleado asociado al usuario')

            _logger.info(f"✅ Empleado verificado: {employee.name} (ID: {employee.id})")

            # Validar datos requeridos
            _logger.info("🔍 Validando campos requeridos...")
            required_fields = ['holiday_status_id', 'request_date_from']
            missing_fields = []
            
            for field in required_fields:
                if not post.get(field):
                    missing_fields.append(field)
                    _logger.error(f"❌ Campo requerido faltante: {field}")
                else:
                    _logger.info(f"✅ Campo {field}: {post.get(field)}")
            
            if missing_fields:
                error_msg = f'Campos requeridos faltantes: {", ".join(missing_fields)}'
                _logger.error(f"❌ Validación fallida: {error_msg}")
                return self._return_error_response(error_msg)

            # Obtener tipo de permiso
            _logger.info("📝 Obteniendo tipo de permiso...")
            try:
                leave_type_id = int(post.get('holiday_status_id'))
                _logger.info(f"   - ID del tipo: {leave_type_id}")
                
                leave_type = request.env['hr.leave.type'].browse(leave_type_id)
                if not leave_type.exists():
                    _logger.error(f"❌ Tipo de permiso no encontrado: {leave_type_id}")
                    return self._return_error_response('Tipo de permiso no válido')
                
                _logger.info(f"✅ Tipo de permiso encontrado: {leave_type.name}")
                _logger.info(f"   - Requiere asignación: {leave_type.requires_allocation}")
                _logger.info(f"   - Requiere documento: {leave_type.support_document}")
                _logger.info(f"   - Unidad: {leave_type.request_unit}")
                
            except (ValueError, TypeError) as e:
                _logger.error(f"❌ Error al convertir holiday_status_id: {e}")
                _logger.error(f"   - Valor recibido: {post.get('holiday_status_id')}")
                _logger.error(f"   - Tipo: {type(post.get('holiday_status_id'))}")
                return self._return_error_response('Tipo de permiso inválido')

            # Verificar solapamiento ANTES de crear
            _logger.info("🔍 Verificando solapamiento de fechas...")
            overlap_result = self._check_date_overlap_detailed(post, employee)
            if overlap_result['has_overlap']:
                _logger.error("❌ SOLAPAMIENTO DETECTADO")
                _logger.error(f"   - Solicitudes en conflicto: {len(overlap_result['overlapping_leaves'])}")
                for leave in overlap_result['overlapping_leaves']:
                    _logger.error(f"   ⚠️  {leave['type']}: {leave['date_from']} - {leave['date_to']} ({leave['state']})")
                
                return self._return_error_response(
                    f"Ya tiene solicitudes de permiso en este período. "
                    f"Conflictos encontrados: {len(overlap_result['overlapping_leaves'])} solicitud(es). "
                    f"Por favor seleccione fechas diferentes."
                )

            _logger.info("✅ No se detectaron conflictos de fechas")

            # Validar disponibilidad de días/horas ANTES de crear
            _logger.info("⏱️ Verificando disponibilidad de horas/días...")
            availability_result = self._validate_leave_availability(employee, leave_type, post)
            if not availability_result['valid']:
                _logger.error("❌ DISPONIBILIDAD INSUFICIENTE")
                _logger.error(f"   - Mensaje: {availability_result['message']}")
                
                return self._return_error_response(availability_result['message'])

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
                return self._return_error_response(friendly_message)
                
            except Exception as create_error:
                _logger.error("❌ ERROR AL CREAR SOLICITUD (Exception)")
                _logger.error(f"   - Error: {str(create_error)}")
                _logger.error(f"   - Tipo: {type(create_error).__name__}")
                
                friendly_message = self._get_friendly_error_message(str(create_error))
                return self._return_error_response(friendly_message)

            # Asociar adjuntos a la solicitud creada
            if attachment_ids:
                _logger.info("🔗 Asociando archivos adjuntos...")
                request.env['ir.attachment'].sudo().browse(attachment_ids).write({
                    'res_id': leave.id
                })
                _logger.info(f"✅ {len(attachment_ids)} archivos asociados a la solicitud {leave.id}")

            # Enviar correo de notificación
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
            response_data = {
                'success': True,
                'message': 'Solicitud de permiso enviada correctamente',
                'leave_id': leave.id,
                'redirect_url': f'/web#id={leave.id}&model=hr.leave&view_type=form'
            }
            
            _logger.info(f"📤 Enviando respuesta exitosa: {response_data}")
            
            return request.make_response(
                json.dumps(response_data),
                headers={'Content-Type': 'application/json'}
            )

        except ValidationError as e:
            _logger.error("=" * 60)
            _logger.error("💥 ERROR DE VALIDACIÓN")
            _logger.error("=" * 60)
            _logger.error(f"❌ Error de validación: {str(e)}")
            _logger.error(f"   - Tipo: ValidationError")
            _logger.error(f"   - Empleado: {employee.name if 'employee' in locals() else 'N/A'}")
            return self._return_error_response(str(e))
            
        except Exception as e:
            _logger.error("=" * 60)
            _logger.error("💥 ERROR INTERNO")
            _logger.error("=" * 60)
            _logger.error(f"❌ Error interno: {str(e)}", exc_info=True)
            _logger.error(f"   - Tipo: {type(e).__name__}")
            _logger.error(f"   - Empleado: {employee.name if 'employee' in locals() else 'N/A'}")
            _logger.error(f"   - Datos POST: {dict(post)}")
            return self._return_error_response(f'Error interno: {str(e)}')

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

    def _prepare_leave_values(self, post, employee, leave_type):
        """Preparar valores para crear la solicitud de permiso"""
        
        _logger.info("⚙️ === PREPARANDO VALORES PARA SOLICITUD ===")
        
        # Valores base
        vals = {
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': post.get('request_date_from'),
            'request_date_to': post.get('request_date_to', post.get('request_date_from')),
            'private_name': post.get('private_name') or f"{employee.name} - {leave_type.name}",
            'notes': post.get('notes', ''),
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
        """Enviar correo de notificación"""
        
        _logger.info("📧 === ENVIANDO CORREO DE NOTIFICACIÓN ===")
        
        try:
            # Destinatarios
            recipients = ['verapolo@icloud.com']
            cc_recipients = ['verapolo@icloud.com']
            
            _logger.info(f"📬 Configuración de correo:")
            _logger.info(f"   - Para: {recipients}")
            _logger.info(f"   - CC: {cc_recipients}")
            _logger.info(f"   - De: {request.env.user.email or 'noreply@corapsac.com.pe'}")

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
            
            _logger.info(f"📋 Datos del correo:")
            for key, value in email_data.items():
                _logger.info(f"   - {key}: {value}")

            # Crear el cuerpo del correo
            _logger.info("🎨 Generando template HTML...")
            email_body = self._create_email_template(email_data)
            _logger.info(f"   - Template generado: {len(email_body)} caracteres")

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
                _logger.info(f"📎 Adjuntando archivos al correo:")
                for att in attachments:
                    _logger.info(f"   - {att.name} (ID: {att.id})")
            else:
                _logger.info("ℹ️ No hay archivos para adjuntar")

            _logger.info("📤 Creando y enviando correo...")
            mail = request.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            
            _logger.info(f"✅ Correo enviado exitosamente:")
            _logger.info(f"   - Mail ID: {mail.id}")
            _logger.info(f"   - Asunto: {mail.subject}")
            _logger.info(f"   - Estado: {mail.state}")

        except Exception as e:
            _logger.error("💥 ERROR AL ENVIAR CORREO:")
            _logger.error(f"   - Error: {str(e)}", exc_info=True)
            _logger.error(f"   - Tipo: {type(e).__name__}")
            _logger.warning("⚠️ Continuando sin correo (no crítico)")

    def _create_email_template(self, data):
        """Crear template HTML para el correo"""
        
        _logger.info("🎨 Generando template HTML para correo...")
        
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
        
        _logger.error("❌ === RETORNANDO RESPUESTA DE ERROR ===")
        _logger.error(f"   - Mensaje: {message}")
        _logger.error(f"   - Timestamp: {datetime.now()}")
        _logger.error(f"   - Usuario: {request.env.user.name if request.env.user else 'N/A'}")
        
        response_data = {
            'success': False,
            'error': message
        }
        
        _logger.error(f"   - Respuesta JSON: {response_data}")
        
        return request.make_response(
            json.dumps(response_data),
            headers={'Content-Type': 'application/json'},
            status=400
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

            # Aquí podrías agregar más validaciones
            # Por ejemplo: verificar días laborables, límites de empresa, etc.
            
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
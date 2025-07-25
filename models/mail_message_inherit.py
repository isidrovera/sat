# models/mail_message_inherit.py
from odoo import models, api, fields
import logging
import re
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class MailMessageCounterInherit(models.Model):
   _inherit = 'mail.message'
   
   @api.model
   def create(self, vals):
       """
       Override seguro del método create que respeta la cadena de herencia
       y procesa correos de contadores en tiempo real
       """
       try:
           # 1. SIEMPRE ejecutar super().create() PRIMERO para mantener compatibilidad
           _logger.debug(f"📨 Creando mail.message con asunto: {vals.get('subject', 'Sin asunto')}")
           message = super().create(vals)
           
           # 2. Ejecutar nuestro hook de forma segura y no bloqueante
           self._safe_contador_automatico_hook(message)
           
           return message
           
       except Exception as e:
           # Si hay error en super().create(), re-lanzar (es crítico)
           _logger.error(f"❌ Error crítico en create de mail.message: {e}")
           raise
   
   def _safe_contador_automatico_hook(self, message):
       """
       Hook seguro para procesamiento de contadores automáticos.
       Cualquier error aquí NO debe afectar la creación del mensaje.
       """
       hook_start_time = datetime.now()
       
       try:
           _logger.debug(f"🔍 Evaluando mensaje ID={message.id} para contadores automáticos")
           
           # Verificar condiciones básicas de forma rápida
           if not self._should_process_counter_message(message):
               _logger.debug(f"⏭️ Mensaje ID={message.id} no cumple criterios básicos, saltando")
               return
           
           # Log detallado del mensaje que SÍ será procesado
           _logger.info(f"📧 === PROCESANDO CORREO CONTADOR ===")
           _logger.info(f"📧 ID: {message.id}")
           _logger.info(f"📧 Asunto: '{message.subject}'")
           _logger.info(f"📧 Remitente: {message.email_from}")
           _logger.info(f"📧 Fecha: {message.date}")
           _logger.info(f"📧 Tipo: {message.message_type}")
           
           # Crear registro contador de forma segura
           self._create_contador_record_safe(message)
           
           # Log de tiempo de procesamiento
           processing_time = (datetime.now() - hook_start_time).total_seconds()
           _logger.info(f"⏱️ Hook completado en {processing_time:.2f} segundos")
           
       except Exception as e:
           # CRÍTICO: Este error NO debe romper la creación del mensaje
           processing_time = (datetime.now() - hook_start_time).total_seconds()
           
           _logger.error(f"❌ === ERROR EN HOOK CONTADOR AUTOMÁTICO ===")
           _logger.error(f"❌ Mensaje ID: {message.id}")
           _logger.error(f"❌ Asunto: {getattr(message, 'subject', 'Sin asunto')}")
           _logger.error(f"❌ Remitente: {getattr(message, 'email_from', 'Sin remitente')}")
           _logger.error(f"❌ Error: {str(e)}")
           _logger.error(f"❌ Tiempo antes del error: {processing_time:.2f} segundos")
           
           # Crear registro de error para seguimiento
           try:
               self._create_error_record(message, e)
           except Exception as error_creating_error:
               _logger.error(f"❌ No se pudo crear registro de error: {error_creating_error}")
   
   def _should_process_counter_message(self, message):
       """
       Filtro SÚPER rápido para determinar si el mensaje debe procesarse.
       Con logging detallado para debugging.
       """
       try:
           _logger.debug(f"🔍 === EVALUANDO CRITERIOS MENSAJE ID={message.id} ===")
           
           # 1. Debe ser email
           message_type = getattr(message, 'message_type', None)
           _logger.debug(f"🔍 Tipo de mensaje: {message_type}")
           if message_type != 'email':
               _logger.debug(f"❌ No es email, saltando")
               return False
           
           # 2. Debe tener asunto
           subject = getattr(message, 'subject', None)
           _logger.debug(f"🔍 Asunto: '{subject}'")
           if not subject:
               _logger.debug(f"❌ Sin asunto, saltando")
               return False
           
           # 3. Filtro rápido por palabras clave (solo las más obvias)
           subject_lower = subject.lower().strip()
           
           # Palabras clave principales para filtro rápido
           quick_keywords = [
               'counter list',
               'counter page', 
               'page counter',
               'contador',
               'ricoh counter',
               'bizhub counter',
               'printer counter'
           ]
           
           # Verificación rápida con logging
           keyword_found = None
           for keyword in quick_keywords:
               if keyword in subject_lower:
                   keyword_found = keyword
                   break
           
           _logger.debug(f"🔍 Palabra clave encontrada: {keyword_found}")
           if not keyword_found:
               _logger.debug(f"❌ No contiene palabras clave de contadores")
               return False
           
           # 4. Verificar que no sea un mensaje del sistema interno
           email_from = getattr(message, 'email_from', '')
           _logger.debug(f"🔍 Email remitente: '{email_from}'")
           if not email_from or '@' not in email_from:
               _logger.debug(f"❌ Email remitente inválido")
               return False
           
           # 5. Verificar que tenga contenido mínimo
           body = getattr(message, 'body', '')
           body_length = len(body.strip()) if body else 0
           _logger.debug(f"🔍 Longitud del cuerpo: {body_length} caracteres")
           if body_length < 20:  # Reducido el mínimo
               _logger.debug(f"❌ Contenido muy corto para ser contador")
               return False
           
           # 6. Verificar que el contenido tenga indicadores de contadores
           content_indicators = ['serial', 'serie', 'counter', 'contador', 'total', 'black', 'color', 'scan']
           indicators_found = []
           body_lower = body.lower() if body else ''
           
           for indicator in content_indicators:
               if indicator in body_lower:
                   indicators_found.append(indicator)
           
           _logger.debug(f"🔍 Indicadores en contenido: {indicators_found}")
           if len(indicators_found) < 2:  # Al menos 2 indicadores
               _logger.debug(f"❌ Pocos indicadores de contadores en contenido")
               return False
           
           _logger.info(f"✅ === MENSAJE APROBADO PARA PROCESAMIENTO ===")
           _logger.info(f"✅ ID: {message.id}")
           _logger.info(f"✅ Palabra clave: '{keyword_found}'")
           _logger.info(f"✅ Indicadores: {indicators_found}")
           _logger.info(f"✅ Remitente: {email_from}")
           
           return True
           
       except Exception as e:
           _logger.error(f"❌ Error en filtro rápido para mensaje ID={getattr(message, 'id', 'unknown')}: {e}")
           # En caso de error en el filtro, mejor no procesar
           return False
   
   def _create_contador_record_safe(self, message):
       """
       Crea el registro en contador.automatico de forma segura.
       LÓGICA CORREGIDA: Solo evita duplicados por original_mail_id.
       Permite múltiples correos del mismo equipo con diferentes contadores.
       """
       creation_start_time = datetime.now()
       
       try:
           _logger.info(f"🆕 === CREANDO REGISTRO CONTADOR ===")
           _logger.info(f"🆕 Para mensaje ID: {message.id}")
           
           # 1. ÚNICA verificación válida: por original_mail_id
           # (Un mensaje específico solo debe crear UN registro)
           _logger.debug(f"🔍 Verificando duplicado por original_mail_id={message.id}")
           
           existing = self.env['contador.automatico'].sudo().search([
               ('original_mail_id', '=', message.id)
           ], limit=1)
           
           if existing:
               _logger.info(f"⏭️ === MENSAJE YA PROCESADO ===")
               _logger.info(f"⏭️ Mensaje ID: {message.id}")
               _logger.info(f"⏭️ Registro existente ID: {existing.id}")
               _logger.info(f"⏭️ Estado del registro: {existing.estado}")
               _logger.info(f"⏭️ Serie detectada: {existing.serie_detectada}")
               return existing  # Retornar el existente
           
           # 2. NO verificamos por asunto+remitente (PERMITIMOS múltiples correos del mismo equipo)
           _logger.debug(f"✅ No hay duplicado, procediendo a crear registro")
           
           # 3. Extraer información del mensaje
           subject = getattr(message, 'subject', f'Sin asunto - {message.id}')
           email_from = getattr(message, 'email_from', 'Sin remitente')
           body = getattr(message, 'body', '')
           message_date = getattr(message, 'date', fields.Datetime.now())
           
           _logger.info(f"📋 === DATOS PARA NUEVO REGISTRO ===")
           _logger.info(f"📋 Asunto: '{subject}'")
           _logger.info(f"📋 Remitente: '{email_from}'")
           _logger.info(f"📋 Fecha mensaje: {message_date}")
           _logger.info(f"📋 Longitud contenido: {len(body)} caracteres")
           
           # 4. Preparar datos del registro
           contador_data = {
               'name': subject,
               'remitente': email_from,
               'contenido_original': body,
               'original_mail_id': message.id,
               'estado': 'pendiente',
               'fecha_procesamiento': fields.Datetime.now()
           }
           
           # 5. Crear registro con logging
           _logger.info(f"💾 Creando registro en base de datos...")
           contador_record = self.env['contador.automatico'].sudo().create(contador_data)
           
           creation_time = (datetime.now() - creation_start_time).total_seconds()
           
           _logger.info(f"✅ === REGISTRO CREADO EXITOSAMENTE ===")
           _logger.info(f"✅ Registro ID: {contador_record.id}")
           _logger.info(f"✅ Estado inicial: {contador_record.estado}")
           _logger.info(f"✅ Tiempo de creación: {creation_time:.2f} segundos")
           
           # 6. Procesar inmediatamente con el sistema inteligente
           self._process_contador_immediately(contador_record, message)
           
           return contador_record
           
       except Exception as e:
           creation_time = (datetime.now() - creation_start_time).total_seconds()
           
           _logger.error(f"❌ === ERROR CREANDO REGISTRO CONTADOR ===")
           _logger.error(f"❌ Mensaje ID: {message.id}")
           _logger.error(f"❌ Error: {str(e)}")
           _logger.error(f"❌ Tiempo antes del error: {creation_time:.2f} segundos")
           
           # Re-lanzar para que se capture en el hook principal
           raise
   
   def _process_contador_immediately(self, contador_record, original_message):
       """
       Procesa el registro contador inmediatamente usando el sistema inteligente existente.
       Con logging completo del proceso.
       """
       processing_start_time = datetime.now()
       
       try:
           _logger.info(f"🧠 === INICIANDO PROCESAMIENTO INTELIGENTE ===")
           _logger.info(f"🧠 Registro ID: {contador_record.id}")
           _logger.info(f"🧠 Mensaje origen ID: {original_message.id}")
           
           # Usar el método existente del sistema inteligente
           _logger.debug(f"🔄 Ejecutando procesar_correo_inteligente()...")
           success = contador_record.procesar_correo_inteligente()
           
           processing_time = (datetime.now() - processing_start_time).total_seconds()
           
           if success:
               _logger.info(f"✅ === PROCESAMIENTO EXITOSO ===")
               _logger.info(f"✅ Registro ID: {contador_record.id}")
               _logger.info(f"✅ Estado final: {contador_record.estado}")
               _logger.info(f"✅ Serie detectada: {contador_record.serie_detectada}")
               _logger.info(f"✅ Tiempo procesamiento: {processing_time:.2f} segundos")
               
               # Log detallado de resultados según el estado
               if contador_record.estado == 'procesado':
                   self._log_successful_processing(contador_record)
                   
               elif contador_record.estado == 'manual':
                   self._log_manual_processing_needed(contador_record)
                   
               elif contador_record.estado == 'error':
                   self._log_processing_error(contador_record)
                   
               elif contador_record.estado == 'filtrado':
                   self._log_filtered_processing(contador_record)
               
           else:
               _logger.warning(f"⚠️ === PROCESAMIENTO FALLÓ ===")
               _logger.warning(f"⚠️ Registro ID: {contador_record.id}")
               _logger.warning(f"⚠️ Estado: {contador_record.estado}")
               _logger.warning(f"⚠️ Error: {contador_record.mensaje_error}")
               _logger.warning(f"⚠️ Tiempo procesamiento: {processing_time:.2f} seconds")
           
       except Exception as e:
           processing_time = (datetime.now() - processing_start_time).total_seconds()
           
           _logger.error(f"❌ === ERROR EN PROCESAMIENTO INMEDIATO ===")
           _logger.error(f"❌ Registro ID: {contador_record.id}")
           _logger.error(f"❌ Error: {str(e)}")
           _logger.error(f"❌ Tiempo antes del error: {processing_time:.2f} segundos")
           
           # Actualizar registro con el error
           try:
               contador_record.sudo().write({
                   'estado': 'error',
                   'mensaje_error': f"Error en procesamiento inmediato desde hook: {str(e)}",
                   'fecha_procesamiento': fields.Datetime.now()
               })
               
               _logger.info(f"📝 Registro actualizado con estado de error")
               
           except Exception as update_error:
               _logger.error(f"❌ No se pudo actualizar registro con error: {update_error}")
   
   def _log_successful_processing(self, contador_record):
       """Log detallado para procesamiento exitoso"""
       _logger.info(f"📊 === CONTADORES PROCESADOS EXITOSAMENTE ===")
       _logger.info(f"📊 Serie: {contador_record.serie_detectada}")
       _logger.info(f"📊 BN detectado: {contador_record.contador_bn_detectado}")
       _logger.info(f"📊 Color detectado: {contador_record.contador_color_detectado}")
       _logger.info(f"📊 Scan detectado: {contador_record.contador_scan_detectado}")
       _logger.info(f"📊 Total calculado: {contador_record.contador_total_detectado}")
       
       if contador_record.equipo_id:
           _logger.info(f"🎯 === EQUIPO ACTUALIZADO ===")
           _logger.info(f"🎯 Equipo ID: {contador_record.equipo_id.id}")
           _logger.info(f"🎯 Serie equipo: {contador_record.equipo_id.serie}")
           
           # Log de valores anteriores vs nuevos
           if contador_record.contador_bn_anterior:
               incremento_bn = contador_record.contador_bn_detectado - contador_record.contador_bn_anterior
               _logger.info(f"📈 BN: {contador_record.contador_bn_anterior} → {contador_record.contador_bn_detectado} (+{incremento_bn})")
           
           if contador_record.contador_color_anterior:
               incremento_color = contador_record.contador_color_detectado - contador_record.contador_color_anterior
               _logger.info(f"📈 Color: {contador_record.contador_color_anterior} → {contador_record.contador_color_detectado} (+{incremento_color})")
           
           if contador_record.contador_scan_anterior:
               incremento_scan = contador_record.contador_scan_detectado - contador_record.contador_scan_anterior
               _logger.info(f"📈 Scan: {contador_record.contador_scan_anterior} → {contador_record.contador_scan_detectado} (+{incremento_scan})")
       
       # Log de información adicional detectada
       if contador_record.idioma_detectado:
           _logger.info(f"🌍 Idioma detectado: {contador_record.idioma_detectado} ({contador_record.confianza_deteccion}%)")
       
       if contador_record.marca_detectada:
           _logger.info(f"🏭 Marca detectada: {contador_record.marca_detectada}")
       
       if contador_record.formato_detectado:
           _logger.info(f"📐 Formato detectado: {contador_record.formato_detectado}")
       
       if contador_record.tipo_equipo_detectado:
           _logger.info(f"🎨 Tipo equipo: {contador_record.tipo_equipo_detectado}")
       
       if contador_record.cliente_detectado:
           _logger.info(f"👤 Cliente: {contador_record.cliente_detectado}")
   
   def _log_manual_processing_needed(self, contador_record):
       """Log para procesamiento que requiere intervención manual"""
       _logger.warning(f"👤 === REQUIERE PROCESAMIENTO MANUAL ===")
       _logger.warning(f"👤 Registro ID: {contador_record.id}")
       _logger.warning(f"👤 Razón: {contador_record.mensaje_error}")
       
       if contador_record.serie_detectada:
           _logger.warning(f"👤 Serie detectada: {contador_record.serie_detectada}")
       
       if any([contador_record.contador_bn_detectado, contador_record.contador_color_detectado, contador_record.contador_scan_detectado]):
           _logger.warning(f"👤 Contadores detectados - BN: {contador_record.contador_bn_detectado}, Color: {contador_record.contador_color_detectado}, Scan: {contador_record.contador_scan_detectado}")
   
   def _log_processing_error(self, contador_record):
       """Log para procesamiento con error"""
       _logger.error(f"🔥 === ERROR EN PROCESAMIENTO ===")
       _logger.error(f"🔥 Registro ID: {contador_record.id}")
       _logger.error(f"🔥 Error: {contador_record.mensaje_error}")
       
       if contador_record.idioma_detectado:
           _logger.error(f"🔥 Idioma detectado: {contador_record.idioma_detectado}")
       
       if contador_record.marca_detectada:
           _logger.error(f"🔥 Marca detectada: {contador_record.marca_detectada}")
   
   def _log_filtered_processing(self, contador_record):
       """Log para procesamiento filtrado"""
       _logger.info(f"🚫 === CORREO FILTRADO ===")
       _logger.info(f"🚫 Registro ID: {contador_record.id}")
       _logger.info(f"🚫 Razón: {contador_record.mensaje_error}")
       _logger.info(f"🚫 Este correo no es de contadores válidos")
   
   def _create_error_record(self, message, error):
       """
       Crea un registro de error para tracking cuando falla el hook
       """
       try:
           error_record = self.env['contador.automatico'].sudo().create({
               'name': f"ERROR HOOK: {getattr(message, 'subject', 'Sin asunto')}",
               'remitente': f"ERROR: {getattr(message, 'email_from', 'Sin remitente')}",
               'contenido_original': f"Error procesando mensaje ID {message.id} en hook de mail.message:\n\nError: {str(error)}\n\nAsunto original: {getattr(message, 'subject', 'N/A')}\nRemitente original: {getattr(message, 'email_from', 'N/A')}",
               'original_mail_id': message.id,
               'estado': 'error',
               'mensaje_error': f"Error en hook de creación de mail.message: {str(error)}",
               'fecha_procesamiento': fields.Datetime.now()
           })
           
           _logger.info(f"📝 Registro de error creado: ID={error_record.id}")
           
       except Exception as create_error:
           _logger.error(f"❌ Error crítico: No se pudo crear registro de error: {create_error}")
   
   def _log_inheritance_chain(self):
       """
       Log de la cadena de herencia para detectar posibles conflictos
       """
       try:
           mro_classes = [cls.__name__ for cls in type(self).__mro__ if hasattr(cls, 'create')]
           _logger.info(f"🔍 === CADENA DE HERENCIA MAIL.MESSAGE ===")
           _logger.info(f"🔍 Clases con create(): {' -> '.join(mro_classes)}")
           
           # Verificar si hay otros inherits que podrían generar conflicto
           if hasattr(self.env.registry, '_inherits'):
               mail_message_inherits = self.env.registry._inherits.get('mail.message', [])
               if mail_message_inherits:
                   _logger.info(f"📋 Otros módulos heredando mail.message: {mail_message_inherits}")
               else:
                   _logger.info(f"📋 No hay otros inherits de mail.message detectados")
           
       except Exception as e:
           _logger.error(f"❌ Error verificando cadena de herencia: {e}")
   
   @api.model
   def init(self):
       """
       Inicialización del inherit con logging
       """
       try:
           # Llamar init del padre si existe
           if hasattr(super(), 'init'):
               super().init()
           
           # Log de inicialización
           _logger.info(f"🚀 === MAIL MESSAGE CONTADOR INHERIT INICIALIZADO ===")
           _logger.info(f"🚀 Módulo: mail_message_inherit")
           _logger.info(f"🚀 Funcionalidad: Procesamiento automático de contadores en tiempo real")
           
           # Verificar cadena de herencia
           self._log_inheritance_chain()
           
           _logger.info(f"✅ Inicialización completada exitosamente")
           
       except Exception as e:
           _logger.error(f"❌ Error en inicialización de mail.message inherit: {e}")
   
   # MÉTODOS DE DEBUGGING Y TESTING
   
   def test_contador_hook_complete(self):
       """
       Método de prueba completo para verificar que el hook funciona
       """
       test_start_time = datetime.now()
       
       try:
           _logger.info(f"🧪 === INICIANDO PRUEBA COMPLETA DE HOOK ===")
           
           # 1. Crear mensaje de prueba realista
           test_subject = f"TEST Counter List - Prueba Hook {datetime.now().strftime('%Y%m%d_%H%M%S')}"
           test_body = """
           [Serial Number], ABC123TEST456
           [Total Counter],00012345
           [Total Black Counter],00008000
           [Total Color Counter],00004345
           [Total Scan/Fax Counter],00001500
           """
           
           _logger.info(f"🧪 Creando mensaje de prueba...")
           _logger.info(f"🧪 Asunto: '{test_subject}'")
           
           test_message = self.env['mail.message'].sudo().create({
               'subject': test_subject,
               'email_from': 'test-contador@hook.com',
               'body': test_body,
               'message_type': 'email',
               'date': fields.Datetime.now()
           })
           
           _logger.info(f"✅ Mensaje de prueba creado: ID={test_message.id}")
           
           # 2. Verificar que se creó registro contador
           _logger.info(f"🔍 Buscando registro contador asociado...")
           
           contador_test = self.env['contador.automatico'].search([
               ('original_mail_id', '=', test_message.id)
           ])
           
           test_total_time = (datetime.now() - test_start_time).total_seconds()
           
           if contador_test:
               _logger.info(f"✅ === PRUEBA EXITOSA ===")
               _logger.info(f"✅ Hook funcionando correctamente")
               _logger.info(f"✅ Registro contador creado: ID={contador_test.id}")
               _logger.info(f"✅ Estado: {contador_test.estado}")
               _logger.info(f"✅ Serie detectada: {contador_test.serie_detectada}")
               _logger.info(f"✅ Tiempo total prueba: {test_total_time:.2f} segundos")
               
               # Log de contadores detectados
               if contador_test.estado == 'procesado':
                   _logger.info(f"📊 Contadores - BN: {contador_test.contador_bn_detectado}, Color: {contador_test.contador_color_detectado}, Scan: {contador_test.contador_scan_detectado}")
               
               return True
               
           else:
               _logger.error(f"❌ === PRUEBA FALLIDA ===")
               _logger.error(f"❌ Hook NO funcionando")
               _logger.error(f"❌ No se creó registro contador para mensaje ID={test_message.id}")
               _logger.error(f"❌ Tiempo total prueba: {test_total_time:.2f} segundos")
               
               # Intentar diagnosticar el problema
               _logger.error(f"🔍 Diagnosticando...")
               
               # Verificar si el mensaje cumplía criterios
               should_process = self._should_process_counter_message(test_message)
               _logger.error(f"🔍 ¿Debería procesar?: {should_process}")
               
               return False
               
       except Exception as e:
           test_total_time = (datetime.now() - test_start_time).total_seconds()
           
           _logger.error(f"❌ === ERROR EN PRUEBA DE HOOK ===")
           _logger.error(f"❌ Error: {str(e)}")
           _logger.error(f"❌ Tiempo antes del error: {test_total_time:.2f} segundos")
           
           return False
   
   def debug_recent_messages(self, hours=1):
       """
       Debug de mensajes recientes para verificar el hook
       """
       try:
           _logger.info(f"🔍 === DEBUGGING MENSAJES RECIENTES ({hours}h) ===")
           
           # Buscar mensajes recientes
           since_time = fields.Datetime.now() - timedelta(hours=hours)
           recent_messages = self.env['mail.message'].search([
               ('create_date', '>=', since_time),
               ('message_type', '=', 'email')
           ], order='create_date desc')
           
           _logger.info(f"📧 Mensajes email encontrados: {len(recent_messages)}")
           
           for i, msg in enumerate(recent_messages[:10], 1):  # Solo primeros 10
               _logger.info(f"📧 {i}. ID={msg.id}, Asunto='{msg.subject}', De='{msg.email_from}'")
               
               # Verificar si debería haber sido procesado
               should_process = self._should_process_counter_message(msg)
               
               # Verificar si se creó registro contador
               contador_exists = self.env['contador.automatico'].search_count([
                   ('original_mail_id', '=', msg.id)
               ])
               
               status = "✅ PROCESADO" if contador_exists else ("🟡 DEBERÍA PROCESAR" if should_process else "⚪ NO RELEVANTE")
               _logger.info(f"    Estado: {status}")
               
               if should_process and not contador_exists:
                   _logger.warning(f"⚠️ PROBLEMA: Mensaje debería haberse procesado pero no tiene registro contador")
           
       except Exception as e:
           _logger.error(f"❌ Error en debug de mensajes recientes: {e}")
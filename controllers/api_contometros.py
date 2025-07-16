from odoo import http, fields
from odoo.http import request
import logging
import json
import re
import traceback
from datetime import datetime

_logger = logging.getLogger(__name__)

class ContadorAPI(http.Controller):

    def log_request_info(self):
        """
        Registra información detallada de la petición
        """
        try:
            _logger.info("🚀 === INICIO DE PETICIÓN API CONTADOR ===")
            _logger.info(f"📊 Método: {request.httprequest.method}")
            _logger.info(f"🌐 URL: {request.httprequest.url}")
            _logger.info(f"📍 IP Cliente: {request.httprequest.remote_addr}")
            _logger.info(f"🕐 Timestamp: {datetime.now().isoformat()}")
            
            # Log de headers (sin información sensible)
            headers_safe = {}
            for key, value in dict(request.httprequest.headers).items():
                if key.lower() not in ['authorization', 'cookie', 'session']:
                    headers_safe[key] = value
                else:
                    headers_safe[key] = '[REDACTED]'
            _logger.info(f"🔗 Headers: {headers_safe}")
            
        except Exception as e:
            _logger.warning(f"⚠️ Error al registrar info de petición: {e}")

    def crear_respuesta_error(self, mensaje, status_code=400, detalle_extra=None):
        """
        Crea una respuesta de error estandarizada
        """
        respuesta = {
            "status": "error",
            "error": mensaje,
            "timestamp": datetime.now().isoformat()
        }
        
        if detalle_extra:
            respuesta["detalle"] = detalle_extra
            
        _logger.error(f"❌ Respuesta de error: {respuesta}")
        
        return request.make_response(
            json.dumps(respuesta, ensure_ascii=False),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            status=status_code
        )

    def crear_respuesta_exitosa(self, data):
        """
        Crea una respuesta exitosa estandarizada
        """
        respuesta = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        _logger.info(f"✅ Respuesta exitosa: {respuesta}")
        
        return request.make_response(
            json.dumps(respuesta, ensure_ascii=False, default=str),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            status=200
        )

    def limpiar_json_power_automate(self, json_string):
        """
        Limpia JSON que viene de Power Automate con saltos de línea problemáticos
        """
        try:
            _logger.info(f"🔧 Iniciando limpieza de JSON...")
            _logger.info(f"📄 JSON original (primeros 200 chars): {repr(json_string[:200])}")
            
            if not json_string or not json_string.strip():
                raise ValueError("JSON vacío o solo espacios")
            
            # 1. Remover BOM si existe
            if json_string.startswith('\ufeff'):
                json_string = json_string[1:]
                _logger.info("🧹 BOM removido")
            
            # 2. Remover caracteres de control problemáticos (excepto \t, \n, \r que pueden ser válidos)
            json_limpio = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', json_string)
            
            # 3. Limpiar saltos de línea y espacios dentro de valores JSON
            def limpiar_valor(match):
                clave_o_valor = match.group(1)
                # Limpiar espacios en blanco del inicio/final y normalizar espacios internos
                limpio = re.sub(r'^\s+|\s+$', '', clave_o_valor)  # Quitar espacios del inicio/final
                limpio = re.sub(r'\s+', ' ', limpio)  # Convertir múltiples espacios en uno
                return f'"{limpio}"'
            
            # 4. Aplicar limpieza a valores entre comillas
            json_limpio = re.sub(r'"([^"]*)"', limpiar_valor, json_limpio)
            
            # 5. Verificar que sigue siendo JSON válido básico
            if not (json_limpio.strip().startswith('{') and json_limpio.strip().endswith('}')):
                raise ValueError("Estructura JSON inválida después de limpieza")
            
            _logger.info(f"✨ JSON limpiado exitosamente")
            _logger.info(f"📄 JSON limpio (primeros 200 chars): {repr(json_limpio[:200])}")
            
            return json_limpio.strip()
            
        except Exception as e:
            _logger.error(f"❌ Error en limpieza de JSON: {e}")
            raise

    def validar_estructura_json(self, data):
        """
        Valida que el JSON tenga la estructura mínima requerida
        """
        try:
            _logger.info(f"🔍 Validando estructura JSON: {data}")
            
            if not isinstance(data, dict):
                raise ValueError("El JSON debe ser un objeto, no una lista o valor primitivo")
            
            # Verificar campos requeridos
            campos_requeridos = ['token', 'serie']
            for campo in campos_requeridos:
                if campo not in data:
                    raise ValueError(f"Campo requerido faltante: '{campo}'")
                if data[campo] is None:
                    raise ValueError(f"Campo '{campo}' no puede ser null")
            
            # Verificar que al menos un contador esté presente
            contadores = ['contador_bn', 'contador_color', 'contador_scan']
            tiene_contador = any(data.get(campo) is not None for campo in contadores)
            
            if not tiene_contador:
                raise ValueError("Debe proporcionar al menos un contador (contador_bn, contador_color, o contador_scan)")
            
            _logger.info("✅ Estructura JSON válida")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error en validación de estructura: {e}")
            raise

    def limpiar_string(self, valor, campo_nombre):
        """
        Limpia caracteres no permitidos de strings
        """
        try:
            if valor is None:
                return None
                
            # Convertir a string si no lo es
            valor_str = str(valor).strip()
            
            _logger.info(f"🧹 Limpiando campo '{campo_nombre}': '{valor_str}' (longitud: {len(valor_str)})")
            
            if not valor_str:
                _logger.warning(f"⚠️ Campo '{campo_nombre}' está vacío después del strip")
                return None
            
            # Para serie: permitir letras, números y algunos caracteres especiales comunes
            if campo_nombre == 'serie':
                # Permitir letras, números, guiones, puntos, pero no espacios ni saltos de línea
                valor_limpio = re.sub(r'[^a-zA-Z0-9\-._]', '', valor_str)
            else:
                # Para token y otros: solo alfanuméricos
                valor_limpio = re.sub(r'[^a-zA-Z0-9]', '', valor_str)
            
            if valor_str != valor_limpio:
                _logger.info(f"🔧 Campo '{campo_nombre}': '{valor_str}' → '{valor_limpio}'")
            
            if not valor_limpio:
                _logger.warning(f"⚠️ Campo '{campo_nombre}' quedó vacío después de limpieza")
                return None
                
            _logger.info(f"✅ Campo '{campo_nombre}' limpio: '{valor_limpio}'")
            return valor_limpio
            
        except Exception as e:
            _logger.error(f"❌ Error limpiando campo '{campo_nombre}': {e}")
            raise ValueError(f"Error al procesar el campo '{campo_nombre}': {str(e)}")

    def validar_contador(self, valor, campo_nombre):
        """
        Valida que el contador sea un número entero válido
        """
        try:
            if valor is None:
                return None
                
            _logger.info(f"🔢 Validando contador '{campo_nombre}': valor='{valor}' (tipo: {type(valor)})")
            
            # Si ya es un entero, validar rango
            if isinstance(valor, int):
                if valor < 0:
                    raise ValueError(f"El contador '{campo_nombre}' no puede ser negativo")
                if valor > 999999999:  # Límite razonable
                    raise ValueError(f"El contador '{campo_nombre}' es demasiado grande")
                _logger.info(f"✅ Contador '{campo_nombre}': {valor}")
                return valor
            
            # Si es float, convertir a int si no hay decimales
            if isinstance(valor, float):
                if valor.is_integer():
                    valor_int = int(valor)
                    return self.validar_contador(valor_int, campo_nombre)
                else:
                    raise ValueError(f"El contador '{campo_nombre}' no puede tener decimales")
            
            # Limpiar string de caracteres no numéricos
            valor_str = str(valor).strip()
            
            if not valor_str:
                raise ValueError(f"El contador '{campo_nombre}' está vacío")
            
            # Remover todos los caracteres no numéricos
            valor_limpio = re.sub(r'[^0-9]', '', valor_str)
            
            if not valor_limpio:
                raise ValueError(f"No se encontraron dígitos válidos en '{campo_nombre}'")
            
            # Evitar números que empiecen con muchos ceros
            valor_limpio = valor_limpio.lstrip('0') or '0'
            
            valor_int = int(valor_limpio)
            
            if valor_int < 0:
                raise ValueError(f"El contador '{campo_nombre}' no puede ser negativo")
            
            if valor_int > 999999999:
                raise ValueError(f"El contador '{campo_nombre}' es demasiado grande (máximo: 999,999,999)")
            
            if valor_str != str(valor_int):
                _logger.info(f"🔧 Contador '{campo_nombre}': '{valor_str}' → {valor_int}")
            
            _logger.info(f"✅ Contador '{campo_nombre}' válido: {valor_int}")
            return valor_int
            
        except ValueError:
            raise  # Re-lanzar ValueError tal como están
        except Exception as e:
            _logger.error(f"❌ Error inesperado validando contador '{campo_nombre}': {e}")
            raise ValueError(f"Error al validar el contador '{campo_nombre}': {str(e)}")

    def validar_token(self, token_recibido):
        """
        Valida el token de autenticación
        """
        try:
            _logger.info(f"🔐 Validando token...")
            
            if not token_recibido:
                raise ValueError("Token no proporcionado")
            
            # Limpiar token
            token = self.limpiar_string(token_recibido, 'token')
            if not token:
                raise ValueError("Token inválido después de limpieza")
            
            # Obtener token válido desde configuración
            token_valido = request.env['ir.config_parameter'].sudo().get_param('api.contador.token')
            
            if not token_valido:
                _logger.error("❌ Token no configurado en parámetros del sistema")
                raise ValueError("Configuración de token no encontrada en el sistema")
            
            _logger.info(f"🔑 Comparando tokens (longitudes: recibido={len(token)}, válido={len(token_valido)})")
            
            if token != token_valido:
                _logger.warning(f"❌ Token inválido: recibido='{token[:10]}...', esperado='{token_valido[:10]}...'")
                raise ValueError("Token de autenticación inválido")
            
            _logger.info("✅ Token válido")
            return token
            
        except ValueError:
            raise
        except Exception as e:
            _logger.error(f"❌ Error inesperado validando token: {e}")
            raise ValueError(f"Error en validación de token: {str(e)}")

    def buscar_equipo(self, serie):
        """
        Busca el equipo por número de serie
        """
        try:
            _logger.info(f"🔍 Buscando equipo con serie: '{serie}'")
            
            # Buscar equipo
            equipo = request.env['alquiler'].sudo().search([('serie', '=', serie)], limit=1)
            
            _logger.info(f"📊 Búsqueda completada. Equipos encontrados: {len(equipo)}")
            
            if not equipo:
                # Buscar equipos similares para sugerir
                equipos_similares = request.env['alquiler'].sudo().search([
                    '|',
                    ('serie', 'ilike', f'%{serie[:5]}%'),
                    ('serie', 'ilike', f'%{serie[-5:]}%')
                ], limit=3)
                
                sugerencias = [eq.serie for eq in equipos_similares] if equipos_similares else []
                
                mensaje = f"No se encontró ningún equipo con la serie '{serie}'"
                if sugerencias:
                    mensaje += f". Series similares encontradas: {', '.join(sugerencias)}"
                
                raise ValueError(mensaje)
            
            _logger.info(f"✅ Equipo encontrado: ID={equipo.id}")
            
            # Log información adicional del equipo si está disponible
            try:
                if hasattr(equipo, 'name'):
                    _logger.info(f"📋 Nombre del equipo: '{equipo.name}'")
                if hasattr(equipo, 'state'):
                    _logger.info(f"📊 Estado del equipo: '{equipo.state}'")
            except:
                pass  # No fallar si no podemos obtener info adicional
            
            return equipo
            
        except ValueError:
            raise
        except Exception as e:
            _logger.error(f"❌ Error buscando equipo: {e}")
            _logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            raise ValueError(f"Error al buscar equipo en la base de datos: {str(e)}")

    def actualizar_equipo(self, equipo, valores):
        """
        Actualiza los contadores del equipo
        """
        try:
            _logger.info(f"💾 Iniciando actualización del equipo ID={equipo.id}")
            _logger.info(f"📊 Valores a escribir: {valores}")
            
            # Verificar permisos antes de escribir
            if not equipo.exists():
                raise ValueError("El equipo ya no existe en la base de datos")
            
            # Realizar backup de valores actuales
            valores_actuales = {}
            for campo in valores.keys():
                if campo != 'fecha_ultima_actualizacion' and hasattr(equipo, campo):
                    try:
                        valores_actuales[campo] = getattr(equipo, campo)
                    except:
                        valores_actuales[campo] = None
            
            _logger.info(f"📋 Valores actuales: {valores_actuales}")
            
            # Realizar la actualización
            equipo.sudo().write(valores)
            
            # Verificar que se escribió correctamente
            equipo.invalidate_cache()  # Forzar recarga desde DB
            
            valores_verificacion = {}
            for campo in valores.keys():
                if campo != 'fecha_ultima_actualizacion' and hasattr(equipo, campo):
                    try:
                        valores_verificacion[campo] = getattr(equipo, campo)
                    except:
                        valores_verificacion[campo] = None
            
            _logger.info(f"✅ Valores después de actualización: {valores_verificacion}")
            _logger.info(f"🎉 Equipo actualizado exitosamente")
            
            return valores_actuales
            
        except Exception as e:
            _logger.error(f"❌ Error actualizando equipo: {e}")
            _logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            raise ValueError(f"Error al actualizar los contadores en la base de datos: {str(e)}")

    @http.route('/api/actualizar_contador', type='http', auth='public', methods=['POST'], csrf=False)
    def actualizar_contador(self, **kwargs):
        """
        Endpoint público protegido por token para actualizar contadores de una máquina en alquiler.
        
        Esperado JSON:
        {
            "token": "string",
            "serie": "string", 
            "contador_bn": int (opcional),
            "contador_color": int (opcional),
            "contador_scan": int (opcional)
        }
        """
        
        try:
            # Log de información de la petición
            self.log_request_info()
            
            # === PARSEO Y LIMPIEZA DEL JSON ===
            try:
                # Obtener datos raw
                raw_data = request.httprequest.data
                
                if not raw_data:
                    return self.crear_respuesta_error("No se recibieron datos en la petición", 400)
                
                _logger.info(f"📦 Datos raw recibidos: {raw_data}")
                _logger.info(f"📏 Tamaño de datos: {len(raw_data)} bytes")
                
                # Decodificar
                if isinstance(raw_data, bytes):
                    json_string = raw_data.decode('utf-8')
                else:
                    json_string = str(raw_data)
                
                # Limpiar JSON usando función especializada
                json_limpio = self.limpiar_json_power_automate(json_string)
                
                # Parsear JSON
                data = json.loads(json_limpio)
                _logger.info(f"✅ JSON parseado exitosamente: {data}")
                
            except UnicodeDecodeError as e:
                return self.crear_respuesta_error("Error de codificación de caracteres", 400, str(e))
            except json.JSONDecodeError as e:
                return self.crear_respuesta_error("JSON inválido", 400, f"Error de parseo: {str(e)}")
            except Exception as e:
                return self.crear_respuesta_error("Error al procesar los datos de entrada", 400, str(e))

            # === VALIDACIÓN DE ESTRUCTURA ===
            try:
                self.validar_estructura_json(data)
            except ValueError as e:
                return self.crear_respuesta_error("Estructura de datos inválida", 400, str(e))

            # === VALIDACIÓN DEL TOKEN ===
            try:
                token = self.validar_token(data.get('token'))
            except ValueError as e:
                return self.crear_respuesta_error(str(e), 401)

            # === VALIDACIÓN Y LIMPIEZA DE LA SERIE ===
            try:
                serie_raw = data.get('serie')
                _logger.info(f"📋 Serie recibida: '{serie_raw}' (tipo: {type(serie_raw)})")
                
                serie = self.limpiar_string(serie_raw, 'serie')
                if not serie:
                    return self.crear_respuesta_error("Número de serie inválido o vacío", 400)
                
            except ValueError as e:
                return self.crear_respuesta_error(str(e), 400)

            # === BÚSQUEDA DEL EQUIPO ===
            try:
                equipo = self.buscar_equipo(serie)
            except ValueError as e:
                return self.crear_respuesta_error(str(e), 404)

            # === VALIDACIÓN DE CONTADORES ===
            try:
                contador_bn_raw = data.get('contador_bn')
                contador_color_raw = data.get('contador_color')
                contador_scan_raw = data.get('contador_scan')

                _logger.info(f"📊 Contadores recibidos:")
                _logger.info(f"  - contador_bn: '{contador_bn_raw}' (tipo: {type(contador_bn_raw)})")
                _logger.info(f"  - contador_color: '{contador_color_raw}' (tipo: {type(contador_color_raw)})")
                _logger.info(f"  - contador_scan: '{contador_scan_raw}' (tipo: {type(contador_scan_raw)})")

                valores = {}
                
                # Validar cada contador
                if contador_bn_raw is not None:
                    contador_bn = self.validar_contador(contador_bn_raw, 'contador_bn')
                    if contador_bn is not None:
                        valores['contador_bn'] = contador_bn
                        
                if contador_color_raw is not None:
                    contador_color = self.validar_contador(contador_color_raw, 'contador_color')
                    if contador_color is not None:
                        valores['contador_color'] = contador_color
                        
                if contador_scan_raw is not None:
                    contador_scan = self.validar_contador(contador_scan_raw, 'contador_scan')
                    if contador_scan is not None:
                        valores['contador_scan'] = contador_scan

                if not valores:
                    return self.crear_respuesta_error(
                        "No se proporcionaron valores de contador válidos", 
                        400,
                        "Verifique que los contadores sean números enteros positivos"
                    )

                _logger.info(f"📈 Valores de contadores validados: {valores}")

            except ValueError as e:
                return self.crear_respuesta_error(str(e), 400)

            # === ACTUALIZACIÓN DEL EQUIPO ===
            try:
                # Agregar fecha de actualización
                fecha_actualizacion = fields.Datetime.now()
                valores['fecha_ultima_actualizacion'] = fecha_actualizacion
                
                _logger.info(f"⏰ Fecha de actualización: {fecha_actualizacion}")
                
                # Realizar actualización y obtener valores anteriores
                valores_anteriores = self.actualizar_equipo(equipo, valores)

            except ValueError as e:
                return self.crear_respuesta_error(str(e), 500)

            # === PREPARAR RESPUESTA EXITOSA ===
            try:
                valores_respuesta = {k: v for k, v in valores.items() if k != 'fecha_ultima_actualizacion'}
                
                respuesta_data = {
                    "message": "Contadores actualizados correctamente",
                    "serie": serie,
                    "valores_actualizados": valores_respuesta,
                    "valores_anteriores": valores_anteriores,
                    "fecha_actualizacion": fecha_actualizacion.isoformat(),
                    "equipo_id": equipo.id
                }
                
                _logger.info("🏁 === FIN EXITOSO DE PETICIÓN API CONTADOR ===")
                return self.crear_respuesta_exitosa(respuesta_data)

            except Exception as e:
                _logger.error(f"❌ Error preparando respuesta: {e}")
                return self.crear_respuesta_error("Error interno del servidor", 500, str(e))

        except Exception as e:
            # Captura cualquier error no manejado
            _logger.error(f"❌ Error crítico no manejado: {e}")
            _logger.error(f"🔍 Traceback completo: {traceback.format_exc()}")
            _logger.info("🏁 === FIN CON ERROR DE PETICIÓN API CONTADOR ===")
            
            return self.crear_respuesta_error(
                "Error interno del servidor", 
                500, 
                "Se ha producido un error inesperado. Revise los logs del servidor."
            )

    @http.route('/api/contador/health', type='http', auth='public', methods=['GET'], csrf=False)
    def health_check(self, **kwargs):
        """
        Endpoint de verificación de salud del servicio
        """
        try:
            _logger.info("🔍 Health check solicitado")
            
            # Verificar conexión a base de datos
            request.env['ir.config_parameter'].sudo().search([], limit=1)
            
            # Verificar configuración de token
            token_configurado = bool(request.env['ir.config_parameter'].sudo().get_param('api.contador.token'))
            
            respuesta = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "database": "connected",
                "token_configured": token_configurado,
                "version": "1.0.0"
            }
            
            return request.make_response(
                json.dumps(respuesta),
                headers={'Content-Type': 'application/json'},
                status=200
            )
            
        except Exception as e:
            _logger.error(f"❌ Health check falló: {e}")
            return request.make_response(
                json.dumps({
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }),
                headers={'Content-Type': 'application/json'},
                status=503
            )
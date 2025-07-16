from odoo import http, fields
from odoo.http import request
import logging
import json
import re

_logger = logging.getLogger(__name__)

class ContadorAPI(http.Controller):

   def limpiar_string(self, valor, campo_nombre):
       """
       Limpia caracteres no permitidos de strings
       """
       if valor is None:
           return None
           
       # Convertir a string si no lo es
       valor_str = str(valor).strip()
       
       # Log del valor original
       _logger.info(f"🧹 Limpiando campo '{campo_nombre}': valor original = '{valor_str}'")
       
       # Remover caracteres problemáticos: espacios, comas, comillas, caracteres especiales
       valor_limpio = re.sub(r'[^a-zA-Z0-9]', '', valor_str)
       
       _logger.info(f"✅ Campo '{campo_nombre}': valor limpio = '{valor_limpio}'")
       
       return valor_limpio if valor_limpio else None

   def validar_contador(self, valor, campo_nombre):
       """
       Valida que el contador sea un número entero válido
       """
       if valor is None:
           return None
           
       _logger.info(f"🔢 Validando contador '{campo_nombre}': valor recibido = '{valor}' (tipo: {type(valor)})")
       
       try:
           # Si ya es un entero, lo devolvemos
           if isinstance(valor, int):
               if valor < 0:
                   raise ValueError(f"El contador no puede ser negativo")
               _logger.info(f"✅ Contador '{campo_nombre}': valor válido = {valor}")
               return valor
           
           # Limpiar string de caracteres no numéricos
           valor_str = str(valor).strip()
           valor_limpio = re.sub(r'[^0-9]', '', valor_str)
           
           if not valor_limpio:
               raise ValueError(f"No se encontraron dígitos válidos")
           
           valor_int = int(valor_limpio)
           
           if valor_int < 0:
               raise ValueError(f"El contador no puede ser negativo")
           
           _logger.info(f"✅ Contador '{campo_nombre}': '{valor_str}' → {valor_int}")
           return valor_int
           
       except (ValueError, TypeError) as e:
           _logger.error(f"❌ Error validando contador '{campo_nombre}': {e}")
           raise ValueError(f"El campo '{campo_nombre}' debe ser un número entero válido")

   @http.route('/api/actualizar_contador', type='http', auth='public', methods=['POST'], csrf=False)
   def actualizar_contador(self, **kwargs):
       """
       Endpoint público protegido por token para actualizar contadores de una máquina en alquiler.
       """
       
       _logger.info("🚀 === INICIO DE PETICIÓN API CONTADOR ===")
       _logger.info(f"📊 Método: {request.httprequest.method}")
       _logger.info(f"🌐 URL: {request.httprequest.url}")
       _logger.info(f"📍 IP Cliente: {request.httprequest.remote_addr}")
       _logger.info(f"🔗 Headers: {dict(request.httprequest.headers)}")
       
       # Leer el JSON del cuerpo de la petición
       try:
           # Obtener datos raw
           raw_data = request.httprequest.data
           _logger.info(f"📦 Datos raw recibidos: {raw_data}")
           _logger.info(f"📏 Tamaño de datos: {len(raw_data)} bytes")
           
           # Decodificar
           if isinstance(raw_data, bytes):
               json_string = raw_data.decode('utf-8')
           else:
               json_string = str(raw_data)
           
           _logger.info(f"📄 JSON string decodificado: '{json_string}'")
           
           # Limpiar caracteres de control problemáticos pero mantener estructura JSON
           json_limpio = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', json_string)
           json_limpio = json_limpio.strip()
           
           if json_string != json_limpio:
               _logger.warning(f"🧹 JSON limpiado: '{json_limpio}'")
           
           # Parsear JSON
           data = json.loads(json_limpio)
           _logger.info(f"✅ JSON parseado exitosamente: {data}")
           
       except UnicodeDecodeError as e:
           _logger.error(f"❌ Error de encoding: {e}")
           return request.make_response(
               json.dumps({"error": "Error de codificación de caracteres"}),
               headers={'Content-Type': 'application/json'},
               status=400
           )
       except json.JSONDecodeError as e:
           _logger.error(f"❌ Error al parsear JSON: {e}")
           _logger.error(f"📄 Datos problemáticos: {json_limpio if 'json_limpio' in locals() else raw_data}")
           return request.make_response(
               json.dumps({"error": f"JSON inválido: {str(e)}"}),
               headers={'Content-Type': 'application/json'},
               status=400
           )
       except Exception as e:
           _logger.error(f"❌ Error general al procesar datos: {e}")
           return request.make_response(
               json.dumps({"error": "Error al procesar la petición"}),
               headers={'Content-Type': 'application/json'},
               status=400
           )

       # Extraer y validar campos principales
       token_raw = data.get('token')
       serie_raw = data.get('serie')
       
       _logger.info(f"🔑 Token recibido: '{token_raw}' (tipo: {type(token_raw)})")
       _logger.info(f"📋 Serie recibida: '{serie_raw}' (tipo: {type(serie_raw)})")

       # Validar token
       if not token_raw:
           _logger.warning("❌ Token no proporcionado")
           return request.make_response(
               json.dumps({"error": "Token requerido"}),
               headers={'Content-Type': 'application/json'},
               status=401
           )

       # Limpiar token
       token = self.limpiar_string(token_raw, 'token')
       if not token:
           _logger.warning("❌ Token vacío después de limpieza")
           return request.make_response(
               json.dumps({"error": "Token inválido"}),
               headers={'Content-Type': 'application/json'},
               status=401
           )

       # Validar token dinámico desde parámetros del sistema
       try:
           token_valido = request.env['ir.config_parameter'].sudo().get_param('api.contador.token')
           _logger.info(f"🔐 Token válido configurado: '{token_valido}'")
           
           if not token_valido:
               _logger.error("❌ Token no configurado en parámetros del sistema")
               return request.make_response(
                   json.dumps({"error": "Configuración de token no encontrada"}),
                   headers={'Content-Type': 'application/json'},
                   status=500
               )
               
           if token != token_valido:
               _logger.warning(f"❌ Token inválido: recibido='{token}', esperado='{token_valido}'")
               return request.make_response(
                   json.dumps({"error": "Token inválido"}),
                   headers={'Content-Type': 'application/json'},
                   status=401
               )
               
           _logger.info("✅ Token válido")
           
       except Exception as e:
           _logger.error(f"❌ Error al validar token: {e}")
           return request.make_response(
               json.dumps({"error": "Error en validación de token"}),
               headers={'Content-Type': 'application/json'},
               status=500
           )

       # Validar serie
       if not serie_raw:
           _logger.warning("❌ Serie no proporcionada")
           return request.make_response(
               json.dumps({"error": "Número de serie requerido"}),
               headers={'Content-Type': 'application/json'},
               status=400
           )

       # Limpiar serie
       serie = self.limpiar_string(serie_raw, 'serie')
       if not serie:
           _logger.warning("❌ Serie vacía después de limpieza")
           return request.make_response(
               json.dumps({"error": "Número de serie inválido"}),
               headers={'Content-Type': 'application/json'},
               status=400
           )

       _logger.info(f"🔍 Buscando equipo con serie: '{serie}'")

       # Buscar el equipo en alquiler por número de serie
       try:
           equipo = request.env['alquiler'].sudo().search([('serie', '=', serie)], limit=1)
           _logger.info(f"🔍 Búsqueda completada. Equipos encontrados: {len(equipo)}")
           
       except Exception as e:
           _logger.error(f"❌ Error al buscar equipo: {e}")
           return request.make_response(
               json.dumps({"error": "Error al buscar equipo"}),
               headers={'Content-Type': 'application/json'},
               status=500
           )

       if not equipo:
           _logger.warning(f"❌ No se encontró equipo con serie: '{serie}'")
           return request.make_response(
               json.dumps({"error": f"No se encontró ningún equipo con la serie '{serie}'"}),
               headers={'Content-Type': 'application/json'},
               status=404
           )

       _logger.info(f"✅ Equipo encontrado: ID={equipo.id}, Nombre='{equipo.name if hasattr(equipo, 'name') else 'N/A'}'")

       # Obtener y validar contadores
       contador_bn_raw = data.get('contador_bn')
       contador_color_raw = data.get('contador_color')
       contador_scan_raw = data.get('contador_scan')

       _logger.info(f"📊 Contadores recibidos:")
       _logger.info(f"  - contador_bn: '{contador_bn_raw}' (tipo: {type(contador_bn_raw)})")
       _logger.info(f"  - contador_color: '{contador_color_raw}' (tipo: {type(contador_color_raw)})")
       _logger.info(f"  - contador_scan: '{contador_scan_raw}' (tipo: {type(contador_scan_raw)})")

       valores = {}
       
       # Validar y convertir contadores
       try:
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
                   
       except ValueError as e:
           _logger.error(f"❌ Error en validación de contadores: {e}")
           return request.make_response(
               json.dumps({"error": str(e)}),
               headers={'Content-Type': 'application/json'},
               status=400
           )

       if not valores:
           _logger.warning("❌ No se proporcionaron valores de contador válidos")
           return request.make_response(
               json.dumps({"error": "No se proporcionaron valores de contador válidos"}),
               headers={'Content-Type': 'application/json'},
               status=400
           )

       _logger.info(f"📈 Valores de contadores validados: {valores}")

       # Agregar fecha de actualización
       fecha_actualizacion = fields.Datetime.now()
       valores['fecha_ultima_actualizacion'] = fecha_actualizacion
       
       _logger.info(f"⏰ Fecha de actualización: {fecha_actualizacion}")
       _logger.info(f"💾 Valores finales a escribir: {valores}")

       # Actualizar el equipo
       try:
           _logger.info(f"💾 Iniciando actualización del equipo ID={equipo.id}")
           equipo.sudo().write(valores)
           _logger.info(f"✅ Equipo actualizado exitosamente")
           
       except Exception as e:
           _logger.error(f"❌ Error al actualizar equipo: {e}")
           _logger.error(f"🔍 Detalles del error: {type(e).__name__}: {str(e)}")
           return request.make_response(
               json.dumps({"error": "Error interno al actualizar los contadores"}),
               headers={'Content-Type': 'application/json'},
               status=500
           )

       # Preparar respuesta exitosa
       valores_respuesta = {k: v for k, v in valores.items() if k != 'fecha_ultima_actualizacion'}
       
       respuesta = {
           "status": "success",
           "message": "Contadores actualizados correctamente",
           "serie": serie,
           "valores_actualizados": valores_respuesta,
           "fecha_actualizacion": fecha_actualizacion.isoformat()
       }
       
       _logger.info(f"🎉 Respuesta exitosa preparada: {respuesta}")
       _logger.info("🏁 === FIN DE PETICIÓN API CONTADOR ===")
       
       return request.make_response(
           json.dumps(respuesta),
           headers={'Content-Type': 'application/json'},
           status=200
       )
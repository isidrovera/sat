from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import requests
import time
import base64
import json
import io
import zipfile
import re
import mimetypes
from datetime import datetime
import hashlib
import magic

_logger = logging.getLogger(__name__)

class ReparacionFoto(models.Model):
    _name = 'reparaciones.foto'
    _description = 'Fotos de Reparaciones'
    _order = 'sequence, create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Nombre", compute='_compute_name', store=True)
    nombre_foto = fields.Char(string="Nombre Original", required=True, tracking=True)
    url_foto = fields.Char(string="URL de Foto", tracking=True)
    foto_binario = fields.Binary(string="Subir Foto", attachment=True)
    mimetype = fields.Char(string="Tipo de Archivo", compute='_compute_mimetype', store=True)
    size = fields.Integer(string="Tamaño (bytes)", readonly=True)
    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', 
        string="Reparación",
        required=True,
        index=True,
        ondelete='cascade',
        tracking=True
    )
    file_id = fields.Char(string="File ID pCloud", index=True, tracking=True)
    public_link = fields.Char(string="Link Público", tracking=True)
    thumb_url = fields.Char(string="Thumbnail URL", tracking=True)
    sequence = fields.Integer(string="Secuencia", default=0)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('uploading', 'Subiendo'),
        ('done', 'Completado'),
        ('error', 'Error'),
        ('deleted', 'Eliminado')
    ], string="Estado", default='draft', tracking=True)
    active = fields.Boolean('Activo', default=True, tracking=True)
    create_date = fields.Datetime('Fecha de Creación', readonly=True)
    write_date = fields.Datetime('Última Modificación', readonly=True)
    share_count = fields.Integer(string="Veces Compartido", default=0)
    download_count = fields.Integer(string="Descargas", default=0)
    unique_id = fields.Char(string="ID Único", readonly=True)

    _sql_constraints = [
        ('unique_sequence_per_repair', 
         'UNIQUE(reparacion_id, sequence)',
         'La secuencia debe ser única por reparación'),
        ('unique_file_name',
         'UNIQUE(reparacion_id, unique_id)',
         'El nombre del archivo debe ser único por reparación')
    ]

    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            _logger.info("[CREATE] Iniciando creación de foto con valores: %s", vals)

            if 'reparacion_id' in vals and 'sequence' not in vals:
                self.env.cr.execute(
                    "SELECT id FROM reparaciones_reparaciones WHERE id = %s FOR UPDATE",
                    [vals['reparacion_id']]
                )
                existing_photos = self.search([
                    ('reparacion_id', '=', vals['reparacion_id'])
                ], order='sequence desc', limit=1)
                vals['sequence'] = (existing_photos.sequence or 0) + 1
                _logger.info("[CREATE] Asignada secuencia: %s", vals['sequence'])

            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            random_string = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:6]
            vals['unique_id'] = f"{timestamp}_{random_string}"
            _logger.info("[CREATE] Generado ID único: %s", vals['unique_id'])

            if 'foto_binario' in vals:
                try:
                    vals['state'] = 'uploading'
                    reparacion = self.env['reparaciones.reparaciones'].browse(vals['reparacion_id'])
                    if not reparacion:
                        _logger.error("[CREATE] No se encontró la reparación: %s", vals['reparacion_id'])
                        raise ValidationError("No se encontró la reparación relacionada")

                    archivo_binario = base64.b64decode(vals['foto_binario'])
                    vals['size'] = len(archivo_binario)

                    pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
                    if not pcloud_config or not pcloud_config.access_token:
                        _logger.error("[CREATE] No se encontró configuración de pCloud válida")
                        raise ValidationError("Configuración de pCloud no encontrada")

                    folder_id = self._obtener_folder_id(reparacion, pcloud_config)
                    _logger.info("[CREATE] Carpeta pCloud obtenida: %s", folder_id)

                    result = self._upload_to_pcloud(
                        archivo_binario,
                        vals['nombre_foto'],
                        folder_id,
                        pcloud_config
                    )

                    if result:
                        vals.update({
                            'file_id': result['file_id'],
                            'url_foto': result['url'],
                            'public_link': result.get('public_link'),
                            'thumb_url': result.get('thumb_url'),
                            'state': 'done',
                            'size': result.get('size', vals['size']),
                            'mimetype': result.get('content_type', 'application/octet-stream')
                        })
                        del vals['foto_binario']
                    else:
                        vals['state'] = 'error'
                        raise ValidationError("Error al subir la foto a pCloud")

                except Exception as e:
                    _logger.exception("[CREATE] Error durante la creación: %s", str(e))
                    vals['state'] = 'error'
                    raise ValidationError(f"Error al subir la foto: {str(e)}")

        return super().create(vals_list)
    
    def upload_to_pcloud(self):
        pcloud_config = self.env['pcloud.configuracion'].sudo().search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            raise ValidationError("No se encontró configuración de pCloud")

        folder_id = self._obtener_folder_id(self.reparacion_id, pcloud_config)
        archivo_binario = base64.b64decode(self.foto_binario)
        
        result = self._upload_to_pcloud(archivo_binario, self.nombre_foto, folder_id, pcloud_config)
        if result and result.get('file_id'):
            self.write({
                'file_id': result['file_id'],
                'url_foto': result['url'],
                'public_link': result.get('public_link'),
                'state': 'done'
            })
        else:
            self.state = 'error'
            raise ValidationError("Error al subir la foto a pCloud")


    def _get_pcloud_url(self, endpoint, file_id, pcloud_config, extra_params=None):
        """Método base para obtener URLs de pCloud"""
        _logger.info("[PCLOUD_URL] Solicitando URL para endpoint: %s, file_id: %s", endpoint, file_id)
        
        if not file_id or not pcloud_config or not pcloud_config.access_token:
            _logger.error("[PCLOUD_URL] Faltan parámetros necesarios")
            return False

        try:
            url = f"{pcloud_config.hostname}/{endpoint}"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id
            }
            if extra_params:
                params.update(extra_params)

            _logger.info("[PCLOUD_URL] Enviando solicitud: %s con params: %s", url, params)
            response = requests.get(url, params=params)
            result = response.json()
            _logger.info("[PCLOUD_URL] Respuesta: %s", result)

            if response.status_code == 200 and result.get('result') == 0:
                final_url = f"https://{result['hosts'][0]}{result['path']}"
                _logger.info("[PCLOUD_URL] URL generada: %s", final_url)
                return final_url

            _logger.error("[PCLOUD_URL] Error en respuesta: %s", result)
            return False

        except Exception as e:
            _logger.exception("[PCLOUD_URL] Error: %s", str(e))
            return False

    def _get_thumb_url(self, file_id, pcloud_config):
        """Obtiene la URL del thumbnail usando getthumblink de pCloud."""
        _logger.info("[THUMB_URL] Solicitando thumbnail para file_id: %s", file_id)
        try:
            url = f"{pcloud_config.hostname}/getthumblink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id,
                'size': '256x256',  # Tamaño de la miniatura
                'crop': 1  # Forzar tamaño exacto
            }
            response = requests.get(url, params=params)
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                thumb_url = f"https://{result['hosts'][0]}{result['path']}"
                _logger.info("[THUMB_URL] URL generada para thumbnail: %s", thumb_url)
                return thumb_url
            else:
                _logger.error("[THUMB_URL] Error en respuesta: %s", result)
                return None

        except Exception as e:
            _logger.exception("[THUMB_URL] Error al obtener thumbnail para file_id %s: %s", file_id, str(e))
            return None



    def _get_file_url(self, file_id, pcloud_config):
        """Obtiene la URL de descarga del archivo en pCloud."""
        _logger.info("[FILE_URL] Solicitando URL de archivo para file_id: %s", file_id)
        try:
            url = f"{pcloud_config.hostname}/getfilelink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id
            }
            response = requests.get(url, params=params)
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                file_url = f"https://{result['hosts'][0]}{result['path']}"
                _logger.info("[FILE_URL] URL generada para archivo: %s", file_url)
                return file_url
            else:
                _logger.error("[FILE_URL] Error en respuesta: %s", result)
                return None

        except Exception as e:
            _logger.exception("[FILE_URL] Error al obtener URL de archivo para file_id %s: %s", file_id, str(e))
            return None
    def _create_public_link(self, file_id, pcloud_config):
        """Crear link público para compartir"""
        _logger.info("[PUBLIC_LINK] Creando link público para file_id: %s", file_id)
        try:
            url = f"{pcloud_config.hostname}/getfilepublink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id
            }

            _logger.info("[PUBLIC_LINK] Enviando solicitud: %s", url)
            response = requests.get(url, params=params)
            result = response.json()
            _logger.info("[PUBLIC_LINK] Respuesta: %s", result)

            if response.status_code == 200 and result.get('link'):
                _logger.info("[PUBLIC_LINK] Link creado: %s", result['link'])
                return result['link']

            _logger.error("[PUBLIC_LINK] Error en respuesta: %s", result)
            return False

        except Exception as e:
            _logger.exception("[PUBLIC_LINK] Error: %s", str(e))
            return False

    @api.model
    def get_photos_preview(self, reparacion_id):
        """
        Obtiene las fotos de una reparación de forma optimizada.
        No realiza llamadas a pCloud por cada foto.
        Utiliza las URLs almacenadas en la base de datos.
        """

        _logger.info("[GET_PHOTOS_PREVIEW] === INICIANDO CARGA OPTIMIZADA (MODO RÁPIDO) ===")
        _logger.info("[GET_PHOTOS_PREVIEW] Reparación ID: %s", reparacion_id)

        try:
            # Buscar fotos
            fotos = self.search(
                [('reparacion_id', '=', reparacion_id)],
                order='sequence asc, create_date asc'
            )

            total_fotos = len(fotos)
            _logger.info("[GET_PHOTOS_PREVIEW] Total de fotos encontradas: %s", total_fotos)

            if not fotos:
                _logger.info("[GET_PHOTOS_PREVIEW] No se encontraron fotos para la reparación")
                return []

            result = []
            successful_loads = 0
            fallback_loads = 0

            for index, foto in enumerate(fotos, 1):

                _logger.info(
                    "[GET_PHOTOS_PREVIEW] 📸 Procesando foto %s/%s - ID: %s",
                    index, total_fotos, foto.id
                )

                # Datos base
                foto_data = {
                    'id': foto.id,
                    'nombre_foto': foto.nombre_foto or f'foto_{foto.id}',
                    'sequence': foto.sequence or 0,
                    'file_id': foto.file_id,
                    'fecha_creacion': foto.create_date.strftime('%Y-%m-%d %H:%M:%S')
                        if foto.create_date else None,
                }

                try:

                    # ------------------------------------
                    # Usar thumbnail guardado si existe
                    # ------------------------------------
                    if getattr(foto, 'thumb_url', None):

                        foto_data['thumb_url'] = foto.thumb_url
                        successful_loads += 1

                        _logger.info(
                            "[GET_PHOTOS_PREVIEW] ✅ Thumbnail desde BD para foto %s",
                            foto.id
                        )

                    else:

                        # fallback al endpoint local
                        foto_data['thumb_url'] = f'/gallery/preview/{foto.id}'
                        fallback_loads += 1

                        _logger.warning(
                            "[GET_PHOTOS_PREVIEW] ⚠️ Thumbnail no almacenado para foto %s, usando fallback",
                            foto.id
                        )

                    # siempre descargar vía endpoint local
                    foto_data['download_url'] = f'/gallery/download/{foto.id}'

                    _logger.info(
                        "[GET_PHOTOS_PREVIEW] 📥 URL de descarga asignada: /gallery/download/%s",
                        foto.id
                    )

                except Exception as e:

                    _logger.error(
                        "[GET_PHOTOS_PREVIEW] ❌ Error procesando foto %s: %s",
                        foto.id, str(e)
                    )

                    foto_data['thumb_url'] = f'/gallery/preview/{foto.id}'
                    foto_data['download_url'] = f'/gallery/download/{foto.id}'
                    fallback_loads += 1

                result.append(foto_data)

                # progreso cada 5 fotos
                if index % 5 == 0 or index == total_fotos:

                    _logger.info(
                        "[GET_PHOTOS_PREVIEW] 📊 Progreso: %s/%s fotos (%s BD, %s fallback)",
                        index,
                        total_fotos,
                        successful_loads,
                        fallback_loads
                    )

            _logger.info("[GET_PHOTOS_PREVIEW] === CARGA COMPLETADA ===")
            _logger.info(
                "[GET_PHOTOS_PREVIEW] Fotos desde BD: %s | fallback: %s",
                successful_loads,
                fallback_loads
            )

            return result

        except Exception as e:

            _logger.exception(
                "[GET_PHOTOS_PREVIEW] ❌ ERROR CRÍTICO: %s",
                str(e)
            )

            # fallback completo
            try:

                fotos = self.search(
                    [('reparacion_id', '=', reparacion_id)],
                    order='sequence asc, create_date asc'
                )

                result = []

                for foto in fotos:

                    result.append({
                        'id': foto.id,
                        'nombre_foto': foto.nombre_foto or f'foto_{foto.id}',
                        'sequence': foto.sequence or 0,
                        'file_id': foto.file_id,
                        'thumb_url': f'/gallery/preview/{foto.id}',
                        'download_url': f'/gallery/download/{foto.id}',
                        'fecha_creacion': foto.create_date.strftime('%Y-%m-%d %H:%M:%S')
                            if foto.create_date else None,
                    })

                _logger.warning(
                    "[GET_PHOTOS_PREVIEW] 🔄 Recuperación fallback con %s fotos",
                    len(result)
                )

                return result

            except Exception as fallback_error:

                _logger.exception(
                    "[GET_PHOTOS_PREVIEW] ❌ Error en recuperación: %s",
                    str(fallback_error)
                )

                return []
    def _get_thumb_url_with_timeout(self, file_id, pcloud_config, timeout=2):
        """Obtiene thumbnail URL con timeout específico y manejo robusto de errores"""
        start_time = time.time()
        _logger.info("[THUMB_TIMEOUT] 🔄 Solicitando thumbnail para file_id: %s (timeout: %ss)", 
                    file_id, timeout)
        
        try:
            if not pcloud_config or not pcloud_config.access_token:
                _logger.error("[THUMB_TIMEOUT] ❌ No hay token de acceso disponible")
                return None
            
            url = f"https://api.pcloud.com/getthumblink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id,
                'size': '320x240',
                'crop': 0,
                'type': 'auto'
            }
            
            _logger.debug("[THUMB_TIMEOUT] 📡 Enviando request a pCloud: %s", url)
            
            # Request con timeout muy corto y configuración optimizada
            import requests
            
            # Configurar session para mejor performance
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Odoo-Gallery/1.0',
                'Accept': 'application/json',
                'Connection': 'keep-alive'
            })
            
            response = session.get(url, params=params, timeout=timeout, stream=False)
            request_time = time.time() - start_time
            
            _logger.debug("[THUMB_TIMEOUT] 📡 Response status: %s en %.2fs", response.status_code, request_time)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    _logger.debug("[THUMB_TIMEOUT] 📄 Respuesta JSON: %s", data)
                    
                    if data.get('result') == 0 and 'hosts' in data and 'path' in data:
                        thumb_url = f"https://{data['hosts'][0]}{data['path']}"
                        _logger.info("[THUMB_TIMEOUT] ✅ URL generada exitosamente en %.2fs: %s", 
                                request_time, thumb_url[:100] + "..." if len(thumb_url) > 100 else thumb_url)
                        return thumb_url
                    else:
                        error_msg = data.get('error', 'Respuesta inválida de pCloud')
                        _logger.error("[THUMB_TIMEOUT] ❌ Error en respuesta pCloud: %s", error_msg)
                        return None
                        
                except ValueError as json_error:
                    _logger.error("[THUMB_TIMEOUT] ❌ Error parsing JSON: %s", str(json_error))
                    _logger.error("[THUMB_TIMEOUT] Response text: %s", response.text[:200])
                    return None
            else:
                _logger.error("[THUMB_TIMEOUT] ❌ HTTP Error %s en %.2fs", response.status_code, request_time)
                return None
                
        except requests.exceptions.Timeout:
            timeout_time = time.time() - start_time
            _logger.error("[THUMB_TIMEOUT] ⏱️ TIMEOUT después de %.2fs para file_id: %s", timeout_time, file_id)
            return None
            
        except requests.exceptions.ConnectionError as conn_error:
            error_time = time.time() - start_time
            _logger.error("[THUMB_TIMEOUT] 🌐 ERROR DE CONEXIÓN en %.2fs: %s", error_time, str(conn_error))
            return None
            
        except requests.exceptions.RequestException as req_error:
            error_time = time.time() - start_time
            _logger.error("[THUMB_TIMEOUT] 📡 ERROR DE REQUEST en %.2fs: %s", error_time, str(req_error))
            return None
            
        except Exception as e:
            error_time = time.time() - start_time
            _logger.exception("[THUMB_TIMEOUT] ❌ ERROR INESPERADO en %.2fs: %s", error_time, str(e))
            return None

    def _get_fallback_photos_data(self, fotos):
        """Genera datos de fotos usando solo endpoints locales como fallback"""
        _logger.info("[FALLBACK_DATA] 🔄 Generando datos fallback para %s fotos", len(fotos))
        
        try:
            result = []
            for foto in fotos:
                foto_data = {
                    'id': foto.id,
                    'nombre_foto': foto.nombre_foto or f'foto_{foto.id}',
                    'sequence': foto.sequence or 0,
                    'file_id': foto.file_id,
                    'thumb_url': f'/gallery/preview/{foto.id}',
                    'download_url': f'/gallery/download/{foto.id}',
                    'fecha_creacion': foto.create_date.strftime('%Y-%m-%d %H:%M:%S') if foto.create_date else None,
                }
                result.append(foto_data)
                _logger.debug("[FALLBACK_DATA] ✅ Datos fallback para foto ID: %s", foto.id)
            
            _logger.info("[FALLBACK_DATA] ✅ Datos fallback generados para %s fotos", len(result))
            return result
            
        except Exception as e:
            _logger.exception("[FALLBACK_DATA] ❌ Error generando datos fallback: %s", str(e))
            return []

    def download_photo(self):
        """Descargar foto individual"""
        self.ensure_one()
        _logger.info("[DOWNLOAD] Iniciando descarga de foto %s", self.id)

        if not self.file_id:
            _logger.error("[DOWNLOAD] No hay file_id para foto %s", self.id)
            return False

        try:
            pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
            if not pcloud_config:
                _logger.error("[DOWNLOAD] No se encontró configuración de pCloud")
                return False

            download_url = self._get_file_url(self.file_id, pcloud_config)
            
            if download_url:
                self.download_count += 1
                _logger.info("[DOWNLOAD] Incrementado contador de descargas para foto %s", self.id)
                return {
                    'type': 'ir.actions.act_url',
                    'url': download_url,
                    'target': 'self',
                }
            
            _logger.error("[DOWNLOAD] No se pudo obtener URL de descarga para foto %s", self.id)
            return False

        except Exception as e:
            _logger.exception("[DOWNLOAD] Error al descargar foto %s: %s", self.id, str(e))
            return False

    @api.model
    def download_multiple(self, ids):
        """Descargar múltiples fotos en ZIP"""
        _logger.info("[DOWNLOAD_MULTIPLE] Iniciando descarga múltiple para fotos: %s", ids)
        
        fotos = self.browse(ids)
        if not fotos:
            _logger.warning("[DOWNLOAD_MULTIPLE] No se encontraron fotos para descargar")
            return False

        try:
            _logger.info("[DOWNLOAD_MULTIPLE] Creando archivo ZIP")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
                if not pcloud_config:
                    _logger.error("[DOWNLOAD_MULTIPLE] No se encontró configuración de pCloud")
                    return False

                for foto in fotos:
                    if foto.file_id:
                        try:
                            download_url = self._get_file_url(foto.file_id, pcloud_config)
                            if download_url:
                                _logger.info("[DOWNLOAD_MULTIPLE] Descargando foto %s", foto.id)
                                response = requests.get(download_url)
                                if response.status_code == 200:
                                    zip_file.writestr(foto.nombre_foto, response.content)
                                    foto.download_count += 1
                                    _logger.info("[DOWNLOAD_MULTIPLE] Foto %s añadida al ZIP", foto.id)
                                else:
                                    _logger.warning("[DOWNLOAD_MULTIPLE] Error al descargar foto %s: %s", 
                                                  foto.id, response.status_code)
                        except Exception as e:
                            _logger.error("[DOWNLOAD_MULTIPLE] Error procesando foto %s: %s", foto.id, str(e))
                            continue

            _logger.info("[DOWNLOAD_MULTIPLE] Creando adjunto temporal")
            zip_buffer.seek(0)
            attachment = self.env['ir.attachment'].create({
                'name': f'fotos_reparacion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
                'type': 'binary',
                'datas': base64.b64encode(zip_buffer.getvalue()),
                'mimetype': 'application/zip',
            })

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'self',
            }

        except Exception as e:
            _logger.exception("[DOWNLOAD_MULTIPLE] Error general: %s", str(e))
            return False

    def unlink(self):
        """Sobrescribir unlink para eliminar archivo de pCloud"""
        _logger.info("[UNLINK] Iniciando eliminación de fotos: %s", self.ids)
        
        for foto in self:
            try:
                if foto.file_id:
                    pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
                    if self._delete_from_pcloud(foto.file_id, pcloud_config):
                        _logger.info("[UNLINK] Archivo eliminado de pCloud: %s", foto.id)
                    else:
                        _logger.warning("[UNLINK] No se pudo eliminar archivo de pCloud: %s", foto.id)
            except Exception as e:
                _logger.error("[UNLINK] Error al eliminar archivo de pCloud %s: %s", foto.id, str(e))

        return super(ReparacionFoto, self).unlink()

    def _delete_from_pcloud(self, file_id, pcloud_config):
        """Eliminar archivo de pCloud"""
        _logger.info("[DELETE_PCLOUD] Iniciando eliminación de archivo %s", file_id)
        
        try:
            url = f"{pcloud_config.hostname}/deletefile"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id
            }

            _logger.info("[DELETE_PCLOUD] Enviando solicitud: %s", url)
            response = requests.get(url, params=params)
            result = response.json()
            _logger.info("[DELETE_PCLOUD] Respuesta: %s", result)

            if response.status_code != 200 or result.get('result') != 0:
                _logger.error("[DELETE_PCLOUD] Error al eliminar archivo: %s", result)
                return False

            _logger.info("[DELETE_PCLOUD] Archivo eliminado exitosamente")
            return True

        except Exception as e:
            _logger.exception("[DELETE_PCLOUD] Error: %s", str(e))
            return False

    @api.depends('nombre_foto')
    def _compute_name(self):
        """Computar nombre basado en secuencia y extensión original"""
        for foto in self:
            if foto.nombre_foto and foto.sequence:
                extension = ''
                ext_match = re.search(r'\.[^.]+$', foto.nombre_foto)
                if ext_match:
                    extension = ext_match.group(0)
                foto.name = f"image{foto.sequence}{extension}"
                _logger.debug("[COMPUTE_NAME] Nombre generado para foto %s: %s", foto.id, foto.name)
            else:
                foto.name = foto.nombre_foto or ''

    @api.depends('nombre_foto')
    def _compute_mimetype(self):
        """Computar el tipo MIME basado en la extensión"""
        for foto in self:
            if foto.nombre_foto:
                mime_type, _ = mimetypes.guess_type(foto.nombre_foto)
                foto.mimetype = mime_type or 'application/octet-stream'
                _logger.debug("[COMPUTE_MIME] Tipo MIME detectado para foto %s: %s", 
                            foto.id, foto.mimetype)
            else:
                foto.mimetype = 'application/octet-stream'

    def _obtener_folder_id(self, reparacion, pcloud_config):
        """Método para obtener o crear el folder ID"""

        # -------------------------------------------------
        # 1️⃣ Usar folder_id guardado si ya existe
        # -------------------------------------------------
        if reparacion.pcloud_folder_id:
            _logger.info(
                "[GET_FOLDER] Usando folder_id almacenado en reparación: %s",
                reparacion.pcloud_folder_id
            )
            return reparacion.pcloud_folder_id

        _logger.info(
            "[GET_FOLDER] No existe folder_id almacenado, buscando/creando carpeta en pCloud"
        )

        folder_name = f"{reparacion.maquina_id.name.name}_{reparacion.serie_id or 'sin_serie'}"
        _logger.info("[GET_FOLDER] Buscando/creando carpeta: %s", folder_name)

        try:
            folders = {
                'root': {'id': 0, 'name': 'root'},
                'fotos': {'name': 'fotos_reparaciones'},
                'maquina': {'name': folder_name}
            }

            # -------------------------------------------------
            # 2️⃣ Obtener/crear carpeta fotos_reparaciones
            # -------------------------------------------------
            folders['fotos']['id'] = self._get_or_create_folder(
                folders['fotos']['name'],
                folders['root']['id'],
                pcloud_config
            )

            if not folders['fotos']['id']:
                _logger.error("[GET_FOLDER] Error al crear carpeta fotos_reparaciones")
                raise ValidationError("Error al crear carpeta fotos_reparaciones")

            # -------------------------------------------------
            # 3️⃣ Obtener/crear carpeta de la máquina
            # -------------------------------------------------
            folders['maquina']['id'] = self._get_or_create_folder(
                folders['maquina']['name'],
                folders['fotos']['id'],
                pcloud_config
            )

            if not folders['maquina']['id']:
                _logger.error("[GET_FOLDER] Error al crear carpeta %s", folder_name)
                raise ValidationError(f"Error al crear carpeta {folder_name}")

            folder_id = folders['maquina']['id']

            _logger.info("[GET_FOLDER] Carpeta creada/obtenida con ID: %s", folder_id)

            # -------------------------------------------------
            # 4️⃣ Guardar folder_id en la reparación
            # -------------------------------------------------
            reparacion.write({
                'pcloud_folder_id': str(folder_id)
            })

            _logger.info(
                "[GET_FOLDER] folder_id guardado en reparación %s: %s",
                reparacion.id,
                folder_id
            )

            return folder_id

        except Exception as e:
            _logger.exception("[GET_FOLDER] Error: %s", str(e))
            raise ValidationError(f"Error al obtener/crear carpetas: {str(e)}")

    def _get_or_create_folder(self, folder_name, parent_id, pcloud_config):
        """Obtiene o crea una carpeta en pCloud"""
        _logger.info("[GET_OR_CREATE] Buscando/creando carpeta '%s' en padre %s", 
                    folder_name, parent_id)

        try:
            # -----------------------------
            # 1️⃣ Listar carpetas existentes
            # -----------------------------
            list_url = f"{pcloud_config.hostname}/listfolder"
            params = {
                'access_token': pcloud_config.access_token,
                'folderid': parent_id
            }

            _logger.info("[GET_OR_CREATE] Listando carpetas en parent_id=%s", parent_id)

            response = requests.get(list_url, params=params, timeout=15)

            _logger.info("[GET_OR_CREATE] HTTP Status listfolder: %s", response.status_code)

            result = response.json()
            _logger.debug("[GET_OR_CREATE] Respuesta listfolder: %s", result)

            if response.status_code == 200 and result.get('result') == 0:

                contents = result.get('metadata', {}).get('contents', [])

                for folder in contents:
                    if folder.get('isfolder') and folder.get('name') == folder_name:
                        folder_id = folder.get('folderid')
                        _logger.info(
                            "[GET_OR_CREATE] Carpeta encontrada '%s' con ID: %s",
                            folder_name,
                            folder_id
                        )
                        return folder_id

            else:
                _logger.warning(
                    "[GET_OR_CREATE] Error al listar carpeta padre %s -> %s",
                    parent_id,
                    result
                )

            # -----------------------------
            # 2️⃣ Crear carpeta
            # -----------------------------
            _logger.info("[GET_OR_CREATE] Carpeta '%s' no existe, creando...", folder_name)

            create_url = f"{pcloud_config.hostname}/createfolder"

            create_params = {
                'access_token': pcloud_config.access_token,
                'name': folder_name,
                'folderid': parent_id
            }

            create_response = requests.get(create_url, params=create_params, timeout=15)

            _logger.info("[GET_OR_CREATE] HTTP Status createfolder: %s", create_response.status_code)

            create_result = create_response.json()

            _logger.debug("[GET_OR_CREATE] Respuesta createfolder: %s", create_result)

            # -----------------------------
            # 3️⃣ Carpeta creada correctamente
            # -----------------------------
            if create_result.get('result') == 0:

                folder_id = create_result['metadata']['folderid']

                _logger.info(
                    "[GET_OR_CREATE] Carpeta creada exitosamente '%s' con ID: %s",
                    folder_name,
                    folder_id
                )

                return folder_id

            # -----------------------------
            # 4️⃣ Carpeta ya existe (ERROR 2004)
            # -----------------------------
            if create_result.get('result') == 2004:

                _logger.warning(
                    "[GET_OR_CREATE] Carpeta '%s' ya existe (result=2004). Buscando nuevamente...",
                    folder_name
                )

                # Volver a listar carpeta
                retry_response = requests.get(list_url, params=params, timeout=15)

                retry_result = retry_response.json()

                if retry_result.get('result') == 0:

                    for folder in retry_result.get('metadata', {}).get('contents', []):

                        if folder.get('isfolder') and folder.get('name') == folder_name:

                            folder_id = folder.get('folderid')

                            _logger.info(
                                "[GET_OR_CREATE] Carpeta encontrada después de retry '%s' ID=%s",
                                folder_name,
                                folder_id
                            )

                            return folder_id

                _logger.error(
                    "[GET_OR_CREATE] Carpeta '%s' existe pero no se pudo recuperar ID",
                    folder_name
                )

                return False

            # -----------------------------
            # 5️⃣ Error real
            # -----------------------------
            _logger.error(
                "[GET_OR_CREATE] Error al crear carpeta '%s': %s",
                folder_name,
                create_result
            )

            return False

        except Exception as e:

            _logger.exception(
                "[GET_OR_CREATE] Excepción creando carpeta '%s': %s",
                folder_name,
                str(e)
            )

            return False

    def get_download_content(self):
        """Obtiene el contenido de la foto para descargar desde pCloud."""
        self.ensure_one()
        _logger.info(f"[DOWNLOAD_CONTENT] Iniciando descarga para foto ID: {self.id} con file_id: {self.file_id}")
    
        try:
            if not self.file_id:
                _logger.error(f"[DOWNLOAD_CONTENT] No se encontró file_id para la foto ID: {self.id}")
                raise ValidationError("No se encontró el archivo en pCloud")
    
            # Obtener configuración de pCloud
            pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
            if not pcloud_config or not pcloud_config.access_token:
                _logger.error(f"[DOWNLOAD_CONTENT] Configuración de pCloud no encontrada o inválida")
                raise ValidationError("No se encontró configuración de pCloud")
    
            # Obtener un enlace actualizado de pCloud para la descarga
            download_url = self._get_file_url(self.file_id, pcloud_config)
            if not download_url:
                _logger.error(f"[DOWNLOAD_CONTENT] No se pudo generar URL de descarga para file_id: {self.file_id}")
                raise ValidationError("No se pudo obtener la URL de descarga desde pCloud")
    
            # Descargar el archivo directamente desde pCloud
            response = requests.get(download_url, stream=True, timeout=10)
            if response.status_code != 200:
                _logger.error(f"[DOWNLOAD_CONTENT] Error al descargar archivo desde pCloud. Status: {response.status_code}")
                raise ValidationError("No se pudo descargar el archivo desde pCloud")
    
            # Retornar el contenido en base64, tipo MIME y nombre del archivo
            return {
                'content': base64.b64encode(response.content).decode('utf-8'),
                'filename': self.nombre_foto,
                'content_type': response.headers.get('Content-Type', 'application/octet-stream')
            }
    
        except requests.exceptions.RequestException as e:
            _logger.exception(f"[DOWNLOAD_CONTENT] Error de red al obtener contenido de pCloud para foto ID {self.id}: {str(e)}")
            raise ValidationError("Error de conexión al descargar la foto. Por favor, inténtelo nuevamente.")
        except Exception as e:
            _logger.exception(f"[DOWNLOAD_CONTENT] Error al obtener contenido de la foto ID {self.id}: {str(e)}")
            raise ValidationError(f"Error al descargar la foto: {str(e)}")
    

    def _get_public_link(self, file_id, pcloud_config):
        """Obtener links públicos para la foto"""
        try:
            # Crear link público
            url = f"{pcloud_config.hostname}/getfilepublink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id
            }

            response = requests.get(url, params=params)
            result = response.json()

            if response.status_code == 200 and result.get('link'):
                # Obtener link de thumbnail
                thumb_url = f"{pcloud_config.hostname}/getthumblink"
                thumb_params = {
                    'access_token': pcloud_config.access_token,
                    'fileid': file_id,
                    'size': '256x256',
                    'crop': 1,
                    'public': 1
                }

                thumb_response = requests.get(thumb_url, thumb_params)
                thumb_result = thumb_response.json()

                if thumb_response.status_code == 200 and thumb_result.get('path'):
                    return {
                        'download_url': result['link'],
                        'thumb_url': f"https://{thumb_result['hosts'][0]}{thumb_result['path']}"
                    }

            return False

        except Exception as e:
            _logger.exception(f"[PUBLIC_LINK] Error: {str(e)}")
            return False

    def _check_token_valid(self, pcloud_config):
        """Verificar si el token de pCloud es válido"""
        try:
            url = f"{pcloud_config.hostname}/userinfo"
            params = {'access_token': pcloud_config.access_token}
            response = requests.get(url, params=params)
            return response.status_code == 200 and response.json().get('result') == 0
        except:
            return False

    def _refresh_pcloud_token(self, pcloud_config):
        """Renovar token de pCloud si es necesario"""
        try:
            # Implementa aquí la lógica para renovar el token
            # Esto dependerá de cómo manejes la autenticación con pCloud
            pass
        except Exception as e:
            _logger.exception(f"[REFRESH_TOKEN] Error: {str(e)}")


        



    def get_download_link(self):
        """Obtener un nuevo link de descarga para una foto"""
        self.ensure_one()
        _logger.info(f"[DOWNLOAD_LINK] Obteniendo link para foto {self.id}")
        
        try:
            pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
            if not pcloud_config or not pcloud_config.access_token:
                raise ValidationError("No se encontró configuración de pCloud")

            # Obtener URL de pCloud con forcedownload
            url = f"{pcloud_config.hostname}/getfilelink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': self.file_id,
                'forcedownload': 1,  # Forzar descarga
                'filename': self.nombre_foto  # Nombre de archivo para descarga
            }
            
            _logger.info(f"[DOWNLOAD_LINK] Solicitando a pCloud con params: {params}")
            response = requests.get(url, params=params)
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                # Crear contenido para descargar
                file_url = f"https://{result['hosts'][0]}{result['path']}"
                file_response = requests.get(file_url)
                
                if file_response.status_code == 200:
                    content = base64.b64encode(file_response.content).decode('utf-8')
                    _logger.info(f"[DOWNLOAD_LINK] Contenido obtenido para foto {self.id}")
                    return {
                        'content': content,
                        'filename': self.nombre_foto,
                        'mimetype': file_response.headers.get('content-type', 'application/octet-stream')
                    }
                
            _logger.error(f"[DOWNLOAD_LINK] Error en respuesta: {result}")
            return False

        except Exception as e:
            _logger.exception(f"[DOWNLOAD_LINK] Error: {str(e)}")
            return False


    def get_photos_zip(self, foto_ids=None):
        """Crear un ZIP en memoria con nombres únicos, descargando desde pCloud."""
        if not foto_ids:
            _logger.warning("[ZIP] No se proporcionaron foto_ids o el valor es None.")
            return False

        _logger.info(f"[ZIP] foto_ids recibidos: {foto_ids} (Tipo: {type(foto_ids)})")

        try:
            fotos = self.browse(foto_ids)
            if not fotos:
                _logger.warning("[ZIP] No se encontraron fotos para descargar")
                return False

            pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
            if not pcloud_config or not pcloud_config.access_token:
                _logger.error("[ZIP] Config pCloud faltante")
                raise ValidationError("No se encontró configuración de pCloud")

            zip_buffer = io.BytesIO()
            existing_names = set()

            def _unique_name(name):
                # normaliza y garantiza unicidad dentro del ZIP
                base, ext = os.path.splitext(name)
                i = 1
                candidate = name
                while candidate in existing_names:
                    i += 1
                    candidate = f"{base} ({i}){ext}"
                existing_names.add(candidate)
                return candidate

            import os
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zip_file:
                for foto in fotos:
                    if not foto.file_id:
                        continue
                    try:
                        url = f"{pcloud_config.hostname}/getfilelink"
                        params = {
                            'access_token': pcloud_config.access_token,
                            'fileid': foto.file_id,
                            'forcedownload': 1
                        }
                        _logger.info(f"[ZIP] Solicitando link de descarga para foto ID: {foto.id} con params: {params}")
                        response = requests.get(url, params=params, timeout=15)
                        result = response.json()
                        _logger.info(f"[ZIP] Respuesta recibida de pCloud para foto ID: {foto.id}: {result}")

                        if response.status_code == 200 and result.get('result') == 0:
                            download_url = f"https://{result['hosts'][0]}{result['path']}"
                            file_response = requests.get(download_url, timeout=30)
                            if file_response.status_code == 200:
                                name = foto.nombre_foto or f'foto_{foto.id}.jpg'
                                safe = _unique_name(name)
                                zip_file.writestr(safe, file_response.content)
                                _logger.info(f"[ZIP] Foto ID: {foto.id} agregada como '{safe}'")
                            else:
                                _logger.error(f"[ZIP] Error al descargar foto {foto.id}: HTTP {file_response.status_code}")
                        else:
                            _logger.error(f"[ZIP] No se pudo obtener link para foto {foto.id}")
                    except Exception as e:
                        _logger.error(f"[ZIP] Error procesando foto {foto.id}: {e}")

            zip_buffer.seek(0)
            content = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')
            _logger.info("[ZIP] ZIP creado exitosamente")
            return {
                'content': content,
                'filename': 'fotos_reparacion.zip',
                'mimetype': 'application/zip'
            }
        except Exception as e:
            _logger.exception(f"[ZIP] Error al crear ZIP: {e}")
            return False

    def _upload_to_pcloud(self, archivo_binario, filename, folder_id, pcloud_config):
        """Sube un archivo a pCloud"""
        _logger.info("[UPLOAD_PCLOUD] Iniciando subida de archivo %s a folder_id %s", filename, folder_id)
        
        try:
            url = f"{pcloud_config.hostname}/uploadfile"
            
            # Preparar los parámetros
            params = {
                'folderid': folder_id,
                'nopartial': 1,  # No guardar archivos parciales
                'renameifexists': 1,  # Renombrar si existe
            }
            
            # Preparar el archivo
            files = {
                'file': (filename, archivo_binario, 'application/octet-stream')
            }
            
            # Agregar el token de acceso
            params['access_token'] = pcloud_config.access_token
            
            _logger.info("[UPLOAD_PCLOUD] Enviando solicitud a %s con params: %s", url, params)
            
            # Realizar la solicitud POST
            response = requests.post(url, 
                                params=params,
                                files=files,
                                timeout=30)  # 30 segundos de timeout
            
            _logger.info("[UPLOAD_PCLOUD] Código de respuesta: %s", response.status_code)
            
            if response.status_code != 200:
                _logger.error("[UPLOAD_PCLOUD] Error en la solicitud: %s", response.text)
                return False
                
            result = response.json()
            _logger.info("[UPLOAD_PCLOUD] Respuesta: %s", result)
            
            if result.get('result') == 0 and result.get('metadata'):
                metadata = result['metadata'][0]
                file_id = metadata.get('fileid')
                
                if not file_id:
                    _logger.error("[UPLOAD_PCLOUD] No se encontró file_id en la respuesta")
                    return False
                    
                _logger.info("[UPLOAD_PCLOUD] Archivo subido exitosamente con ID: %s", file_id)
                
                # Obtener la URL pública del archivo
                public_link = self._create_public_link(file_id, pcloud_config)
                thumb_url = self._get_thumb_url(file_id, pcloud_config)
                
                # Obtener la URL de descarga
                download_url = self._get_file_url(file_id, pcloud_config)
                
                if not download_url:
                    _logger.error("[UPLOAD_PCLOUD] No se pudo obtener la URL de descarga")
                    return False
                    
                return {
                    'file_id': file_id,
                    'url': download_url,
                    'public_link': public_link,
                    'thumb_url': thumb_url,
                    'size': metadata.get('size'),
                    'content_type': metadata.get('contenttype'),
                    'created': metadata.get('created'),
                    'modified': metadata.get('modified'),
                    'thumb': metadata.get('thumb', False)
                }
                
            else:
                error_msg = result.get('error', 'Error desconocido')
                _logger.error("[UPLOAD_PCLOUD] Error en respuesta: %s", error_msg)
                return False
                
        except requests.exceptions.Timeout:
            _logger.error("[UPLOAD_PCLOUD] Timeout durante la subida del archivo")
            return False
        except requests.exceptions.RequestException as e:
            _logger.exception("[UPLOAD_PCLOUD] Error en la solicitud: %s", str(e))
            return False
        except Exception as e:
            _logger.exception("[UPLOAD_PCLOUD] Error general: %s", str(e))
            return False



    # === NUEVO: helpers para upload links de pCloud ===
    def _get_or_create_uploadlink(self, folder_id, pcloud_config):
        """
        Devuelve el 'code' de un upload link (File Request) para esa carpeta.
        Si ya existe uno utilizable, lo reutiliza. Si no, crea uno.
        """
        try:
            # 1) Buscar si ya hay upload links
            list_ul = f"{pcloud_config.hostname}/listuploadlinks"
            params = {'access_token': pcloud_config.access_token}
            r = requests.get(list_ul, params=params, timeout=15)
            data = r.json() if r.status_code == 200 else {}

            if data.get('result') == 0:
                for link in data.get('links', []):
                    # Cada link tiene 'folderid' o 'path' (dependiendo de versión). Reusamos si coincide.
                    if str(link.get('folderid')) == str(folder_id):
                        # link['code'] es el identificador del upload link
                        return link.get('code')

            # 2) Crear nuevo upload link
            create_ul = f"{pcloud_config.hostname}/createuploadlink"
            create_params = {
                'access_token': pcloud_config.access_token,
                'folderid': folder_id,
                # Opcionales (descomenta si quieres):
                # 'maxspace': 0,         # 0 = sin límite
                # 'expires': 0,          # 0 = sin vencimiento
                # 'name': 'reparacion'   # etiqueta opcional
            }
            cr = requests.get(create_ul, params=create_params, timeout=15)
            cres = cr.json() if cr.status_code == 200 else {}
            if cres.get('result') == 0 and cres.get('code'):
                return cres.get('code')

            _logger.error("[UPLOADLINK] No se pudo crear upload link: %s", cres)
            return False
        except Exception as e:
            _logger.exception("[UPLOADLINK] Error: %s", str(e))
            return False


    def _get_upload_post_url(self, code, pcloud_config):
        """
        Convierte el 'code' de un upload link en una URL de POST (host+path) para subir vía fetch(FormData)
        """
        try:
            get_ul = f"{pcloud_config.hostname}/getuploadlink"
            params = {'code': code}
            r = requests.get(get_ul, params=params, timeout=15)
            data = r.json() if r.status_code == 200 else {}
            # Respuesta típica: { result:0, hosts:[...], path:"/x/y/z" }
            if data.get('result') == 0 and data.get('hosts') and data.get('path'):
                return f"https://{data['hosts'][0]}{data['path']}"
            _logger.error("[UPLOADLINK] getuploadlink error: %s", data)
            return False
        except Exception as e:
            _logger.exception("[UPLOADLINK] Error get_upload_post_url: %s", str(e))
            return False

    # === NUEVO: listar archivo por nombre y registrar sin binario (upload directo a pCloud) ===
    def _find_file_in_folder(self, folder_id, filename, pcloud_config):
        """Busca un archivo por nombre en la carpeta pCloud (no recursivo)."""
        try:
            url = f"{pcloud_config.hostname}/listfolder"
            params = {
                'access_token': pcloud_config.access_token,
                'folderid': folder_id
            }
            r = requests.get(url, params=params, timeout=15)
            data = r.json() if r.status_code == 200 else {}
            if data.get('result') == 0:
                for e in data.get('metadata', {}).get('contents', []):
                    if not e.get('isfolder') and e.get('name') == filename:
                        return {'file_id': e.get('fileid'), 'size': e.get('size'), 'contenttype': e.get('contenttype')}
            return None
        except Exception as e:
            _logger.exception("[FIND_FILE] Error listando carpeta %s: %s", folder_id, str(e))
            return None

    @api.model
    def register_from_pcloud(self, reparacion_id, filename, sequence=None):
        _logger.info("[REGISTER_FROM_PCLOUD] reparacion_id=%s filename=%s sequence=%s",
                    reparacion_id, filename, sequence)

        rep = self.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)

        if not rep.exists():
            _logger.error("[REGISTER_FROM_PCLOUD] Reparación no encontrada: %s", reparacion_id)
            raise ValidationError('Reparación no encontrada')

        cfg = self.env['pcloud.configuracion'].sudo().search([], limit=1)

        if not cfg or not cfg.access_token or not cfg.hostname:
            _logger.error("[REGISTER_FROM_PCLOUD] Configuración de pCloud no encontrada")
            raise ValidationError("Configuración de pCloud no encontrada")

        folder_id = self._obtener_folder_id(rep, cfg)
        _logger.info("[REGISTER_FROM_PCLOUD] folder_id obtenido: %s", folder_id)

        meta = self._find_file_in_folder(folder_id, filename, cfg)

        if not meta:
            _logger.error("[REGISTER_FROM_PCLOUD] Archivo no encontrado en pCloud: %s", filename)
            raise ValidationError("Archivo no encontrado en la carpeta de la reparación")

        _logger.info("[REGISTER_FROM_PCLOUD] Archivo encontrado file_id=%s", meta['file_id'])

        if sequence is None:
            # Lock al padre para serializar inserts concurrentes
            self.env.cr.execute(
                "SELECT id FROM reparaciones_reparaciones WHERE id = %s FOR UPDATE",
                [reparacion_id]
            )

            last = self.search(
                [('reparacion_id', '=', reparacion_id)],
                order='sequence desc',
                limit=1
            )

            sequence = (last.sequence or 0) + 1
            _logger.info("[REGISTER_FROM_PCLOUD] Secuencia calculada: %s", sequence)

        vals = {
            'reparacion_id': reparacion_id,
            'nombre_foto': filename,
            'file_id': meta['file_id'],
            'size': meta.get('size') or 0,
            'mimetype': meta.get('contenttype') or 'application/octet-stream',
            'sequence': sequence,
            'state': 'done',
        }

        rec = self.sudo().create(vals)
        _logger.info("[REGISTER_FROM_PCLOUD] Registro creado ID=%s", rec.id)

        _logger.info("[REGISTER_FROM_PCLOUD] Generando thumbnail para file_id=%s", rec.file_id)
        thumb = self._get_thumb_url(rec.file_id, cfg)

        if thumb:
            _logger.info("[REGISTER_FROM_PCLOUD] Thumbnail obtenido: %s", thumb)
            rec.sudo().write({'thumb_url': thumb})
            _logger.info("[REGISTER_FROM_PCLOUD] Thumbnail guardado en BD para foto %s", rec.id)
        else:
            thumb = f'/gallery/preview/{rec.id}'
            _logger.warning("[REGISTER_FROM_PCLOUD] Thumbnail no generado, usando fallback")

        return {
            'id': rec.id,
            'sequence': rec.sequence,
            'nombre_foto': rec.nombre_foto,
            'thumb_url': thumb,
        }
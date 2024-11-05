from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import requests
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
        """Sobrescribe el método create para manejar la subida de fotos"""
        for vals in vals_list:
            _logger.info("[CREATE] Iniciando creación de foto con valores: %s", vals)
            
            if 'reparacion_id' in vals:
                # Obtener la siguiente secuencia
                existing_photos = self.search([
                    ('reparacion_id', '=', vals['reparacion_id'])
                ], order='sequence desc', limit=1)
                vals['sequence'] = (existing_photos.sequence or 0) + 1
                _logger.info("[CREATE] Asignada secuencia: %s", vals['sequence'])

            # Generar ID único
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            random_string = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:6]
            vals['unique_id'] = f"{timestamp}_{random_string}"
            _logger.info("[CREATE] Generado ID único: %s", vals['unique_id'])

            if 'foto_binario' in vals:
                try:
                    vals['state'] = 'uploading'
                    # Obtener la reparación
                    reparacion = self.env['reparaciones.reparaciones'].browse(vals['reparacion_id'])
                    if not reparacion:
                        _logger.error("[CREATE] No se encontró la reparación: %s", vals['reparacion_id'])
                        raise ValidationError("No se encontró la reparación relacionada")

                    # Procesar archivo
                    archivo_binario = base64.b64decode(vals['foto_binario'])
                    vals['size'] = len(archivo_binario)
                    
                    # Detectar tipo de archivo
                    mime_type = magic.from_buffer(archivo_binario, mime=True)
                    extension = mimetypes.guess_extension(mime_type) or '.bin'
                    _logger.info("[CREATE] Tipo MIME detectado: %s, extensión: %s", mime_type, extension)

                    # Generar nombre único
                    nuevo_nombre = f"{vals['unique_id']}{extension}"
                    vals['nombre_foto'] = nuevo_nombre
                    _logger.info("[CREATE] Nombre generado para archivo: %s", nuevo_nombre)

                    # Configuración pCloud
                    pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
                    if not pcloud_config or not pcloud_config.access_token:
                        _logger.error("[CREATE] No se encontró configuración de pCloud válida")
                        raise ValidationError("Configuración de pCloud no encontrada")

                    # Obtener carpeta
                    folder_id = self._obtener_folder_id(reparacion, pcloud_config)
                    _logger.info("[CREATE] Carpeta pCloud obtenida: %s", folder_id)

                    # Subir archivo
                    result = self._upload_to_pcloud(
                        archivo_binario,
                        nuevo_nombre,
                        folder_id,
                        pcloud_config
                    )

                    if result and result.get('file_id'):
                        _logger.info("[CREATE] Archivo subido exitosamente: %s", result)
                        vals.update({
                            'file_id': result['file_id'],
                            'url_foto': result['url'],
                            'public_link': result.get('public_link'),
                            'state': 'done'
                        })
                        del vals['foto_binario']
                    else:
                        _logger.error("[CREATE] Error al subir archivo a pCloud")
                        vals['state'] = 'error'
                        raise ValidationError("Error al subir la foto a pCloud")

                except Exception as e:
                    _logger.exception("[CREATE] Error durante la creación: %s", str(e))
                    vals['state'] = 'error'
                    raise ValidationError(f"Error al subir la foto: {str(e)}")

        return super().create(vals_list)
    
    def _upload_to_pcloud(self, archivo_binario, nombre_archivo, folder_id, pcloud_config):
        """Método para subir archivo a pCloud y crear link público"""
        _logger.info("[UPLOAD] Iniciando subida de archivo: %s", nombre_archivo)
        try:
            # Subir archivo
            url = f"{pcloud_config.hostname}/uploadfile"
            params = {
                'access_token': pcloud_config.access_token,
                'folderid': folder_id,
                'nopartial': 1,
                'renameifexists': 1
            }
            files = {
                'file': (nombre_archivo, archivo_binario, 'application/octet-stream')
            }

            _logger.info("[UPLOAD] Enviando solicitud a pCloud: %s", url)
            response = requests.post(url, params=params, files=files)
            result = response.json()
            _logger.info("[UPLOAD] Respuesta de pCloud: %s", result)

            if response.status_code != 200 or 'metadata' not in result:
                _logger.error("[UPLOAD] Error en respuesta de pCloud: %s", result)
                return False

            file_id = str(result['metadata'][0]['fileid'])
            _logger.info("[UPLOAD] File ID obtenido: %s", file_id)

            # Crear link público
            public_url = self._create_public_link(file_id, pcloud_config)
            _logger.info("[UPLOAD] Link público creado: %s", public_url)

            # Obtener URL de descarga
            download_url = self._get_file_url(file_id, pcloud_config)
            _logger.info("[UPLOAD] URL de descarga: %s", download_url)

            return {
                'file_id': file_id,
                'url': download_url,
                'public_link': public_url
            }

        except Exception as e:
            _logger.exception("[UPLOAD] Error durante la subida: %s", str(e))
            return False

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
        """Obtiene la URL del thumbnail"""
        _logger.info("[THUMB_URL] Solicitando thumbnail para file_id: %s", file_id)
        return self._get_pcloud_url('getthumblink', file_id, pcloud_config, {
            'size': '256x256',
            'crop': 1
        })

    def _get_file_url(self, file_id, pcloud_config):
        """Obtiene la URL de descarga"""
        _logger.info("[FILE_URL] Solicitando URL para file_id: %s", file_id)
        return self._get_pcloud_url('getfilelink', file_id, pcloud_config)

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
        """Obtiene todas las fotos con sus previsualizaciones"""
        _logger.info("[PREVIEW] Iniciando para reparación ID: %s", reparacion_id)
        
        photos = []
        domain = [('reparacion_id', 'in', [reparacion_id] if isinstance(reparacion_id, int) else reparacion_id)]
        fotos = self.search(domain, order='sequence')
        
        _logger.info("[PREVIEW] Encontradas %d fotos", len(fotos))
        
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            _logger.error("[PREVIEW] No se encontró configuración de pCloud")
            return photos

        for foto in fotos:
            try:
                if foto.file_id:
                    thumb_url = self._get_thumb_url(foto.file_id, pcloud_config)
                    download_url = self._get_file_url(foto.file_id, pcloud_config)
                    
                    if thumb_url and download_url:
                        photos.append({
                            'id': foto.id,
                            'nombre_foto': foto.name,
                            'sequence': foto.sequence,
                            'thumb_url': thumb_url,
                            'download_url': download_url,
                            'file_id': foto.file_id,
                            'public_link': foto.public_link,
                            'mimetype': foto.mimetype,
                            'size': foto.size
                        })
                        _logger.info("[PREVIEW] Foto %s procesada exitosamente", foto.id)
                    else:
                        _logger.warning("[PREVIEW] No se pudieron obtener URLs para foto %s", foto.id)
            except Exception as e:
                _logger.exception("[PREVIEW] Error procesando foto %s: %s", foto.id, str(e))
                continue

        _logger.info("[PREVIEW] Total de fotos procesadas: %d", len(photos))
        return photos

    def share_photo(self):
        """Compartir foto (incrementa contador y devuelve link público)"""
        self.ensure_one()
        _logger.info("[SHARE] Compartiendo foto %s", self.id)
        
        if self.public_link:
            self.share_count += 1
            _logger.info("[SHARE] Incrementado contador de compartidos para foto %s", self.id)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Link Copiado',
                    'message': self.public_link,
                    'sticky': False,
                    'type': 'success',
                }
            }
        _logger.warning("[SHARE] No hay link público disponible para foto %s", self.id)
        return False

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
        folder_name = f"{reparacion.maquina_id.name.name}_{reparacion.serie_id or 'sin_serie'}"
        _logger.info("[GET_FOLDER] Buscando/creando carpeta: %s", folder_name)
        
        try:
            folders = {
                'root': {'id': 0, 'name': 'root'},
                'fotos': {'name': 'fotos_reparaciones'},
                'maquina': {'name': folder_name}
            }
            
            # Obtener/Crear carpeta fotos_reparaciones
            folders['fotos']['id'] = self._get_or_create_folder(
                folders['fotos']['name'],
                folders['root']['id'],
                pcloud_config
            )
            
            if not folders['fotos']['id']:
                _logger.error("[GET_FOLDER] Error al crear carpeta fotos_reparaciones")
                raise ValidationError("Error al crear carpeta fotos_reparaciones")
                
            # Obtener/Crear carpeta de la máquina
            folders['maquina']['id'] = self._get_or_create_folder(
                folders['maquina']['name'],
                folders['fotos']['id'],
                pcloud_config
            )
            
            if not folders['maquina']['id']:
                _logger.error("[GET_FOLDER] Error al crear carpeta %s", folder_name)
                raise ValidationError(f"Error al crear carpeta {folder_name}")
                
            _logger.info("[GET_FOLDER] ID de carpeta obtenido: %s", folders['maquina']['id'])
            return folders['maquina']['id']
            
        except Exception as e:
            _logger.exception("[GET_FOLDER] Error: %s", str(e))
            raise ValidationError(f"Error al obtener/crear carpetas: {str(e)}")

    def _get_or_create_folder(self, folder_name, parent_id, pcloud_config):
        """Obtiene o crea una carpeta en pCloud"""
        _logger.info("[GET_OR_CREATE] Buscando/creando carpeta %s en padre %s", 
                    folder_name, parent_id)
        try:
            # Listar carpetas
            list_url = f"{pcloud_config.hostname}/listfolder"
            params = {
                'access_token': pcloud_config.access_token,
                'folderid': parent_id
            }
            
            _logger.info("[GET_OR_CREATE] Listando carpetas: %s", list_url)
            response = requests.get(list_url, params=params)
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                # Buscar carpeta existente
                for folder in result['metadata']['contents']:
                    if folder['isfolder'] and folder['name'] == folder_name:
                        _logger.info("[GET_OR_CREATE] Carpeta encontrada: %s", folder['folderid'])
                        return folder['folderid']
                        
                # Crear nueva carpeta
                _logger.info("[GET_OR_CREATE] Creando nueva carpeta: %s", folder_name)
                create_url = f"{pcloud_config.hostname}/createfolder"
                create_params = {
                    'access_token': pcloud_config.access_token,
                    'name': folder_name,
                    'folderid': parent_id
                }
                
                create_response = requests.get(create_url, params=create_params)
                create_result = create_response.json()
                
                if create_result.get('result') == 0:
                    _logger.info("[GET_OR_CREATE] Carpeta creada: %s", 
                               create_result['metadata']['folderid'])
                    return create_result['metadata']['folderid']
                
                _logger.error("[GET_OR_CREATE] Error al crear carpeta: %s", create_result)
                    
            _logger.error("[GET_OR_CREATE] Error al listar/crear carpeta: %s", result)
            return False
            
        except Exception as e:
            _logger.exception("[GET_OR_CREATE] Error: %s", str(e))
            return False

    def get_download_content(self):
        """Obtiene el contenido de la foto para descargar"""
        self.ensure_one()
        _logger.info(f"[DOWNLOAD] Obteniendo contenido para foto {self.id}")

        try:
            if not self.file_id:
                raise ValidationError("No se encontró el archivo")

            pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
            if not pcloud_config:
                raise ValidationError("No se encontró configuración de pCloud")

            # Obtener contenido del archivo
            url = self._get_file_url(self.file_id, pcloud_config)
            if not url:
                raise ValidationError("No se pudo obtener la URL de descarga")

            response = requests.get(url)
            if response.status_code != 200:
                raise ValidationError("No se pudo descargar el archivo")

            return {
                'content': base64.b64encode(response.content).decode('utf-8'),
                'filename': self.nombre_foto,
                'mimetype': response.headers.get('content-type', 'application/octet-stream')
            }

        except Exception as e:
            _logger.exception(f"[DOWNLOAD] Error al obtener contenido: {str(e)}")
            raise ValidationError(f"Error al descargar la foto: {str(e)}")
    def get_photos_zip(self, foto_ids):
        """Crea un ZIP con las fotos seleccionadas"""
        _logger.info(f"[ZIP] Creando ZIP para fotos: {foto_ids}")
        
        try:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for foto in self.browse(foto_ids):
                    content = foto.get_download_content()
                    if content:
                        zip_file.writestr(
                            content['filename'],
                            base64.b64decode(content['content'])
                        )

            return {
                'content': base64.b64encode(buffer.getvalue()).decode('utf-8'),
                'filename': 'fotos_seleccionadas.zip',
                'mimetype': 'application/zip'
            }

        except Exception as e:
            _logger.exception(f"[ZIP] Error al crear ZIP: {str(e)}")
            raise ValidationError(f"Error al crear el archivo ZIP: {str(e)}")
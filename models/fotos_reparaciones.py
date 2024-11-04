from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import requests
import base64
import json

_logger = logging.getLogger(__name__)

class ReparacionFoto(models.Model):
    _name = 'reparaciones.foto'
    _description = 'Fotos de Reparaciones'

    url_foto = fields.Char(string="URL de Foto")
    nombre_foto = fields.Char(string="Nombre de la Foto")
    foto_binario = fields.Binary(string="Subir Foto" attachment=True)
    reparacion_id = fields.Many2one('reparaciones.reparaciones', string="Reparación")
    file_id = fields.Char(string="File ID pCloud")

    @api.model
    def create(self, vals):
        """Sobrescribe el método create para manejar la subida de fotos"""
        _logger.info(f"Creando nueva foto con valores: {vals}")
        
        if 'url_foto' in vals:
            _logger.info(f"URL proporcionada: {vals['url_foto']}")
            # Si se proporciona una URL, intentar extraer el file_id
            file_id = vals.get('url_foto', '').split('/')[-1]
            if file_id:
                vals['file_id'] = file_id
                _logger.info(f"File ID extraído de URL: {file_id}")

        if 'foto_binario' in vals:
            _logger.info("Procesando foto binaria")
            try:
                # Obtener la reparación relacionada
                reparacion = self.env['reparaciones.reparaciones'].browse(vals.get('reparacion_id'))
                if not reparacion:
                    _logger.error("No se encontró la reparación relacionada")
                    raise ValidationError("No se encontró la reparación relacionada")

                # Subir la foto a pCloud
                archivo_binario = base64.b64decode(vals['foto_binario'])
                nombre_archivo = vals.get('nombre_foto', 'foto.jpg')
                url_foto = self._subir_foto_pcloud(archivo_binario, nombre_archivo, reparacion)
                
                vals['url_foto'] = url_foto
                del vals['foto_binario']
                _logger.info(f"Foto subida exitosamente. URL: {url_foto}")
            except Exception as e:
                _logger.exception(f"Error al subir la foto a pCloud: {str(e)}")
                raise ValidationError(f"Error al subir la foto: {str(e)}")

        return super(ReparacionFoto, self).create(vals)

    def _subir_foto_pcloud(self, archivo_binario, nombre_archivo, reparacion):
        """Método privado para subir la foto a pCloud"""
        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            raise ValidationError("Configuración de pCloud no encontrada o falta el token de acceso")

        # Obtener el ID de la carpeta
        folder_name = f"{reparacion.maquina_id.name.name}_{reparacion.serie_id or 'sin_serie'}"
        folder_id = self._obtener_folder_id(folder_name, pcloud_config)

        if not folder_id:
            raise ValidationError(f"No se encontró la carpeta {folder_name} en pCloud")

        # Preparar la URL y los parámetros para la solicitud
        url = f"{pcloud_config.hostname}/uploadfile"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': folder_id,
            'nopartial': 1,  # Para evitar subidas parciales
            'renameifexists': 1  # Renombrar si existe un archivo con el mismo nombre
        }
        files = {
            'file': (nombre_archivo, archivo_binario, 'application/octet-stream')
        }

        try:
            # Enviar la solicitud a la API de pCloud
            response = requests.post(url, params=params, files=files)
            result = response.json()

            # Verificar la respuesta
            _logger.info("Respuesta de pCloud al subir el archivo: %s", json.dumps(result, indent=4))
            if response.status_code == 200 and 'metadata' in result:
                return result['metadata'][0]['fileid']
            else:
                error_message = result.get('error', 'Error desconocido')
                raise ValidationError(f"Error al subir la foto a pCloud: {error_message}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error de conexión con pCloud: {str(e)}")
            raise ValidationError("Error de conexión con pCloud: %s" % str(e))

    def _obtener_folder_id(self, folder_name, pcloud_config):
        """Método privado para obtener el ID de una subcarpeta específica dentro de 'fotos_reparaciones'."""
        # Paso 1: Buscar la carpeta principal 'fotos_reparaciones'
        url = f"{pcloud_config.hostname}/listfolder"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': 0  # Carpeta raíz
        }

        response = requests.get(url, params=params)
        result = response.json()

        if response.status_code == 200 and result.get('result') == 0:
            fotos_reparaciones_id = None
            for folder in result['metadata']['contents']:
                if folder['isfolder'] and folder['name'] == 'fotos_reparaciones':
                    fotos_reparaciones_id = folder['folderid']
                    break

            if not fotos_reparaciones_id:
                raise ValidationError("No se encontró la carpeta 'fotos_reparaciones' en pCloud.")

            # Paso 2: Buscar la subcarpeta específica dentro de 'fotos_reparaciones'
            params['folderid'] = fotos_reparaciones_id
            response = requests.get(url, params=params)
            result = response.json()

            if response.status_code == 200 and result.get('result') == 0:
                for folder in result['metadata']['contents']:
                    if folder['isfolder'] and folder['name'] == folder_name:
                        return folder['folderid']

            return None  # No se encontró la subcarpeta
        else:
            raise ValidationError("Error al listar carpetas en pCloud: %s" % result.get('error'))


    def _generar_url_foto(self, result):
        """Método privado para generar la URL de la foto"""
        if 'hosts' in result and 'path' in result:
            return f"https://{result['hosts'][0]}{result['path']}"
        raise ValidationError("No se pudo generar la URL de la foto")


    @api.model
    def get_photos_preview(self, reparacion_id):
        """Obtiene todas las fotos con sus previsualizaciones"""
        _logger.info(f"Obteniendo fotos para reparación ID: {reparacion_id}")
        
        photos = []
        domain = [('reparacion_id', '=', reparacion_id)]
        fotos = self.search(domain)
        
        _logger.info(f"Fotos encontradas: {len(fotos)}")
        for foto in fotos:
            _logger.info(f"Procesando foto ID: {foto.id}")
            _logger.info(f"Datos de foto: nombre={foto.nombre_foto}, url={foto.url_foto}, file_id={foto.file_id}")
            
            try:
                # Intentar obtener URL directamente del campo url_foto
                url = foto.url_foto
                if not url:
                    # Si no hay URL, intentar obtenerla de pCloud
                    url = foto.get_download_url()
                
                if url:
                    _logger.info(f"URL obtenida para foto {foto.id}: {url}")
                    photos.append({
                        'id': foto.id,
                        'nombre_foto': foto.nombre_foto,
                        'url_foto': url,
                    })
                else:
                    _logger.warning(f"No se pudo obtener URL para foto {foto.id}")
            except Exception as e:
                _logger.exception(f"Error procesando foto {foto.id}: {str(e)}")
                continue

        _logger.info(f"Total de fotos procesadas con éxito: {len(photos)}")
        return photos

    @api.model
    def get_photos_zip(self, foto_ids):
        """Crea un ZIP con las fotos seleccionadas"""
        fotos = self.browse(foto_ids)
        if not fotos:
            return False

        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for foto in fotos:
                    url = foto.get_download_url()
                    if url:
                        try:
                            response = requests.get(url)
                            if response.status_code == 200:
                                filename = foto.nombre_foto or f'foto_{foto.id}.jpg'
                                zip_file.writestr(filename, response.content)
                        except Exception:
                            continue

            zip_buffer.seek(0)
            attachment = self.env['ir.attachment'].create({
                'name': 'fotos_seleccionadas.zip',
                'type': 'binary',
                'datas': base64.b64encode(zip_buffer.read()),
                'mimetype': 'application/zip',
            })

            return f'/web/content/{attachment.id}?download=true'
        except Exception:
            return False


    def get_download_url(self):
        """Obtiene la URL de descarga desde pCloud"""
        self.ensure_one()
        _logger.info(f"Obteniendo URL de descarga para foto ID: {self.id}")
        _logger.info(f"URL actual: {self.url_foto}")
        _logger.info(f"File ID: {self.file_id}")

        if self.url_foto:
            _logger.info("Usando URL existente")
            return self.url_foto

        pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
        if not pcloud_config or not pcloud_config.access_token:
            _logger.error("No se encontró configuración de pCloud")
            return False

        try:
            url = f"{pcloud_config.hostname}/getfilelink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': self.file_id or self.url_foto,
                'forcedownload': 1
            }
            
            _logger.info(f"Realizando petición a pCloud con parámetros: {params}")
            response = requests.get(url, params=params)
            _logger.info(f"Respuesta de pCloud: {response.text}")
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                download_url = f"https://{result['hosts'][0]}{result['path']}"
                _logger.info(f"URL de descarga generada: {download_url}")
                return download_url
            else:
                _logger.error(f"Error en respuesta de pCloud: {result}")
            
            return False

        except Exception as e:
            _logger.exception(f"Error al obtener URL de descarga: {str(e)}")
            return False

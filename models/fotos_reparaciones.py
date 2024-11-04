from odoo import models, fields, api
from odoo.exceptions import ValidationError
import requests
import base64
import logging

_logger = logging.getLogger(__name__)

class ReparacionFoto(models.Model):
    _name = 'reparaciones.foto'
    _description = 'Fotos de Reparaciones'

    url_foto = fields.Char(string="URL de Foto", readonly=True)
    nombre_foto = fields.Char(string="Nombre de la Foto")
    reparacion_id = fields.Many2one('reparaciones.reparaciones', string="Reparación")

    @api.model
    def create(self, vals):
        """Sobrescribe el método create para manejar la subida de fotos a pCloud"""
        if 'foto_binario' in vals:  # Asegúrate de enviar la foto en formato binario
            try:
                # Obtener la configuración de pCloud
                pcloud_config = self.env['pcloud.configuracion'].search([], limit=1)
                if not pcloud_config or not pcloud_config.access_token:
                    raise ValidationError("Configuración de pCloud no encontrada o falta el token de acceso.")

                # Preparar archivo para subir
                archivo_binario = base64.b64decode(vals['foto_binario'])
                nombre_archivo = vals.get('nombre_foto', 'foto.jpg')

                # Crear o usar la carpeta 'fotos_reparaciones'
                folder_id = pcloud_config.main_folder_id or pcloud_config.create_pcloud_folder()

                # Subir archivo a pCloud
                file_id = self._upload_file_to_pcloud(nombre_archivo, archivo_binario, folder_id, pcloud_config)
                
                # Obtener la URL de descarga del archivo subido
                file_info = pcloud_config.get_pcloud_file_info(file_id)
                download_url = file_info.get('downloadlink')

                if not download_url:
                    raise ValidationError("No se pudo obtener el enlace de descarga del archivo.")

                # Guardar la URL en el registro
                vals['url_foto'] = download_url
                del vals['foto_binario']  # Eliminar el binario ya que no lo necesitamos guardar

            except Exception as e:
                _logger.error(f"Error al subir la foto a pCloud: {str(e)}")
                raise ValidationError(f"Error al subir la foto: {str(e)}")

        return super(ReparacionFoto, self).create(vals)

    def _upload_file_to_pcloud(self, file_name, file_content, folder_id, pcloud_config):
        """Método privado para subir un archivo a pCloud"""
        url = f"{pcloud_config.hostname}/uploadfile"
        params = {
            'access_token': pcloud_config.access_token,
            'folderid': folder_id,
            'nopartial': 1  # Evitar subidas parciales
        }
        files = {
            'file': (file_name, file_content, 'application/octet-stream')
        }

        response = requests.post(url, params=params, files=files)
        result = response.json()
        _logger.info("Respuesta de pCloud al subir el archivo: %s", result)

        if response.status_code == 200 and 'metadata' in result:
            return result['metadata'][0]['fileid']
        else:
            raise ValidationError(f"Error al subir el archivo a pCloud: {result.get('error', 'Desconocido')}")

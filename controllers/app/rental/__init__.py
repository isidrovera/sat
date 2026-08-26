# -*- coding: utf-8 -*-

# API Flutter - Área de Alquiler
#
# Este paquete agrupa los controladores por responsabilidad para evitar
# concentrar toda la API del modelo `alquiler` en un único archivo.
#
# IMPORTANTE:
# - base.py debe cargarse primero porque los demás controladores heredan
#   de RentalBaseController.
# - Los demás módulos pueden mantenerse independientes.
# - No mover lógica funcional a este archivo.

from . import base
from . import list
from . import detail
from . import state
from . import maintenance
from . import planner
from . import geo
from . import toner
from . import blocking
from . import inspection
from . import related
from . import qr

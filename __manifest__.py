# -*- coding: utf-8 -*-
{
    'name': "Sistema de Administración de Taller",
    'version': '1.0',
    'summary': "Administra las operaciones de un taller de fotocopiadoras",
    'sequence': -100,
    'description': """Gestiona reparaciones, mantenimientos y más.""",
    'author': "Isidro vera polo",
    'website': "https://copiercompanysac.com",
    'category': 'Services',

    'depends': [
        'base',
        'mail',
        'contacts',
        'sale_management',
        'portal',
        'web',
        'stock',
        'crm',
        'purchase',
        'project',
        'hr_holidays',
        'calendar',
        'im_livechat',
        'survey',
        'hr_attendance',
        'hr',
        'website',
        'bus',
    ],
    'external_dependencies': {
        'python': ['matplotlib', 'numpy'],
    },

    'data': [
        # ================================================================
        # 1. SEGURIDAD — siempre primero
        # ================================================================
        'security/acceso.xml',

        # ================================================================
        # 2. DATA: secuencias de numeración
        # ================================================================
        'data/ir_secuense.xml',
        'data/ir_secuense_ticket.xml',
        'data/ir.secuense_info.xml',
        'data/ir_secuense_ev.xml',
        'data/ir.secuence_incidencia.xml',

        # ================================================================
        # 3. DATA: configuración base y catálogos iniciales
        # ================================================================
        'data/print.xml',        
        'data/componente_color_data.xml',
        'data/color_tipo_data.xml',
        'data/accesorio_tipo_data.xml',
        'data/componente_tipo_data.xml',
        'data/componente_subparte_data.xml',
        'data/componente_estado_data.xml',
        'data/accesorio_estado_data.xml',
        'data/ir_actions_server_migration.xml',

        # ================================================================
        # 4. DATA: tareas programadas (crons)
        # ================================================================
        'data/cron_data.xml',
        'data/cron_evaluador_diario.xml',
        'data/cron_tickets.xml',

        # ================================================================
        # 5. DATA: plantillas de correo
        # ================================================================
        'data/plantillas_correo.xml',
        'data/correos_reparaciones.xml',
        'data/correos_tickets.xml',
        'data/correos_informes.xml',
        'data/correos_maquinas.xml',
        'data/correos_alquiler.xml',
        'data/mail_permisos.xml',
        'data/correos_evaluaciones_tecnicos.xml',
        'data/email_templates_consolidated.xml',

        # ================================================================
        # 6. REPORTS — definiciones de reportes PDF/QWeb
        # ================================================================
        'report/report_reparaciones_ventas.xml',
        'report/ticket_enlace.xml',
        'report/ticket_reporte.xml',
        'report/informes.xml',
        'report/evaluacion.xml',
        'report/evaluacion_enlace.xml',
        'report/report_qr_codes_reparaciones.xml',
        'report/reporte_estado_maquinas_report.xml',
        'report/qr_alquiler.xml',
        'report/evaluacion_servicio.xml',
        'report/equipment_visit_report.xml',

        # ================================================================
        # 7. VIEWS: modelos operativos principales
        # ================================================================
        'views/ventas.xml',
        'views/modelos.xml',
        'views/repuestos_alquiler.xml',
        'views/marcas.xml',
        'views/informes.xml',
        'views/fallas.xml',
        'views/reporte_cotizacion.xml',
        'views/reparaciones.xml',
        'views/alquiler.xml',
        'views/alquiler_views.xml',
        'views/repuestos_alquiler_list.xml',
        'views/evaluacion.xml',
        'views/incidencias.xml',
        'views/fotos_reparaciones.xml',
        'views/levantamiento.xml',
        'views/inspeccion_vista.xml',
        'views/transportistas.xml',
        'views/graficos.xml',

        # ================================================================
        # 8. VIEWS: ventas / opciones de producto
        # ================================================================
        'views/opciones_cliente.xml',
        'views/opciones_product.xml',
        'views/sale_order_.xml',
        'views/linea_pedido.xml',
        'views/mail_maquinas.xml',

        # ================================================================
        # 9. VIEWS: portal y templates web públicos
        # ================================================================
        'views/crear_ticket_portal.xml',
        'views/template_formulario_ticket.xml',
        'views/pagina_con_opciones.xml',
        'views/reportar_incidencia_form.xml',
        'views/pagina_confirmacion.xml',
        'views/solicitar_toner_form_template.xml',
        'views/pagina_confirmacion_toner.xml',
        'views/gallery_templates.xml',
        'views/templates_mantenimientos.xml',
        'views/customer_records_page.xml',
        'views/leave_request_template.xml',
        'views/soporte_dashboard.xml',
        'views/soporte.alquiler.xml',
        'views/partes_templates_alquiler.xml',
        'views/partes_templates_publicos.xml',
        'views/portal_templates.xml',
        'views/solicitud_partes_portal.xml',

        # ================================================================
        # 10. VIEWS: importación y carga de datos
        # ================================================================
        'views/importacionexcel.xml',
        'views/sat_import_line_views.xml',
        'views/ticket_create_import_views.xml',
        'views/tickets_masivos.xml',

        # ================================================================
        # 11. VIEWS: evaluaciones y desempeño de técnicos
        # ================================================================
        'views/evaluacion_tecnicos_alquiler.xml',
        'views/template_evaluacion_tecnicos.xml',
        'views/envio_masivo_evaluaciones.xml',
        'views/equipment_visit_report_views.xml',

        # ================================================================
        # 12. VIEWS: solicitudes de partes
        # ================================================================
        'views/solicitud_partes.xml',
        'views/solicitud_template.xml',
        'views/solicitud_partes_views.xml',
        'views/solicitud_parte_tecnico_views.xml',

        # ================================================================
        # 13. VIEWS: tóner y contadores automáticos
        # ================================================================
        'views/view_toner_counter_submission.xml',
        'views/view_toner_delivery_confirmation.xml',
        'views/view_toner_delivery_schedule.xml',
        'views/view_contador_automatico.xml',
        'views/view_patron_contador.xml',

        # ================================================================
        # 14. VIEWS: integración externa (PrintTracker, GPS, MDM)
        # ================================================================
        'views/printtracker_views.xml',
        'views/traccar_tracking_views.xml',
        'views/mdm_views.xml',
        'views/tracking_diagnostico_views.xml',

        # ================================================================
        # 15. VIEWS: reportes internos
        # ================================================================
        'views/reporte_maquinas_alquiler.xml',

        # ================================================================
        # 16. VIEWS: componentes, accesorios e intervenciones técnicas
        # ================================================================
        'views/componente.tipo.xml',
        'views/componente.subparte.xml',
        'views/componente_estado_views.xml',
        'views/modelo.maquina.componente.xml',
        'views/informe.regla.xml',
        'views/checklist.componente.map.xml',
        'views/reparacion_intervencion_views.xml',
        'views/reparacion_componente_evaluacion_views.xml',
        'views/reparacion_accesorio_evaluacion_views.xml',
        'views/accesorio_catalogos_views.xml',
        'views/modelo_accesorios.xml',

        # ================================================================
        # 17. VIEWS: autenticación, notificaciones y APIs
        # ================================================================
        'views/reparacion_autenticacion_wizard_view.xml',
        'views/whatsapp_notification_wizard_views.xml',
        'views/gemini_config_views.xml',

        # ================================================================
        # 18. WIZARDS — vistas de asistentes
        #     (después de todas las views de las que dependen)
        # ================================================================
        'views/solicitud_partes_wizards_views.xml',
        'views/wizard_asignar_componentes_views.xml',
        'wizards/sat_import_assign_header_wizard_views.xml',
        'wizards/sat_entrega_wizard_view.xml',

        # ================================================================
        # 19. MENÚS Y ACCIONES — siempre al final
        #     Referencia search_view_id de todos los archivos anteriores.
        #     Si se carga antes que sus refs, Odoo lanza ValueError.
        # ================================================================
        'views/acciones_menus.xml',
    ],

    'assets': {
        'web.assets_backend': [
            # Chart.js
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',

            # Font Awesome
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css',

            # Bootstrap 5
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',

            # Animate.css
            'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css',

            # AOS (Animate On Scroll)
            'https://unpkg.com/aos@2.3.1/dist/aos.css',
            'https://unpkg.com/aos@2.3.1/dist/aos.js',

            # Tailwind CSS
            'https://cdn.tailwindcss.com',

            # Lucide Icons
            'https://unpkg.com/lucide@latest/dist/umd/lucide.js',

            # Particles.js
            'https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js',

            # Typed.js
            'https://cdn.jsdelivr.net/npm/typed.js@2.0.12',

            # ECharts
            'https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js',

            # Lottie
            'https://cdnjs.cloudflare.com/ajax/libs/lottie-web/5.12.2/lottie.min.js',

            # Remix Icons
            'https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css',

            # Unicons
            'https://unicons.iconscout.com/release/v4.0.8/css/line.css',

            # Lord Icon
            'https://cdn.lordicon.com/lordicon.js',

            # CSS locales
            'sat/static/src/css/dashboard.css',
            'sat/static/src/css/style.css',
            'sat/static/src/css/tree_dashboard.css',
            'sat/static/src/css/evaluation_form.css',
            'sat/static/src/css/parts_request_message.css',
            'sat/static/src/css/image-viewer.css',
            'sat/static/src/css/sat_table_styles.css',
            'sat/static/src/css/gallery.css',
            'sat/static/src/css/geo_map_widget.css',

            # SCSS locales
            '/sat/static/src/scss/list_dashboard.scss',
            'sat/static/src/scss/sat_dashboard.scss',
            'sat/static/src/scss/alquiler_dashboard.scss',
            'sat/static/src/scss/gallery_widget.scss',

            # XML / QWeb
            'sat/static/src/xml/dashboard.xml',
            'sat/static/src/xml/photo_gallery_template.xml',
            'sat/static/src/xml/list_view.xml',
            'sat/static/src/xml/selection_subparts_template.xml',
            'sat/static/src/xml/sat_dashboard.xml',
            'sat/static/src/xml/alquiler_dashboard.xml',
            'sat/static/src/xml/geo_map_widget.xml',

            # JS locales
            'sat/static/src/js/selection_subparts.js',
            'sat/static/src/js/gallery_widget.js',
            'sat/static/src/js/**/*',
        ],

        'web.assets_frontend': [
            'sat/static/src/js/searchFilter.js',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
        ],

        'web.assets_qweb': [],
    },

    'demo': [
        'demo/demo_data.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
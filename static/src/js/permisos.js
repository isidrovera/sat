/** @odoo-module **/

/*
 * ============================================================
 * PERMISOS WEB
 * Ruta: /leave/request
 * Modelo backend: mantenimiento.tecnico.ausencia
 *
 * Este JS maneja:
 * - Día completo / por horas
 * - Fecha fin automática
 * - Nombre de archivo adjunto
 * - Validación frontend
 * - Envío por FormData
 * - Mensajes de éxito/error
 * ============================================================
 */

(function () {
    "use strict";

    const LOG_PREFIX = "[PermisosWeb]";

    function log(...args) {
        console.log(LOG_PREFIX, ...args);
    }

    function warn(...args) {
        console.warn(LOG_PREFIX, ...args);
    }

    function error(...args) {
        console.error(LOG_PREFIX, ...args);
    }

    function qs(selector, root = document) {
        return root.querySelector(selector);
    }

    function qsa(selector, root = document) {
        return Array.from(root.querySelectorAll(selector));
    }

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    ready(function () {
        const form = qs("#leaveRequestForm");

        if (!form) {
            return;
        }

        log("Inicializando formulario de permisos");

        const state = {
            submitting: false,
        };

        const els = {
            form,
            alertBox: qs("#leaveAlertBox"),
            submitBtn: qs("#submitLeaveBtn"),
            tipo: qs("#tipo"),
            fechaInicio: qs("#fecha_inicio"),
            fechaFin: qs("#fecha_fin"),
            diaCompleto: qs("#dia_completo"),
            hoursBlock: qs("#hoursBlock"),
            horaInicio: qs("#hora_inicio"),
            horaFin: qs("#hora_fin"),
            motivo: qs("#motivo"),
            adjunto: qs("#adjunto"),
            fileNameLabel: qs("#fileNameLabel"),
        };

        bindEvents(els, state);
        syncInitialState(els);
    });

    function bindEvents(els, state) {
        if (els.diaCompleto) {
            els.diaCompleto.addEventListener("change", function () {
                toggleHoursBlock(els);
            });
        }

        if (els.fechaInicio) {
            els.fechaInicio.addEventListener("change", function () {
                syncFechaFinMin(els);
                clearFieldError(els.fechaInicio);
            });
        }

        if (els.fechaFin) {
            els.fechaFin.addEventListener("change", function () {
                clearFieldError(els.fechaFin);
            });
        }

        if (els.tipo) {
            els.tipo.addEventListener("change", function () {
                clearFieldError(els.tipo);
            });
        }

        if (els.motivo) {
            els.motivo.addEventListener("input", function () {
                clearFieldError(els.motivo);
            });
        }

        if (els.horaInicio) {
            els.horaInicio.addEventListener("change", function () {
                clearFieldError(els.horaInicio);
            });
        }

        if (els.horaFin) {
            els.horaFin.addEventListener("change", function () {
                clearFieldError(els.horaFin);
            });
        }

        if (els.adjunto) {
            els.adjunto.addEventListener("change", function () {
                handleFileChange(els);
            });
        }

        els.form.addEventListener("submit", function (ev) {
            ev.preventDefault();
            submitForm(els, state);
        });
    }

    function syncInitialState(els) {
        toggleHoursBlock(els);
        syncFechaFinMin(els);
        handleFileChange(els, true);
    }

    function toggleHoursBlock(els) {
        if (!els.diaCompleto || !els.hoursBlock) {
            return;
        }

        const isFullDay = els.diaCompleto.checked;

        if (isFullDay) {
            els.hoursBlock.classList.add("d-none");

            if (els.horaInicio) {
                els.horaInicio.required = false;
            }

            if (els.horaFin) {
                els.horaFin.required = false;
            }

            log("Modo día completo activado");
        } else {
            els.hoursBlock.classList.remove("d-none");

            if (els.horaInicio) {
                els.horaInicio.required = true;
            }

            if (els.horaFin) {
                els.horaFin.required = true;
            }

            log("Modo por horas activado");
        }
    }

    function syncFechaFinMin(els) {
        if (!els.fechaInicio || !els.fechaFin) {
            return;
        }

        const fechaInicio = els.fechaInicio.value;

        if (!fechaInicio) {
            return;
        }

        els.fechaFin.min = fechaInicio;

        if (!els.fechaFin.value) {
            els.fechaFin.value = fechaInicio;
        }

        if (els.fechaFin.value < fechaInicio) {
            els.fechaFin.value = fechaInicio;
        }
    }

    function handleFileChange(els, silent = false) {
        if (!els.adjunto || !els.fileNameLabel) {
            return;
        }

        const file = els.adjunto.files && els.adjunto.files[0];

        if (!file) {
            els.fileNameLabel.textContent = "Ningún archivo seleccionado";
            return;
        }

        els.fileNameLabel.textContent = file.name;

        if (!silent) {
            log("Archivo seleccionado", {
                name: file.name,
                size: file.size,
                type: file.type,
            });
        }
    }

    function validateForm(els) {
        const errors = [];

        clearAllFieldErrors(els);

        const tipo = getValue(els.tipo);
        const fechaInicio = getValue(els.fechaInicio);
        const fechaFin = getValue(els.fechaFin) || fechaInicio;
        const motivo = getValue(els.motivo);
        const diaCompleto = els.diaCompleto ? els.diaCompleto.checked : true;
        const horaInicio = getValue(els.horaInicio);
        const horaFin = getValue(els.horaFin);

        if (!tipo) {
            errors.push("Selecciona el tipo de permiso.");
            markFieldError(els.tipo);
        }

        if (!fechaInicio) {
            errors.push("Selecciona la fecha de inicio.");
            markFieldError(els.fechaInicio);
        }

        if (fechaInicio && fechaFin && fechaFin < fechaInicio) {
            errors.push("La fecha fin no puede ser menor que la fecha de inicio.");
            markFieldError(els.fechaFin);
        }

        if (!motivo || motivo.length < 4) {
            errors.push("Ingresa un motivo válido para la solicitud.");
            markFieldError(els.motivo);
        }

        if (!diaCompleto) {
            if (!horaInicio) {
                errors.push("Ingresa la hora de inicio.");
                markFieldError(els.horaInicio);
            }

            if (!horaFin) {
                errors.push("Ingresa la hora de fin.");
                markFieldError(els.horaFin);
            }

            if (horaInicio && horaFin && timeToMinutes(horaFin) <= timeToMinutes(horaInicio)) {
                errors.push("La hora fin debe ser mayor que la hora inicio.");
                markFieldError(els.horaInicio);
                markFieldError(els.horaFin);
            }
        }

        const fileError = validateFile(els);
        if (fileError) {
            errors.push(fileError);
            markFieldError(els.adjunto);
        }

        return {
            valid: errors.length === 0,
            errors,
        };
    }

    function validateFile(els) {
        if (!els.adjunto || !els.adjunto.files || !els.adjunto.files.length) {
            return null;
        }

        const file = els.adjunto.files[0];
        const maxSize = 10 * 1024 * 1024;

        if (file.size > maxSize) {
            return "El archivo adjunto supera los 10 MB.";
        }

        const allowedExtensions = [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"];
        const fileName = (file.name || "").toLowerCase();

        const ok = allowedExtensions.some((ext) => fileName.endsWith(ext));

        if (!ok) {
            return "El archivo debe ser PDF, imagen o documento Word.";
        }

        return null;
    }

    async function submitForm(els, state) {
        if (state.submitting) {
            warn("Submit ignorado porque ya se está enviando");
            return;
        }

        hideAlert(els);

        const validation = validateForm(els);

        if (!validation.valid) {
            showAlert(
                els,
                "error",
                "Revisa la solicitud",
                validation.errors.join("<br/>")
            );
            scrollToAlert(els);
            return;
        }

        state.submitting = true;
        setSubmitting(els, true);

        try {
            const formData = new FormData(els.form);

            /*
             * Importante:
             * Cuando un checkbox no está marcado, el navegador no lo envía.
             * Por eso aseguramos dia_completo=true/false para el controlador.
             */
            if (els.diaCompleto) {
                formData.set("dia_completo", els.diaCompleto.checked ? "true" : "false");
            }

            if (els.fechaFin && !els.fechaFin.value && els.fechaInicio && els.fechaInicio.value) {
                formData.set("fecha_fin", els.fechaInicio.value);
            }

            log("Enviando solicitud a", els.form.action);

            const response = await fetch(els.form.action, {
                method: "POST",
                body: formData,
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            const data = await parseJsonResponse(response);

            if (!response.ok || !data.success) {
                const message = buildErrorMessage(data);
                showAlert(els, "error", "No se pudo enviar la solicitud", message);
                scrollToAlert(els);
                error("Error en respuesta", data);
                return;
            }

            log("Solicitud creada correctamente", data);

            showAlert(
                els,
                "success",
                "Solicitud enviada",
                data.message || "Tu solicitud fue enviada correctamente."
            );

            disableFormAfterSuccess(els);

            /*
             * Redirección opcional:
             * Esperamos un poco para que el usuario vea el mensaje.
             */
            if (data.redirect_url) {
                setTimeout(function () {
                    window.location.href = data.redirect_url;
                }, 1300);
            }

        } catch (err) {
            error("Error enviando formulario", err);

            showAlert(
                els,
                "error",
                "Error inesperado",
                "No se pudo enviar la solicitud. Intenta nuevamente o contacta al administrador."
            );

            scrollToAlert(els);

        } finally {
            state.submitting = false;
            setSubmitting(els, false);
        }
    }

    async function parseJsonResponse(response) {
        const text = await response.text();

        if (!text) {
            return {};
        }

        try {
            return JSON.parse(text);
        } catch (err) {
            error("Respuesta no es JSON", text);
            return {
                success: false,
                error: "Respuesta inválida del servidor.",
                raw: text,
            };
        }
    }

    function buildErrorMessage(data) {
        if (!data) {
            return "No se recibió respuesta del servidor.";
        }

        let message = data.error || data.message || "Ocurrió un error procesando la solicitud.";

        if (data.suggestion) {
            message += "<br/><small>" + escapeHtml(data.suggestion) + "</small>";
        }

        if (data.details && Array.isArray(data.details)) {
            message += "<br/><br/>";
            message += data.details.map(function (item) {
                const ref = item.name || "Registro";
                const tipo = item.tipo || "";
                const estado = item.estado || "";
                const desde = item.fecha_inicio || "";
                const hasta = item.fecha_fin || "";
                return "• " + escapeHtml(ref + " " + tipo + " " + estado + " " + desde + " - " + hasta);
            }).join("<br/>");
        }

        return message;
    }

    function setSubmitting(els, submitting) {
        if (!els.submitBtn) {
            return;
        }

        if (submitting) {
            els.submitBtn.disabled = true;
            els.submitBtn.dataset.originalText = els.submitBtn.textContent;
            els.submitBtn.textContent = "Enviando...";
        } else {
            els.submitBtn.disabled = false;
            els.submitBtn.textContent = els.submitBtn.dataset.originalText || "Enviar solicitud";
        }
    }

    function disableFormAfterSuccess(els) {
        qsa("input, select, textarea, button", els.form).forEach(function (el) {
            el.disabled = true;
        });
    }

    function showAlert(els, type, title, message) {
        if (!els.alertBox) {
            return;
        }

        els.alertBox.classList.remove("d-none", "is-success", "is-error", "is-warning");

        if (type === "success") {
            els.alertBox.classList.add("is-success");
        } else if (type === "warning") {
            els.alertBox.classList.add("is-warning");
        } else {
            els.alertBox.classList.add("is-error");
        }

        els.alertBox.innerHTML = "<strong>" + escapeHtml(title) + "</strong>" + message;
    }

    function hideAlert(els) {
        if (!els.alertBox) {
            return;
        }

        els.alertBox.classList.add("d-none");
        els.alertBox.classList.remove("is-success", "is-error", "is-warning");
        els.alertBox.innerHTML = "";
    }

    function scrollToAlert(els) {
        if (!els.alertBox) {
            return;
        }

        els.alertBox.scrollIntoView({
            behavior: "smooth",
            block: "center",
        });
    }

    function markFieldError(field) {
        if (!field) {
            return;
        }

        field.classList.add("o_leave_is-invalid");
        field.classList.remove("o_leave_is-valid");
    }

    function clearFieldError(field) {
        if (!field) {
            return;
        }

        field.classList.remove("o_leave_is-invalid");
    }

    function clearAllFieldErrors(els) {
        [
            els.tipo,
            els.fechaInicio,
            els.fechaFin,
            els.horaInicio,
            els.horaFin,
            els.motivo,
            els.adjunto,
        ].forEach(clearFieldError);
    }

    function getValue(el) {
        return el && el.value ? el.value.trim() : "";
    }

    function timeToMinutes(value) {
        if (!value) {
            return 0;
        }

        const parts = value.split(":");

        if (parts.length !== 2) {
            const floatValue = parseFloat(value);
            if (Number.isNaN(floatValue)) {
                return 0;
            }
            return Math.round(floatValue * 60);
        }

        const h = parseInt(parts[0], 10) || 0;
        const m = parseInt(parts[1], 10) || 0;

        return h * 60 + m;
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
})();
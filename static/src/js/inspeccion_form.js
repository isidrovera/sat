/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class InspeccionForm extends Component {
   setup() {
       this.notification = useService("notification");
       this.formRef = useRef("form");
       this.state = useState({
           isSubmitting: false,
       });
       
       onWillStart(async () => {
           const { token } = this.props;
           if (!token) {
               this.notification.add(this.env._t("Token inválido"), {
                   type: "danger",
               }); 
           }
       });
   }

   async onSubmit(ev) {
       ev.preventDefault();
       if (this.state.isSubmitting) return;

       const form = this.formRef.el;
       const formData = new FormData(form);

       this.state.isSubmitting = true;

       try {
           const response = await fetch('/inspeccion/submit', {
               method: 'POST',
               body: formData,
           });

           const result = await response.json();

           if (result.success) {
               this.notification.add(this.env._t("Inspección enviada"), {
                   type: "success",
               });
               window.location.href = '/inspeccion/gracias';
           } else {
               throw new Error(result.error);
           }

       } catch (error) {
           this.notification.add(error.message, {
               type: "danger",
           });
       } finally {
           this.state.isSubmitting = false;
       }
   }
}

InspeccionForm.template = "sat.InspeccionForm";
InspeccionForm.props = {
   token: String,
};

registry.category("public_components").add("InspeccionForm", InspeccionForm);
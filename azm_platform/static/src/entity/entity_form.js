import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";
import { formView } from "@web/views/form/form_view";

/** Entity page: keep the chatter below the content so the overview gets the full width. */
export class AzmEntityFormController extends FormController {
    get className() {
        const result = super.className;
        delete result["o_xxl_form_view h-100"];
        return result;
    }
}

export class AzmEntityFormRenderer extends FormRenderer {
    mailLayout(hasAttachmentContainer) {
        const layout = super.mailLayout(hasAttachmentContainer);
        return layout === "SIDE_CHATTER" ? "BOTTOM_CHATTER" : layout;
    }
}

registry.category("views").add("azm_entity_form", {
    ...formView,
    Controller: AzmEntityFormController,
    Renderer: AzmEntityFormRenderer,
});

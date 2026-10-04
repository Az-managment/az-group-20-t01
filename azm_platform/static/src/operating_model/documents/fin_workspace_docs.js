import { patch } from "@web/core/utils/patch";
import { AzmFinWorkspace } from "@azm_operating_model/fin_workspace/fin_workspace";

/** Read / download the document of a requirement (FIN.PUR.03 …) straight from the answer workspace. */
patch(AzmFinWorkspace.prototype, {
    async azmOpenDocument(req, download = false) {
        const action = await this.orm.call(
            "azm.fin.answer",
            download ? "action_azm_doc_download" : "action_azm_doc_read",
            [[req.answer_id]]
        );
        await this.actionService.doAction(action);
    },
});

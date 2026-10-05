import { patch } from "@web/core/utils/patch";
import { AzmFinWorkspace } from "@azm_operating_model/fin_workspace/fin_workspace";
import { deliver, holdTab } from "@azm_platform/components/doc_preview";

/** Read / download the document of a requirement (FIN.PUR.03 …) straight from the answer workspace. */
patch(AzmFinWorkspace.prototype, {
    async azmOpenDocument(req, download = false) {
        // the document is often built on the way out, and by the time it is ready the
        // browser has stopped counting the window as the reader's doing — so the tab is
        // claimed here, in the click itself, exactly as the tree and the library do
        const tab = download ? null : holdTab({ label: req.title || req.code });
        try {
            const action = await this.orm.call(
                "azm.fin.answer",
                download ? "action_azm_doc_download" : "action_azm_doc_read",
                [[req.answer_id]]
            );
            deliver(this, action, download, tab);
        } catch (error) {
            if (tab) {
                tab.close();
            }
            throw error;
        }
    },
});

import { patch } from "@web/core/utils/patch";
import { AzmWorkspace } from "@azm_operating_model/workspace/azm_workspace";

/** Let the platform open the answer workspace directly on a given stage. */
patch(AzmWorkspace.prototype, {
    setup() {
        super.setup(...arguments);
        const stageId = this.props.action?.params?.stage_id;
        if (stageId) {
            this.state.stageId = stageId;
        }
    },
});

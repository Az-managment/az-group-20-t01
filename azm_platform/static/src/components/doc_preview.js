/**
 * Reading a document in place, shared by every page that offers one.
 *
 * The tree and the outputs library both let somebody read a deliverable without
 * leaving the page they found it on. The behaviour lives here so the two cannot
 * drift: the same loading state, the same error in the pane rather than a dialog,
 * the same "open in a tab" and "download" beside it.
 *
 * A component using these keeps `preview` on its state and renders
 * azm_platform.DocPreview.
 */

/** Read a document in place. Builds it first if nobody ever has. */
export async function previewDocument(component, doc) {
    if (!doc) {
        return;
    }
    component.state.preview = { doc, loading: true, error: "", name: doc.label || "" };
    try {
        const found = await component.keepPreview.add(
            component.orm.call("azm.dashboard", "preview_tree_document", [], {
                kind: doc.kind,
                node_id: doc.id || null,
                tab: doc.tab || null,
                company_id: doc.company_id || component.previewCompanyId,
            })
        );
        component.state.preview = { doc, loading: false, error: "", ...found };
    } catch (error) {
        // say so where the reader is looking, rather than throwing them a dialog
        component.state.preview = {
            doc, loading: false, name: doc.label || "",
            error: (error && error.data && error.data.message) || (error && error.message)
                || "تعذّر عرض هذا المستند.",
        };
    }
}

export function closeDocument(component) {
    component.state.preview = null;
}

/** Open the document in a tab of its own, or download it. */
export async function openDocument(component, doc, download = false) {
    if (!doc) {
        return;
    }
    const action = await component.orm.call("azm.dashboard", "open_tree_document", [], {
        kind: doc.kind,
        node_id: doc.id || null,
        tab: doc.tab || null,
        company_id: doc.company_id || component.previewCompanyId,
        download,
    });
    await component.action.doAction(action);
}

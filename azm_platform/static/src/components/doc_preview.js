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

/**
 * Open the document in a tab of its own, or download it.
 *
 * The tab is opened inside the click, before anything is awaited. A document is often
 * built on the way out — the first time anybody asks for it, which is the whole point
 * of building on open — and by the time its url comes back the browser has stopped
 * counting the window as the reader's doing and blocks it as a popup. So the tab is
 * opened empty straight away, told what it is waiting for, and pointed at the document
 * when there is one. A download asks for no window at all — see deliver().
 */
export async function openDocument(component, doc, download = false) {
    if (!doc) {
        return;
    }
    const tab = download ? null : holdTab(doc);
    try {
        const action = await component.orm.call("azm.dashboard", "open_tree_document", [], {
            kind: doc.kind,
            node_id: doc.id || null,
            tab: doc.tab || null,
            company_id: doc.company_id || component.previewCompanyId,
            download,
        });
        deliver(component, action, download, tab);
    } catch (error) {
        // a tab left sitting on "preparing…" for ever is worse than no tab: the error
        // itself is shown where the reader is, by whoever called this
        if (tab) {
            tab.close();
        }
        throw error;
    }
}

/** The empty tab, opened in the click so the browser allows it. */
export function holdTab(doc) {
    const tab = window.open("", "_blank");
    if (!tab) {
        return null;   // blocked outright; the caller falls back to Odoo's own handling
    }
    tab.document.write(
        '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">' +
        "<title>" + escapeHtml(doc.label || "مستند") + "</title></head>" +
        '<body style="font:14px system-ui,sans-serif;color:#64748b;padding:2rem">' +
        'يُجهَّز المستند… <span style="color:#94a3b8">Preparing the document…</span>' +
        "</body></html>");
    tab.document.close();
    return tab;
}

/**
 * Hand the reader the document, without asking the browser for a window.
 *
 * Odoo opens a download the same way it opens a tab — window.open — and this is reached
 * after the document has been built, by which time the browser blocks it. A download
 * needs no window: a link clicked for it is not a popup, and the file lands with the
 * name the server gave it.
 */
export function deliver(component, action, download, tab = null) {
    if (download) {
        const link = document.createElement("a");
        link.href = action.url;
        link.download = "";       // same origin, so the server's filename is kept
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        return;
    }
    if (tab) {
        // replace, so the holding page is not left in the tab's history
        tab.location.replace(action.url);
        return;
    }
    // the window was refused outright: let Odoo say so in its own words. The service is
    // called `action` on the pages here and `actionService` in the answer workspace.
    const service = component.action || component.actionService;
    if (service) {
        service.doAction(action);
    }
}

/** The document's own title goes into the holding page, so it is escaped. */
function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

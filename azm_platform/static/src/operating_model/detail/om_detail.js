import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * What is behind a figure on an operating model page — shown beside it.
 *
 * Every count on those pages used to be a door into the backend: the questions of a
 * stage, the findings of a domain, the requirements of a module, the gaps of an
 * entity. Clicking one swapped the page for a list view with its own filters and its
 * own breadcrumb, and none of the context the reader had built up; coming back meant
 * building it again.
 *
 * The panel fetches its own rows from the kind and scope it is given, so a page says
 * what it wants to show rather than how to fetch it. It is mounted under a key made of
 * the two, which is what reloads it when the reader asks for something else.
 */
export class AzmOmDetail extends Component {
    static template = "azm_platform.OmDetail";

    props = useProps({
        // one of: questions, findings, requirements, gaps
        kind: t.string(),
        // the named parts of the scope; the server builds the domain from them
        scope: t.any().optional(() => ({})),
        // what the reader clicked, said in their words rather than the kind's
        heading: t.string().optional(""),
        onClose: t.function(),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ loading: true, error: "", data: null, query: "", open: {} });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.data = await this.orm.call("azm.dashboard", "om_detail", [], {
                kind: this.props.kind,
                ...(this.props.scope || {}),
            });
        } catch (error) {
            this.state.error = (error && error.data && error.data.message)
                || (error && error.message) || "Could not load the details.";
        } finally {
            this.state.loading = false;
        }
    }

    get title() {
        return this.props.heading || (this.state.data ? this.state.data.title : "");
    }

    /** The rows that match what is typed, matched across everything on show rather
     * than the title alone — a code and an entity are what people actually type. */
    get rows() {
        const rows = this.state.data ? this.state.data.rows : [];
        const query = this.state.query.trim().toLowerCase();
        if (!query) {
            return rows;
        }
        return rows.filter((row) =>
            `${row.code} ${row.title} ${(row.meta || []).join(" ")}`.toLowerCase().includes(query));
    }

    isOpen(row) {
        return !!this.state.open[row.id];
    }

    toggle(row) {
        if (!row.detail) {
            return;
        }
        this.state.open[row.id] = !this.state.open[row.id];
    }
}

import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

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
        this.state = proxy({
            loading: true, error: "", data: null, query: "", open: {},
            rows: [], total: 0, hasMore: false, loadingMore: false,
        });
        // searched as it is typed, but not once per keystroke: the catalogue is
        // searched on the server now, and a request per letter would have the answers
        // arriving out of order
        this.searchLater = useDebounced(() => this.load(), 300);
        onWillStart(() => this.load());
    }

    /** Fetch from the start, with whatever is typed. */
    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const out = await this.fetch(0);
            this.state.data = out;
            this.state.rows = out.rows;
            this.state.total = out.total;
            this.state.hasMore = out.has_more;
        } catch (error) {
            this.state.error = this.messageOf(error);
        } finally {
            this.state.loading = false;
        }
    }

    /** Fetch the next page and add it to what is already shown. */
    async loadMore() {
        if (this.state.loadingMore || !this.state.hasMore) {
            return;
        }
        this.state.loadingMore = true;
        try {
            const out = await this.fetch(this.state.rows.length);
            this.state.rows = [...this.state.rows, ...out.rows];
            this.state.total = out.total;
            this.state.hasMore = out.has_more;
        } catch (error) {
            this.state.error = this.messageOf(error);
        } finally {
            this.state.loadingMore = false;
        }
    }

    fetch(offset) {
        return this.orm.call("azm.dashboard", "om_detail", [], {
            kind: this.props.kind,
            query: this.state.query,
            offset,
            ...(this.props.scope || {}),
        });
    }

    onQueryInput(value) {
        this.state.query = value;
        this.searchLater();
    }

    messageOf(error) {
        return (error && error.data && error.data.message)
            || (error && error.message) || "Could not load the details.";
    }

    get title() {
        return this.props.heading || (this.state.data ? this.state.data.title : "");
    }

    get rows() {
        return this.state.rows;
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

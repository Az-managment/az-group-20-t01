import { registry } from "@web/core/registry";

/**
 * The Trees page and the two trees it opens: the page lists the entities, opening one
 * shows the trees it has, and a tree walks down to a leaf. The way back lands on the
 * entities again.
 */
registry.category("web_tour.tours").add("azm_trees_tour", {
    steps: () => [
        // the landing page: a card per entity, and no tree until one is picked
        { trigger: ".o_azm_trees .o_azm_entities_grid .o_azm_tree_card" },
        { trigger: ".o_azm_trees:not(:has(.o_azm_trees_financial))" },
        { trigger: ".o_azm_trees .o_azm_entities_grid .o_azm_tree_card:first-child", run: "click" },
        // that entity opened: the trees it has, named and counted
        { trigger: ".o_azm_trees .o_azm_trees_crumb_here strong" },
        { trigger: ".o_azm_trees .o_azm_trees_procurement" },
        { trigger: ".o_azm_trees .o_azm_trees_financial", run: "click" },

        // the financial tree, opened on the entity whose card was clicked
        { trigger: ".o_azm_tree_financial .o_azm_tree_panel .o_azm_tree_l1" },
        // every output of a branch hangs on it: fold them open, then away again
        { trigger: ".o_azm_tree_financial .o_azm_tree_branch:first-child .o_azm_tree_docs_btn", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_docs .o_azm_doc_chip .o_azm_doc_open" },
        // a document is read inside the tree, not in a tab of its own
        { trigger: ".o_azm_tree_financial .o_azm_tree_docs .o_azm_doc_open", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_preview_frame" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_preview_tools button:last-child", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_docs_btn.o_azm_open", run: "click" },
        // how many policies, how many SOPs — and each count is a way to them.
        // "All" is a chip too and is the one pressed to begin with, so the filter
        // being exercised here is any chip that is not it.
        { trigger: ".o_azm_tree_financial .o_azm_tree_outputs .o_azm_output_chip" },
        { trigger: ".o_azm_tree_financial .o_azm_output_chip:not(.o_azm_output_all)", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_output_chip.o_azm_active:not(.o_azm_output_all)" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_docs .o_azm_doc_chip" },
        { trigger: ".o_azm_tree_financial .o_azm_output_chip.o_azm_active:not(.o_azm_output_all)", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_l1:first-child", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_l2:first-of-type", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_l3", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_detail .o_azm_tree_facts" },

        // back to the entities, into the same one, and down its other tree
        { trigger: ".o_azm_tree_financial .o_azm_tree_back", run: "click" },
        { trigger: ".o_azm_trees .o_azm_entities_grid .o_azm_tree_card:first-child", run: "click" },
        { trigger: ".o_azm_trees .o_azm_trees_procurement", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_panel .o_azm_tree_l1" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_branch:first-child .o_azm_tree_docs_btn", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_docs .o_azm_doc_chip .o_azm_doc_open" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_outputs .o_azm_output_chip" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_l1:first-child", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_l2:first-of-type", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_l3", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_detail .o_azm_tree_facts" },
    ],
});

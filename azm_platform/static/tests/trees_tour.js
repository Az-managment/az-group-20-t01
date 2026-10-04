import { registry } from "@web/core/registry";

/**
 * The Trees page and the two trees it opens: a card picks an entity, the tree walks
 * down to a leaf, and the way back lands on the list of trees again.
 */
registry.category("web_tour.tours").add("azm_trees_tour", {
    steps: () => [
        // the landing page: a section per model, a card per entity under it
        { trigger: ".o_azm_trees .o_azm_trees_financial .o_azm_trees_grid .o_azm_tree_card" },
        { trigger: ".o_azm_trees .o_azm_trees_procurement .o_azm_trees_grid .o_azm_tree_card" },
        { trigger: ".o_azm_trees .o_azm_trees_financial .o_azm_tree_card:first-child", run: "click" },

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
        // how many policies, how many SOPs — and each count is a way to them
        { trigger: ".o_azm_tree_financial .o_azm_tree_outputs .o_azm_output_tile" },
        { trigger: ".o_azm_tree_financial .o_azm_output_tile:not(:disabled)", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_output_tile.o_azm_active" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_docs .o_azm_doc_chip" },
        { trigger: ".o_azm_tree_financial .o_azm_output_tile.o_azm_active", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_l1:first-child", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_l2:first-of-type", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_l3", run: "click" },
        { trigger: ".o_azm_tree_financial .o_azm_tree_detail .o_azm_tree_facts" },

        // back to the list of trees, then down the other one
        { trigger: ".o_azm_tree_financial .o_azm_tree_back", run: "click" },
        { trigger: ".o_azm_trees .o_azm_trees_procurement .o_azm_tree_card:first-child", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_panel .o_azm_tree_l1" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_branch:first-child .o_azm_tree_docs_btn", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_docs .o_azm_doc_chip .o_azm_doc_open" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_outputs .o_azm_output_tile" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_l1:first-child", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_l2:first-of-type", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_l3", run: "click" },
        { trigger: ".o_azm_tree_procurement .o_azm_tree_detail .o_azm_tree_facts" },
    ],
});

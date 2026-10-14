import { registry } from "@web/core/registry";

/**
 * The outputs library: filter the shelf, open a deliverable to see which entities hold
 * it, and read one in place.
 */
registry.category("web_tour.tours").add("azm_library_tour", {
    steps: () => [
        { trigger: ".o_azm_library .o_azm_library_kpis .o_azm_kpi" },
        { trigger: ".o_azm_library .o_azm_output .o_azm_output_type" },
        // narrowing by a kind of output leaves only that kind on the shelf
        { trigger: ".o_azm_library .o_azm_library_rail button.o_azm_facet", run: "click" },
        { trigger: ".o_azm_library .o_azm_facet.o_azm_on" },
        { trigger: ".o_azm_library .o_azm_output" },
        // a deliverable names the entities that hold it
        { trigger: ".o_azm_library .o_azm_output_head", run: "click" },
        { trigger: ".o_azm_library .o_azm_output_entities .o_azm_output_entity" },
        // and one of them can be read without leaving the page
        { trigger: ".o_azm_library .o_azm_output_actions .btn:first-child", run: "click" },
        { trigger: ".o_azm_library .o_azm_library_preview .o_azm_tree_preview_frame" },
        { trigger: ".o_azm_library .o_azm_tree_preview_tools button:last-child", run: "click" },
        // and the filter is its own undo
        { trigger: ".o_azm_library .o_azm_library_clear", run: "click" },
        { trigger: ".o_azm_library .o_azm_library_rail .o_azm_facet:not(.o_azm_on)" },
    ],
});

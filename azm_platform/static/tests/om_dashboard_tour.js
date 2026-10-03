import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("azm_om_dashboard_tour", {
    steps: () => [
        // AZM Home: Operating Model KPI + section
        { trigger: ".o_azm_dashboard .o_azm_kpi [data-icon=view_module]" },
        { trigger: ".o_azm_dashboard .o_azm_om_home .o_azm_om_home_domain:nth-child(3)", run: "click" },
        // Operating Model page opened on the Financial domain
        { trigger: ".o_azm_om .o_azm_om_tab.active:nth-child(4)" },
        { trigger: ".o_azm_om .o_azm_om_stage .o_azm_om_stage_code:contains(PUR-PAY)" },
        { trigger: ".o_azm_om .o_azm_om_tab:nth-child(1)", run: "click" },
        { trigger: ".o_azm_om .o_azm_om_tab.active:nth-child(1)" },
        { trigger: ".o_azm_om .o_azm_om_stage .o_azm_om_stage_code:contains(PUR-GOV)" },
        { trigger: ".o_azm_om .o_azm_om_kpis .o_azm_kpi" },
        // Switch to the unified financial model
        { trigger: ".o_azm_om .o_azm_om_models .o_azm_om_model:nth-child(3)", run: "click" },
        { trigger: ".o_azm_fin_page .o_azm_om_model.active:nth-child(3)" },
        { trigger: ".o_azm_fin_page .o_azm_om_stage .o_azm_om_stage_code:contains(FIN-WFC)" },
        { trigger: ".o_azm_fin_page .o_azm_om_tab:nth-child(3)", run: "click" },
        { trigger: ".o_azm_fin_page .o_azm_om_tab.active:nth-child(3)" },
        // Back to the operating models (files) and open the procurement file
        { trigger: ".o_azm_fin_page .o_azm_om_model_back", run: "click" },
        { trigger: ".o_azm_hub .o_azm_hub_file:nth-child(2)" },
        { trigger: ".o_azm_hub .o_azm_hub_file:nth-child(1) header", run: "click" },
        { trigger: ".o_azm_om .o_azm_om_model.active:nth-child(2)" },
        // Financial assessments live inside the financial model file
        { trigger: ".o_azm_om .o_azm_om_model_back", run: "click" },
        { trigger: ".o_azm_hub .o_azm_hub_file:nth-child(2) .o_azm_hub_link:nth-child(1)", run: "click" },
        { trigger: ".o_azm_unified .o_azm_om_tab.active:nth-child(3)" },
        { trigger: ".o_azm_unified .o_azm_om_tab:nth-child(1)", run: "click" },
        { trigger: ".o_azm_unified .o_azm_om_tab.active:nth-child(1)" },
    ],
});

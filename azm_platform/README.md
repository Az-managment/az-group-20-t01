# AZM Enterprise Operating Model Platform (Odoo 20)

A **read-only cockpit** over the data that already exists in your Odoo database.
Nothing is duplicated: every figure is computed live.

| Screen element | Source in Odoo |
|---|---|
| Entities (cards / list / group tree / entity page) | `res.company` (Settings › Companies) |
| Employees, "People by department", teams | `hr.employee`, `hr.department` |
| Projects, open / overdue tasks, task completion %, "My tasks" | `project.project`, `project.task`, `mail.activity` |
| Documents | `documents.document` (Enterprise, auto-detected) or `ir.attachment` |
| Recent activity | chatter messages (`mail.message`) of the records above |
| Login page (group list, stats, hero image) | companies + employee count |

## Install
1. Copy `azm_platform` into your custom addons path.
2. Update the apps list, install **AZM Enterprise Operating Model Platform**
   (pulls `hr`, `project`, `web_hierarchy`, `auth_oauth`).
3. Give users the group **AZM Platform / User** (or Administrator).
4. Optional: Settings › Languages › add Arabic — the module ships `i18n/ar.po`.

## Make it look like the design
On each company (Settings › Companies › *company* › **AZM Platform** tab) set:
logo, cover image, name in the other language, entity type, sector, tagline.
The root company's cover image is used as the login-page background.

Status per entity is derived automatically:
*Active* = has employees, departments and projects · *In preparation* = some of them · *Not started* = none.

## Sign in with Microsoft / Google
Settings › Integrations › OAuth Providers: enable Google and/or add Azure AD (Microsoft).
The buttons then appear on the AZM login card.

## AI assistant
Settings › AZM Platform: paste an Anthropic API key (and optionally the model name).
The assistant answers using the live figures of your companies.

## Notes
* Every figure respects the access rights of the person looking at it: counts, charts,
  lists and the AI assistant only include the records that person is allowed to open
  (companies they belong to, HR / Project / Documents rights and record rules).
* The sidebar only appears inside the AZM app; other Odoo apps are untouched.

## Who sees what
* Every AZM screen (Home, Entities, Group Structure, entity pages, AI assistant) follows the
  **company switcher** (top right) like the rest of Odoo: tick several companies to see them together.
* Counts and lists only include records the person may open (HR / Project / Documents rights and record rules).
* Links, cards and quick links to an app the person has no rights on are hidden (or not clickable)
  instead of ending on an access error; "Edit entity data" is for Settings › Access Rights administrators.
* Group Structure only shows companies the person belongs to; a company whose parent is hidden
  is attached to its nearest visible ancestor.


# Operating models
Included in this module (requires **azm_operating_model**, installed automatically as a dependency).
It replaces the former bridge module *azm_platform_operating_model*: upgrading `azm_platform` moves its data and retires it.

## Operating Models (files)
The sidebar entry **Operating Models** opens a landing page where every operating model is a *file*:
**Procurement cycle** (13 stages · 396 questions) and **Unified financial model** (17 modules · 167 requirements).
Each file shows its KPIs (assessments, completion, certainty / maturity, open findings / gaps, entities covered);
clicking it opens the model page with all its data and statistics. Group KPIs and an entity × model table sit on top and below.

## شجر · Trees
The sidebar entry **شجر · Trees** — marked by the group's own tree, three tiers drawn from
the same triangle as the AZM logo (`static/src/components/tree_mark.xml`, one SVG in
`currentColor` that serves the dark sidebar, a tinted badge and a card footer at any size)
— opens a landing page of every model that can be walked
branch by branch, three levels deep. There is a section per model and a **card per entity**
under it, carrying that entity's own figures; clicking a card opens *that entity's* tree:

| Tree | Levels | A leaf shows |
|---|---|---|
| Unified financial model | module › topic › requirement | what is required, what happens in this entity today, and its filed document (read / download) |
| Procurement cycle | stage › group › question | what is asked, the answer this entity gave, the sentence the book will print from it, and the risks the catalogue watches on that answer |

Both trees are the same page with a different leaf: walking, searching, folding and the entity
picker live in one component (`static/src/operating_model/trees/tree_base.js`) and one set of
templates, so a third model costs a section on the landing page and a detail panel.

### Every output hangs on the tree
A branch carries all of its outputs, a leaf carries its own sheet, and the tree carries
the entity's summary — all of them real documents, filed in the Documents app:

| On the tree | Documents |
|---|---|
| a financial module | 7 outputs: policies, SOPs, authority, reports & KPIs, integration, gaps, target direction |
| a procurement stage | 11 outputs: current state, policy, procedure, workflow map, authority, gaps, risks, controls, system requirements, KPIs, coverage |
| a leaf | its own requirement sheet / question sheet |
| the tree itself | the entity summary / the cycle summary |

They are one kind of object: the same record (`azm.doc.publication`), the same report, the
same per-company folder tree. An output whose body its own engine writes (a policy, a
procedure, a workflow drawing) hands the report that prose; everything around it — cover,
path, status banner, at-a-glance table, controlled-copy footer — is identical to a
requirement sheet's.

The tree offers every output the catalogue defines, published or not. The document is
resolved when somebody opens it, and **built then if nobody has read it yet**: the cycle
asks 396 questions of each entity, so pre-rendering all of them for every company would
spend hundreds of megabytes on PDFs nobody asked for. A document already read is re-used,
and rebuilt by itself once the answers behind it move.

A node's status is that entity's own answer and nothing else. On the procurement tree,
visibility is decided by the engine that drives the answer workspace, so a question this
entity is never asked reads as "لا يُسأل هنا" rather than as an unanswered hole. An entity
that has not started still gets a card and a tree — it shows what the model asks of it.

## What it adds
| Where | What |
|---|---|
| AZM sidebar | **Operating Model**, **Assessments**, **Risk Register**, **شجر · Trees**, **Question Catalogue** (managers) |
| Unified financial model page | KPIs, application status, one card per financial module (FIN/HRF, templates, applicability, completion, maturity, gaps), charts, entities, top gaps, assessments |
| Operating Model page | 8 KPIs, 3 domain cards (Governance / Procurement Operations / Financial), one card per question area (stage) with questions, risk rules, risks, findings, completion, certainty, question mix, application status; risk-register & assessment donuts; entities table; top open risks; current assessments |
| AZM Home | "Operating Model" KPI tile, quick links and an Operating Model section (KPIs, domains, latest assessments, top risks) |
| Entity (company) page | Operating Model section for the entities linked to that company |
| Operating Model app | Same page as the first menu "لوحة المؤشرات" |

## Model domains
Each stage gets a **Model Domain** (Settings › Stages):
`GOV` → Governance · `BUD INV ADV PAY CLS` → Financial · the rest → Procurement Operations.
Change it per stage if needed; the value you choose is kept on catalogue reloads.
Questions, risk rules and findings inherit it (filters/group-by "Model Domain").

## Entities ↔ companies
On install, Operating Model entities are linked to companies whose name, "Name (other language)"
or initials match. Otherwise link them in Operating Model › Settings › Entities (column "Company").

## Filters on the page
Domain tabs · entity · one assessment (then each card opens the answer workspace on that stage).

## Figures
Computed live with the same engine as the answer workspace:
* Completion = answered / applicable (visible) questions
* Certainty = answers that are not "لا أعرف / غير مدرج" / answered
* Risks triggered = risk rules matched by current answers; Open findings = tracked risk register
* High = likelihood × impact ≥ 15

## Tests
`odoo-bin -d <db> -u azm_platform --test-tags=/azm_platform --stop-after-init`

## Who sees what (operating models)
Every page only counts the records the person may open (no superuser totals):
* **Role** – preparer: own assessments · reviewer: own + those assigned to them · manager: everything.
* **Entity** – non-managers only see entities they are listed on (Operating Model › Settings › Entities › "Allowed users").
* **Company** – only entities/assessments of the companies the person belongs to.
* Platform figures (employees, departments, projects, tasks, documents) follow HR / Project / Documents rights.

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

## مساحتي · My work
Home is the group's cockpit — every entity, every model, the whole picture. It is the
right page for somebody who runs the group and the wrong one for somebody whose job is
to answer their own entity's questions: they were opening it onto figures they cannot
act on, next to a technical menu holding the question catalogue.

**مساحتي** is the other page, and it is where an AZM user lands when they log in. One
person: the entities they are assigned to, each model they can answer with how far it
has got and exactly how many questions are left, where their work stands in words —
*معك الآن*, *مع المراجع*, *معتمدة* — the deliverables their answers have produced, and
the projects, tasks and team around the work. Everything on it is already narrowed by
the record rules, so a manager opening it sees their own work rather than everybody's.

**A model can be divided.** The financial model is 19 modules; Treasury, HR and
Procurement each know their own part. A module — or a stage of the cycle — can be given
to somebody from the assessment's **التوزيع** tab, and then it is theirs: they answer it
and everybody else reads it, including the person preparing the assessment. What is not
given to anybody stays with the preparer, so an entity that does not want to divide the
work changes nothing. مساحتي then counts each person's own parts: *"14 questions left"*
has to be *their* fourteen. An administrator sees the whole picture across both models
under **من يجيب ماذا** — who has what, and how far they have got.

**Answering and reviewing are two jobs, and they get two pages.** When every question of
the assessment is answered — and only then, and only for the person preparing it —
**أرسل للمراجعة** appears on the row. Somebody who has finished their own share while
other parts are still open sees *بانتظار البقية* instead: their count is their share,
but what goes for review is the whole of it, and sending it early would have taken
everybody else's unanswered work to the reviewer along with it.

The answering workspace offers the same step in the place it is reached: at the end of
the model the forward button stops being *الموديول التالي* and becomes whatever is
actually left — the first part still missing answers, or **أرسل للمراجعة** when nothing
is. Whether it may be sent is the record's own answer (`_azm_can_send`), so the
workspace, مساحتي and the server that honours either cannot disagree about it. It hands the work to
whoever reviews it and says who that was. Submitting used to write the state and
schedule an activity *if* a reviewer happened to be named on the record; where none was,
the work left the preparer's hands and arrived in nobody's. Now it goes to the named
reviewer, else to the reviewers assigned to that entity, else to the managers — and if
somehow nobody can be reached it refuses rather than parking the work in a state nobody
is watching. A preparer is never their own reviewer.

A reviewer's page carries a second section, **بانتظار مراجعتك**: the work submitted on
the entities they are assigned to, never their own. They can open what they are shown —
the rules and the list say the same thing, so the two cannot drift apart.

| Who | Lands on | The AZM sidebar holds |
|---|---|---|
| مُعد إفادات (answerer) | مساحتي | **مساحتي** and **مكتبة المخرجات** — their work, and what it produces |
| مراجع (reviewer) | مساحتي | the above, plus **الإفادات**, **سجل المخاطر**, **شجر**, المشاريع والمهام والمستندات |
| مدير النموذج (manager) | wherever they choose | all of it, plus **التقدّم**, the cockpit, the catalogue and the configuration — but not **مساحتي**, which is one person's own work |

Somebody whose job is answering their entity's questions was being shown the group
cockpit, the entity list, the group structure and the model dashboards — figures about
other people's work that they cannot act on — and a technical menu holding the question
catalogue beside them. Each role now gets the pages its job needs and no more.

Accepting the answers **publishes what they produce**. A document is built from the
answers and rebuilt whenever they change, which the queue notices within the hour —
right while the work is being done, wrong at the moment it is signed off. So acceptance
sets the queue going: the entity's policies, procedures, authority matrices and books
are built and filed into its Documents folders in the moment after, and the assessment
says so in its own chatter. Queued rather than built in the click: an entity holds some
two hundred and fifty documents and each one is a PDF.

**التقدّم · Progress** is the administrator's page, and deliberately not مساحتي:
somebody tracking the work does not want their own work, they want everybody's. Who
prepares each model for each entity, who reviews it, where it stands, how much is
answered, and — where the work has been divided — which part belongs to whom and how far
each of them has got, with a per-person summary on top. The people being tracked are not
offered it.

Each person on it is described by what they actually carry. Measuring everybody on
answering parts told a reviewer with three assessments to look at that they had
*لا أجزاء مُسندة إليه*, and somebody preparing ten the same — so it reads *يجيب N جزءًا*,
*يُعدّ N إفادة*, *يراجع N إفادة*, and the figure beside it is whichever of those is
actually outstanding: questions left in their parts, questions left in the drafts they
prepare, or assessments waiting on their review. Whoever is carrying the most sorts
first.

Opening the answers from مساحتي lands in the **answering workspace**, for both models,
rather than on the assessment's form with another button to find. A reviewer opens the
same workspace to read what was sent, then **اقبل الإجابات** to accept it — which
snapshots the version and records who accepted — or sends it back, which returns it to
the preparer and tells them. Nobody accepts their own work; that is the one part of
manager-only approval worth keeping, and it is still enforced.

The technical menu — the question catalogue, the stages, the risk rules, the financial
model's own configuration — is a reviewer's and upwards. An answerer was being shown it
next to their work. Note what this is and is not: the **menu** is what hides it, and
that takes the catalogue out of the interface. Reading a question is still permitted,
because answering one requires it — so the data remains reachable to somebody who goes
looking for it over RPC. What has gone is any way to sit and browse it.

## شجر · Trees
The sidebar entry — **شجر** to an Arabic reader and **Trees** to an English one, never
both at once — marked by the group's own tree, three tiers drawn from
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

### Coding — AZM Master Coding Registry v2.1
Every document carries the registry's canonical identifier and nothing else inside it:

```
AZM-<DOMAIN>-<TYPE>-<SERIAL>        AZM-FIN-POL-000001
```

Identity holds no entity, no version and no lifecycle stage — those stand beside it, as
the registry asks a controlled PDF to carry them: `AZM-FIN-POL-000001 · FUIE · v1 · CS`.
One artifact is registered per node and output for the whole group (`azm.artifact`), so
the nine entities holding the policy of FIN.GOV all print the same code and are told
apart by scope.

Only what exists is numbered. A module with no requirement of a kind has no document
of that kind — FIN.GOV holds no procedure — so it takes no serial, is not offered on the
tree and is not counted; the first procedure is the first module that has one. The same
holds for the cycle: the engine does not write governance as an operating procedure, so
a governance stage has neither procedure nor workflow. And a document is offered to an
entity only if that entity's own answers put something in it.

Serials follow **the model, not the reader**: the whole catalogue is numbered in its own
order — modules by the canonical ID the registry gave them, then their outputs, then the
leaves, then the documents belonging to the model as a whole. So `AZM-FIN-POL-000001` is
the policy of FIN.GOV whichever document anyone happened to open first, and the fifth is
FIN.INV's because the registry orders INV before PUR. Once numbered an artifact never
moves; a module added later takes the next serial rather than displacing anyone. Requirements keep the IDs the registry already gave them (`AZM-FIN-REQ-000004`);
they are not renumbered here. Modules carry their registry IDs too — taken from the file,
not derived, because the registry orders INV before PUR and the catalogue does not.

| Output | Type | Stage |
|---|---|---|
| policies / السياسات | POL | CS |
| procedures, SOPs | PRO | CS |
| workflow map | WFL | CS |
| authority, DOA | DOA | CS |
| reports & KPIs | RPT / KPI | CS / CA |
| system requirements | SRQ | TD |
| gaps | GAP | GR |
| risks | RSK | GR |
| controls | CTL | TD |
| target direction | DEC | TD |
| requirement / question sheet | REQ | CS |
| entity & cycle summary | RPT | CS |
| the bound book | MAN | CS |

The lifecycle (CS → GR → TD → SF → IMP → UAT → GLA → CA) is a stage a document speaks
from, never part of what it is called. A document filed under an older coding ages by
itself and is rebuilt the next time it is read.

### One book for all of it
A button on each tree binds the entity's whole model into a single filed PDF: the
summary first, then every branch output in tree order — 69 documents, one volume, with a
contents page. It is built when asked for, like the rest.

### Read where you picked, and see what is on file
A document opens **inside the tree**: the tree keeps the left, the document takes the
right, and closing the preview puts the node's own detail back. Opening it in a tab and
downloading it are still a click away in the preview's header.

Above the tree, a tile per family says how many of each this entity holds — 14 policies,
10 SOPs, 8 authority maps — counted from what the tree offers less the outputs the model
found nothing to say in. The tile is also the way to them: clicking it unfolds every
branch showing just that family.

A node's status is that entity's own answer and nothing else. On the procurement tree,
visibility is decided by the engine that drives the answer workspace, so a question this
entity is never asked reads as "لا يُسأل هنا" rather than as an unanswered hole. An entity
that has not started still gets a card and a tree — it shows what the model asks of it.

## مكتبة المخرجات · Outputs Library
The sidebar entry — **مكتبة المخرجات**, or **Outputs Library** in English — reads the
group the other way round from the trees. A tree reads one model for one entity; the library reads **one deliverable
across every entity** — the question the trees cannot answer: *how many of our entities
have a procurement policy, and which ones are missing it?*

A deliverable is the master artifact of the coding registry, so it appears once however
many entities hold a copy; the bar on its row is how many of them have theirs ready.
Opening a row names the entities, and each one can be read in place, downloaded, have
its **whole book** downloaded as a single PDF, or be opened **on that entity's tree** —
on the branch, with the output showing, rather than at the top of the model. A tree is
one entity's, so each entity carries its own way onto it.

Picking a kind of output offers one more thing: **اجمعها في مستند واحد**, which binds
all of that kind for one entity into a single volume — the policy manual, the procedure
manual. The entity book binds one model whole in tree order; this binds one kind across
the branches and across both models, which is the shape somebody asking for "our
policies" means. It is a compilation, not a deliverable: every part carries its own
registry code and the volume takes none.

Filters narrow by:

| | |
|---|---|
| entity | a set — pick any of the entities you work in; asking for one you do not only ever narrows |
| kind of output | POL, PRO, WFL, DOA, CTL, KPI, RPT, SRQ, GAP, RSK, DEC, MAN |
| model | the unified financial model, or the procurement cycle |
| lifecycle stage | CS → GR → TD → SF → IMP → UAT → GLA → CA |
| position in the tree | FIN.GOV, PUR-REQ … |
| search | by code or node |

Only what the group actually produces is on the shelf, and only that is numbered. Every
entity marked investments, real estate and inter-company **not applicable** — nobody does
that work — so there is no investments policy and no investments SOP. Fourteen codes
stood for documents that exist nowhere, and each of them pushed every real deliverable
after it up a place, which is why the third procedure once looked like the first. The
registry is derived rather than accumulated: numbered in the catalogue's order, skipping
what nothing is produced for, closing up so each type reads `000001..N` with no holes. A
deliverable that becomes real later — an entity takes on investments — takes its place in
that order and the ones after it move down. A document prints its code into its own
fingerprint, so the ones affected age by themselves and are rebuilt when next read.

The per-requirement and per-question sheets are left out unless asked for: there are
nine hundred of them and the tree is where they are read. Reading a document in place is
the same component the trees use (`static/src/components/doc_preview.*`), so a
deliverable looks and behaves the same whichever page you found it on.

## What it adds
| Where | What |
|---|---|
| AZM sidebar | **My work** (first, and where an AZM user lands), **Operating Model**, **Assessments**, **Risk Register**, **Trees**, **Outputs Library**, **Question Catalogue** (managers) — each named in the reader's own language, Arabic or English, never the two side by side |
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

"""Would these modules install onto an empty database?

A data file may only point at an external ID that an earlier file has already
created. Nothing on a long-lived database notices when that is broken: the ID is
in ir_model_data from the previous install, so every update passes and every test
run is green. It appears the first time somebody installs clean.

That is exactly how it reached production. A menuitem in azm_assignment_views.xml
hung off azm_menu_root, which azm_menus.xml defines two entries later in the
manifest, and installing the module raised

    ValueError: External ID not found in the system: azm_operating_model.azm_menu_root

after months of green updates here.

So the load order is replayed: our modules in dependency order, their data files in
manifest order, and every reference into our own modules checked against where it
is defined. Within one file document order is what counts, because Odoo applies
records as it reads them.
"""
import ast
import os
import re
import xml.etree.ElementTree as ET

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

OURS = ("az_group_base", "azm_operating_model", "azm_platform")
REF_ATTRS = ("parent", "action", "ref", "inherit_id", "src_model")


@tagged("post_install", "-at_install")
class TestTheModulesInstallFromScratch(TransactionCase):

    def _files(self):
        """(module, absolute path) for every XML data file, in load order."""
        found = []
        for module in OURS:
            root = get_module_path(module)
            if not root:
                continue
            with open(os.path.join(root, "__manifest__.py"), encoding="utf-8") as handle:
                manifest = ast.literal_eval(handle.read())
            for rel in manifest.get("data", []):
                if rel.endswith(".xml"):
                    found.append((module, os.path.join(root, rel)))
        return found

    def test_every_external_id_exists_before_it_is_used(self):
        files = self._files()
        self.assertTrue(files, "no data files were found to check")
        order = {path: i for i, (_m, path) in enumerate(files)}

        defined = {}
        for module, path in files:
            if not os.path.exists(path):
                continue
            for pos, el in enumerate(ET.parse(path).getroot().iter()):
                rid = el.get("id")
                if rid:
                    defined.setdefault(rid if "." in rid else f"{module}.{rid}",
                                       (order[path], pos))

        problems = []
        for module, path in files:
            if not os.path.exists(path):
                continue
            for pos, el in enumerate(ET.parse(path).getroot().iter()):
                refs = [(a, el.get(a)) for a in REF_ATTRS if el.get(a)]
                if el.get("groups"):
                    refs += [("groups", g.strip().lstrip("-"))
                             for g in el.get("groups").split(",") if g.strip()]
                refs += [("eval", m) for m in
                         re.findall(r"ref\(['\"]([\w.]+)['\"]\)", el.get("eval") or "")]
                for attr, value in refs:
                    if not value or value.startswith("$"):
                        continue
                    full = value if "." in value else f"{module}.{value}"
                    owner, _, name = full.partition(".")
                    # a standard addon's id, or one the ORM makes rather than a data file
                    if owner not in OURS or name.startswith("model_"):
                        continue
                    where = defined.get(full)
                    if where is None:
                        problems.append(
                            f'{os.path.basename(path)}: {attr}="{value}" is defined nowhere')
                    elif where > (order[path], pos):
                        later = os.path.basename(
                            next(p for p, i in order.items() if i == where[0]))
                        problems.append(
                            f'{os.path.basename(path)}: {attr}="{value}" '
                            f'is used before {later} defines it')

        self.assertFalse(problems, "these would fail a fresh install:\n  "
                                   + "\n  ".join(problems))

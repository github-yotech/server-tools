from odoo import fields, models
import logging

from .. import compare
from odoo.addons.upgrade_analysis import compare as original_compare

try:
    from odoo.addons.openupgrade_scripts.apriori import merged_modules, renamed_modules # type: ignore
except ImportError:
    renamed_modules = {}
    merged_modules = {}

_logger = logging.getLogger(__name__)
_IGNORE_MODULES = ["openupgrade_records", "upgrade_analysis"]

class UpgradeAnalysis(models.Model):
    _inherit = "upgrade.analysis"

    def _get_remote_modules(self, remote_record_obj):
        """Get list of modules from remote Odoo, even if list_modules() is missing."""

        # Try calling remote list_modules() if available
        if hasattr(remote_record_obj, "list_modules"):
            try:
                return remote_record_obj.list_modules()
            except Exception:
                pass  # fallback if it exists but fails

        # Fallback: safe ORM call via search_read
        records = remote_record_obj.search_read([], ["module"])
        return sorted({r["module"] for r in records})

    def generate_noupdate_changes(self):
        """Communicate with the remote server to fetch all xml data records
        per module, and generate a diff in XML format that can be imported
        from the module's migration script using openupgrade.load_data()
        """
        self.ensure_one()
        connection = self.config_id.get_connection()
        remote_record_obj = self._get_remote_model(connection, "record")
        local_record_obj = self.env["upgrade.record"]
        local_modules = local_record_obj.list_modules()
        all_remote_modules = self._get_remote_modules(remote_record_obj) # This is changed
        for local_module in local_modules:
            remote_files = []
            remote_modules = []
            remote_update, remote_noupdate = {}, {}
            for remote_module in all_remote_modules:
                if local_module == renamed_modules.get(
                    remote_module, merged_modules.get(remote_module, remote_module)
                ):
                    remote_files.extend(
                        remote_record_obj.get_xml_records(remote_module)
                    )
                    remote_modules.append(remote_module)
                    add_remote_update, add_remote_noupdate = self._parse_files(
                        remote_files, remote_module
                    )
                    remote_update.update(add_remote_update)
                    remote_noupdate.update(add_remote_noupdate)
            if not remote_modules:
                continue
            local_files = local_record_obj.get_xml_records(local_module)
            local_update, local_noupdate = self._parse_files(local_files, local_module)
            diff = self._get_xml_diff(
                remote_update, remote_noupdate, local_update, local_noupdate
            )
            if diff:
                module = self.env["ir.module.module"].search(
                    [("name", "=", local_module)]
                )
                self._write_file(
                    local_module,
                    module.installed_version,
                    diff,
                    filename="noupdate_changes.xml",
                )
        return True
    
    def analyze(self):
        """
        Retrieve both sets of database representations,
        perform the comparison and register the resulting
        change set
        """
        self.ensure_one()
        self.write(
            {
                "analysis_date": fields.Datetime.now(),
            }
        )

        connection = self.config_id.get_connection()
        RemoteRecord = self._get_remote_model(connection, "record")
        LocalRecord = self.env["upgrade.record"]

        # Retrieve field representations and compare
        remote_records = RemoteRecord.field_dump()
        
        local_records = LocalRecord.field_dump()
        res = compare.compare_sets(remote_records, local_records)

        # Retrieve xml id representations and compare
        flds = [
            "module",
            "model",
            "name",
            "noupdate",
            "prefix",
            "suffix",
            "domain",
            "definition",
        ]
        local_xml_records = [
            {field: record[field] for field in flds if field in record} # This is patched
            for record in LocalRecord.search([("type", "=", "xmlid")])
        ]
        remote_xml_record_ids = RemoteRecord.search([("type", "=", "xmlid")]) # This is patched
        remote_xml_records = [
            {field: record[field] for field in flds if field in record}
            for record in RemoteRecord.read(remote_xml_record_ids, flds)
        ]
        res_xml = original_compare.compare_xml_sets(remote_xml_records, local_xml_records)

        # Retrieve model representations and compare
        flds = [
            "module",
            "model",
            "name",
            "model_original_module",
            "model_type",
        ]
        local_model_records = [
            {field: record[field] for field in flds}
            for record in LocalRecord.search([("type", "=", "model")])
        ]
        remote_model_record_ids = RemoteRecord.search([("type", "=", "model")])
        _logger.info("DEBUG -> remote_model_record_ids = %s", remote_model_record_ids)
        _logger.info("DEBUG -> flds = %s", flds)
        for record in RemoteRecord.read(remote_model_record_ids, flds):
            _logger.info("DEBUG -> record = %s", record)
        
        remote_model_records = [
            {field: record[field] for field in flds}
            for record in RemoteRecord.read(remote_model_record_ids, flds)
        ]
        res_model = original_compare.compare_model_sets(
            remote_model_records, local_model_records
        )

        affected_modules = sorted(
            {
                record["module"]
                for record in remote_records
                + local_records
                + remote_xml_records
                + local_xml_records
                + remote_model_records
                + local_model_records
            }
        )
        if "base" in affected_modules:
            try:
                pass
            except ImportError:
                _logger.error(
                    "You are using upgrade_analysis on core modules without "
                    " having openupgrade_scripts module available."
                    " The analysis process will not work properly,"
                    " if you are generating analysis for the odoo modules"
                    " in an openupgrade context."
                )

        # reorder and output the result
        keys = ["general"] + affected_modules
        modules = {
            module["name"]: module
            for module in self.env["ir.module.module"].search(
                [("state", "=", "installed")]
            )
        }
        general_log = ""

        no_changes_modules = []

        for ignore_module in _IGNORE_MODULES:
            if ignore_module in keys:
                keys.remove(ignore_module)

        for key in keys:
            contents = "---Models in module '%s'---\n" % key
            if key in res_model:
                contents += "\n".join([str(line) for line in res_model[key]])
                if res_model[key]:
                    contents += "\n"
            contents += "---Fields in module '%s'---\n" % key
            if key in res:
                contents += "\n".join([str(line) for line in sorted(res[key])])
                if res[key]:
                    contents += "\n"
            contents += "---XML records in module '%s'---\n" % key
            if key in res_xml:
                contents += "\n".join([str(line) for line in res_xml[key]])
                if res_xml[key]:
                    contents += "\n"
            if key not in res and key not in res_xml and key not in res_model:
                contents += "---nothing has changed in this module--\n"
                no_changes_modules.append(key)
            if key == "general":
                general_log += contents
                continue
            if original_compare.module_map(key) not in modules:
                general_log += (
                    "ERROR: module not in list of installed modules:\n" + contents
                )
                continue
            if key not in modules:
                # no need to log in full log the merged/renamed modules
                continue
            if self.write_files:
                error = self._write_file(key, modules[key].installed_version, contents)
                if error:
                    general_log += error
                    general_log += contents
            else:
                general_log += contents

        # Store the full log
        if self.write_files and "base" in modules:
            self._write_file(
                "base",
                modules["base"].installed_version,
                general_log,
                "upgrade_general_log.txt",
            )

        try:
            self.generate_noupdate_changes()
        except Exception as e:
            _logger.exception("Error generating noupdate changes: %s" % e)
            general_log += "ERROR: error when generating noupdate changes: %s\n" % e
        try:
            self.generate_module_coverage_file(no_changes_modules)
        except Exception as e:
            _logger.exception("Error generating module coverage file: %s" % e)
            general_log += "ERROR: error when generating module coverage file: %s\n" % e

        self.write(
            {
                "state": "done",
                "log": general_log,
            }
        )
        return True
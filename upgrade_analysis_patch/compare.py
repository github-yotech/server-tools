import collections
import copy
from odoo.addons.upgrade_analysis.compare import fieldprint, search, model_map, IGNORE_FIELDS

def report_generic(new, old, attrs, reprs):
    for attr in attrs:
        try:
           old[attr]
        except KeyError:
            continue

        if attr == "required":
            if old[attr] != new["required"] and new["required"]:
                text = "now required"
                fieldprint(old, new, "", text, reprs)
        elif attr == "stored":
            if old[attr] != new[attr]:
                if new["stored"]:
                    text = "is now stored"
                else:
                    text = "not stored anymore"
                fieldprint(old, new, "", text, reprs)
        elif attr == "isfunction":
            if old[attr] != new[attr]:
                if new["isfunction"]:
                    text = "now a function"
                else:
                    text = "not a function anymore"
                fieldprint(old, new, "", text, reprs)
        elif attr == "isproperty":
            if old[attr] != new[attr]:
                if new[attr]:
                    text = "now a property"
                else:
                    text = "not a property anymore"
                fieldprint(old, new, "", text, reprs)
        elif attr == "isrelated":
            if old[attr] != new[attr]:
                if new[attr]:
                    text = "now related"
                else:
                    text = "not related anymore"
                fieldprint(old, new, "", text, reprs)
        elif attr == "table":
            if old[attr] != new[attr]:
                fieldprint(old, new, attr, "", reprs)
            if old[attr] and new[attr]:
                if old["column1"] != new["column1"]:
                    fieldprint(old, new, "column1", "", reprs)
                if old["column2"] != new["column2"]:
                    fieldprint(old, new, "column2", "", reprs)
        elif old[attr] != new[attr]:
            fieldprint(old, new, attr, "", reprs)


def compare_sets(old_records, new_records):
    """
    Compare a set of OpenUpgrade field representations.
    Try to match the equivalent fields in both sets.
    Return a textual representation of changes in a dictionary with
    module names as keys. Special case is the 'general' key
    which contains overall remarks and matching statistics.
    """
    reprs = collections.defaultdict(list)

    def clean_records(records):
        result = []
        for record in records:
            if record["field"] not in IGNORE_FIELDS:
                result.append(record)
        return result

    old_records = clean_records(old_records)
    new_records = clean_records(new_records)

    origlen = len(old_records)
    new_models = {column["model"] for column in new_records}
    old_models = {column["model"] for column in old_records}

    matched_direct = 0
    matched_other_module = 0
    matched_other_type = 0
    in_obsolete_models = 0

    obsolete_models = []
    for model in old_models:
        if model not in new_models:
            if model_map(model) not in new_models:
                obsolete_models.append(model)

    non_obsolete_old_records = []
    for column in copy.copy(old_records):
        if column["model"] in obsolete_models:
            in_obsolete_models += 1
        else:
            non_obsolete_old_records.append(column)

    def match(match_fields, report_fields, warn=False):
        count = 0
        for column in copy.copy(non_obsolete_old_records):
            found = search(column, new_records, match_fields)
            if found:
                if warn:
                    pass
                    # print "Tentatively"
                report_generic(found, column, report_fields, reprs)
                old_records.remove(column)
                non_obsolete_old_records.remove(column)
                new_records.remove(found)
                count += 1
        return count

    matched_direct = match(
        ["module", "mode", "model", "field"],
        [
            "relation",
            "type",
            "selection_keys",
            "_inherits",
            "stored",
            "isfunction",
            "isrelated",
            "required",
            "table",
            "_order",
        ],
    )

    # other module, same type and operation
    matched_other_module = match(
        ["mode", "model", "field", "type"],
        [
            "module",
            "relation",
            "selection_keys",
            "_inherits",
            "stored",
            "isfunction",
            "isrelated",
            "required",
            "table",
            "_order",
        ],
    )

    # other module, same operation, other type
    matched_other_type = match(
        ["module", "mode", "model", "field"],
        [
            "relation",
            "type",
            "selection_keys",
            "_inherits",
            "stored",
            "isfunction",
            "isrelated",
            "required",
            "table",
            "_order",
        ],
    )

    # Info that is displayed for deleted fields
    printkeys_old = [
        "relation",
        "required",
        "selection_keys",
        "_inherits",
        "mode",
        "attachment",
    ]
    # Info that is displayed for new fields
    printkeys_new = printkeys_old + [
        "hasdefault",
    ]
    for column in old_records:
        if column["field"] == "_order":
            continue
        # we do not care about removed non stored function fields
        if not column["stored"] and (column["isfunction"] or column["isrelated"]):
            continue
        if column["mode"] == "create":
            column["mode"] = ""
        
        extra_message = ", ".join(
            [
                k + ": " + str(column[k]) if k != str(column[k]) else k
                for k in printkeys_old
                if k in column # This is patched
            ]
        )
        if extra_message:
            extra_message = " " + extra_message
        fieldprint(column, "", "", "DEL" + extra_message, reprs)

    for column in new_records:
        if column["field"] == "_order":
            continue
        # we do not care about newly added non stored function fields
        if not column["stored"] and (column["isfunction"] or column["isrelated"]):
            continue
        if column["mode"] == "create":
            column["mode"] = ""
        printkeys = printkeys_new.copy()
        if column["isfunction"] or column["isrelated"]:
            printkeys.extend(["isfunction", "isrelated", "stored"])
        extra_message = ", ".join(
            [
                k + ": " + str(column[k]) if k != str(column[k]) else k
                for k in printkeys
                if column[k]
            ]
        )
        if extra_message:
            extra_message = " " + extra_message
        fieldprint(column, "", "", "NEW" + extra_message, reprs)

    for line in [
        "# %d fields matched," % (origlen - len(old_records)),
        "# Direct match: %d" % matched_direct,
        "# Found in other module: %d" % matched_other_module,
        "# Found with different type: %d" % matched_other_type,
        "# In obsolete models: %d" % in_obsolete_models,
        "# Not matched: %d" % len(old_records),
        "# New columns: %d" % len(new_records),
    ]:
        reprs["general"].append(line)
    return reprs

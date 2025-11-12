{
    "name": "Upgrade Analysis Patch",
    "summary": "Patch code of Upgrade analysis",
    "version": "17.0.1.0.0",
    "category": "Migration",
    "author": "Yotech",
    "data": [
        "views/view_upgrade_analysis.xml",
    ],
    "installable": True,
    "depends": ["upgrade_analysis"],
    "external_dependencies": {
        "python": ["mako", "dataclasses", "odoorpc", "openupgradelib"],
    },
    "license": "AGPL-3",
}

from __future__ import annotations

SEBI_EXAMPLE = {
    "prompt": (
        "I am working on a compliance monitoring solution which will pull in the latest "
        "circulars from SEBI and parse them. Once it is parsed into a table of clauses, "
        "you will need to extract the following information:\n"
        "1. The new compliance requirements proposed by the regulator\n"
        "2. Gap analysis with my existing compliance setup\n"
        "3. The impact of these new compliance requirements on my organization "
        "at an IT and operational level"
    ),
    "diagram_types": [
        "sequential",
        "component",
        "class",
        "activity",
        "deployment",
        "use_case",
    ],
}

DEFAULT_KINDS = ["sequence", "component", "class", "activity", "deployment"]

EXAMPLES = [
    {
        "label": "SEBI compliance",
        "prompt": SEBI_EXAMPLE["prompt"],
        "diagram_types": SEBI_EXAMPLE["diagram_types"],
    },
    {
        "label": "Order checkout",
        "prompt": (
            "Design an e-commerce checkout with cart, payment gateway, inventory, "
            "and fraud checks."
        ),
        "diagram_types": ["sequence", "component", "state_machine"],
    },
    {
        "label": "Data pipeline",
        "prompt": (
            "Build a batch ETL pipeline: S3 ingest, Spark transform, warehouse load, "
            "and DQ alerts."
        ),
        "diagram_types": ["activity", "deployment", "component"],
    },
]

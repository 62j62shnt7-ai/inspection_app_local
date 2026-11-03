"""Create disposable interchange input without reading user workbooks."""
from inspection_app.exports import export_workbook
from inspection_app.store import Store


def make_workbook(root):
    producer = Store(root / "fixture.db")
    asset = producer.save_asset(None, {
        "name": "Synthetic line", "family": "Flowline",
        "inspections": [{"inspection_type": "OSI", "applicable": "Yes", "next_inspection_month": "2032-12"}],
        "notes": [{"note_type": "Remark", "note_text": "Synthetic joint note"}],
        "source_cells": [{"source_sheet": "Synthetic", "source_row": 2, "source_cell": "A2", "original_value": "Synthetic evidence"}],
    }, None)
    return export_workbook(producer, root / "fixture.xlsx"), asset["id"]

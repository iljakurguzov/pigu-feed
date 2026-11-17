"""Convert Pigu 'Categories_fields_and_values.xlsx' into data/categories.json.

Usage: python tools/convert_categories.py path/to/Categories_fields_and_values.xlsx
"""
import json
import sys
from collections import OrderedDict

import openpyxl

MAX_VALUES = 150  # longer lists (e.g. brands) are treated as free text


def split(v):
    if not v:
        return []
    return [x.strip() for x in str(v).split(";") if x.strip()]


def main(src, dst="data/categories.json"):
    wb = openpyxl.load_workbook(src, read_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    head = rows[0]
    idx = {h: i for i, h in enumerate(head)}
    cats = OrderedDict()
    for r in rows[1:]:
        cid = str(r[idx["lowest_category_id"]])
        c = cats.setdefault(cid, {
            "title_lt": (r[idx["lowest_category_title"]] or "").strip(),
            "title_en": (r[idx["lowest_category_title_en"]] or "").strip(),
            "top_lt": (r[idx["top_category_title"]] or "").strip(),
            "top_en": (r[idx["top_category_title_en"]] or "").strip(),
            "fields": [],
        })
        vals = split(r[idx["lt values"]])
        f = {
            "id": r[idx["field_id"]],
            "title_lt": (r[idx["field_title"]] or "").strip(),
            "title_en": (r[idx["field_title_en"]] or "").strip(),
            "mandatory": r[idx["mandatory"]] == "y",
            "type": r[idx["field_value_type"]],
        }
        if vals and len(vals) <= MAX_VALUES:
            f["values_lt"] = vals
        c["fields"].append(f)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(cats, fh, ensure_ascii=False, indent=0)
    print(f"{len(cats)} categories -> {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])

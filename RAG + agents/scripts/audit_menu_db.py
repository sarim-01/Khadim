#!/usr/bin/env python3
"""Read public.menu_item (and deal) from DATABASE_URL; report anomalies."""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

URL = os.getenv("DATABASE_URL", "").strip()
if not URL:
    print("DATABASE_URL missing", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    eng = create_engine(URL)
    issues: list[str] = []

    with eng.connect() as c:
        rows = c.execute(
            text(
                """
                SELECT item_id, item_name, item_price, item_category,
                       COALESCE(image_url, '') AS image_url
                FROM public.menu_item
                ORDER BY item_id
                """
            )
        ).mappings().all()

        deal_rows = c.execute(
            text(
                """
                SELECT deal_id, deal_name, deal_price,
                       COALESCE(image_url, '') AS image_url
                FROM public.deal
                ORDER BY deal_id
                """
            )
        ).mappings().all()

    print(f"menu_item rows: {len(rows)}")
    print(f"deal rows: {len(deal_rows)}")
    print()

    by_lower: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        name = (r["item_name"] or "").strip()
        lid = name.lower()
        by_lower[lid].append(int(r["item_id"]))

    dupes = {k: v for k, v in by_lower.items() if k and len(v) > 1}
    if dupes:
        issues.append(f"Duplicate item_name (case-insensitive): {len(dupes)} groups")
        for k, ids in sorted(dupes.items(), key=lambda x: -len(x[1]))[:30]:
            issues.append(f"  {k!r} -> ids {ids}")

    for r in rows:
        iid = r["item_id"]
        name = (r["item_name"] or "").strip()
        price = r["item_price"]
        cat = (r["item_category"] or "").strip()
        img = (r["image_url"] or "").strip()

        if not name:
            issues.append(f"item_id {iid}: empty item_name")
        if name and len(name) < 2:
            issues.append(f"item_id {iid}: very short name {name!r}")
        if price is None:
            issues.append(f"item_id {iid}: NULL item_price")
        elif float(price or 0) < 0:
            issues.append(f"item_id {iid}: negative price {price}")

        if img and not re.match(r"^(https?://|/|uploads/)", img, re.I):
            if ".." in img or img.startswith("\\\\"):
                issues.append(f"item_id {iid}: suspicious image_url {img!r}")

        # Double spaces / trailing punctuation in name
        if name and (name != " ".join(name.split()) or name != name.strip(" \t.")):
            issues.append(f"item_id {iid}: noisy name whitespace/punct {name!r}")

    deal_lower: dict[str, list[int]] = defaultdict(list)
    for r in deal_rows:
        n = (r["deal_name"] or "").strip().lower()
        deal_lower[n].append(int(r["deal_id"]))

    ddupes = {k: v for k, v in deal_lower.items() if k and len(v) > 1}
    if ddupes:
        issues.append(f"Duplicate deal_name (case-insensitive): {len(ddupes)} groups")
        for k, ids in list(ddupes.items())[:20]:
            issues.append(f"  {k!r} -> ids {ids}")

    print("--- Potential issues ---")
    if not issues:
        print("(none flagged by heuristics)")
    else:
        for line in issues:
            print(line)

    print()
    print("--- Full menu_item list (id | name | price | category) ---")
    for r in rows:
        nm = (r["item_name"] or "").replace("\n", " ")[:80]
        print(
            f"{r['item_id']:4d} | Rs {float(r['item_price'] or 0):8.2f} | "
            f"{(r['item_category'] or '')[:24]:24} | {nm}"
        )

    print()
    print("--- Full deal list (id | name | price) ---")
    for r in deal_rows:
        nm = (r["deal_name"] or "").replace("\n", " ")[:80]
        print(f"{r['deal_id']:4d} | Rs {float(r['deal_price'] or 0):8.2f} | {nm}")

    with eng.connect() as c:
        bad_m = c.execute(
            text(
                """
                SELECT di.deal_id, di.menu_item_id
                FROM public.deal_item di
                LEFT JOIN public.menu_item m ON m.item_id = di.menu_item_id
                WHERE m.item_id IS NULL
                """
            )
        ).fetchall()
        bad_d = c.execute(
            text(
                """
                SELECT di.deal_id
                FROM public.deal_item di
                LEFT JOIN public.deal d ON d.deal_id = di.deal_id
                WHERE d.deal_id IS NULL
                """
            )
        ).fetchall()
    print()
    print("--- deal_item integrity ---")
    print(f"orphan menu_item refs: {len(bad_m)}", bad_m[:5] if bad_m else "")
    print(f"orphan deal refs: {len(bad_d)}", bad_d[:5] if bad_d else "")


if __name__ == "__main__":
    main()

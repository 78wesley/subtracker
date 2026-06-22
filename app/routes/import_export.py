"""
import_export.py — Bulk import / export of the active team's subscriptions.

Export serialises every (non-deleted) subscription for the current team together
with all its price periods, as either CSV (one row per period) or JSON (periods
nested). Import accepts the same shapes and recreates subscriptions in the active
team. Both reuse the ordinary subscription permissions: export needs
`subscriptions.view`, import needs `subscriptions.create` (+ a writable team) and is
audited per created subscription exactly like a manual create.

CSV round-trips by grouping rows that share a `name` into one subscription, so the
period columns may repeat the same identity fields across several rows.
"""

import csv
import io
import json
import math

from fasthtml.common import *

from app import timeutil
from app.authz import require, writable_team
from app.components import alert, nav_bar, page_title, section_card
from app.cost_utils import normalise_cadence
from app.db import (
    add_period,
    audit,
    get_all_subscriptions,
    get_db,
    get_periods_map,
)
from app.permissions import Perm
from app.styles import LINK, MUTED_SM, PAGE_HEADER, btn

ar = APIRouter()

# Identity/cadence fields first, then the period columns (blank for sub-less rows).
CSV_COLUMNS = ["name", "category", "frequency", "interval", "base_unit", "notes",
               "amount", "start_date", "end_date"]

# Leading characters a spreadsheet may interpret as a formula (CSV injection). A
# field starting with one is prefixed with a single quote on export and unwrapped
# on import, so it stays inert in Excel/Sheets while still round-tripping cleanly.
_CSV_RISKY = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in _CSV_RISKY else s


def _csv_unwrap(value: str) -> str:
    return value[1:] if len(value) >= 2 and value[0] == "'" and value[1] in _CSV_RISKY else value


# Bound a single import so a huge upload can't exhaust memory or create unbounded rows.
MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMPORT_SUBS = 2000

_FILE_INPUT = ("block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md "
               "file:border-0 file:bg-primary file:text-primary-foreground file:px-3 "
               "file:py-1.5 file:text-sm file:font-medium hover:file:bg-primary/90 "
               "cursor-pointer")


# ── Serialisation ─────────────────────────────────────────────────────────────

def _collect(db, ctx) -> tuple:
    """(subscriptions, {sub_id: [periods]}) for the caller's team, sorted by name."""
    subs = get_all_subscriptions(db, ctx)
    return subs, get_periods_map(db, [s["id"] for s in subs])


def _to_csv(subs, periods_map) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for s in subs:
        base = [_csv_safe(s["name"]), _csv_safe(s.get("category") or ""), s["frequency"],
                s["interval"] or 1, s.get("base_unit") or "", _csv_safe(s.get("notes") or "")]
        periods = periods_map.get(s["id"], [])
        if periods:
            for p in periods:
                w.writerow(base + [p["amount"], p["start_date"], p["end_date"] or ""])
        else:
            w.writerow(base + ["", "", ""])
    return buf.getvalue()


def _to_json(subs, periods_map) -> str:
    payload = {
        "exported_at": timeutil.now_iso(),
        "version": 1,
        "subscriptions": [
            {
                "name": s["name"], "category": s.get("category"),
                "frequency": s["frequency"], "interval": s["interval"] or 1,
                "base_unit": s.get("base_unit"), "notes": s.get("notes") or "",
                "periods": [
                    {"amount": p["amount"], "start_date": p["start_date"],
                     "end_date": p["end_date"]}
                    for p in periods_map.get(s["id"], [])
                ],
            }
            for s in subs
        ],
    }
    return json.dumps(payload, indent=2)


# ── Export ────────────────────────────────────────────────────────────────────

@ar("/export")
def get(req, session, fmt: str = "csv"):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_VIEW)): return r
    db = get_db()
    subs, periods_map = _collect(db, ctx)
    # Filename-safe local timestamp, e.g. 2026-06-18_143005 (no colons).
    stamp = timeutil.now_iso()[:19].replace("T", "_").replace(":", "")
    if fmt == "json":
        body, media, ext = _to_json(subs, periods_map), "application/json", "json"
    else:
        body, media, ext = _to_csv(subs, periods_map), "text/csv", "csv"
    return Response(
        body, media_type=media,
        headers={"content-disposition": f'attachment; filename="subscriptions-{stamp}.{ext}"'},
    )


# ── Parsing (file -> list of {name, cadence…, periods:[…]} + parse errors) ──────

def _parse_csv(text: str) -> tuple:
    errors, groups, order = [], {}, []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        name = _csv_unwrap((row.get("name") or "").strip())
        if not name:
            errors.append(f"Row {i}: missing name — skipped.")
            continue
        if name not in groups:
            groups[name] = {
                "name": name,
                "category": _csv_unwrap((row.get("category") or "").strip()) or None,
                "frequency": (row.get("frequency") or "monthly").strip(),
                "interval": row.get("interval") or 1,
                "base_unit": (row.get("base_unit") or "").strip(),
                "notes": _csv_unwrap((row.get("notes") or "").strip()),
                "periods": [],
            }
            order.append(name)
        amount = (row.get("amount") or "").strip()
        start = (row.get("start_date") or "").strip()
        if not amount and not start:
            continue  # identity-only row (subscription with no periods)
        try:
            amt = float(amount)
            if not math.isfinite(amt):
                raise ValueError
        except ValueError:
            errors.append(f"Row {i} ({name}): invalid amount '{amount}' — period skipped.")
            continue
        if not start:
            errors.append(f"Row {i} ({name}): period has an amount but no start_date — skipped.")
            continue
        groups[name]["periods"].append({
            "amount": amt, "start_date": start,
            "end_date": (row.get("end_date") or "").strip() or None,
        })
    return [groups[n] for n in order], errors


def _parse_json(text: str) -> tuple:
    errors = []
    data = json.loads(text)  # JSONDecodeError handled by the caller
    raw = data.get("subscriptions") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return [], ["JSON must be an object with a 'subscriptions' array (or a top-level array)."]
    subs = []
    for i, item in enumerate(raw, start=1):
        name = (item.get("name") or "").strip() if isinstance(item, dict) else ""
        if not name:
            errors.append(f"Item {i}: missing name — skipped.")
            continue
        periods = []
        for p in (item.get("periods") or []):
            start = (str(p.get("start_date") or "")).strip()
            try:
                amt = float(p.get("amount"))
                if not math.isfinite(amt):
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"'{name}': period has an invalid amount — skipped.")
                continue
            if not start:
                errors.append(f"'{name}': period missing start_date — skipped.")
                continue
            periods.append({"amount": amt, "start_date": start,
                            "end_date": (p.get("end_date") or None)})
        subs.append({
            "name": name, "category": item.get("category"),
            "frequency": item.get("frequency") or "monthly",
            "interval": item.get("interval") or 1,
            "base_unit": item.get("base_unit") or "",
            "notes": item.get("notes") or "", "periods": periods,
        })
    return subs, errors


def _import_subs(db, ctx, parsed) -> tuple:
    """Create each parsed subscription + its periods. Returns (created, periods, errors)."""
    created, periods_added, errors = 0, 0, []
    now = timeutil.now_iso()
    for sub in parsed:
        freq, interval, base_unit = normalise_cadence(sub["frequency"], sub["interval"],
                                                       sub["base_unit"])
        category = (sub.get("category") or None)
        if isinstance(category, str):
            category = category.strip() or None
        sub_id = db["subscriptions"].insert({
            "team_id": ctx.active_team_id, "created_by": ctx.user["id"],
            "name": sub["name"], "currency": "EUR", "category": category,
            "notes": sub.get("notes") or "", "frequency": freq, "interval": interval,
            "base_unit": base_unit, "created_at": now, "updated_at": now,
        }).last_pk

        # Insert chronologically so add_period's open-ended auto-close behaves predictably.
        n = 0
        for p in sorted(sub["periods"], key=lambda x: x["start_date"]):
            err, _ = add_period(db, sub_id, p["amount"], p["start_date"],
                                p["end_date"], ctx.user["id"])
            if err:
                errors.append(f"'{sub['name']}' period {p['start_date']}: {err}")
            else:
                n += 1
        periods_added += n
        created += 1
        audit(ctx, "CREATE", "subscription", sub_id, sub["name"],
              f"Imported '{sub['name']}' with {n} period(s)",
              new_values={"name": sub["name"], "frequency": freq, "category": category}, db=db)
    return created, periods_added, errors


# ── Import / Export page ────────────────────────────────────────────────────────

def _result_block(created: int, periods_added: int, errors: list):
    kind = "success" if (created and not errors) else ("warning" if created else "error")
    summary = (f"Imported {created} subscription(s) and {periods_added} period(s)."
               if created else "No subscriptions were imported.")
    issues = (
        section_card(
            P(f"{len(errors)} issue(s) while importing:", cls="font-medium text-sm mb-2"),
            Ul(*[Li(e, cls="text-sm") for e in errors[:30]], cls="list-disc pl-5 grid gap-1"),
            (P(f"…and {len(errors) - 30} more.", cls=MUTED_SM) if len(errors) > 30 else ""),
        ) if errors else ""
    )
    return Div(alert(summary, kind), issues)


def _page(ctx, result=None):
    can_import = ctx.can(Perm.SUB_CREATE)

    export_card = section_card(
        P("Download every subscription for the current team, including all of its "
          "price periods.", cls=MUTED_SM),
        Div(
            A("⬇ Export CSV", href="/export?fmt=csv", role="button", cls=btn("outline")),
            A("⬇ Export JSON", href="/export?fmt=json", role="button", cls=btn("outline")),
            cls="flex gap-2 flex-wrap mt-3",
        ),
        heading="Export",
    )

    import_card = section_card(
        P("Upload a CSV or JSON file to add subscriptions to the current team. "
          "The format matches what Export produces, so an export is the easiest "
          "template.", cls=MUTED_SM),
        Form(
            Input(type="file", name="file", accept=".csv,.json", required=True, cls=_FILE_INPUT),
            Button("Import", type="submit", cls=btn("outline")),
            method="post", action="/import", enctype="multipart/form-data",
            cls="grid gap-3 max-w-md mt-3",
        ),
        Details(
            Summary("Expected format", cls="cursor-pointer text-sm font-medium"),
            Div(
                P("CSV — one row per price period, with a header row:", cls="text-sm mt-2"),
                Pre(", ".join(CSV_COLUMNS),
                    cls="text-xs bg-muted rounded-md p-2 overflow-x-auto"),
                P("Rows sharing the same name are merged into one subscription "
                  "(repeat the identity columns on each period row). Leave the "
                  "amount/start_date columns blank for a subscription with no "
                  "periods yet.", cls=MUTED_SM),
                P("JSON — an object with a \"subscriptions\" array; each entry carries "
                  "its identity fields plus a nested \"periods\" list.",
                  cls="text-sm mt-2"),
                cls="grid gap-1",
            ),
            cls="mt-4",
        ),
        heading="Import",
    ) if can_import else ""

    body = [Div(H2("Import / Export"), A("← Manage", href="/manage", cls=LINK), cls=PAGE_HEADER)]
    if result is not None:
        body.append(result)
    body += [export_card, import_card]
    return page_title("Import / Export"), nav_bar(ctx, "manage"), Main(*body)


@ar("/import")
def get(req, session):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_VIEW)): return r
    return _page(ctx)


@ar("/import")
async def post(req, session):
    ctx = req.scope["ctx"]
    if (r := require(ctx, Perm.SUB_CREATE)): return r
    if not writable_team(ctx):
        return _page(ctx, alert("Switch to a specific team (not “All teams”) before "
                                "importing subscriptions.", "warning"))

    form = await req.form()
    upload = form.get("file")
    filename = getattr(upload, "filename", "") or ""
    if not filename:
        return _page(ctx, alert("Choose a CSV or JSON file to import.", "error"))

    raw = await upload.read()
    if len(raw) > MAX_IMPORT_BYTES:
        return _page(ctx, alert(f"File is too large (max {MAX_IMPORT_BYTES // (1024 * 1024)} MB).",
                                "error"))
    try:
        text = raw.decode("utf-8-sig")  # tolerate a UTF-8 BOM (e.g. from Excel)
    except UnicodeDecodeError:
        return _page(ctx, alert("File must be UTF-8 encoded text (CSV or JSON).", "error"))

    is_json = filename.lower().endswith(".json")
    try:
        parsed, errors = _parse_json(text) if is_json else _parse_csv(text)
    except json.JSONDecodeError as e:
        return _page(ctx, alert(f"Could not parse JSON: {e}", "error"))

    if not parsed:
        return _page(ctx, _result_block(0, 0, errors or ["No subscriptions found in the file."]))
    if len(parsed) > MAX_IMPORT_SUBS:
        return _page(ctx, alert(f"Too many subscriptions in one import ({len(parsed)}); "
                                f"the limit is {MAX_IMPORT_SUBS}.", "error"))

    created, periods_added, import_errors = _import_subs(db=get_db(), ctx=ctx, parsed=parsed)
    return _page(ctx, _result_block(created, periods_added, errors + import_errors))

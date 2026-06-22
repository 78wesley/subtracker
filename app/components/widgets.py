"""
widgets.py — Small reusable UI widgets, styled with shadcn utility classes.
"""

from fasthtml.common import *

from app.styles import ALERT, badge_cls, btn

# shadcn DropdownMenu content + item recipes. Show/hide is the native <details>
# behaviour; the open animation + chevron rotation live in GLOBALS (app/styles.py),
# scoped to `details[data-dropdown]` (no reliable Tailwind-CDN utility for either).
# When open, DROPDOWN_JS re-positions the menu as `position:fixed` so it floats above
# any clipping ancestor (e.g. a table wrapper with overflow).
_MENU = ("absolute z-50 mt-1 min-w-[11rem] rounded-md border "
         "bg-popover p-1 text-popover-foreground shadow-md")
_MENU_ITEM = ("flex w-full items-center rounded-sm px-2 py-1.5 text-sm cursor-pointer "
              "select-none transition-colors hover:bg-accent hover:text-accent-foreground "
              "border-0 bg-transparent text-left")
_MENU_ITEM_DANGER = ("flex w-full items-center rounded-sm px-2 py-1.5 text-sm cursor-pointer "
                     "select-none transition-colors text-destructive hover:bg-destructive/10 "
                     "border-0 bg-transparent text-left")
_SUMMARY = (btn("outline", "sm") + " list-none marker:hidden "
            "[&::-webkit-details-marker]:hidden")
# Trigger for select_menu: looks like a shadcn Select (input-sized, chevron right).
_SELECT_TRIGGER = ("inline-flex h-9 items-center justify-between gap-2 rounded-md border "
                   "border-input bg-background px-3 text-sm shadow-sm transition-colors "
                   "hover:bg-accent hover:text-accent-foreground focus-visible:outline-none "
                   "focus-visible:ring-1 focus-visible:ring-ring cursor-pointer list-none "
                   "marker:hidden [&::-webkit-details-marker]:hidden")

# lucide chevron-down (rotation handled in GLOBALS when the menu is open).
_CHEVRON = NotStr(
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" class="ml-1 opacity-60 transition-transform">'
    '<path d="m6 9 6 6 6-6"/></svg>'
)


def alert(msg: str, kind: str = "warning") -> Div:
    return Div(msg, cls=ALERT.get(kind, ALERT["warning"]))


def badge(text: str, kind: str = "default") -> Span:
    return Span(text, cls=badge_cls(kind))


def status_badge(is_active: int) -> Span:
    return badge("Active", "active") if is_active else badge("Inactive", "inactive")


def action_btn(label: str, href: str = None, variant: str = "outline",
               hx_post: str = None, hx_confirm: str = None) -> object:
    """A small (sm) shadcn button, either a link or an HTMX button."""
    cls = btn(variant, "sm")
    if href:
        return A(label, href=href, role="button", cls=cls)
    btn_el = Button(label, cls=cls)
    if hx_post:
        btn_el.attrs["hx-post"] = hx_post
        btn_el.attrs["hx-target"] = "body"
        btn_el.attrs["hx-push-url"] = "true"
        if hx_confirm:
            btn_el.attrs["hx-confirm"] = hx_confirm
    return btn_el


def menu_item_cls(*, danger: bool = False, active: bool = False) -> str:
    """Class string for one DropdownMenu item (link, button, or form-submit button)."""
    cls = _MENU_ITEM_DANGER if danger else _MENU_ITEM
    return cls + " bg-accent text-accent-foreground" if active else cls


def dropdown_menu(trigger, *items, align: str = "right") -> Details:
    """
    shadcn DropdownMenu (built on <details>): an outline trigger with a chevron and a
    popover of `items` (build each with menu_item_cls). Outside-click / Escape close
    and floating (position:fixed) are handled by DROPDOWN_JS (see app/main.py).
    """
    edge = "right-0" if align == "right" else "left-0"
    return Details(
        Summary(trigger, _CHEVRON, cls=_SUMMARY),
        Div(*items, cls=_MENU + " " + edge, role="menu"),
        cls="relative inline-block",
        data_dropdown=True, data_align=align,
    )


def select_menu(name: str, options, *, value=None, width: str = "w-[160px]",
                onchange: str = None) -> Details:
    """
    A shadcn Select rendered as a <details> dropdown that carries its value in a
    hidden <input name=...>, so it submits inside a normal form. DROPDOWN_JS updates
    the value + trigger label on pick (and dispatches a 'change' event on the input,
    so an optional `onchange` handler still fires). `options` is [(value, label), …].
    """
    opts = [(str(v), lbl) for v, lbl in options]
    val = str(value) if value is not None else (opts[0][0] if opts else "")
    current = next((lbl for v, lbl in opts if v == val), opts[0][1] if opts else "")
    items = [
        Button(lbl, type="button", role="menuitem", data_value=v,
               cls=menu_item_cls(active=(v == val)))
        for v, lbl in opts
    ]
    hidden = Input(type="hidden", name=name, value=val,
                   **({"onchange": onchange} if onchange else {}))
    return Details(
        Summary(Span(current, cls="truncate text-left", data_select_label=True),
                _CHEVRON, cls=_SELECT_TRIGGER + " " + width),
        hidden,
        Div(*items, cls=_MENU + " left-0", role="menu"),
        cls="relative inline-block " + width,
        data_dropdown=True, data_select=True,
    )


def action_menu(sub_id: int, name: str, *, can_edit: bool = True,
                can_delete: bool = True) -> object:
    """
    Per-row Actions menu for the manage table. Only renders the items the current
    role may use; returns a muted dash if nothing is permitted.
    """
    items = []
    if can_edit:
        items.append(
            A("Edit", href=f"/subscriptions/{sub_id}/edit", cls=menu_item_cls(), role="menuitem"))
    if can_delete:
        items.append(Button("Delete", cls=menu_item_cls(danger=True), role="menuitem",
                            hx_post=f"/subscriptions/{sub_id}/delete",
                            hx_confirm=f"Delete '{name}'? (soft-delete)",
                            hx_target="body", hx_push_url="true"))
    if not items:
        return Span("—", cls="text-muted-foreground")
    return dropdown_menu("Actions", *items)


def pagination_bar(page: int, total_pages: int, base_url: str) -> Div:
    sep = "&" if "?" in base_url else "?"
    prev_btn = (A("← Prev", href=f"{base_url}{sep}page={page-1}", role="button",
                  cls=btn("outline", "sm")) if page > 1 else "")
    next_btn = (A("Next →", href=f"{base_url}{sep}page={page+1}", role="button",
                  cls=btn("outline", "sm")) if page < total_pages else "")
    return Div(prev_btn,
               Span(f"Page {page} of {total_pages}", cls="text-sm text-muted-foreground px-3"),
               next_btn,
               cls="flex items-center gap-2 mt-4")

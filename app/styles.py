"""
styles.py — shadcn/ui (Tailwind) theme for SubTracker.

PicoCSS is disabled (fast_app(pico=False)). This stylesheet implements the shadcn
design system: its CSS design tokens (HSL variables) plus component styling for the
native elements FastHTML emits (article=Card, .grid=Grid, button, input, table, …).
Tailwind is loaded via CDN (see app/main.py) with these same tokens, so utility
classes are available too. Legacy `--pico-*` variables are aliased to shadcn tokens
so existing inline styles keep working.
"""

CSS = """
/* ── shadcn design tokens ─────────────────────────────────────────────────── */
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --card: 0 0% 100%;
  --card-foreground: 222.2 84% 4.9%;
  --popover: 0 0% 100%;
  --popover-foreground: 222.2 84% 4.9%;
  --primary: 222.2 47.4% 11.2%;
  --primary-foreground: 210 40% 98%;
  --secondary: 210 40% 96.1%;
  --secondary-foreground: 222.2 47.4% 11.2%;
  --muted: 210 40% 96.1%;
  --muted-foreground: 215.4 16.3% 46.9%;
  --accent: 210 40% 96.1%;
  --accent-foreground: 222.2 47.4% 11.2%;
  --destructive: 0 72.2% 50.6%;
  --destructive-foreground: 210 40% 98%;
  --success: 142.1 70.6% 45.3%;
  --warning: 38 92% 50%;
  --info: 217.2 91.2% 59.8%;
  --border: 214.3 31.8% 91.4%;
  --input: 214.3 31.8% 91.4%;
  --ring: 222.2 84% 4.9%;
  --radius: 0.5rem;

  /* Legacy aliases so existing inline styles resolve to shadcn tokens. */
  --pico-color: hsl(var(--foreground));
  --pico-muted-color: hsl(var(--muted-foreground));
  --pico-card-background-color: hsl(var(--card));
  --pico-muted-border-color: hsl(var(--border));
  --pico-primary: hsl(var(--primary));
  --pico-primary-hover: hsl(var(--primary) / 0.85);
  --pico-border-radius: var(--radius);
  --pico-font-size: 0.95rem;
}

.dark {
  --background: 222.2 84% 4.9%;
  --foreground: 210 40% 98%;
  --card: 222.2 47% 8%;
  --card-foreground: 210 40% 98%;
  --popover: 222.2 84% 4.9%;
  --popover-foreground: 210 40% 98%;
  --primary: 210 40% 98%;
  --primary-foreground: 222.2 47.4% 11.2%;
  --secondary: 217.2 32.6% 17.5%;
  --secondary-foreground: 210 40% 98%;
  --muted: 217.2 32.6% 17.5%;
  --muted-foreground: 215 20.2% 65.1%;
  --accent: 217.2 32.6% 17.5%;
  --accent-foreground: 210 40% 98%;
  --destructive: 0 62.8% 50%;
  --destructive-foreground: 210 40% 98%;
  --border: 217.2 32.6% 22%;
  --input: 217.2 32.6% 22%;
  --ring: 212.7 26.8% 83.9%;
}

/* ── Base ─────────────────────────────────────────────────────────────────── */
* { box-sizing: border-box; }
html { font-size: 100%; }
body {
  margin: 0 auto; max-width: 1200px; padding: 1.25rem;
  background: hsl(var(--background)); color: hsl(var(--foreground));
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, "Apple Color Emoji", sans-serif;
  font-size: var(--pico-font-size); line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
main, main.container { display: block; width: 100%; }
h1, h2, h3, h4 { font-weight: 600; line-height: 1.25; letter-spacing: -0.01em; margin: 0 0 .5rem; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.35rem; } h3 { font-size: 1.05rem; }
p { margin: .4rem 0; }
small { font-size: .8rem; }
a { color: hsl(var(--foreground)); text-decoration: none; }
a:hover { color: hsl(var(--primary)); }
hr { border: none; border-top: 1px solid hsl(var(--border)); margin: 1rem 0; }
strong { font-weight: 600; }
::selection { background: hsl(var(--primary) / 0.15); }

/* Card = <article>; section-card / cost-card share the look */
article, .section-card, .cost-card {
  background: hsl(var(--card)); color: hsl(var(--card-foreground));
  border: 1px solid hsl(var(--border)); border-radius: var(--radius);
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.04); padding: 1.5rem; margin-bottom: 1.25rem;
}
article > header { font-weight: 600; margin: -1.5rem -1.5rem 1rem; padding: 1rem 1.5rem;
  border-bottom: 1px solid hsl(var(--border)); }
article > footer { margin: 1rem -1.5rem -1.5rem; padding: 1rem 1.5rem;
  border-top: 1px solid hsl(var(--border)); }
.section-card h3 { margin-top: 0; }

/* Grid (Pico .grid) → responsive auto-fit columns */
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(0, 1fr)); gap: 1rem; }
@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }

/* ── Forms ────────────────────────────────────────────────────────────────── */
label { display: block; font-size: .875rem; font-weight: 500; margin: .6rem 0 .3rem; }
input:not([type=checkbox]):not([type=radio]), select, textarea {
  width: 100%; height: 2.4rem; padding: 0 .7rem; margin: .15rem 0 0;
  font-size: .875rem; color: hsl(var(--foreground));
  background: hsl(var(--background));
  border: 1px solid hsl(var(--input)); border-radius: calc(var(--radius) - 2px);
  transition: box-shadow .15s, border-color .15s; appearance: none;
}
textarea { height: auto; padding: .55rem .7rem; line-height: 1.5; }
input:focus, select:focus, textarea:focus {
  outline: none; border-color: hsl(var(--ring));
  box-shadow: 0 0 0 2px hsl(var(--background)), 0 0 0 4px hsl(var(--ring) / 0.35);
}
input::placeholder, textarea::placeholder { color: hsl(var(--muted-foreground)); }
input[type=checkbox] { width: 1rem; height: 1rem; accent-color: hsl(var(--primary)); vertical-align: middle; }
select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right .55rem center; padding-right: 1.8rem;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
button, [role=button], a[role=button], input[type=submit] {
  display: inline-flex; align-items: center; justify-content: center; gap: .4rem;
  height: 2.4rem; padding: 0 1rem; font-size: .875rem; font-weight: 500;
  border-radius: calc(var(--radius) - 2px); border: 1px solid transparent;
  background: hsl(var(--primary)); color: hsl(var(--primary-foreground));
  cursor: pointer; transition: background-color .15s, opacity .15s, border-color .15s;
  text-decoration: none; white-space: nowrap; line-height: 1;
}
button:hover, [role=button]:hover, a[role=button]:hover { background: hsl(var(--primary) / 0.9); }
button:focus-visible { outline: none; box-shadow: 0 0 0 2px hsl(var(--background)), 0 0 0 4px hsl(var(--ring) / 0.4); }
/* Variants (Pico class names reused) */
.secondary { background: hsl(var(--secondary)); color: hsl(var(--secondary-foreground)); }
.secondary:hover { background: hsl(var(--secondary) / 0.8); }
.outline, .secondary.outline {
  background: hsl(var(--background)); color: hsl(var(--foreground));
  border: 1px solid hsl(var(--border));
}
.outline:hover, .secondary.outline:hover { background: hsl(var(--accent)); color: hsl(var(--accent-foreground)); }
.contrast { background: hsl(var(--foreground)); color: hsl(var(--background)); }
.btn-danger { background: hsl(var(--destructive)) !important; color: hsl(var(--destructive-foreground)) !important; border-color: transparent !important; }
.btn-danger:hover { background: hsl(var(--destructive) / 0.9) !important; }

/* ── Tables ───────────────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; font-size: .875rem; }
thead th { text-align: left; font-weight: 500; color: hsl(var(--muted-foreground));
  white-space: nowrap; padding: .55rem .75rem; border-bottom: 1px solid hsl(var(--border)); }
td { padding: .6rem .75rem; border-bottom: 1px solid hsl(var(--border));
  vertical-align: top; overflow-wrap: anywhere; word-break: break-word; max-width: 22rem; }
tbody tr:hover { background: hsl(var(--muted) / 0.5); }
td.nowrap, th.nowrap { white-space: nowrap; overflow-wrap: normal; word-break: normal; max-width: none; }
.cell-clip { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* ── Nav ──────────────────────────────────────────────────────────────────── */
nav { display: flex; align-items: center; gap: 1.1rem; padding: .6rem 1rem; flex-wrap: wrap;
  background: hsl(var(--card)); border: 1px solid hsl(var(--border));
  border-radius: var(--radius); margin-bottom: 1.5rem; box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.04); }
nav .brand { font-weight: 700; font-size: 1.05rem; color: hsl(var(--foreground)); }
nav a { font-size: .875rem; color: hsl(var(--muted-foreground)); }
nav a:hover { color: hsl(var(--foreground)); }
nav a.active { color: hsl(var(--foreground)); font-weight: 600; }
nav .spacer { flex: 1; }
nav .debug-pill { background: hsl(var(--warning) / 0.15); border: 1px solid hsl(var(--warning) / 0.4);
  color: hsl(38 92% 35%); font-size: .72rem; padding: .15rem .55rem; border-radius: 9999px; }
nav .team-switch { margin: 0; }
nav .team-switch select { margin: 0; height: 2rem; padding: 0 1.8rem 0 .6rem; width: auto; font-size: .8rem; }

/* ── Badges ───────────────────────────────────────────────────────────────── */
.badge { display: inline-flex; align-items: center; padding: .12rem .55rem; border-radius: 9999px;
  font-size: .72rem; font-weight: 600; border: 1px solid transparent; line-height: 1.4; }
.badge-active   { background: hsl(var(--success) / 0.12);     color: hsl(142 70% 30%);  border-color: hsl(var(--success) / 0.3); }
.badge-inactive { background: hsl(var(--destructive) / 0.10); color: hsl(var(--destructive)); border-color: hsl(var(--destructive) / 0.3); }
.badge-warn     { background: hsl(var(--warning) / 0.14);     color: hsl(38 92% 35%);   border-color: hsl(var(--warning) / 0.35); }
.badge-info     { background: hsl(var(--info) / 0.12);        color: hsl(217 91% 45%);  border-color: hsl(var(--info) / 0.3); }
.badge-role     { background: hsl(var(--secondary));          color: hsl(var(--secondary-foreground)); border-color: hsl(var(--border)); }

/* ── Alerts ───────────────────────────────────────────────────────────────── */
.alert-warning, .alert-error, .alert-success {
  border: 1px solid; border-radius: var(--radius); padding: .75rem 1rem; margin-bottom: 1rem; font-size: .875rem; }
.alert-warning { background: hsl(var(--warning) / 0.10); border-color: hsl(var(--warning) / 0.4); color: hsl(38 92% 32%); }
.alert-error   { background: hsl(var(--destructive) / 0.08); border-color: hsl(var(--destructive) / 0.4); color: hsl(var(--destructive)); }
.alert-success { background: hsl(var(--success) / 0.10); border-color: hsl(var(--success) / 0.4); color: hsl(142 70% 28%); }

/* ── Cost cards ───────────────────────────────────────────────────────────── */
.cost-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1rem; margin-bottom: 1.25rem; }
.cost-card { text-align: center; padding: 1.1rem 1rem; }
.cost-card .label { font-size: .72rem; color: hsl(var(--muted-foreground)); text-transform: uppercase; letter-spacing: .05em; margin-bottom: .25rem; }
.cost-card .amount { font-size: 1.4rem; font-weight: 700; color: hsl(var(--foreground)); }
.cost-card .sub { font-size: .75rem; color: hsl(var(--muted-foreground)); margin-top: .2rem; }
@media (max-width: 900px) { .cost-cards { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .cost-cards { grid-template-columns: 1fr; } }

/* ── Charts ───────────────────────────────────────────────────────────────── */
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 1.25rem; }
@media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } }
.bar-chart { width: 100%; height: auto; font-size: 11px; }
.bar-chart .bar { fill: hsl(var(--primary)); transition: fill .15s; }
.bar-chart .bar:hover { fill: hsl(var(--primary) / 0.8); }
.bar-chart .axis-label { fill: hsl(var(--muted-foreground)); }
.bar-chart .grid-line { stroke: hsl(var(--border)); stroke-width: 1; }
.empty-chart { color: hsl(var(--muted-foreground)); text-align: center; padding: 2rem 0; }
.hbar-row { display: grid; grid-template-columns: 9rem 1fr 5.5rem; align-items: center; gap: .6rem; margin-bottom: .45rem; font-size: .85rem; }
.hbar-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hbar-track { background: hsl(var(--muted)); border-radius: 9999px; height: .55rem; overflow: hidden; }
.hbar-fill { background: hsl(var(--primary)); height: 100%; border-radius: 9999px; }
.hbar-val { text-align: right; color: hsl(var(--muted-foreground)); }

/* ── Misc layout ──────────────────────────────────────────────────────────── */
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
.page-header h2 { margin: 0; }
.year-bar, .filters { display: flex; gap: 1rem; align-items: flex-end; margin-bottom: 1rem; flex-wrap: wrap; }
.year-bar label, .filters label { margin: 0; font-size: .8rem; }
.year-bar select, .year-bar input, .filters input, .filters select { margin: 0; }
.detail-actions { display: flex; gap: .6rem; flex-wrap: wrap; margin-top: 1rem; }
.upcoming-item { display: flex; justify-content: space-between; align-items: center; padding: .45rem 0; border-bottom: 1px solid hsl(var(--border)); }
.upcoming-item:last-child { border-bottom: none; }
details summary { cursor: pointer; font-weight: 600; }
pre { font-size: .78rem; white-space: pre-wrap; word-break: break-all; background: hsl(var(--muted) / 0.5);
  border: 1px solid hsl(var(--border)); border-radius: calc(var(--radius) - 2px); padding: .6rem .75rem; }

/* ── Action dropdown menu ─────────────────────────────────────────────────── */
.action-menu { position: relative; display: inline-block; }
.action-menu details { margin: 0; }
.action-menu details summary {
  font-weight: 500; font-size: .82rem; margin: 0; padding: .35rem .75rem; list-style: none; cursor: pointer;
  border: 1px solid hsl(var(--border)); border-radius: calc(var(--radius) - 2px);
  background: hsl(var(--background)); color: hsl(var(--foreground)); user-select: none; white-space: nowrap; }
.action-menu details summary::-webkit-details-marker { display: none; }
.action-menu details summary:hover { background: hsl(var(--accent)); }
.action-menu details[open] summary { border-radius: calc(var(--radius) - 2px) calc(var(--radius) - 2px) 0 0; }
.action-menu .drop-list {
  position: absolute; right: 0; z-index: 200; min-width: 160px;
  background: hsl(var(--popover)); border: 1px solid hsl(var(--border)); border-top: none;
  border-radius: 0 0 calc(var(--radius) - 2px) calc(var(--radius) - 2px);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.12); overflow: hidden; padding: .25rem; }
.action-menu .drop-list a, .action-menu .drop-list button {
  display: block; width: 100%; box-sizing: border-box; height: auto; justify-content: flex-start;
  padding: .45rem .6rem; font-size: .84rem; text-decoration: none; color: hsl(var(--foreground));
  background: none; border: none; text-align: left; cursor: pointer; margin: 0; border-radius: calc(var(--radius) - 4px); }
.action-menu .drop-list a:hover, .action-menu .drop-list button:hover { background: hsl(var(--accent)); }
.action-menu .drop-danger { border-top: 1px solid hsl(var(--border)); margin-top: .25rem; padding-top: .25rem; }
.action-menu .drop-danger button { color: hsl(var(--destructive)); }
.action-menu .drop-danger button:hover { background: hsl(var(--destructive) / 0.1); }
"""

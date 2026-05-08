# DJACC Pro - Project Map

## [TECH_STACK]

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend** | Python / Django | 3.14 / 5.1 |
| **Database** | SQLite (dev) | - |
| **CSS Framework** | Bootstrap 5 RTL | 5.3.3 |
| **Design System** | Custom (tokens.css, components.css, layout.css) | v1.0 |
| **JS Libraries** | HTMX, Bootstrap JS Bundle, Chart.js (reports) | 1.9.10 / 5.3.3 |
| **Font** | Cairo (Google Fonts) | 400, 500, 600, 700, 800 |
| **Icons** | Bootstrap Icons | 1.11.3 |
| **Forms** | Crispy Forms + crispy-bootstrap5 | - |

## [ARCHITECTURE]

### Design System - Frontend (`static/css/`)

```
static/css/
├── tokens.css         ← Design variables (colors, spacing, shadows, fonts)
├── components.css     ← UI components (cards, tables, buttons, forms, badges)
└── layout.css         ← Layout system (sidebar, navbar, content area, responsive)
```

### Template Structure (`templates/`)

- `base.html` — Single base template with blocks: `title`, `header`, `content`, `extra_css`, `extra_js`
- `partials/` — Shared partials (pagination, form errors)
- `{app}/` — App-specific templates (dashboard, list, form, detail)

### Key Design Principles

1. **CSS Custom Properties** — all design tokens in `tokens.css` as `--color-*`, `--space-*`, `--shadow-*`, etc.
2. **Bootstrap 5.3.3** — primary framework, custom styles build on top
3. **RTL First** — all templates use `dir="rtl"` with Bootstrap RTL CDN
4. **Inline Style Reduction** — `<style>` blocks from 14 templates reduced/minimized
5. **No JS Build** — CDN-only, no webpack/vite required

## [SYSTEM_FLOW]

```
User Request → URL → View → Service Layer → Model → DB
                                    ↓
                    JournalService.create_entry()
                                    ↓
                    JournalEntry + JournalLine
                                    ↓
                    AuditService.log()
```

### Core Flows
- **Payroll**: PayrollPeriod → generate_payslips → approve → post (3 journal entries)
- **Sales**: SalesInvoice → reduce_stock → create_entry → auto-receipt (cash)
- **Purchases**: PurchaseInvoice → increase_stock → create_entry
- **Inventory**: ItemLedger (weighted average cost with quantity-zero reset)
- **Reports**: Bulk aggregation queries on JournalLine with OPENING entry handling

## [ORPHANS & PENDING]

| Item | Status | Priority |
|------|--------|----------|
| `test_purchase_invoice` missing `subtotal` in setup | ✅ Fixed | - |
| `test_sales_invoice` missing `due_date` in setup | ✅ Fixed | - |
| `record_movement` premature `total_cost` calc before None check | ✅ Fixed | - |
| `increase_stock` ignores `base_quantity=0` default | ✅ Fixed | - |
| `SalesService.post_invoice` ignores `base_quantity=0` default | ✅ Fixed | - |
| `AccountType` strings in `assets/services.py` | ✅ Fixed | - |
| HR loan deduction per-employee (not aggregated) | ✅ Fixed | - |
| Visual identity system (tokens, components, layout) | ✅ Fixed | - |

## [DESIGN SYSTEM REFERENCE]

### Color Palette

```css
--color-primary:        #4F46E5 (Indigo)
--color-success:        #10B981 (Emerald)
--color-warning:        #F59E0B (Amber)
--color-danger:         #EF4444 (Rose)
--color-info:           #0EA5E9 (Sky)
--bg-page:              #F8FAFC (Slate 50)
--bg-sidebar:           #0F172A (Slate 900)
--text-primary:         #0F172A (Slate 900)
```

### Component Classes (in components.css)

- `.stat-card` — Dashboard stat card with hover lift
- `.modern-table` — Clean table with uppercase headers
- `.badge-soft-{color}` — Soft background badges
- `.bg-soft-{color}` — Soft background utility
- `.icon-box` — 48×48 icon container
- `.report-link-card` — Report navigation card
- `.avatar-sm` / `.avatar-xs` — User avatar circles
- `.btn-menu-toggle` — Mobile sidebar toggle

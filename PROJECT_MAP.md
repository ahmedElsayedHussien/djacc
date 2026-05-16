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
| **E-Invoice** | cryptography, lxml, qrcode, requests | latest |

## [SYSTEM_FLOW - E-INVOICE]

```
SalesInvoice Created
        ↓
Generate ETA XML (XMLGenerator)
        ↓
Sign with Digital Certificate (Signer)
        ↓
Submit to Tax Authority API (TaxAPIClient)
        ↓
Receive IRN + UUID + QR Code
        ↓
Save to EInvoiceLog
        ↓
Update SalesInvoice with E-Invoice Data
        ↓
Display QR on Invoice PDF
```

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
| `DocumentService.generate_number` uses ID (sensitive to deletions) | ✅ Fixed | - |
| Income tax calculation using fixed percentage only | ✅ Fixed | - |
| Trial Balance report missing | ✅ Fixed (already exists) | - |
| **E-Invoice: Company Settings** | ✅ Done (M1) | - |
| **E-Invoice: EInvoiceConfig** | ✅ Done (M1) | - |
| **E-Invoice: Certificate Management** | ✅ Done (M1) | - |
| **E-Invoice: EInvoiceLog** | ✅ Done (M1) | - |
| **E-Invoice: XML Template (M2)** | ✅ Done | - |
| **E-Invoice: Digital Signature (M3)** | ✅ Done | - |
| **E-Invoice: API Client (M4)** | ✅ Done | - |
| **E-Invoice: QR Code Generator (M5)** | ✅ Done | - |
| **E-Invoice: Sales Integration (M6)** | 🔄 In Progress | 🔴 عالية |
| **E-Invoice: Testing (M7)** | 🚫 Pending | 🟡 متوسطة |
| **Mobile Responsive: Sidebar + Overlay (M1)** | ✅ Done | 🔴 عالية |
| **Mobile Responsive: Tables (M2)** | ✅ Done | 🔴 عالية |
| **Mobile Responsive: Forms (M3)** | ✅ Done | 🔴 عالية |
| **Mobile Responsive: Buttons + Inputs (M4)** | ✅ Done | 🔴 عالية |
| **Mobile Responsive: Cards + Stats (M5)** | ✅ Done | 🟡 متوسطة |
| **Mobile Responsive: Navbar + Menu (M6)** | ✅ Done | 🟡 متوسطة |
| **Mobile Responsive: Pagination (M7)** | ✅ Done | 🟡 متوسطة |
| **Mobile Responsive: Testing (M8)** | ✅ Done | 🟡 متوسطة |
| **Mobile: Table scroll internal only (no page scroll)** | ✅ Fixed | 🔴 عالية |
| **Tax: VAT validation on Sales** | ✅ Verified | 🔴 عالية |
| **Tax: VAT validation on Purchases** | ✅ Verified | 🔴 عالية |
| **Tax: WHT validation on Sales** | ✅ Verified | 🔴 haute |
| **Tax: WHT validation on Purchases** | ✅ Verified | 🔴 haute |
| **Tax: VAT Report function** | ✅ Added | 🔴 haute |
| **Tax: WHT Report function** | ✅ Added | 🔴 haute |
| **Tax: Stamp Tax (2124) account** | ✅ Added | 🟡 متوسطة |
| **Tax: VAT Report View + URL** | ✅ Added | 🔴 haute |
| **Tax: WHT Report View + URL** | ✅ Added | 🔴 haute |
| **Tax: VAT Report Template** | ✅ Added | 🔴 haute |
| **Tax: WHT Report Template** | ✅ Added | 🔴 haute |
| **Tax: VAT/WHT Menu Integration** | ✅ Added | 🟡 متوسطة |
| **Pricing: Item standard_price field** | ✅ Added | 🔴 عالية |
| **Pricing: extra_discount_percent in SalesInvoiceLine** | ✅ Added | 🔴 عالية |
| **Pricing: sector offer discount auto-apply** | ✅ Added | 🔴 عالية |
| **Pricing: price_list auto-fill with standard_price fallback** | ✅ Fixed | 🔴 عالية |
| **Pricing: Quotation-to-Invoice extra_discount_percent** | ✅ Added | 🟡 متوسطة |

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

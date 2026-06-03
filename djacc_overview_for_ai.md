# DJACC ERP System - Project Overview for AI Models

This document serves as a comprehensive context guide for any AI model working on the "DJACC" project. It outlines the technology stack, system architecture, database models, business logic, and UI/UX conventions used in the project.

## 1. Technology Stack
*   **Backend Framework:** Python / Django
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript, Bootstrap 5 (using custom glass-morphism and modern UI elements).
*   **Template Engine:** Django Templates (with heavily customized macros and includes).
*   **Database:** Relational Database (via Django ORM).

## 2. System Architecture & Apps
The system is built as a modular ERP/Accounting software, divided into several interconnected Django applications (`apps/` directory):

### 2.1. `core` (Accounting & System Core)
*   **Purpose:** The backbone of the financial system.
*   **Key Models:**
    *   `Account`: Chart of Accounts (دليل الحسابات).
    *   `CostCenter`: Cost Centers (مراكز التكلفة).
    *   `TaxType`: Tax definitions (الضرائب).
    *   `JournalEntry` & `JournalEntryLine`: General Ledger entries (قيود اليومية).
*   **Key Components:**
    *   `PermRequiredMixin`: Custom mixin used across CBVs (Class-Based Views) to handle permissions gracefully.
    *   `setup_permissions.py` (Management Command): Script to initialize default groups (e.g., `مبيعات`, `حسابات`) and assign specific app permissions automatically.

### 2.2. `sales` (Sales Management)
*   **Purpose:** Managing customers, sales representatives, invoicing, and collections.
*   **Key Models:**
    *   `Customer`, `CustomerSector`, `PriceList`, `Quotation`.
    *   `SalesRepresentative`: Links an `Employee` (from HR) to a User account and tracks commission rates and cash boxes.
    *   `SalesInvoice` & `SalesInvoiceLine`: Sales invoices (cash or credit).
    *   `SalesReturn` & `SalesReturnLine`: Sales returns.
    *   `CustomerReceipt`: Payments received from customers (سندات القبض).
    *   `ReceiptAllocation`: Junction table allocating a single `CustomerReceipt` amount across multiple outstanding `SalesInvoice`s.
*   **Business Logic:**
    *   **Auto-Allocation:** Creating a receipt dynamically fetches a customer's outstanding invoices via an internal API (`/sales/api/customer/<id>/invoices/`) and allows the user to allocate the payment via JavaScript.
    *   **Financial Integration:** `SalesService.record_receipt()` and similar service methods automatically generate `JournalEntry` records upon saving sales documents.

### 2.3. `purchases` (Purchases Management)
*   **Purpose:** Managing suppliers, purchase invoices, and outgoing payments (سندات الصرف). Structurally mirrors the `sales` app.

### 2.4. `inventory` (Inventory & Stock)
*   **Purpose:** Managing items, warehouses, and stock movements.
*   **Key Models:** `Item`, `Warehouse`, `StockTransaction`.
*   **Costing Method (طريقة تقييم المخزون):** The system uses **Weighted Average Costing** (متوسط التكلفة المرجح). The `average_cost` is recalculated dynamically (`total_value / quantity_on_hand`) and affects the COGS (Cost of Goods Sold) when posting out-bound transactions.

### 2.5. `assets` (Fixed Assets Management)
*   **Purpose:** Managing fixed assets and calculating their depreciation (الأصول الثابتة والإهلاك).
*   **Depreciation Method (طريقة الإهلاك):** The system includes a service module (`services.py` in the `assets` app) responsible for automatically generating depreciation schedules and posting the corresponding journal entries periodically.

### 2.6. Other Apps
*   `expenses`: For managing operational and administrative expenses.
*   `pos`: Point of Sale interface for fast retail transactions.
*   `e_invoice`: Electronic Invoicing integration (likely for local tax authority compliance).

### 2.7. `hr` (Human Resources)
*   **Key Models:** `Employee`, `Department`, `JobTitle`. Used to link system users to their organizational roles.

### 2.6. `treasury` (Treasury & Cash Management)
*   **Key Models:** `CashBox` (الخزينة), `BankAccount`.
*   **Utilities:** `get_available_cash_boxes(user)` ensures users only interact with cash boxes they have access to.

### 2.7. `reports` (Reporting Engine)
*   **Purpose:** Financial and operational reporting.
*   **Key Views:**
    *   `TrialBalanceView`, `IncomeStatementView`, `BalanceSheetView`.
    *   `CustomerStatementView`, `SupplierStatementView`, `AccountStatementView`.
    *   `SalesRepDashboardView`: A specialized, highly dynamic dashboard for Sales Reps showing targets, commissions, van stock, and outstanding credit invoices (`outstanding_invoices`).

## 3. UI/UX and Frontend Conventions
*   **Framework:** Bootstrap 5 is used extensively (`row`, `col`, `card`, `nav-pills`, etc.).
*   **Dynamic Interactions:** JavaScript `fetch()` API is used to load related data asynchronously without page reloads (e.g., loading invoices when a customer is selected).
*   **URL Parameters for State:** Views often read `request.GET` parameters to pre-fill forms or activate specific tabs. For example:
    *   `?tab=credit` opens the credit tab.
    *   `?customer=X&amount=Y&invoice=Z` auto-populates the receipt creation form and binds the sync logic between total amount and specific invoice allocation.
*   **Form Rendering:** Django forms are customized with `widgets=attrs{...}` in `forms.py` to inject Bootstrap classes (`form-control`, `form-select`).

## 4. Permission System & Security
*   The system uses Django's built-in `Group` and `Permission` models but orchestrates them via `setup_permissions.py`.
*   **Role-Based Access Control (RBAC):**
    *   Groups like `سوبر ادمن`, `مدير حسابات`, `حسابات`, `مدير مبيعات`, `مبيعات`.
    *   Views are protected by `LoginRequiredMixin` and `PermRequiredMixin`.
    *   `get_success_url()` is frequently overridden to redirect users based on their roles (e.g., redirecting a Sales Rep to their dashboard instead of a generic receipt list after creating a receipt).

## 5. Core Accounting Rules & Constraints
Any AI model modifying or adding financial features MUST strictly adhere to the following accounting principles implemented in the system:
1.  **Double-Entry Accounting:** Every financial transaction must generate a `JournalEntry` (قيد يومية).
2.  **Balanced Entries:** A `JournalEntry` is considered invalid and must raise an exception if the sum of debit lines (`debit`) does not exactly equal the sum of credit lines (`credit`). Never force-save an unbalanced entry.
3.  **Chart of Accounts (شجرة الحسابات):** The system relies on a hierarchical Chart of Accounts (Model: `Account`). 
    *   There is a built-in initialization script/function that generates the default standard Chart of Accounts structure.
    *   Accounts have types (Assets, Liabilities, Equity, Revenue, Expenses) and hierarchical levels (Parent/Child).
    *   Journal entry lines (`JournalEntryLine`) must only be posted to **leaf accounts** (حسابات فرعية لا يتفرع منها حسابات أخرى).
4.  **Immutability of Posted Documents:** Once a document (Invoice, Receipt, Return) is marked as `POSTED` (مُرحل) and its journal entries are generated, it MUST NOT be edited or deleted. 
5.  **Audit Trail & Reversals (عكس القيود):** The concept of deleting or permanently canceling a `JournalEntry` does **NOT** exist in this system. If an error is made, the original entry remains intact, and a **Reversal Entry** (قيد عكسي) must be generated to offset it. Reversals or adjustments must be handled via formal credit notes or return documents that generate these counter-entries.

## 6. Development Guidelines for AI
1.  **Service Layer:** Do not write raw journal entry creation inside views. Always look for existing service classes (e.g., `SalesService.record_receipt()`, `DocumentService.generate_number()`).
2.  **Form Validation:** Place business logic validation in `clean_<fieldname>()` or `clean()` methods inside `forms.py` (e.g., preventing future dates, validating limits).
3.  **Permissions:** When adding a new view, always add the corresponding `permission_required`. If the view is for an existing group, update `setup_permissions.py`.
4.  **JavaScript:** Keep JS vanilla. Use `document.querySelector` and `addEventListener`. Handle async operations gracefully and ensure DOM elements exist before attaching events (especially for elements injected via `fetch`).
5.  **Naming Conventions:** 
    *   URLs use hyphens (e.g., `receipt-create`).
    *   URL names use underscores (e.g., `name='receipt_create'`) or hyphens interchangeably depending on the app, always double-check `urls.py`.
    *   Views are strictly Class-Based Views (CBVs).

"""Permission codes (`module.action`) and default role templates. Roles are editable per tenant."""

PERMISSIONS = {
    # tenancy & org
    "org.view": "View company structure",
    "org.manage": "Manage legal entities and branches",
    "users.manage": "Invite users and assign roles",
    # setup (phase 2)
    "catalog.view": "View services and prices",
    "catalog.manage": "Create and edit services and categories",
    "staff.view": "View staff",
    "staff.manage": "Create and edit staff, branches and skills",
    "customers.view": "View customers and beneficiaries",
    "customers.manage": "Create and edit customers and beneficiaries",
    # POS & operations (implemented in phase 3)
    "pos.sell": "Sell at the POS",
    "pos.discount.line": "Apply discounts within the role limit",
    "pos.discount.override": "Approve discounts above the limit",
    "pos.credit_sale": "Create credit (deferred payment) invoices",
    "pos.return": "Approve returns",
    "catalog.price.change": "Change prices",
    "cash.session.open": "Open/close cash sessions",
    "cash.variance.approve": "Approve cash shortages/overages",
    "report.view.cost_profit": "See cost, margin and profit",
    "commission.view.all": "See all staff commissions",
    "inventory.adjust": "Adjust stock",
    # accounting
    "accounting.view": "View ledger, journals and trial balance",
    "accounting.journal.post": "Create and post manual journal entries",
    "accounting.journal.reverse": "Reverse posted journal entries",
    "accounting.period.close": "Close and reopen fiscal periods",
    "accounting.setup": "Edit chart of accounts and posting mappings",
    "reporting.statements.approve": "Approve financial statements",
    "qayd.export": "Prepare and download the Qayd template",
    "qayd.submission.record": "Record Qayd submission, receipt and result",
    "data.export": "Export data",
    "audit.view": "View the audit log",
}

ALL = set(PERMISSIONS)

ROLE_TEMPLATES = {
    "owner": {"name_ar": "مالك الشركة", "name_en": "Owner", "permissions": ALL},
    "operations_manager": {"name_ar": "مدير العمليات", "name_en": "Operations manager", "permissions": ALL - {
        "accounting.journal.post", "accounting.journal.reverse", "accounting.period.close", "accounting.setup",
        "reporting.statements.approve", "qayd.export", "qayd.submission.record"}},
    "branch_manager": {"name_ar": "مدير الفرع", "name_en": "Branch manager", "permissions": {
        "org.view", "catalog.view", "staff.view", "customers.view", "customers.manage",
        "pos.sell", "pos.discount.line", "pos.discount.override", "pos.credit_sale", "pos.return",
        "cash.session.open", "cash.variance.approve", "commission.view.all", "data.export"}},
    "cashier": {"name_ar": "كاشير واستقبال", "name_en": "Cashier / reception", "permissions": {
        "catalog.view", "staff.view", "customers.view", "customers.manage",
        "pos.sell", "pos.discount.line", "cash.session.open"}},
    "service_provider": {"name_ar": "مقدم خدمة", "name_en": "Service provider", "permissions": {"catalog.view"}},
    "inventory_officer": {"name_ar": "مسؤول المخزون", "name_en": "Inventory officer", "permissions": {
        "inventory.adjust", "org.view", "catalog.view"}},
    "accountant": {"name_ar": "محاسب", "name_en": "Accountant", "permissions": {
        "org.view", "catalog.view", "accounting.view", "accounting.journal.post", "report.view.cost_profit",
        "commission.view.all", "qayd.export", "qayd.submission.record", "data.export"}},
    "finance_manager": {"name_ar": "المدير المالي", "name_en": "Finance manager", "permissions": {
        "org.view", "accounting.view", "accounting.journal.post", "accounting.journal.reverse",
        "accounting.period.close", "accounting.setup", "reporting.statements.approve", "report.view.cost_profit",
        "commission.view.all", "cash.variance.approve", "qayd.export", "qayd.submission.record", "data.export",
        "audit.view"}},
    "auditor": {"name_ar": "مراجع خارجي", "name_en": "External auditor", "permissions": {
        "org.view", "accounting.view", "report.view.cost_profit", "commission.view.all", "audit.view"}},
}

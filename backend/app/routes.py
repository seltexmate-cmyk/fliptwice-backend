from __future__ import annotations

from fastapi import APIRouter

from app.automation.routes import router as automation_router
from app.analytics.routes import router as analytics_router
from app.business.routes import router as business_router
from app.items.routes import router as items_router
from app.expenses.routes import router as expenses_router
from app.dashboard.routes import router as dashboard_router
from app.ledger.routes import router as ledger_router
from app.finance.routes import router as finance_router
from app.integrations.ebay.routes import router as ebay_router

router = APIRouter(tags=["app"])

router.include_router(business_router)
router.include_router(items_router)
router.include_router(expenses_router)
router.include_router(dashboard_router)
router.include_router(ledger_router)
router.include_router(finance_router)
router.include_router(analytics_router)
router.include_router(automation_router)
router.include_router(ebay_router)
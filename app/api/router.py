from fastapi import APIRouter, Depends

from app.api.v1.auth import router as auth_router
from app.api.v1.cash import router as cash_router
from app.api.v1.categories import router as categories_router
from app.api.v1.customers import router as customers_router
from app.api.v1.development import router as development_router
from app.api.v1.goldPurities import router as gold_purities_router
from app.api.v1.insights import router as insights_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.inventory_history import router as inventory_history_router
from app.api.v1.inventory_operations import router as inventory_operations_router
from app.api.v1.inventoryBalance import router as inventory_balance_router
from app.api.v1.inventoryServicing import router as servicing_router
from app.api.v1.item_photos import router as item_photos_router
from app.api.v1.legacy_books import router as legacy_books_router
from app.api.v1.locations import router as locations_router
from app.api.v1.products import router as products_router
from app.api.v1.purchase import router as purchase_router
from app.api.v1.sale import router as sale_router
from app.api.v1.supplier_ledger import router as supplier_ledger_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.users import router as users_router
from app.core.dependencies import get_current_user

api_router = APIRouter(
    prefix="/api/v1",
)

routers = [
    auth_router,
    users_router,
    products_router,
    gold_purities_router,
    categories_router,
    suppliers_router,
    customers_router,
    locations_router,
    inventory_history_router,
    inventory_router,
    inventory_balance_router,
    purchase_router,
    sale_router,
    servicing_router,
    supplier_ledger_router,
]

for router in routers:
    api_router.include_router(
        router, dependencies=[] if router is auth_router else [Depends(get_current_user)]
    )

api_router.include_router(inventory_operations_router, dependencies=[Depends(get_current_user)])
api_router.include_router(legacy_books_router, dependencies=[Depends(get_current_user)])

api_router.include_router(cash_router, dependencies=[Depends(get_current_user)])

api_router.include_router(item_photos_router, dependencies=[Depends(get_current_user)])

api_router.include_router(insights_router, dependencies=[Depends(get_current_user)])

api_router.include_router(development_router, dependencies=[Depends(get_current_user)])

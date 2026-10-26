from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.products import router as products_router
from app.api.v1.goldPurities import router as gold_purities_router
from app.api.v1.categories import router as categories_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.customers import router as customers_router
from app.api.v1.locations import router as locations_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.inventoryBalance import router as inventory_balance_router
from app.api.v1.purchase import router as purchase_router
from app.api.v1.sale import router as sale_router
from app.api.v1.saleBook import router as sale_book_router
from app.api.v1.purchaseBook import router as purchase_book_router

api_router = APIRouter(
    prefix="/api/v1",
)

routers = [auth_router, users_router, products_router, gold_purities_router,
           categories_router, suppliers_router, customers_router, locations_router,
           inventory_router, inventory_balance_router, purchase_router, sale_router, purchase_book_router,
           sale_book_router]

for router in routers:
    api_router.include_router(router)
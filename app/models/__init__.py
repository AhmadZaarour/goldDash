"""Register every mapped table for application startup and Alembic."""

from app.models.categories import Category
from app.models.customers import Customer
from app.models.goldPurities import GoldPurity
from app.models.inventoryBalance import InventoryBalance
from app.models.inventoryItem import InventoryItem
from app.models.inventoryMovement import InventoryMovement
from app.models.inventoryServicing import InventoryService
from app.models.inventoryStock import InventoryStock
from app.models.itemReturn import ItemReturn
from app.models.location import Location
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchaseBook import PurchaseBook
from app.models.purchaseItem import PurchaseItem
from app.models.purchaseStock import PurchaseStock
from app.models.saleBook import SaleBook
from app.models.saleItem import SaleItem
from app.models.sales import Sale
from app.models.saleStock import SaleStock
from app.models.stockTransfer import StockTransferRecord
from app.models.supplierLedger import SupplierLedgerEntry
from app.models.suppliers import Supplier
from app.models.user import User, UserRole

__all__ = [
    "ItemReturn",
    "StockTransferRecord",
    "SupplierLedgerEntry",
    "Category",
    "Customer",
    "GoldPurity",
    "InventoryBalance",
    "InventoryItem",
    "InventoryMovement",
    "InventoryService",
    "InventoryStock",
    "Location",
    "Product",
    "Purchase",
    "PurchaseBook",
    "PurchaseItem",
    "PurchaseStock",
    "SaleBook",
    "SaleItem",
    "SaleStock",
    "Sale",
    "Supplier",
    "User",
    "UserRole",
]

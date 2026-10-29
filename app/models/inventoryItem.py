from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InventoryItem(Base):
    __tablename__ = "inventoryItems"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    purchase_item_id: Mapped[int] = mapped_column(ForeignKey("purchaseItems.id"), unique=True)

    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))

    barcode: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    purchase_item: Mapped["PurchaseItem"] = relationship(lazy="joined")

    @property
    def base_cost_usd(self) -> Decimal:
        line = self.purchase_item
        return (
            line.gold_charge_in_grams * line.gold_price_per_gram + line.making_charge
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    status: Mapped[str] = mapped_column(
        String(50),
    )


if TYPE_CHECKING:
    from app.models.purchaseItem import PurchaseItem

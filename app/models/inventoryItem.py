from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.workspace import UnitOwned


class InventoryItem(UnitOwned, Base):
    __tablename__ = "inventoryItems"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    __table_args__ = (
        CheckConstraint(
            "(purchase_item_id IS NOT NULL AND production_piece_id IS NULL) "
            "OR (purchase_item_id IS NULL AND production_piece_id IS NOT NULL)",
            name="ck_inventory_origin",
        ),
    )
    production_piece_id: Mapped[int | None] = mapped_column(
        ForeignKey("production_pieces.id"), unique=True
    )
    production_piece: Mapped["ProductionPiece | None"] = relationship(lazy="joined")
    company_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    owner_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    acquisition_internal_id: Mapped[int | None] = mapped_column(ForeignKey("internal_invoices.id"))

    purchase_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchaseItems.id"), unique=True
    )

    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))

    barcode: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    purchase_item: Mapped["PurchaseItem"] = relationship(lazy="joined")

    @property
    def origin_line(self):
        return self.purchase_item or self.production_piece

    @property
    def cost_basis_usd(self):
        if self.owner_cost_usd is not None:
            return self.owner_cost_usd
        line = self.origin_line
        return line.weight * line.gold_price_per_gram + line.making_charge

    @property
    def base_cost_usd(self) -> Decimal:
        if self.owner_cost_usd is not None:
            return self.owner_cost_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line = self.origin_line
        return (line.weight * (line.gold_price_per_gram + line.making_charge)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    status: Mapped[str] = mapped_column(
        String(50),
    )


if TYPE_CHECKING:
    from app.models.operations import ProductionPiece
    from app.models.purchaseItem import PurchaseItem

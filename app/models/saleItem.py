from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SaleItem(Base):
    __tablename__ = "saleItems"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id"),
        nullable=False,
    )

    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventoryItems.id"))

    gold_price_per_gram: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
    )

    discount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    sell_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    return_record: Mapped["ItemReturn | None"] = relationship(
        lazy="joined", uselist=False, viewonly=True
    )

    @property
    def returned(self) -> bool:
        return self.return_record is not None

    @property
    def return_id(self) -> int | None:
        return self.return_record.id if self.return_record else None

    @property
    def refund_usd(self) -> Decimal:
        return self.return_record.refund_usd if self.return_record else Decimal("0")

    @property
    def returned_at(self) -> datetime | None:
        return self.return_record.created_at if self.return_record else None


if TYPE_CHECKING:
    from app.models.itemReturn import ItemReturn

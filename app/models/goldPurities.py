from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GoldPurity(Base):
    __tablename__ = "goldPurities"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    karat: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    purity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

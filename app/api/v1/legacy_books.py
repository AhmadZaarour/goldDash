from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Retired invoice books"])


async def retired():
    raise HTTPException(
        410, "Invoice books are retired; use supplier balances, ledger history, and settlements"
    )


async def retired_detail(book_id: int):
    return await retired()


for resource in ["purchaseBook", "saleBook"]:
    for method in ["GET", "POST", "PATCH"]:
        for detail in [False, True]:
            scope = "detail" if detail else "list"
            router.add_api_route(
                f"/{resource}" + ("/{book_id}" if detail else ""),
                retired_detail if detail else retired,
                methods=[method],
                deprecated=True,
                operation_id=f"retired_{resource}_{scope}_{method.lower()}",
            )

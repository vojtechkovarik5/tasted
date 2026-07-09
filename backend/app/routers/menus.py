import uuid

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.auth import OptionalUserDep
from app.domain import Money, Preferences
from app.models import Menu, ScanItem, User
from app.schemas import (
    DishOut,
    MenuItemOut,
    MenuItemStatus,
    MenuOut,
    MenuStatus,
    MenuSummaryOut,
)
from app.services.currencies import CurrencyService, CurrencyServiceDep
from app.services.menus import MenuService, MenuServiceDep, PhotoUpload
from app.tasks import process_menu_task

router = APIRouter(tags=["menus"])


async def _item_out(
    item: ScanItem, target_currency: str, currencies: CurrencyService
) -> MenuItemOut:
    """Map a ScanItem to the API shape, converting the printed price to the
    user's currency (rates change daily, so this is computed at read time)."""
    menu_price = approx_price = None
    if item.menu_price is not None and item.menu_price_currency:
        menu_price = Money(amount=float(item.menu_price), currency=item.menu_price_currency)
        converted = await currencies.convert(
            item.menu_price, item.menu_price_currency, target_currency
        )
        if converted is not None:
            approx_price = Money(amount=round(float(converted), 2), currency=target_currency)
    return MenuItemOut(
        id=item.id,
        original_name=item.original_name,
        status=MenuItemStatus(item.status),
        menu_price=menu_price,
        approx_price=approx_price,
        regional_note=item.regional_note,
        dish=DishOut.from_orm_dish(item.dish) if item.dish is not None else None,
    )


def _menu_status(menu: Menu) -> MenuStatus:
    done = all(s.status == "complete" for s in menu.scans)
    return MenuStatus.complete if done else MenuStatus.processing


async def _menu_out(menu: Menu, user: User | None, currencies: CurrencyService) -> MenuOut:
    # Anonymous scans convert into the default currency; the device applies
    # its local preference on top if it differs.
    prefs = Preferences.model_validate(user.prefs or {}) if user else Preferences()
    currency = prefs.currency
    items = [
        await _item_out(i, currency, currencies) for i in MenuService.combined_items(menu)
    ]
    return MenuOut(
        id=menu.id,
        name=menu.name,
        status=_menu_status(menu),
        created_at=menu.created_at.isoformat(),
        language=menu.language,
        items=items,
    )


@router.post("/menus", response_model=MenuOut)
async def create_menu(
    photos: list[UploadFile],
    user: OptionalUserDep,
    menus: MenuServiceDep,
    currencies: CurrencyServiceDep,
    name: str | None = Form(None),  # optional restaurant title from the app
) -> MenuOut:
    """Create a menu from one or more photos (pages of the same menu).

    Works logged out: an anonymous menu has no owner and is reachable only by
    its id, which the client keeps as its "current menu". Logged in, the menu
    lands in the user's history. Pages go to object storage, the Celery
    pipeline is enqueued, and the client polls GET /menus/{id} while items
    resolve.
    """
    uploads = [
        PhotoUpload(data=await p.read(), content_type=p.content_type) for p in photos
    ]
    menu = await menus.create_with_photos(
        uploads, user_id=user.id if user else None, name=name
    )
    process_menu_task.delay(str(menu.id))
    return await _menu_out(menu, user, currencies) # TODO move currency fetch to service


@router.get("/menus", response_model=list[MenuSummaryOut])
async def list_menus(user: OptionalUserDep, menus: MenuServiceDep) -> list[MenuSummaryOut]:
    """The authenticated user's menu history (newest first). Scoped to the
    auth header — nobody can read another user's history. Anonymous users
    have no server-side history (the app keeps their current menu locally),
    so this returns []."""
    if user is None:
        return []
    rows = await menus.list_for_user(user.id)
    return [
        MenuSummaryOut(
            id=m.id,
            name=m.name,
            status=_menu_status(m),
            created_at=m.created_at.isoformat(),
            item_count=len(MenuService.combined_items(m)),
        )
        for m in rows
    ]


@router.get("/menus/{menu_id}", response_model=MenuOut)
async def get_menu(
    menu_id: uuid.UUID,
    user: OptionalUserDep,
    menus: MenuServiceDep,
    currencies: CurrencyServiceDep,
) -> MenuOut:
    """Poll a menu's resolution progress. Items flip pending -> ready as the
    background pipeline enriches them.

    Access: an owned menu is visible only to its owner; an anonymous menu is
    reachable by anyone holding its (unguessable) id — that id is the
    logged-out user's "current menu" capability.
    """
    menu = await menus.get(menu_id)
    owned_by_someone_else = menu is not None and menu.user_id is not None and (
        user is None or menu.user_id != user.id
    )
    if menu is None or owned_by_someone_else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu not found")
    return await _menu_out(menu, user, currencies)

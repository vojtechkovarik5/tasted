import uuid

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.auth import OptionalUserDep
from app.domain import Language, Money, Preferences
from app.models import Menu, ScanItem, User
from app.schemas import (
    DishOut,
    MenuItemOut,
    MenuItemStatus,
    MenuOut,
    MenuRename,
    MenuStatus,
    MenuSummaryOut,
    MenuTagOut,
)
from app.schemas.dish import Labels, attribute_label_pairs
from app.services.currencies import CurrencyService, CurrencyServiceDep
from app.services.menus import MenuService, MenuServiceDep, PhotoUpload
from app.services.trackables import TrackableService, TrackableServiceDep
from app.tasks import process_menu_task

router = APIRouter(tags=["menus"])


async def _item_out(
    item: ScanItem,
    target_currency: str,
    currencies: CurrencyService,
    language: Language,
    labels: Labels,
) -> MenuItemOut:
    """Map a ScanItem to the API shape, converting the printed price to the
    user's currency (rates change daily, so this is computed at read time)
    and localizing catalog labels to the user's language."""
    menu_price = approx_price = None
    if item.menu_price is not None and item.menu_price_currency:
        menu_price = Money(amount=float(item.menu_price), currency=item.menu_price_currency)
        # No approx twin when the menu already prints the user's currency.
        if item.menu_price_currency != target_currency:
            converted = await currencies.convert(
                item.menu_price, item.menu_price_currency, target_currency
            )
            if converted is not None:
                approx_price = Money(
                    amount=round(float(converted), 2), currency=target_currency
                )
    # Printed ingredients keep the menu's wording (translated during
    # extraction); printed allergens are canonical slugs resolved through the
    # catalog like every other tag.
    menu_ingredients = [
        MenuTagOut(key=ing.get("key"), name=ing.get("translated_name") or ing.get("name"))
        for ing in (item.menu_ingredients or [])
        if ing.get("name")
    ]
    menu_allergens = [
        MenuTagOut(key=key, name=labels.get(("allergen", key), key.replace("-", " ")))
        for key in (item.menu_allergens or [])
    ]
    return MenuItemOut(
        id=item.id,
        original_name=item.original_name,
        menu_number=item.menu_number,
        translated_name=item.translated_name,
        menu_description=item.menu_description,
        menu_description_translated=item.menu_description_translated,
        group_name=item.group_name,
        group_name_translated=item.group_name_translated,
        status=MenuItemStatus(item.status),
        menu_price=menu_price,
        approx_price=approx_price,
        regional_note=item.regional_note,
        menu_ingredients=menu_ingredients,
        menu_allergens=menu_allergens,
        dish=(
            DishOut.from_orm_dish(item.dish, language=language, labels=labels)
            if item.dish is not None
            else None
        ),
        match_confidence=item.match_confidence,
        matched_variant_key=item.dish_variant.key if item.dish_variant else None,
    )


def _menu_status(menu: Menu) -> MenuStatus:
    done = all(s.status == "complete" for s in menu.scans)
    return MenuStatus.complete if done else MenuStatus.processing


async def _menu_out(
    menu: Menu, user: User | None, currencies: CurrencyService, trackables: TrackableService
) -> MenuOut:
    # Anonymous scans convert into the default currency; the device applies
    # its local preference on top if it differs.
    prefs = Preferences.model_validate(user.prefs or {}) if user else Preferences()
    currency = prefs.currency
    combined = MenuService.combined_items(menu)
    # One catalog query localizes every tag on the menu: printed allergens
    # plus each matched dish's attribute labels.
    pairs: set[tuple[str, str]] = set()
    for item in combined:
        pairs.update(("allergen", key) for key in (item.menu_allergens or []))
        if item.dish is not None:
            pairs.update(attribute_label_pairs(item.dish))
    labels = await trackables.labels(pairs, prefs.language)
    items = [
        await _item_out(i, currency, currencies, prefs.language, labels) for i in combined
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
    trackables: TrackableServiceDep,
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
    # TODO move currency fetch to service
    return await _menu_out(menu, user, currencies, trackables)


@router.get("/menus", response_model=list[MenuSummaryOut])
async def list_menus(user: OptionalUserDep, menus: MenuServiceDep) -> list[MenuSummaryOut]:
    """The authenticated user's menu history (newest first). Scoped to the
    auth header — nobody can read another user's history. Anonymous users
    have no server-side history (the app keeps their current menu locally),
    so this returns []."""
    if user is None:
        return []
    rows = await menus.list_for_user(user.id)
    return [_summary_out(m) for m in rows]


def _summary_out(menu: Menu) -> MenuSummaryOut:
    return MenuSummaryOut(
        id=menu.id,
        name=menu.name,
        status=_menu_status(menu),
        created_at=menu.created_at.isoformat(),
        item_count=len(MenuService.combined_items(menu)),
        scan_count=len(menu.scans),
        language=menu.language,
    )


def _accessible(menu: Menu | None, user: User | None) -> Menu:
    """Shared access rule: an owned menu is visible only to its owner; an
    anonymous menu is reachable by anyone holding its (unguessable) id."""
    owned_by_someone_else = menu is not None and menu.user_id is not None and (
        user is None or menu.user_id != user.id
    )
    if menu is None or owned_by_someone_else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu not found")
    return menu


@router.patch("/menus/{menu_id}", response_model=MenuSummaryOut)
async def rename_menu(
    menu_id: uuid.UUID,
    body: MenuRename,
    user: OptionalUserDep,
    menus: MenuServiceDep,
) -> MenuSummaryOut:
    """Rename a menu (the pencil next to the name in the list). Same access
    rule as GET: the owner, or anyone holding an anonymous menu's id."""
    menu = _accessible(await menus.get(menu_id), user)
    return _summary_out(await menus.rename(menu, body.name))


@router.delete("/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu(
    menu_id: uuid.UUID,
    user: OptionalUserDep,
    menus: MenuServiceDep,
) -> None:
    """Delete a menu with its scans and items (swipe-to-delete in the list).
    Canonical dishes are shared knowledge and stay untouched."""
    menu = _accessible(await menus.get(menu_id), user)
    await menus.delete(menu)


@router.get("/menus/{menu_id}", response_model=MenuOut)
async def get_menu(
    menu_id: uuid.UUID,
    user: OptionalUserDep,
    menus: MenuServiceDep,
    currencies: CurrencyServiceDep,
    trackables: TrackableServiceDep,
) -> MenuOut:
    """Poll a menu's resolution progress. Items flip pending -> ready as the
    background pipeline enriches them.

    Access: an owned menu is visible only to its owner; an anonymous menu is
    reachable by anyone holding its (unguessable) id — that id is the
    logged-out user's "current menu" capability.
    """
    menu = _accessible(await menus.get(menu_id), user)
    return await _menu_out(menu, user, currencies, trackables)

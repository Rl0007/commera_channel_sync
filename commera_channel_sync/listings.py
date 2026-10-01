import frappe
from commera.app_events import is_listed_item
from commera.utils import get_available_stock
from frappe.utils import flt, now_datetime

from commera_channel_sync.fake_channel import FakeChannelUnavailable, push_listing

SYNCED_FIELDS = ("title", "price", "price_list", "available_qty")


def on_product_updated(event):
	listing = get_listing(event.reference_name)
	set_item_details(listing)
	sync_listing(listing, event)


def on_inventory_changed(event):
	"""The qty is re-read rather than taken from event.data, so a late or replayed event can only push today's stock."""
	item_code = event.reference_name
	if not frappe.db.exists("Channel Listing", item_code) and not is_listed_item(item_code):
		return

	listing = get_listing(item_code)
	listing.available_qty = get_sellable_qty(item_code)
	listing.last_event_qty = flt(event.data.get("actual_qty"))
	sync_listing(listing, event)


def get_listing(item_code: str):
	if frappe.db.exists("Channel Listing", item_code):
		return frappe.get_doc("Channel Listing", item_code, for_update=True)

	listing = frappe.new_doc("Channel Listing")
	listing.item_code = item_code
	set_item_details(listing)
	listing.available_qty = get_sellable_qty(item_code)
	return listing


def set_item_details(listing):
	listing.title = frappe.db.get_value("Item", listing.item_code, "item_name")
	listing.price_list, listing.price = get_store_price(listing.item_code)


def get_store_price(item_code: str) -> tuple[str | None, float]:
	"""The sale price list's rate when the item has one, else the default list's, as the product page shows it."""
	settings = frappe.get_cached_doc("Commera Settings")
	price_lists = [
		price_list for price_list in (settings.sale_price_list, settings.default_price_list) if price_list
	]
	rates = {
		row.price_list: row.price_list_rate
		for row in frappe.get_all(
			"Item Price",
			filters={
				"item_code": item_code,
				"price_list": ["in", price_lists],
				"selling": 1,
				"customer": ["is", "not set"],
			},
			fields=["price_list", "price_list_rate"],
			order_by="creation asc",
		)
	}
	for price_list in price_lists:
		if price_list in rates:
			return price_list, flt(rates[price_list])
	return None, 0


def get_sellable_qty(item_code: str) -> float:
	warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
	return flt(get_available_stock(item_code, warehouse)["stock_qty"])


def sync_listing(listing, event):
	listing.last_event = event.id
	if listing.sync_status == "Synced" and not has_synced_fields_changed(listing):
		listing.save()
		return

	try:
		push_listing(listing, event.id)
	except FakeChannelUnavailable:
		mark_failed(listing.name)
		raise

	listing.sync_status = "Synced"
	listing.last_synced_at = now_datetime()
	listing.save()


def has_synced_fields_changed(listing) -> bool:
	if listing.is_new():
		return True
	saved_values = frappe.db.get_value("Channel Listing", listing.name, SYNCED_FIELDS, as_dict=True)
	return any(listing.get(fieldname) != saved_values.get(fieldname) for fieldname in SYNCED_FIELDS)


def mark_failed(listing_name: str | None):
	# Commera rolls back a handler's writes when it raises, so the Failed status has to be committed first.
	frappe.db.rollback()
	if listing_name and frappe.db.exists("Channel Listing", listing_name):
		frappe.db.set_value("Channel Listing", listing_name, "sync_status", "Failed")
		frappe.db.commit()

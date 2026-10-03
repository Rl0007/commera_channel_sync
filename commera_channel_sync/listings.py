import frappe
from commera.sdk import catalog
from frappe.utils import flt, now_datetime

from commera_channel_sync.fake_channel import FakeChannelUnavailable, push_listing

SYNCED_FIELDS = ("title", "price", "available_qty")


def on_product_updated(event):
	"""Fires for a template or a size item, and also right after a product is unpublished."""
	item_code = event.reference_name
	item_codes = frappe.get_all("Item", filters={"variant_of": item_code}, pluck="name") or [item_code]
	for catalog_item in catalog.get_items(item_codes).values():
		if not catalog_item["is_listed"] and not frappe.db.exists(
			"Channel Listing", catalog_item["item_code"]
		):
			continue
		listing = get_listing(catalog_item["item_code"])
		set_item_details(listing, catalog_item)
		sync_listing(listing, event.id)


def on_inventory_changed(event):
	"""The qty is re-read rather than taken from event.data, so a late or replayed event can only push today's stock."""
	item_code = event.reference_name
	catalog_item = catalog.get_items([item_code]).get(item_code)
	if not catalog_item:
		return
	if not frappe.db.exists("Channel Listing", item_code) and not catalog_item["is_listed"]:
		return

	listing = get_listing(item_code)
	set_item_details(listing, catalog_item)
	listing.last_event_qty = flt(event.data.get("actual_qty"))
	sync_listing(listing, event.id)


def sync_product_listings(item_codes: list[str]):
	for catalog_item in catalog.get_items(item_codes).values():
		listing = get_listing(catalog_item["item_code"])
		set_item_details(listing, catalog_item)
		try:
			sync_listing(listing, None)
		except FakeChannelUnavailable:
			continue
		frappe.db.commit()


def get_listing(item_code: str):
	if frappe.db.exists("Channel Listing", item_code):
		return frappe.get_doc("Channel Listing", item_code, for_update=True)

	listing = frappe.new_doc("Channel Listing")
	listing.item_code = item_code
	return listing


def set_item_details(listing, catalog_item: dict):
	listing.title = catalog_item["title"]
	listing.price = flt(catalog_item["price"])
	listing.available_qty = catalog_item["available_qty"]


def sync_listing(listing, event_id: str | None):
	listing.last_event = event_id or listing.last_event
	if listing.sync_status == "Synced" and not has_synced_fields_changed(listing):
		listing.save()
		return

	try:
		push_listing(listing, event_id)
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

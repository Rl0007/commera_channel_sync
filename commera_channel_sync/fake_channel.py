import frappe


class FakeChannelUnavailable(Exception):
	pass


def push_listing(listing, event_id: str):
	"""Stands in for the marketplace's listing API: a full overwrite of one SKU, so a repeated push is harmless."""
	if frappe.db.get_single_value("Channel Sync Settings", "fake_channel_down", cache=False):
		raise FakeChannelUnavailable(f"Fake channel is down: {listing.item_code} was not pushed")

	frappe.get_doc(
		{
			"doctype": "Fake Channel Request",
			"item_code": listing.item_code,
			"title": listing.title,
			"price": listing.price,
			"available_qty": listing.available_qty,
			"commera_event": event_id,
		}
	).insert()

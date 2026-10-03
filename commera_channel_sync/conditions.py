import frappe

from commera_channel_sync.api import get_product_item_codes


def has_listings(doctype: str, name: str) -> bool:
	return frappe.has_permission("Channel Listing", "write") and bool(
		frappe.db.exists("Channel Listing", {"item_code": ["in", get_product_item_codes(name)]})
	)

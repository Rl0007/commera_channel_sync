import frappe
from frappe import _
from frappe.utils.data import cint

SYNC_STATUSES = ("Synced", "Pending", "Failed")


@frappe.whitelist(methods=["GET"])
def get_listings(sync_status: str | None = None, start: int = 0, page_length: int = 20) -> dict:
	if sync_status and sync_status not in SYNC_STATUSES:
		frappe.throw(_("Sync status must be one of {0}.").format(", ".join(SYNC_STATUSES)))

	rows = frappe.get_list(
		"Channel Listing",
		filters={"sync_status": sync_status} if sync_status else {},
		fields=["name", "item_code", "title", "price", "available_qty", "sync_status", "last_synced_at"],
		order_by="modified desc",
		start=cint(start),
		page_length=cint(page_length),
	)
	counts = {
		row.sync_status: cint(row.count)
		for row in frappe.get_list(
			"Channel Listing",
			fields=["sync_status", {"COUNT": "*", "as": "count"}],
			group_by="sync_status",
			order_by="sync_status asc",
		)
	}
	return {
		"rows": rows,
		"total": counts.get(sync_status, 0) if sync_status else sum(counts.values()),
		"counts": {status: counts.get(status, 0) for status in SYNC_STATUSES},
		"channel_down": cint(frappe.db.get_single_value("Channel Sync Settings", "fake_channel_down")),
	}


@frappe.whitelist(methods=["GET"])
def get_product_listings(item: str) -> list[dict]:
	frappe.has_permission("Item", "read", item, throw=True)
	return frappe.get_list(
		"Channel Listing",
		filters={"item_code": ["in", get_product_item_codes(item)]},
		fields=["name", "item_code", "title", "price", "available_qty", "sync_status", "last_synced_at"],
		order_by="item_code asc",
	)


@frappe.whitelist(methods=["POST"])
def sync_product(name: str) -> str:
	frappe.has_permission("Channel Listing", "write", throw=True)
	listings = frappe.get_list(
		"Channel Listing", filters={"item_code": ["in", get_product_item_codes(name)]}, pluck="name"
	)
	if not listings:
		frappe.throw(_("{0} has no channel listings to sync.").format(name))

	frappe.db.set_value("Channel Listing", {"name": ["in", listings]}, "sync_status", "Pending")
	frappe.enqueue(
		"commera_channel_sync.listings.sync_product_listings",
		item_codes=listings,
		job_id=f"commera_channel_sync::{name}",
		deduplicate=True,
		enqueue_after_commit=True,
	)
	if len(listings) == 1:
		return _("Queued 1 listing for the channel.")
	return _("Queued {0} listings for the channel.").format(len(listings))


def get_product_item_codes(item: str) -> list[str]:
	return [item, *frappe.get_all("Item", filters={"variant_of": item}, pluck="name")]

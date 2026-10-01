import time

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from frappe.utils import flt, now_datetime

STYLE_ITEM = "CCS-TEE"
SIZE_ITEMS = {"S": "CCS-TEE-S", "M": "CCS-TEE-M", "L": "CCS-TEE-L"}
OFF_STORE_ITEM = "CCS-OFF-1"
ITEM_ATTRIBUTE = "CCS Colour"
CUSTOMER = "CCS Channel Shopper"
CUSTOMER_EMAIL = "ccs.channel.shopper@example.com"
APP = "commera_channel_sync"


def setup():
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	for item_code, is_stock_item in [
		(STYLE_ITEM, 0),
		*[(size_item, 1) for size_item in SIZE_ITEMS.values()],
		(OFF_STORE_ITEM, 1),
	]:
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.update(
				{
					"item_code": item_code,
					"item_name": item_code.replace("-", " ").title(),
					"item_group": item_group,
					"stock_uom": "Nos",
					"is_stock_item": is_stock_item,
					"valuation_rate": 100,
				}
			)
			item.insert()

	settings = frappe.get_cached_doc("Commera Settings")
	for item_code in SIZE_ITEMS.values():
		add_item_price(item_code, settings.default_price_list, 999)
	add_item_price(SIZE_ITEMS["M"], settings.sale_price_list, 799)

	if not frappe.db.exists("Item Attribute", ITEM_ATTRIBUTE):
		item_attribute = frappe.new_doc("Item Attribute")
		item_attribute.attribute_name = ITEM_ATTRIBUTE
		item_attribute.append("item_attribute_values", {"attribute_value": "Black", "abbr": "BLK"})
		item_attribute.insert()

	configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": STYLE_ITEM}, "name")
	if not configurator:
		configurator_doc = frappe.new_doc("Style Attribute Configurator")
		configurator_doc.update({"item_template": STYLE_ITEM, "item_attribute": ITEM_ATTRIBUTE})
		configurator_doc.insert()
		configurator = configurator_doc.name

	if not frappe.db.exists("Style Attribute Variant", {"configurator": configurator}):
		variant = frappe.new_doc("Style Attribute Variant")
		variant.update(
			{
				"configurator": configurator,
				"item_style": STYLE_ITEM,
				"attribute_value": "Black",
				"display_name": "CCS Tee",
				"is_published": 1,
				"images": [{"image": "/assets/frappe/images/frappe-framework-logo.svg"}],
				"sizes": [{"size": size, "item_code": item_code} for size, item_code in SIZE_ITEMS.items()],
			}
		)
		variant.insert()

	frappe.db.set_single_value("Channel Sync Settings", "fake_channel_down", 0)
	frappe.db.commit()
	print("company", company, "store warehouse", settings.ecommerce_warehouse)
	print("events for CCS items after setup:", count_events([*SIZE_ITEMS.values(), STYLE_ITEM]))


def add_item_price(item_code: str, price_list: str, rate: float):
	if frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		return
	item_price = frappe.new_doc("Item Price")
	item_price.update({"item_code": item_code, "price_list": price_list, "price_list_rate": rate})
	item_price.insert()


def s1_product_updated():
	started_at = now_datetime()
	item = frappe.get_doc("Item", SIZE_ITEMS["M"])
	item.item_name = f"CCS Tee M {started_at:%H%M%S}"
	item.save()
	off_store_item = frappe.get_doc("Item", OFF_STORE_ITEM)
	off_store_item.description = f"edited {started_at}"
	off_store_item.save()
	frappe.db.commit()

	listing, seconds = wait_for(
		lambda: frappe.db.get_value(
			"Channel Listing", SIZE_ITEMS["M"], ["title", "price", "price_list", "sync_status"], as_dict=True
		),
		lambda value: value and value.title == item.item_name and value.sync_status == "Synced",
	)
	print("storefront item listing", listing, "after", seconds, "s")
	print_events(SIZE_ITEMS["M"], started_at)
	time.sleep(5)
	print_events(OFF_STORE_ITEM, started_at)

	price_started_at = now_datetime()
	item_price = frappe.get_doc(
		"Item Price",
		{
			"item_code": SIZE_ITEMS["M"],
			"price_list": frappe.get_cached_doc("Commera Settings").sale_price_list,
		},
	)
	item_price.price_list_rate = flt(item_price.price_list_rate) + 1
	item_price.save()
	frappe.db.commit()
	time.sleep(5)
	print(
		"after Item Price edit to",
		item_price.price_list_rate,
		"events:",
		count_events([SIZE_ITEMS["M"]], price_started_at),
	)


def s2_store_receipt():
	started_at = now_datetime()
	stock_entry = make_stock_entry(list(SIZE_ITEMS.values()), get_store_warehouse(), 10)
	print("stock entry", stock_entry, "into", get_store_warehouse())
	wait_for(lambda: count_events(list(SIZE_ITEMS.values()), started_at), lambda value: value >= 3)
	time.sleep(5)
	for item_code in SIZE_ITEMS.values():
		print_events(item_code, started_at)
	wait_for(lambda: listing_statuses(), lambda value: all(row.sync_status == "Synced" for row in value))
	for row in listing_statuses():
		print("listing", row)


def s3_other_warehouse_receipt():
	started_at = now_datetime()
	warehouse = frappe.db.get_value(
		"Warehouse",
		{"is_group": 0, "name": ["!=", get_store_warehouse()], "warehouse_name": "Stores"},
		"name",
	)
	stock_entry = make_stock_entry([*SIZE_ITEMS.values(), OFF_STORE_ITEM], warehouse, 5)
	print("stock entry", stock_entry, "into", warehouse)
	time.sleep(10)
	print(
		"events since:",
		count_events([*SIZE_ITEMS.values(), OFF_STORE_ITEM], started_at),
		"(any inventory_changed on this site since:",
		frappe.db.count("Commera Event", {"event": "inventory_changed", "creation": [">=", started_at]}),
		")",
	)


def s4_cod_delivery():
	item_code = SIZE_ITEMS["M"]
	started_at = now_datetime()
	print("bin before", get_bin(item_code))
	sales_order_name = place_cod_order(item_code, 2)
	sales_order = frappe.get_doc("Sales Order", sales_order_name)
	sales_order.flags.ignore_permissions = True
	sales_order.submit()
	frappe.db.commit()
	time.sleep(5)
	print("order", sales_order_name, "submitted; bin", get_bin(item_code))
	print(
		"inventory events after SO submit (reservation):",
		count_events([item_code], started_at, "inventory_changed"),
	)

	delivery_started_at = now_datetime()
	delivery_note = make_delivery_note(sales_order_name)
	delivery_note.insert()
	delivery_note.submit()
	frappe.db.commit()
	print("delivery note", delivery_note.name, "bin", get_bin(item_code))
	wait_for(
		lambda: count_events([item_code], delivery_started_at, "inventory_changed"), lambda value: value >= 1
	)
	time.sleep(3)
	print_events(item_code, delivery_started_at)
	print(
		"listing",
		frappe.db.get_value(
			"Channel Listing", item_code, ["available_qty", "last_event_qty", "sync_status"], as_dict=True
		),
	)


def s5_outage(phase: str = "down"):
	item_code = SIZE_ITEMS["S"]
	if phase == "down":
		frappe.db.set_single_value("Channel Sync Settings", "fake_channel_down", 1)
		frappe.db.commit()
		started_at = now_datetime()
		print("started_at", started_at)
		make_stock_entry([item_code], get_store_warehouse(), 1)
		wait_for(lambda: my_deliveries(item_code, started_at), lambda value: value and value[0].attempts >= 1)
		make_stock_entry([item_code], get_store_warehouse(), 2)
		wait_for(lambda: count_events([item_code], started_at), lambda value: value >= 2)
		time.sleep(8)
		for row in my_deliveries(item_code, started_at):
			print(row)
		print(
			"listing",
			frappe.db.get_value("Channel Listing", item_code, ["available_qty", "sync_status"], as_dict=True),
		)
		print("bin", get_bin(item_code))
		return

	frappe.db.set_single_value("Channel Sync Settings", "fake_channel_down", 0)
	frappe.db.commit()
	since = frappe.utils.get_datetime(phase)
	rows, seconds = wait_for(
		lambda: my_deliveries(item_code, since),
		lambda value: value and all(row.status != "Queued" for row in value),
		timeout=420,
	)
	print("drained after", seconds, "s")
	for row in rows:
		print(row)
	print(
		"fake channel pushes:",
		frappe.get_all(
			"Fake Channel Request",
			filters={"item_code": item_code, "creation": [">=", since]},
			fields=["available_qty", "commera_event", "creation"],
			order_by="creation asc",
		),
	)
	print(
		"listing",
		frappe.db.get_value(
			"Channel Listing", item_code, ["available_qty", "last_event_qty", "sync_status"], as_dict=True
		),
	)
	print("bin", get_bin(item_code))


def s6_volume(moves: int = 20):
	item_code = SIZE_ITEMS["L"]
	started_at = now_datetime()
	error_logs_before = frappe.db.count("Error Log")
	for _ in range(int(moves)):
		make_stock_entry([item_code], get_store_warehouse(), 1)
	finished_at = now_datetime()
	print(
		moves,
		"stock entries in",
		round((finished_at - started_at).total_seconds(), 1),
		"s; bin",
		get_bin(item_code),
	)
	time.sleep(20)
	events = frappe.get_all(
		"Commera Event",
		filters={"reference_doctype": "Item", "reference_name": item_code, "creation": [">=", started_at]},
		fields=["name", "event", "data", "creation"],
		order_by="creation asc",
	)
	deliveries = frappe.get_all(
		"Commera Event Delivery",
		filters={"parent": ["in", [event.name for event in events] or [""]]},
		fields=["app", "status"],
	)
	pushes = frappe.db.count("Fake Channel Request", {"item_code": item_code, "creation": [">=", started_at]})
	print(
		"events", len(events), "deliveries", len(deliveries), "apps", sorted({row.app for row in deliveries})
	)
	print("event qtys", [frappe.parse_json(event.data).get("actual_qty") for event in events])
	print("fake channel pushes", pushes, "new error logs", frappe.db.count("Error Log") - error_logs_before)
	print(
		"listing",
		frappe.db.get_value(
			"Channel Listing", item_code, ["available_qty", "last_event_qty", "sync_status"], as_dict=True
		),
	)
	print(
		"commera events on site:",
		frappe.db.count("Commera Event"),
		"deliveries:",
		frappe.db.count("Commera Event Delivery"),
	)


def make_stock_entry(item_codes: list[str], warehouse: str, qty: float) -> str:
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.stock_entry_type = "Material Receipt"
	stock_entry.company = frappe.db.get_value("Warehouse", warehouse, "company")
	for item_code in item_codes:
		stock_entry.append(
			"items", {"item_code": item_code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 100}
		)
	stock_entry.insert()
	stock_entry.submit()
	frappe.db.commit()
	return stock_entry.name


def place_cod_order(item_code: str, qty: float) -> str:
	from commera.api.payments import place_cod_order as commera_place_cod_order

	customer, contact = get_shopper()
	settings = frappe.get_cached_doc("Commera Settings")
	company = frappe.db.get_value("Warehouse", settings.ecommerce_warehouse, "company")
	currency = frappe.get_cached_value("Company", company, "default_currency")
	quotation = frappe.new_doc("Quotation")
	quotation.update(
		{
			"quotation_to": "Customer",
			"party_name": customer,
			"company": company,
			"order_type": "Shopping Cart",
			"contact_person": contact,
			"contact_email": CUSTOMER_EMAIL,
			"currency": currency,
			"conversion_rate": 1,
			"selling_price_list": settings.default_price_list,
			"price_list_currency": currency,
			"plc_conversion_rate": 1,
			"items": [{"item_code": item_code, "qty": qty, "warehouse": settings.ecommerce_warehouse}],
		}
	)
	quotation.flags.ignore_permissions = True
	quotation.insert()
	sales_order = commera_place_cod_order(quotation.name)
	frappe.db.commit()
	return sales_order.name


def get_shopper() -> tuple[str, str]:
	if not frappe.db.exists("Customer", CUSTOMER):
		customer = frappe.new_doc("Customer")
		customer.update({"customer_name": CUSTOMER, "customer_type": "Individual"})
		customer.insert()
	contact = frappe.db.get_value("Contact", {"email_id": CUSTOMER_EMAIL}, "name")
	if not contact:
		contact_doc = frappe.new_doc("Contact")
		contact_doc.first_name = "CCS Shopper"
		contact_doc.append("email_ids", {"email_id": CUSTOMER_EMAIL, "is_primary": 1})
		contact_doc.append("links", {"link_doctype": "Customer", "link_name": CUSTOMER})
		contact_doc.insert()
		contact = contact_doc.name
	return CUSTOMER, contact


def get_store_warehouse() -> str:
	return frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")


def get_bin(item_code: str):
	return frappe.db.get_value(
		"Bin",
		{"item_code": item_code, "warehouse": get_store_warehouse()},
		["actual_qty", "reserved_qty"],
		as_dict=True,
	)


def count_events(item_codes: list[str], since=None, event: str | None = None) -> int:
	frappe.db.rollback()
	filters = {"reference_doctype": "Item", "reference_name": ["in", item_codes]}
	if since:
		filters["creation"] = [">=", since]
	if event:
		filters["event"] = event
	return frappe.db.count("Commera Event", filters)


def print_events(item_code: str, since):
	frappe.db.rollback()
	events = frappe.get_all(
		"Commera Event",
		filters={"reference_doctype": "Item", "reference_name": item_code, "creation": [">=", since]},
		fields=["name", "event", "data"],
		order_by="creation asc",
	)
	print(item_code, "events:", len(events))
	for event in events:
		deliveries = frappe.get_all(
			"Commera Event Delivery", filters={"parent": event.name}, fields=["app", "status", "attempts"]
		)
		print("  ", event.name, event.event, event.data and event.data.replace("\n", ""), deliveries)


def my_deliveries(item_code: str, since):
	frappe.db.rollback()
	event_names = frappe.get_all(
		"Commera Event",
		filters={"reference_doctype": "Item", "reference_name": item_code, "creation": [">=", since]},
		pluck="name",
	)
	if not event_names:
		return []
	deliveries = frappe.get_all(
		"Commera Event Delivery",
		filters={"parent": ["in", event_names], "app": APP},
		fields=["parent", "status", "attempts", "next_retry_at", "finished_at", "creation"],
		order_by="creation asc",
	)
	data_by_event = {
		event.name: frappe.parse_json(event.data).get("actual_qty")
		for event in frappe.get_all(
			"Commera Event", filters={"name": ["in", event_names]}, fields=["name", "data"]
		)
	}
	for delivery in deliveries:
		delivery.event_qty = data_by_event.get(delivery.parent)
	return deliveries


def listing_statuses():
	frappe.db.rollback()
	return frappe.get_all(
		"Channel Listing",
		filters={"item_code": ["in", list(SIZE_ITEMS.values())]},
		fields=["item_code", "price", "price_list", "available_qty", "last_event_qty", "sync_status"],
	)


def wait_for(read, is_done, timeout: int = 60):
	started = time.time()
	while time.time() - started < timeout:
		value = read()
		if is_done(value):
			return value, round(time.time() - started, 1)
		time.sleep(1)
		frappe.db.rollback()
	return read(), None

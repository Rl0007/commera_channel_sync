app_name = "commera_channel_sync"
app_title = "Commera Channel Sync"
app_publisher = "Rahul Agrawal"
app_description = "Keeps a marketplace channel's listings in step with the Commera storefront"
app_email = "12agrawalrahul@gmail.com"
app_license = "mit"

required_apps = ["commera"]

commera_api_version = [1]
commera_product_updated = ["commera_channel_sync.listings.on_product_updated"]
commera_inventory_changed = ["commera_channel_sync.listings.on_inventory_changed"]

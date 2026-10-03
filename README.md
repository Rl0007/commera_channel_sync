# Channel Sync

Keeps a marketplace channel's listings in step with the Commera storefront. An example app built on [Commera](https://github.com/bwhtech/commera).

## Install

```bash
bench get-app https://github.com/Rl0007/commera_channel_sync
bench --site <site> install-app commera_channel_sync
bench build --app commera_channel_sync
```

## What it adds

- **Channel sync** page under Apps in /commera, with listing counts.
- A listing card and a **Sync to channel now** action on each product.
- Keeps listings in step through Commera's `commera_product_updated` and `commera_inventory_changed` events, using `commera.sdk.catalog.get_items` for price and stock.

## License

MIT

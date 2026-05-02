# Product Size Stock Dataset

This folder stores size-level stock for existing catalog products.

## Files
- `product_size_stock.json`: generated stock index keyed by product URL.
- `mock_products_inventory.json`: rich mock inventory records used by backend seeding and sync.

## Inventory Schema (`mock_products_inventory.json`)
Each record contains:
- `id`: product identifier
- `name`: product name
- `brand`: derived from product URL domain
- `category`: product category
- `color`: primary color label
- `price`: numeric price value
- `style`: primary style tag
- `event`: inferred event context (for recommendation scenarios)
- `product_url`: canonical URL used as stock key
- `sizes`: list of `{ "size": string, "stock": number }`

Notes:
- Records are generated for all products loaded from the catalog dataset.
- Size stock is synchronized with `product_size_stock.json` during startup seeding and cart stock mutations.

## Behavior
- Only sizes with stock > 0 are exposed as `available_sizes` to clients.
- When an item is added to cart with a selected size, stock is decremented.
- If stock reaches 0, that size is no longer offered by the size picker.

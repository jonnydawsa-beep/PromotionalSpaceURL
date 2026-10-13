# Deal Burrow — public site

Static GitHub Pages site for the Product Opportunity Miner project.

## Publication model

The public site reads `deals.json`. The file is intentionally valid even when there are zero deals.

The miner/publisher should only write offers that have passed a separate publication gate. The website must not be used to turn raw screening candidates into public claims automatically.

## `deals.json` schema

```json
{
  "meta": {
    "schema_version": "1.0",
    "generated_at": "2026-10-07T10:00:00Z",
    "publication_mode": "VALIDATED_ONLY"
  },
  "deals": [
    {
      "deal_id": "uuid-or-stable-id",
      "publishable": true,
      "title": "Exact product title",
      "brand": "Brand",
      "category": "DIY & Tools",
      "retailer": "Retailer name",
      "current_price": 89.99,
      "comparison_price": 109.99,
      "saving_percent": 18.18,
      "price_basis": "ITEM_ONLY",
      "checked_at": "2026-10-07T10:00:00Z",
      "image_url": "https://...",
      "product_url": "https://...",
      "affiliate_url": "https://..."
    }
  ]
}
```

## GitHub Pages

Deploy from the repository root on the `main` branch.

## Safety / compliance

- Never commit miner `secrets.json`, Awin API tokens, SQLite databases, logs or raw feed dumps to this public repository.
- Affiliate links should use `rel="sponsored nofollow noopener"`.
- Do not claim an offer is the cheapest on the internet unless that is independently supported.
- Prices and stock can change; users must confirm them on the retailer site.

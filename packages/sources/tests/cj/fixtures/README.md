Handwritten synthetic payloads following CJ's public documentation, checked 2026-10-22.
No CJ API endpoint was called. Token strings and catalog identifiers are test-only values; `categories.json` uses the single real category ID from the public documentation example.

- `auth.json`, `refresh.json`: [authentication schema](https://developers.cjdropshipping.com/en/api/api2/api/auth.html), deliberately short expiry dates to exercise refresh with a fake clock.
- `list_v2.json`, `empty.json`: [listV2 schema](https://developers.cjdropshipping.com/en/api/api2/api/product.html), including nested `content[].productList[]`, USD price ranges and missing listing count.
- `errors.json`: [global codes](https://developers.cjdropshipping.com/en/api/api2/standard/ps-code.html), [IP limits](https://developers.cjdropshipping.com/en/api/start/limit.html), and [points exhaustion](https://developers.cjdropshipping.com/en/api/api2/standard/points.html). Each case includes its HTTP status separately from its response body.

- `categories.json`: the public `getCategory` example, retaining its exact Office category ID and names. It is not a complete tree and does not prove the ten seed mappings.
- `category_tree_synthetic.json`: entirely test-only names and IDs for parent expansion and overlap/deduplication; never a real CJ tree or seed mapping.

P1-08b adds fake HTTP/Redis and clock tests; no API request was made. Detail, stock and freight payloads are deferred to P1-08c.

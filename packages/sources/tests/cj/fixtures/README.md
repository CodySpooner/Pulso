Handwritten synthetic payloads following CJ's public documentation, checked 2026-10-22.
No CJ API endpoint was called. Token strings and catalog identifiers are test-only values; `categories.json` uses the single real category ID from the public documentation example.

- `auth.json`, `refresh.json`: [authentication schema](https://developers.cjdropshipping.com/en/api/api2/api/auth.html), deliberately short expiry dates to exercise refresh with a fake clock.
- `list_v2.json`, `empty.json`: [listV2 schema](https://developers.cjdropshipping.com/en/api/api2/api/product.html), including nested `content[].productList[]`, USD price ranges and missing listing count.
- `errors.json`: [global codes](https://developers.cjdropshipping.com/en/api/api2/standard/ps-code.html), [IP limits](https://developers.cjdropshipping.com/en/api/start/limit.html), and [points exhaustion](https://developers.cjdropshipping.com/en/api/api2/standard/points.html). Each case includes its HTTP status separately from its response body.

- `categories.json`: the public `getCategory` example, retaining its exact Office category ID and names. It is not a complete tree and does not prove the ten seed mappings.
- `category_tree_synthetic.json`: entirely test-only names and IDs for parent expansion and overlap/deduplication; never a real CJ tree or seed mapping.

P1-08b adds fake HTTP/Redis and clock tests; no API request was made.

P1-08c adds handwritten `detail.json`, `stock.json` and `freight.json`, following the public [product detail and product-ID inventory schemas](https://developers.cjdropshipping.com/en/api/api2/api/product.html) and [freight schema](https://developers.cjdropshipping.com/en/api/api2/api/logistic.html), checked 2026-10-23. All product/variant identifiers and carrier names are synthetic. The stock fixture distinguishes country totals from warehouse subtotals and includes unknown inventory; freight includes unknown delivery time. Tests use fake HTTP only, with the autouse network refusal retained.

P1-08d adds synthetic `pointsInfo` to auth/refresh/catalog/detail fixtures and inline unknown/exhausted/invalid balances, following the public [points schema and minute refill](https://developers.cjdropshipping.com/en/api/api2/standard/points.html), checked 2026-10-23. These are invented test balances, never account evidence. `import.csv` uses the existing shared CJ template with two variants, CN/US freight, an older observation date, and a SKU-only EUR row; no stock column or transaction evidence is fabricated.

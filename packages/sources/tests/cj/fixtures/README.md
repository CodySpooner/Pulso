Handwritten synthetic payloads following CJ's public documentation, checked 2026-10-22.
No CJ API endpoint was called. All identifiers and token strings are test-only values.

- `auth.json`, `refresh.json`: [authentication schema](https://developers.cjdropshipping.com/en/api/api2/api/auth.html), deliberately short expiry dates to exercise refresh with a fake clock.
- `list_v2.json`, `empty.json`: [listV2 schema](https://developers.cjdropshipping.com/en/api/api2/api/product.html), including nested `content[].productList[]`, USD price ranges and missing listing count.
- `errors.json`: [global codes](https://developers.cjdropshipping.com/en/api/api2/standard/ps-code.html), [IP limits](https://developers.cjdropshipping.com/en/api/start/limit.html), and [points exhaustion](https://developers.cjdropshipping.com/en/api/api2/standard/points.html). Each case includes its HTTP status separately from its response body.

Detail, stock, categories and freight payloads are deferred with P1-08b; this slice does not use those endpoints.

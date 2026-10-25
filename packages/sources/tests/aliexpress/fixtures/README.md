Handwritten synthetic payloads (the repo is public). No AliExpress endpoint was called; every ID, name, price and request ID is test-only.

Shapes follow the AliExpress Open Platform docs read 2026-10-25 (`docs/DATA_SOURCES.md`, AliExpress section):

- `product.json`: `aliexpress.ds.product.get` (doc 1790 and its response-in-JSON example). The `{"ae_item_sku_info_d_t_o": [...]}` list wrapper follows the doc's unsimplified screenshot and the freight example; the parser also accepts a bare list. The base `currency_code` is CNY while SKU prices are USD, as in the doc example.
- `freight.json`: `aliexpress.ds.freight.query` (doc 1597 successful response). `shipping_fee_cent` carries major units, as the doc example does ("172.71" for "US $172.71").
- `errors.json`:
  - `freight_unavailable`: the doc 1597 failed response (code 505).
  - `not_found`: product.get's documented 605 `ITEM_ID_NOT_FOUND`, placed in `rsp_code`/`rsp_msg` (the doc lists the code, not where it appears).
  - `throttled`: the documented message "Api access frequency exceeds the limit. this ban will last 1 seconds" (doc 1790 Common Issues). The code is invented: the docs do not name it.
  - `auth_rejected`, `backend_error`: the `error_response` {type, code, msg, request_id} envelope from the official Java SDK (`IopResponse`, `AeDefaultErrorField`); `SYSTEM` and `ISP` are the documented categories (doc 1372). Codes and messages are invented.

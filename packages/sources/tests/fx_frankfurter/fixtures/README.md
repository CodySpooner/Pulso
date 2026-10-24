# Frankfurter fixtures

Synthetic offline examples in the documented v2 flat-array shape; never fetched from a data endpoint.
Contract checked 2026-10-22: https://frankfurter.dev/ and https://frankfurter.dev/javascript/.
Re-checked 2026-10-24 (data-06): `/v2/rates` "returns a flat array, one row per quote"; rates are
blended across providers by default; NDJSON only when the `Accept` header asks for it (the adapter
sends `application/json`). No response schema is published for range requests.
Hand check: USD 1.23 × 150 JPY/USD = JPY 184.5 → 185 with ROUND_HALF_UP;
JPY 1500 ÷ 150 = USD 10.00 (1000 minor units); USD 1 × 0.3075 = KWD 0.3075 → 308 minor units.

`test_fx_run.py` builds its synthetic bodies inline and replays the first live run (2026-10-24 18:50Z)
through `execute_run`: a latest row dated 2026-10-25 (skipped, DEC-230), an object body
(`FxNotRateArray`), a duplicate pair/date (`FxDuplicateRow`), and NDJSON and an unsupported currency,
which record `JSONDecodeError` and `ValidationError` instead of `ValueError`.

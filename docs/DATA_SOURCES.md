# Pulso Data Sources

Canonical compliance record required by SPEC §4.2: for every data source, its access method, terms, limits, cost, status and phase. **Re-check a source's official docs and terms before building or changing its adapter, and update this file in the same PR.**

- Last full check: **2026-10-22** (terms and limits verified against primary sources in the research pass of that date; items marked *unverified* could not be confirmed).
- Market scope: **US only, USD** (owner decision, 2026-10-22).
- Collector host: the owner's Windows home PC runs all live collectors and schedules until Railway go-live (owner decision, 2026-10-22). Only that checkout sets `PULSO_SCHEDULER=on` / `COLLECTORS_LIVE=on`.
- Detailed design per source lives in the Obsidian vault: `C:\Users\Xody2\OneDrive\Desktop\Vaults\Pulso Vault\Data\Sources\`.
- Not legal advice.

**Status legend:** `enabled` = adapter live on the collector host · `planned` = approved for its phase, not built yet · `candidate` = allowed by our rules, waiting on an owner action or approval · `disabled` = blocked by a pending owner decision or by the source.

## Rules (summary of SPEC §4.2 plus agreed additions)

1. Prefer official APIs. Honest User-Agent naming Pulso with a contact URL. Respect robots.txt and rate limits.
2. No CAPTCHA solving, no scraping behind logins, no anti-bot evasion, no rotating/residential proxies, no forged request signatures.
3. Blocked = auto-disable + Data Health alert. Default block rule: 5 consecutive 429/430/403 responses, or a source-specific fatal code (listed per source). Never retry from a different IP.
4. Every source has a manual CSV import (a collector run with `trigger=csv`, parsed by the adapter's `parse_csv()`).
5. Sources whose terms forbid storage are live lookup only (Redis, 24 h TTL), never written to `raw_payloads`, snapshots or features. Today: AliExpress.
6. No vendor-scraped data (Apify, Bright Data, ScrapeCreators, etc.) without an explicit owner decision in `docs/DECISIONS.md`. Default until Phase 1 exit: official sources + CSV.
7. Never use the Shopify Storefront API or Global Catalog to collect or cache data; never probe `/cart*`.
8. Store no personal data we don't need (no reviewer names; advertisers as page/business identifiers only). Secrets only in `.env`; request params in `raw_payloads` are stored with secrets stripped.

## Overview

| Source | Key | Access | Status | Phase | Cost |
|---|---|---|---|---|---|
| Competitor Shopify stores | `shopify_stores` | Public storefront JSON (unauthenticated) | planned (enable after fixtures pass + risk acceptance copied to DECISIONS.md) | 1 | Free |
| CJ Dropshipping | `cj` | Official API 2.0, API key | planned (pending owner answer on 30-day transactions) | 1 | Free |
| Google Trends | `google_trends` | SerpApi free tier; official alpha if granted | planned | 1 | Free (≤ 250 searches/mo) |
| Frankfurter FX | `fx_frankfurter` | Official, keyless | planned | 1 | Free |
| AliExpress | `aliexpress` | Open Platform Affiliate + DS APIs (app approval) | planned, live-lookup only | 3 | Free ("temporarily") |
| Amazon | `amazon` | Manual CSV only (no usable official API) | planned (CSV); Creators API disabled (ineligible) | 3 | Free |
| Meta Ad Library | `meta_ad_library` | Graph API v26.0 `ads_archive` (EU/UK commercial only); CSV for US | planned | 8 (CSV optional earlier) | Free |
| TikTok Creative Center | `tiktok_cc` | Manual CSV only | planned (CSV); automation disabled | 8 | Free |
| Keepa | `keepa` | Official paid API | candidate (owner must approve cost) | later | ~€49/mo (unverified) |
| Google Merchant Best Sellers | `merchant_bestsellers` | Official Merchant API v1 | candidate | 1–3 if eligible | Free |
| Pinterest Trends | `pinterest_trends` | Official API v5, OAuth app | candidate | 1–3 if app created | Free |
| YouTube Data API v3 | `youtube` | Official, API key | candidate (backlog) | 5+ | Free |
| 17TRACK | `track17` | Official, key | candidate (backlog) | 7 | ~$119 / 5k numbers (unverified) |
| TikTok Shop vendor data | `tiktok_shop` | Vendor scrape | disabled (owner decision on vendor data pending) | revisit at Phase 1 exit | $0.75–7 / 1k records |
| DataForSEO / SerpApi paid | `dataforseo` | Paid API vendors | candidate (owner must approve cost) | 1–4 | pay as you go |
| Store Leads | `store_leads` | Paid API | candidate (owner must approve cost) | 3+ | $75–250/mo |

---

## Competitor Shopify stores (`shopify_stores`)

- **Access:** `GET /meta.json`, `/products.json?limit=250&page=N` with `If-None-Match`, `/products/<handle>.js` for tracked products, `/robots.txt`. No auth. Headless and password-protected stores return 403/404 and are marked untrackable. Web Bot Auth signing deferred.
- **Never:** `/cart*`, `/search`, `sort_by` collection pages, `/recommendations/products`, Storefront GraphQL, Global Catalog MCP.
- **Terms (checked 2026-10-22):**
  - Default robots.txt does not disallow the JSON catalog endpoints.
  - Shopify Terms of Service §1 item 9 (updated 2026-10-20) bans accessing or monitoring the Services with robots/scrapers; may bind the owner as a merchant — https://www.shopify.com/legal/terms
  - API License & Terms (updated 2026-10-07) §2.3.4, §2.3.8, §2.3.14, §2.3.24 (no AI/ML training on data derived from any merchant store), §6.2.5 apply to API use; relevant once a Pulso Shopify app exists (Phase 7) — https://www.shopify.com/legal/api-terms
  - Bot changelog (published 2026-05-07, effective 2026-05-30): unsigned bots get the strictest limits — https://shopify.dev/changelog/bots-and-agents-should-identify-themselves-via-web-bot-auth
  - Since 2026-09-29 cloud IPs report 429 (`retry-after: 60`) on the first request even when signed; staff: a signature is "necessary but not sufficient" without registration.
- **Owner risk acceptance (2026-10-22):** the owner accepts the ToS risk; strict §4.2 behaviour; runs from the home-PC collector host (residential IP). Moving this collector to a different network *because* of a block requires a new owner decision. Recorded in DECISIONS.md as DEC-003 (approved 2026-10-22).
- **Limits:** none published. Our budget: ≤ 30 requests/min total across all stores, sequential, honour `retry-after`, no IP changes.
- **Block rule:** 1 × 430 → disable; 5 consecutive 429 → disable. 403/404 on one store → that store only.
- **Availability pre-check (2026-10-22, not the DEC-003 spike):** one `/meta.json` per candidate store from the home PC, 2 s apart: 37/46 returned 200 JSON, 1 returned 403 (inspireuplift.com), rest dead/headless. No 429s. The `/products.json` spike that gates enabling (DEC-003, Phase 0 SPK-2) has not run yet.
- **Count semantics:** Grade A = `.js` `inventory_quantity` deltas where `inventory_management=shopify` and `inventory_policy=deny` (undocumented field, may disappear); Grade B = `updated_at` bump counts (lower bound on order events); availability flips. Store count is a Saturation input, not demand. Features prefixed `shp_`.
- **Cost:** free. **Status:** planned. **Phase:** 1.

## CJ Dropshipping (`cj`)

- **Access:** API 2.0, base `https://developers.cjdropshipping.com/api2.0/v1`. Key from CJ App Store → My CJ → API → Add API (no review). `POST /authentication/getAccessToken {apiKey}` (1 call/s), header `CJ-Access-Token`; token expiry read from the response (docs: 180 days; older docs: 15).
- **Endpoints used:** `/product/getCategory`, `/product/listV2` (max 6,000 results/query; size ≤ 100), `/product/query`, variant/stock queries, `/logistic/freightCalculate` (US only), product reviews (Phase 5).
- **Terms (checked 2026-10-22):** official API for dropshippers; low risk — https://developers.cjdropshipping.com/en/api/api2/api/auth.html · https://developers.cjdropshipping.com/en/api/start/limit.html · https://developers.cjdropshipping.com/en/api/api2/standard/points.html
- **Limits:** 10 req/s per IP; per user 1/2/4/6 req/s by account level; max 3 CJ users per IP. 50,000 base points/day (reset 00:00 UTC, refilled per minute), +100 points per $1 of highest monthly transaction (last 3 months). Costs: listV2 50; query/variant/stock/freight 10; image search 1,000 (Level 3+); unlisted endpoints 0.
- **Inactivity:** 30 consecutive days with zero transaction amount → API disabled (error `1600014`); reactivation is manual in My CJ. **Owner question pending:** does the account place a real order every 30 days?
- **Block rule / error mapping:** `1600014` → disable; `one ip limit 3 users` → disable; 429 "Insufficient API points" → quota (run partial, not a block); 429 rate limit → back off, counts toward block rule.
- **Count semantics:** `listedNum` = number of CJ users who listed the product (adoption, not orders) → `listing_snapshots.listed_count`; stock is an inventory level per warehouse (summed). Features prefixed `cj_`. Unproven as demand.
- **Planned spend:** ≈ 11,000 points/day (guess) of 50,000.
- **Cost:** free. **Status:** planned. **Phase:** 1.

## Google Trends (`google_trends`)

- **Access:** SerpApi `engine=google_trends`, `geo=US`, `tz=0`, one keyword per search, `date=today 3-m` weekly and `today 5-y` once per keyword. Official Trends API alpha by application (owner to apply). DataForSEO only with owner approval.
- **Excluded:** pytrends (archived 2025-04-17; returns 429/404) and any direct scraping (Google terms prohibit automated access).
- **Terms (checked 2026-10-22):** official alpha "can't open the API for everyone yet" — https://developers.google.com/search/apis/trends · SerpApi Trends engine — https://serpapi.com/google-trends-api · pricing — https://serpapi.com/pricing. SerpApi performs the scraping; Google's litigation against SerpApi is ongoing (impact unknown).
- **Limits:** SerpApi free tier 250 searches/month (paid from $25/1k). Plan: 50 keywords weekly ≈ 217 searches/month.
- **Block rule:** 401 → disable; monthly cap reached → quota (pause until next month).
- **Count semantics:** relative index 0–100 rescaled **per request**; last point partial. Every capture is appended in full to `search_trends`; slopes only within one capture. Features prefixed `gt_`.
- **Cost:** free at planned volume. **Status:** planned. **Phase:** 1.

## Frankfurter FX (`fx_frankfurter`)

- **Access:** `GET https://api.frankfurter.dev/v2/rates?base=USD&from=<last+1>&to=<today>` once a day (self-fills gaps). No key.
- **Terms (checked 2026-10-22):** blended rates free for commercial use; provider-specific endpoints follow provider terms (not used) — https://frankfurter.dev/
- **Limits:** no quotas; abuse rate limits only.
- **Use:** `fx_rates(date, base, quote, rate, source)`; convert at the rate for the observation's UTC date (latest earlier date on weekends/holidays).
- **Cost:** free. **Status:** planned. **Phase:** 1.

## AliExpress (`aliexpress`)

- **Access:** Open Platform app (review ~2 business days; may need business licence/ID) + AliExpress Portals affiliate application. Affiliate API (`aliexpress.affiliate.hotproduct.query` etc.) and DS API (`aliexpress.ds.product.get`, `ds.image.searchV2`, `ds.freight.query`); OAuth 2.0 for DS; gateway `https://api-sg.aliexpress.com/sync`.
- **Terms (checked 2026-10-22):** API Use Agreement (2022-01-25) — https://terms.alicdn.com/legal-agreement/terms/suit_bu1_aliexpress/suit_bu1_aliexpress202201220006_10755.html
  - §7.6/§9.2: no storing platform operation data without prior written approval.
  - §7.3.2: no resale/redistribution. §7.5.4: user data only in the collecting app. §7.10: no AliExpress/Alibaba marks in our name/URL.
  - §6.5 unilateral suspension; §11.1 termination without notice. §6.1 "temporarily free of charge".
- **Design consequence:** live lookup only, Redis 24 h TTL, on demand from the UI; nothing written to `raw_payloads`, snapshots or features until AliExpress approves storage in writing (owner to ask during application).
- **Limits:** unpublished (third-party: 5,000/day; 500/day for new apps — unverified). Our cap: 500 calls/day.
- **Count semantics:** `lastest_volume` (window unverified, reportedly 30 days), `sales_count` — not storable today, so no AliExpress demand history.
- **Cost:** free. **Status:** planned (live-only). **Phase:** 3.

## Amazon (`amazon`)

- **Access:** manual CSV import (`asin, title, url, category, rank, rank_kind, price, currency, rating, review_count, observed_on`).
- **Terms / official routes (checked 2026-10-22):**
  - PA-API 5.0: retired, returns HTTP 403 `AccessDeniedException` — https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation
  - Creators API: requires Associates enrollment and ≥ 10 qualifying sales in the past 30 days; 1 TPS / 8,640 TPD to start; affiliate-data use for research is against program intent → **disabled** — https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction
  - Conditions of Use exclude data mining/robots; direct scraping excluded (a direct request returned a CAPTCHA on 2026-10-22).
  - Vendor scraper (Apify `junglee/amazon-bestsellers`, from $3.20/1k): disabled pending vendor-data decision.
- **Count semantics:** ranks (BSR per category, Movers & Shakers 24 h gain), not counts; review count cumulative. Features prefixed `amz_`.
- **Cost:** free (CSV). **Status:** planned (CSV). **Phase:** 3.

## Meta Ad Library (`meta_ad_library`)

- **Access:** Graph API v26.0 `/ads_archive`; identity confirmation at facebook.com/ID + developer app; token ~60 days.
- **Terms (checked 2026-10-22):** ads that did not reach the EU return only if political/issue — so **US commercial ads are not available via the API** — https://developers.facebook.com/docs/graph-api/reference/ads_archive/ . Commercial ads never include spend or impressions. Never scrape logged in.
- **US route:** manual CSV (`library_id, page_name, page_id, start_date, active, platforms, landing_url, creative_url, text, observed_on`); vendor scraper (Apify `apify/facebook-ads-scraper`, $3.40–5.80/1k) disabled pending vendor-data decision.
- **Limits:** unpublished (error 613); ~200 calls/hour per secondary sources (unconfirmed).
- **Count semantics:** distinct active ads/advertisers; ad age from delivery start (rebuildable); ad-count growth not rebuildable. Features prefixed `meta_`. Until ad data exists, score components get weight 0 and the UI says "no source yet".
- **Cost:** free. **Status:** planned. **Phase:** 8 (CSV optional earlier).

## TikTok Creative Center (`tiktok_cc`)

- **Access:** manual CSV of Top Ads and hashtag Trends. Top Products is **likely retired** (help article and page redirected, old path 404 on 2026-10-22). Internal API rejects unsigned calls (`40101 no permission`); forging signatures is prohibited.
- **Terms (checked 2026-10-22):** TikTok US Terms of Service §3.4 (updated 2026-07-15) ban automated extraction without written approval — https://www.tiktok.com/legal/page/us/terms-of-service/en . TikTok Research API excludes commercial users. Official EU-only Commercial Content API exists (`POST https://open.tiktokapis.com/v2/research/adlib/ad/query/`, 10 results/call) — low value for a US-only product.
- **Vendor route:** Apify `datapeak/tiktok-creative-center` ($1.50/1k ads, $1/1k trends) disabled pending vendor-data decision.
- **Count semantics:** CTR score 0–1 and spend tier 0–5 are relative; hashtag rank ordinal within 7/30-day windows. Features prefixed `ttcc_`.
- **Cost:** free (CSV). **Status:** planned (CSV); automation disabled. **Phase:** 8.

## Keepa (`keepa`)

- **Access:** paid official API, key; `domain=1` (amazon.com).
- **Terms (checked 2026-10-22):** token costs official — product 1/ASIN (+6 per offers page), search 10/page, deals 5/150, best-seller list 50; unused tokens expire after 60 min — https://keepa.com/api-docs/plans-tokens.html . Prices not on Keepa's docs; ~€49/mo for 20 tokens/min (third-party, unverified). Redistribution terms unverified → internal use only.
- **Count semantics:** BSR, price and review-count history (not rescaled; backfilled points carry past `observed_for`). Features prefixed `kp_`.
- **Status:** candidate — SPEC §4.3 #8 requires owner approval before enabling. **Phase:** later.

## Candidates (no adapter yet)

| Source | Access / terms (checked 2026-10-22) | Limits / cost | Status |
|---|---|---|---|
| Google Merchant API Best Sellers | `accounts.reports.search` on Merchant API v1; Merchant Center must meet undefined eligibility; Content API sunset 2026-08-18 — https://developers.google.com/merchant/api/guides/reports/understand-the-market | weekly, today-only; free | candidate (if eligible) |
| Pinterest Trends API | `GET /v5/trends/keywords/{region}/top/{trend_type}`, top 50, today only; Standard tier needs a video demo — https://developers.pinterest.com/docs/analytics-and-reports/trends/ | numeric limits unverified; free | candidate (if app created) |
| YouTube Data API v3 | 10,000 units/day; `search.list` 100 calls/day; stored data refreshed or deleted within 30 days — https://developers.google.com/youtube/v3/determine_quota_cost | free | candidate (backlog) |
| 17TRACK | API v2.4, 40 numbers/request, 3 req/s, webhooks; free 100/mo ended 2026-01-07 — https://api.17track.net/en/doc?version=v2.4 | ~$119 per 5k numbers (unverified) | candidate (backlog) |
| TikTok Shop vendor data | Apify / Bright Data / ScrapeCreators / EchoTik scrape logged-out product pages; TikTok US ToS §3.4 risk | $0.75–7 per 1k records | **disabled** (vendor-data decision) |
| DataForSEO | Trends $0.0027/task Standard (5 keywords), $0.011 Live; Merchant/Shopping $0.001–0.002/item — https://dataforseo.com/pricing/keywords-data/google-trends | pay as you go | candidate (cost approval) |
| SerpApi paid plans | $25/1k … $725/100k; Shopping, Ads Transparency engines — https://serpapi.com/pricing | per search | candidate (cost approval) |
| Store Leads | 3.16M Shopify stores, weekly; API from Pro — https://storeleads.app/ | Premium $75/mo (no API), Pro $250/mo | candidate (cost approval) |

## Excluded

| Source | Reason |
|---|---|
| pytrends / direct Google Trends scraping | archived 2025-04-17; Google terms prohibit automated access |
| TikTok Research API | commercial users ineligible (official FAQ) |
| TikTok Creative Center internal API | requires forged signatures |
| Amazon PA-API 5.0 | retired (403) |
| Shopify Storefront API / Global Catalog MCP (for collection) | API Terms §2.3.14, §2.3.4, §6.2.5; Global Catalog bans caching |
| Shopify `/cart*` probes | robots.txt disallows `/cart` |
| Temu | no research API; scrape-only, high risk |
| Spocket | no public API (developers.spocket.co NXDOMAIN, 2026-10-22) |
| DSers | developer program is for supplier/channel apps, not data |
| 1688 | requires Chinese company verification |
| Reddit API | approval for every new token since 2025-11-11; commercial use needs a contract |
| Residential/rotating proxies | §4.2 |

## Change log

- 2026-10-22 — file created from the verified research pass and spec review; owner decisions recorded (US only; home-PC collector host; Shopify ToS risk accepted). Seed lists drafted for approval (vault: `Data/Seed Lists.md`).

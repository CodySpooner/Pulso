# Pulso Data Sources

Canonical compliance record required by SPEC §4.2: for every data source, its access method, terms, limits, cost, status and phase. **Re-check a source's official docs and terms before building or changing its adapter, and update this file in the same PR.**

- Last full check: **2026-10-22** (terms and limits verified against primary sources in the research pass of that date; items marked *unverified* could not be confirmed).
- Market scope: **US only, USD** (owner decision, 2026-10-22).
- Collector host: the owner's Windows home PC runs all live collectors and schedules until Railway go-live (owner decision, 2026-10-22). Only that checkout sets `PULSO_SCHEDULER=on` / `COLLECTORS_LIVE=on`.
- Detailed design per source lives in the Obsidian vault: `C:\Users\Xody2\OneDrive\Desktop\Vaults\Pulso Vault\Data\Sources\`.
- DOC-3 evidence: source notes above and `Data/Candidate Sources.md`, then vault research **SI** = `Research/Store Intelligence.md`, **SF** = `Research/Supplier & Fulfillment Data Sources.md`, **TA** = `Research/Trend & Ad Intelligence Sources.md`. Public docs were read only for gaps, marked **checked 2026-10-22**; no data endpoints were called. *Unverified* means evidence is missing, not permission or an unlimited quota.
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

- **Access:** `GET /meta.json`, `/products.json?limit=250&page=N` with `If-None-Match`, `/products/<handle>.js` for tracked products, `/robots.txt`. No auth. Headless and password-protected stores return 403/404 and are marked untrackable. Web Bot Auth signing deferred. Manual CSV / URL-paste fallback (same request limits).
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
- **SPK-2 spike command (DEC-073, DEC-077; not run yet):** the lead runs it exactly once, from `C:\dev\pulso` only, after every precondition in the vault Lead Playbook §6 step 2 holds. The script refuses linked worktrees. PowerShell 5.1:

  ```powershell
  Set-Location C:\dev\pulso
  $env:PULSO_BOT_CONTACT = 'https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md'
  uv run python infra/scripts/spikes/shopify_probe.py sageandsill.com meowingtons.com thecloudies.com bleame.com --max-requests 20 --out C:/Users/Xody2/orca/workspaces/pulso/spike-SPK-2.md
  ```

  - **Budget:** at most 20 requests in the whole run. That covers robots.txt, `/products.json?limit=1`, one conditional repeat of it, `/meta.json` and one `/products/<handle>.js`: 5 per fully probed store, so the four stores fit exactly. Redirects count as requests and are never followed. Requests are at least 3 s apart (≤ 20/min). The cap must be between 1 and 50.
  - **Stopping:** the first 429, 430 or 403 stops the whole run with no retry. The remaining stores are recorded as not reached.
  - **Report:** the header records the requests used out of the budget, the stores reached, the stop reason and any stores not reached. The table rows are the observations. If the `--out` directory is missing, the run is refused before any request is sent.
  - The results table goes into this section and into the vault note `Source - Shopify Stores`; SPK-3's go/no-go is a separate proposed DEC. Public bot page: [`docs/BOT.md`](BOT.md).
- **Count semantics:** Grade A = `.js` `inventory_quantity` deltas where `inventory_management=shopify` and `inventory_policy=deny` (undocumented field, may disappear); Grade B = `updated_at` bump counts (lower bound on order events); availability flips. Store count is a Saturation input, not demand. Features prefixed `shp_`.
- **Risk:** merchant-account ToS exposure (DEC-003), cloud-IP blocking and undocumented inventory fields disappearing; no key expiry. Evidence: `Source - Shopify Stores`, SI §2–3.
- **Cost:** free public endpoints / CSV; no paid access tier. **Status:** planned. **Phase:** 1.

## CJ Dropshipping (`cj`)

- **Access:** API 2.0, base `https://developers.cjdropshipping.com/api2.0/v1`. Key from CJ App Store → My CJ → API → Add API (no review). `POST /authentication/getAccessToken {apiKey}` (1 call/s), header `CJ-Access-Token`; token expiry read from the response (docs: 180 days; older docs: 15). Manual supplier/stock/freight CSV fallback, including while DEC-009 is pending.
- **Endpoints used:** `/product/getCategory`, `/product/listV2` (max 6,000 results/query; size ≤ 100), `/product/query`, variant/stock queries, `/logistic/freightCalculate` (US only), product reviews (Phase 5).
- **Terms (checked 2026-10-22):** official API for dropshippers; the points policy's inactivity clause revokes access after 30 days without transactions, requiring manual reactivation — https://developers.cjdropshipping.com/en/api/api2/standard/points.html · auth / token validity — https://developers.cjdropshipping.com/en/api/api2/api/auth.html · IP/user restrictions — https://developers.cjdropshipping.com/en/api/start/limit.html
- **Limits:** 10 req/s per IP; per user 1/2/4/6 req/s by account level; max 3 CJ users per IP. 50,000 base points/day (reset 00:00 UTC, refilled per minute), +100 points per $1 of highest monthly transaction (last 3 months). Costs: listV2 50; query/variant/stock/freight 10; image search 1,000 (Level 3+); unlisted endpoints 0.
- **Inactivity:** 30 consecutive days with zero transaction amount → API disabled (error `1600014`); reactivation is manual in My CJ. **Owner question pending:** does the account place a real order every 30 days?
- **Block rule / error mapping:** `1600014` → disable; `one ip limit 3 users` → disable; 429 "Insufficient API points" → quota (run partial, not a block); 429 rate limit → back off, counts toward block rule.
- **Count semantics:** `listedNum` = number of CJ users who listed the product (adoption, not orders) → `listing_snapshots.listed_count`; stock is an inventory level per warehouse (summed). Features prefixed `cj_`. Unproven as demand.
- **Planned spend:** ≈ 11,000 points/day (guess) of 50,000.
- **Risk:** inactivity suspension, expiring tokens and the three-users-per-IP rule; refresh once on expiry, then fail the run. Evidence: `Source - CJ Dropshipping`, SF §2; DEC-009/035.
- **Cost:** free API and CSV; no separately priced API tier documented in SF §2 (higher quotas depend on account level / transactions). **Status:** planned. **Phase:** 1.

## Google Trends (`google_trends`)

- **Access:** SerpApi vendor API `engine=google_trends`, `geo=US`, `tz=0`, one keyword per search, `date=today 3-m` weekly and `today 5-y` once per keyword. Official Trends API alpha by application (owner to apply). DataForSEO only with owner approval. Manual Trends CSV fallback.
- **Excluded:** pytrends (archived 2025-04-17; returns 429/404) and any direct scraping (Google terms prohibit automated access).
- **Terms (checked 2026-10-22):** official alpha "can't open the API for everyone yet" — https://developers.google.com/search/apis/trends · SerpApi Trends engine — https://serpapi.com/google-trends-api · pricing — https://serpapi.com/pricing. SerpApi performs the scraping; Google's litigation against SerpApi is ongoing (impact unknown).
- **Vendor terms (checked 2026-10-22):** SerpApi §1/§12 prohibit unauthorized use and infringement; §16 permits termination without notice; §13 excludes Free, Starter and Developer plans from its Legal Shield — https://serpapi.com/legal . Buying API access does not grant source-data rights.
- **Limits:** SerpApi free tier 250 searches/month (paid from $25/1k). Plan: 50 keywords weekly ≈ 217 searches/month.
- **Block rule:** 401 → disable; monthly cap reached → quota (pause until next month).
- **Count semantics:** relative index 0–100 rescaled **per request**; last point partial. Every capture is appended in full to `search_trends`; slopes only within one capture. Features prefixed `gt_`.
- **Risk:** API-key rejection, quota exhaustion or vendor withdrawal/litigation can stop Trends; official alpha admission is not guaranteed. Evidence: `Source - Google Trends`, TA §2.7.
- **Cost:** free at ≤250 searches/month; first paid SerpApi tier $25/month for 1,000 (owner approval). Official alpha quotas and free/paid pricing are unpublished in TA §2.7. **Status:** planned. **Phase:** 1.

## Frankfurter FX (`fx_frankfurter`)

- **Access:** `GET https://api.frankfurter.dev/v2/rates?base=USD&from=<last+1>&to=<today>` once a day (self-fills gaps). No key. Manual FX CSV fallback.
- **Terms (checked 2026-10-22):** blended rates free for commercial use; provider-specific endpoints follow provider terms (not used) — https://frankfurter.dev/
- **Limits:** no quotas; abuse rate limits only.
- **Use:** `fx_rates(date, base, quote, rate, source)`; convert at the rate for the observation's UTC date (latest earlier date on weekends/holidays).
- **Risk:** low for blended rates; provider-specific terms differ, outages can delay rates, and abuse blocking still follows the default block rule. No key expiry. Evidence: `Source - Frankfurter FX`, SF §13.
- **Cost:** free; no paid tier documented for this keyless service. **Status:** planned. **Phase:** 1.

## AliExpress (`aliexpress`)

- **Access:** Open Platform app (review ~2 business days; may need business licence/ID) + AliExpress Portals affiliate application. Affiliate API (`aliexpress.affiliate.hotproduct.query` etc.) and DS API (`aliexpress.ds.product.get`, `ds.image.searchV2`, `ds.freight.query`); OAuth 2.0 for DS; gateway `https://api-sg.aliexpress.com/sync`.
- **Terms (checked 2026-10-22):** API Use Agreement (2022-01-25) — https://terms.alicdn.com/legal-agreement/terms/suit_bu1_aliexpress/suit_bu1_aliexpress202201220006_10755.html
  - §7.6/§9.2: no storing platform operation data without prior written approval.
  - §7.3.2: no resale/redistribution. §7.5.4: user data only in the collecting app. §7.10: no AliExpress/Alibaba marks in our name/URL.
  - §6.5 unilateral suspension; §11.1 termination without notice. §6.1 "temporarily free of charge".
- **Design consequence:** live lookup only, Redis 24 h TTL, on demand from the UI; nothing written to `raw_payloads`, snapshots or features until AliExpress approves storage in writing (owner to ask during application).
- **CSV fallback:** parse transiently into the same ≤24 h Redis cache; no raw file/object or durable market rows, including owner-entered quotes (`Source - AliExpress` R-17; DEC-037).
- **Limits:** unpublished (third-party: 5,000/day; 500/day for new apps — unverified). Our cap: 500 calls/day.
- **Count semantics:** `lastest_volume` (window unverified, reportedly 30 days), `sales_count` — not storable today, so no AliExpress demand history.
- **Risk:** app review / OAuth revocation, frequency bans and unilateral suspension; storage permission remains unresolved. Evidence: `Source - AliExpress`, SF §1.
- **Cost:** temporarily free (§6.1); first paid tier not published, charges may be introduced on notice. **Status:** planned (live-only). **Phase:** 3.

## Amazon (`amazon`)

- **Access:** manual CSV import (`asin, title, url, category, rank, rank_kind, price, currency, rating, review_count, observed_on`).
- **Terms / official routes (checked 2026-10-22):**
  - PA-API 5.0: retired, returns HTTP 403 `AccessDeniedException` — https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation
  - Creators API: requires Associates enrollment and ≥ 10 qualifying sales in the past 30 days; 1 TPS / 8,640 TPD to start; affiliate-data use for research is against program intent → **disabled** — https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction . Free Associates enrollment; no paid API tier documented — https://affiliate-program.amazon.com/creatorsapi/docs/en-us/onboarding (checked 2026-10-22). Access can lapse after 30 days without qualifying sales (`Source - Amazon`); CSV remains the fallback.
  - Conditions of Use exclude data mining/robots; direct scraping excluded (the earlier research request returned a CAPTCHA on 2026-10-22) — https://relay.amazon.com/terms (TA §2.11).
  - Vendor scraper: [Apify `junglee/amazon-bestsellers`](https://apify.com/junglee/amazon-bestsellers), API/feed or CSV export, from $3.20/1k; shared Apify free/paid tiers below. Source throughput unverified (listing checked 2026-10-22); Amazon's extraction restriction still matters. Risk: CAPTCHA/blocking and vendor failure; **disabled** pending DEC-010, manual CSV fallback.
- **Limits:** manual CSV has no source API quota; disabled Creators API limits above are not a CSV limit.
- **Count semantics:** ranks (BSR per category, Movers & Shakers 24 h gain), not counts; review count cumulative. Features prefixed `amz_`.
- **Risk:** no key for CSV; obtain data lawfully, since CSV is not an exemption from source terms. Official affiliate eligibility and direct-scrape blocking prevent an automated route today. Evidence: `Source - Amazon`, TA §2.11 / SF §8.
- **Cost:** free CSV, no paid CSV tier; optional paid Keepa is separate below. **Status:** planned (CSV). **Phase:** 3.

## Meta Ad Library (`meta_ad_library`)

- **Access:** Graph API v26.0 `/ads_archive`; identity confirmation at facebook.com/ID + developer app; token ~60 days.
- **Terms (checked 2026-10-22):** ads that did not reach the EU return only if political/issue — so **US commercial ads are not available via the API** — https://developers.facebook.com/docs/graph-api/reference/ads_archive/ . Commercial ads never include spend or impressions. Never scrape logged in.
- **US route:** manual CSV (`library_id, page_name, page_id, start_date, active, platforms, landing_url, creative_url, text, observed_on`); [Apify `apify/facebook-ads-scraper`](https://apify.com/apify/facebook-ads-scraper) vendor API/feed or CSV export, $3.40–5.80/1k (TA §2.5), shared Apify tiers below, **disabled** pending DEC-010. Source throughput unverified (listing checked 2026-10-22). Vendor risk: blocking and changing UI; current [automated-collection terms](https://www.facebook.com/legal/automated_data_collection_terms) redirected to login/block on public check 2026-10-22, so the applicable permission clause remains unverified, not cleared by vendor availability.
- **Limits:** unpublished (error 613); ~200 calls/hour per secondary sources (unconfirmed).
- **Count semantics:** distinct active ads/advertisers; ad age from delivery start (rebuildable); ad-count growth not rebuildable. Features prefixed `meta_`. Until ad data exists, score components get weight 0 and the UI says "no source yet".
- **Risk:** US commercial coverage absent; token expiry (~60 days) / code 190 disables API access until refreshed, and code 613 signals throttling. Evidence: `Source - Meta Ad Library`, TA §2.5.
- **Cost:** free official API and CSV; no paid official API tier documented (vendor prices above). **Status:** planned. **Phase:** 8 (CSV optional earlier).

## TikTok Creative Center (`tiktok_cc`)

- **Access:** manual CSV of Top Ads and hashtag Trends. Top Products is **likely retired** (help article and page redirected, old path 404 on 2026-10-22). Internal API rejects unsigned calls (`40101 no permission`); forging signatures is prohibited.
- **Terms (checked 2026-10-22):** TikTok US Terms of Service §3.4 (updated 2026-07-15) ban automated extraction without written approval — https://www.tiktok.com/legal/page/us/terms-of-service/en . TikTok Research API excludes commercial users. Official EU-only Commercial Content API exists (`POST https://open.tiktokapis.com/v2/research/adlib/ad/query/`, 10 results/call) — low value for a US-only product.
- **Vendor route:** [Apify `datapeak/tiktok-creative-center`](https://apify.com/datapeak/tiktok-creative-center), vendor API/feed or CSV export ($1.50/1k ads, $1/1k trends; shared Apify tiers below), **disabled** pending DEC-010. Source throughput unverified (listing checked 2026-10-22). TikTok §3.4 still applies; signing workarounds and page changes carry blocking/ToS risk. Manual CSV remains the fallback.
- **Limits:** no API quota for manual CSV. The official Commercial Content alternative is application-gated, EU-only, 10 results/call; request-rate quota unpublished (TA §2.3), free with no paid tier documented. [Product page](https://developers.tiktok.com/products/commercial-content-api) frames access for the public/researchers; commercial-use permission remains unverified, so application rejection / terms are risks, not a US-data workaround.
- **Count semantics:** CTR score 0–1 and spend tier 0–5 are relative; hashtag rank ordinal within 7/30-day windows. Features prefixed `ttcc_`.
- **Risk:** automation violates the cited extraction clause without written approval; internal signing, retired Top Products and moving pages make it fragile. No key expiry for CSV. Evidence: `Source - TikTok Creative Center`, TA §2.1–4.
- **Cost:** free CSV, no paid CSV tier (vendor prices above). **Status:** planned (CSV); automation disabled. **Phase:** 8.

## Keepa (`keepa`)

- **Access:** paid official API, key; `domain=1` (amazon.com). Manual CSV fallback.
- **Terms (checked 2026-10-22):** the How Plans Work clause bills monthly in advance and renews until cancelled — https://keepa.com/api-docs/plans-tokens.html . Redistribution permission remains unverified; existing internal-use-only restriction is not clearance to enable.
- **Limits:** token bucket by plan; product 1/ASIN (+6 per offers page), search 10/page, deals 5/150, best-seller list 50; unused tokens expire after 60 min (same official token docs).
- **Cost:** no free API tier; reported entry ~€49/month for 20 tokens/min is third-party and unverified, not an official quote (`Source - Keepa`, TA §2.11).
- **Risk:** exhausted tokens pause requests; invalid/revoked key or ended subscription stops access. Official entry price and redistribution terms must be confirmed before adoption; owner cost approval still required.
- **Count semantics:** BSR, price and review-count history (not rescaled; backfilled points carry past `observed_for`). Features prefixed `kp_`.
- **Status:** candidate — SPEC §4.3 #8 requires owner approval before enabling. **Phase:** later.

## Candidates (no adapter yet)

All candidates retain a manual CSV fallback, subject to the same rights/storage restrictions as the API. CSV does not authorize a vendor purchase or bypass DEC-010/038 approval. Evidence: vault `Candidate Sources`, TA §2.4/7–9/13–15, SF §12, SI §5. *No paid tier documented* is not a promise of unlimited free service.

For the disabled Apify routes above and below: [platform pricing](https://apify.com/pricing), checked 2026-10-22, gives $5/month free usage credit and first paid Starter at $19/month plus usage ($19 credit included); actor fees consume that credit. These are vendor-platform allowances, not permission or source request quotas. Actor-specific source throughput remains unverified; no adapter is authorized.

| Source | Access / terms (checked 2026-10-22) | Limits / cost | Risk / status |
|---|---|---|---|
| Google Merchant API Best Sellers | Official Merchant API v1 `accounts.reports.search`, OAuth; CSV fallback. [Guide](https://developers.google.com/merchant/api/guides/reports/understand-the-market) requires minimum Merchant Center eligibility (criteria unverified); Content API sunset 2026-08-18 | Weekly reports; account/method-specific daily and per-minute quotas, no universal number ([quota docs](https://developers.google.com/merchant/api/guides/quotas-limits/quotas), checked 2026-10-22). Free; no paid tier documented | Eligibility denial / authorization loss / 429; history availability unverified (vault says today-only). candidate (if eligible), DEC-038 approval still required |
| Pinterest Trends API | Official v5 OAuth, top-keyword endpoint; CSV fallback subject to rights. [Developer guidelines](https://policy.pinterest.com/en/developer-guidelines) Basics prohibit storage except authorized campaign analytics; What not to do requires written authorization for competitor research and express permission for ML use. Checked 2026-10-22 | Top 50, today only; Trial per-day/app and Standard per-minute/user/app, numeric quotas unverified ([access tiers](https://developers.pinterest.com/docs/key-concepts/access-tiers/), TA §2.8). Free; no paid tier documented; Standard needs video demo | Storage/research restrictions conflict with vault daily-snapshot plan; app removal / OAuth loss. candidate (if app created), **not adoptable without owner review / written permission** |
| YouTube Data API v3 | Official API key; CSV fallback. [Developer Policies](https://developers.google.com/youtube/terms/developer-policies) storage rule requires non-authorized data refreshed/deleted within 30 days (TA §2.9; exemptions unverified) | [Quota](https://developers.google.com/youtube/v3/determine_quota_cost): 10,000 units/day; separate `search.list` 100 calls/day; `videos.list` 1 unit. Free; no paid tier documented, increases require audit | Retention conflicts with append-only history; derived-series permission unresolved, quota/key rejection can stop access. candidate (backlog) |
| 17TRACK | Official API v2.4, key, webhooks; CSV fallback. [License](https://www.17track.net/en/about/licensing) §1.2 includes API paid services; §5.1.3 forbids unauthorized integrations, §5.2.1 permits suspension for violations; service-specific terms still need review. Checked 2026-10-22 | [Docs](https://api.17track.net/en/doc?version=v2.4): 40 numbers/request, 3 req/s; recurring 100/month free ended 2026-01-07, new accounts get 200 once. First paid tier unverified; research quotes ~$119/5k numbers, 12-month validity (SF §12), not a confirmed entry tier | 401 for bad key/IP whitelist/account disabled; 429 throttling; quota expiry and shipment privacy. candidate (backlog) |
| TikTok Shop vendor data | Vendor API/feed via Apify / Bright Data / ScrapeCreators / EchoTik; manual CSV fallback. [TikTok US ToS §3.4](https://www.tiktok.com/legal/page/us/terms-of-service/en) bans automated extraction without written approval | Vendor/source quotas unverified; Apify tiers above. [Bright Data](https://brightdata.com/solutions/data-extraction/tiktok/shop) advertises free tier (amount unverified), from $0.75/1k and datasets $250/100k; Apify actors $1.99–7/1k, ScrapeCreators $47/25k credits (unverified), EchoTik quote-only (TA §2.4). Entry tier depends on vendor | Buying does not remove TikTok contract risk; blocks / vendor breakage / estimated counts. **disabled** (DEC-010) |
| DataForSEO | Vendor API with credentials; CSV fallback. [Terms §7.1–7.2](https://dataforseo.com/terms-of-service): no SERP use competing with/harming source search engines; customer indemnifies misuse. §6.1 permits suspension. Checked 2026-10-22 | [Trends](https://docs.dataforseo.com/v3/keywords_data-google_trends-overview/): 2,000 calls/min (checked 2026-10-22), ≤5 keywords/task; other endpoint quotas must be checked separately. [FAQ](https://dataforseo.com/faq): $1 trial credit + sandbox, first deposit $50 (checked 2026-10-22); PAYG [Trends](https://dataforseo.com/pricing/keywords-data/google-trends) $0.0027 Standard / $0.011 Live; Shopping $0.001–0.002/item (TA §2.13) | Balance exhaustion, credential/suspension errors; source rights not transferred by purchase. candidate (cost approval) |
| SerpApi paid plans | Vendor API key for Shopping / Ads Transparency etc.; CSV fallback. [Terms §1/§12/§16](https://serpapi.com/legal): no unauthorized/infringing use; termination without notice. Checked 2026-10-22 | [Pricing](https://serpapi.com/pricing): 250 searches/month free; first paid $25/month for 1,000, larger tiers to $725/100k; plan-dependent throughput (numeric rate unverified here) | Key rejection, exhausted cap or vendor withdrawal; Google litigation impact unknown (vault `Source - Google Trends`). candidate (cost approval) |
| Store Leads | Official paid API key or Pro CSV export; manual CSV fallback. [Terms §2.1.5–9](https://storeleads.app/terms): no competitive use, resale/republishing without permission, or undocumented API access; §2.12 requires deletion on termination. Checked 2026-10-22 | [API](https://storeleads.app/api): Pro list-domains 2 req/s, single-resource reads 5 req/s, bulk export 1/min, respect Retry-After (checked 2026-10-22). [Pricing](https://storeleads.app/): free limited preview, first paid Premium $75/month (no API/export), first API tier Pro $250/month; weekly data | Competitive-use / redistribution / deletion obligations conflict with assumed low-risk research history; key revocation / 429. candidate (cost approval), **not adoptable without owner review / written permission** |

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
- 2026-10-22 — P0-12 / DOC-3 (Codex): completed access/CSV, terms, limits, free/first-paid cost and risk fields from vault evidence plus public-doc gap checks; recorded Pinterest/Store Leads permission risks and remaining unverified details. No collection, source enablement or decision changes.

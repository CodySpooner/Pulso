# Pulso hub: connected stores and ads — design

- **Date:** 2026-10-25 (owner session, Claude)
- **Status:** approved by owner 2026-10-26 (DEC-365, SPEC A-14). Owner: "I approve the hub plan. Add it to the SPEC, the vault and the lead's queue without stopping the current build."
- **Changes:** SPEC §1, §6 (new sections), §10 and §11 (Phase 7 amended, Phases 9–12 added); vault phase and feature notes; Lead Playbook §5.
- **Evidence:** two research runs on 2026-10-25 using public docs only (no sign-ups, logins or API calls). Key sources are in the appendix. "Unverified" means the research couldn't read a primary source.

---

## 1. Intent

The owner's own words, from this session:

- "this will act as a hub for my ecommerce business i plan to open multiple stores on multiple platforms, with different niches"
- "i want to be able to sign into a selected store account or ad account and see the information im looking for i dont want to do daily or weekly task to keep this up so this all has to be automated after i sign into an account"
- "a section where i can see all my ads from selected store … how ads are performing and what should be cut out or what should be getting more ad budget … this needs to have every piece of info we can get"
- "i havent started yet but i want to go ahead and get this platform built so i have it when i start"
- On the build order below: "yea that will work … just make sure it doesnt stop our continus building"

**Why:** one place to find products, run stores on several platforms, and run their ads. It should be ready before the first store opens, so launch day means signing in, not waiting for a build.

## 2. What Pulso becomes

Three sections, plus one place to connect accounts:

1. **Research.** What exists and is being built now (Phases 2–6 and 8). Unchanged by this design.
2. **Stores.** Every connected store gets its own page, plus an **All stores** view.
3. **Ads.** Every connected ad account gets creative-level analytics like Motion's, with explained advice on what to cut, scale or refresh.
4. **Connections** (in Settings). Sign in once per account. Pulso does the rest.

The sections feed each other:

- A product found in Research goes onto the Testing Board and is pushed to a store (Phase 7's existing push).
- Its ads and sales then come back automatically.
- The Testing Board fills itself in, and ad advice is judged against the product's **break-even ROAS**, which Pulso already knows from its landed-cost and fee math. Motion and Foreplay can't do this, because they don't know the product's margin.

## 3. Goals, non-goals, anti-goals

### Goals
- **G1 One sign-in per account.** After that, syncing, token renewal and backfill run on their own. Where a platform forces a fresh sign-in (eBay about every 18 months, for example), Pulso warns ahead of time and offers one button.
- **G2 Store analytics.** Everything each platform's official API gives for a store, plus a rollup across all stores (§6).
- **G3 Ad analytics.** Creative-level metrics, reports, and explained cut/scale/refresh advice for each ad account and each store (§7).
- **G4 Built before launch.** Each connection is built and tested on free test accounts and saved sample payloads. Turning on a real account is a sign-in, not a build.
- **G5 The continuous build never stops.** Owner-only steps go to the vault note `Phases/Owner To-Dos` and never block a phase. Every connection ships switched off until its keys exist, the same pattern already used for CJ and AliExpress.

### Non-goals (for now)
- **Logged-in scraping or browser automation** of Vinted, Depop or any account. The owner said: "ok we will skip those for noe but we will keep in our minds". This goes to BACKLOG.
- **Paid data sources.** The owner said none for now, until the stores make money.
- **Competitor ad spying like Foreplay's.** US commercial ads aren't available through Meta's official API, and Meta's automated-collection terms need written permission. The existing Ad Intelligence plan (Phase 8, manual CSV) is unchanged.
- **Benchmarks across other businesses,** AI models trained on other advertisers' data, tracking-pixel attribution, and marketing-mix models. All of these need data a one-owner app can't have.
- **Pulso pausing ads or changing budgets by itself.** Version 1 gives advice only. *(My call.)* Acting on the advice later needs extra permissions and its own DEC.
- **Cross-listing** (posting listings to several platforms), beyond Phase 7's Shopify push.
- **Selling Pulso as a product.** DEC-136 is unchanged, and the data model stays multi-tenant ready.

### Anti-goals (failure even if it works)
- Anything that puts the owner's store or ad accounts at risk. This is the same principle as DEC-261.
- Any daily or weekly manual step for a connected platform.
- Platform-reported numbers and blended numbers mixed together so they can't be told apart, or AI advice presented as data (DEC-047).
- Showing 0 where there is no data. Show "no source yet" instead (DEC-040).

## 4. Build order and phases

Owner-approved order:
1. Finish product research.
2. Shopify + Meta ads.
3. TikTok ads + Google ads.
4. eBay + Etsy.
5. TikTok Shop.
6. Vinted + Depop.

Phase mapping *(my call)*:

| Phase | Scope |
|---|---|
| 4, 5, 6 | Unchanged (research). Phase 6's data-gated exit criteria don't block the next phase (DEC-049). |
| **7 Hub 1: Shopify + Meta ads** (amends "Store Operations") | Connections framework (§5), the Stores section and All stores view (§6), the Ads section (§7), and the Shopify and Meta ads connections. Also everything already in Phase 7: product push, order sync, ad spend entry, the Profit Dashboard, test results feeding the model, email/Discord alerts and the digest. Manual ad-spend entry stays for accounts that aren't connected. |
| 8 | Unchanged (research views, launch prep). |
| **9 Hub 2: TikTok ads + Google ads** | Both ad connections, mapped onto the §7 metric library (YouTube video metrics included). |
| **10 Hub 3: eBay + Etsy** | Both store connections. Etsy uses its official Seller App, with file upload as a fallback. |
| **11 Hub 4: TikTok Shop, then Vinted + Depop** | TikTok Shop store connection: orders, finance, and shop/product/video analytics. Then file-upload importers for Vinted and Depop sales (Q1). Two small importers don't need a phase of their own *(my call)*. |

After the last hub phase, the improvement rotation takes over: Lead Playbook §5 step 5 changes from "after Phase 8" to "after the last phase".

Why Phase 8 stays where it is:
- Renumbering would break links across the vault.
- Its remaining items (Compare, Niches, Calendar, the ad-library CSV) are extra research views, while Phases 2–6 are the research core.
- *(My call; the owner can ask to move Phase 8 ahead of Phase 7.)*

Each new phase starts with the lead's usual brainstorm round, which breaks it into tasks (Playbook §5 step 4).

## 5. Connections

**One Connections page** (Settings → Connections). Each platform gets a card showing:
- its status: not connected, test account, connected, syncing, needs attention, or "reconnect by DATE";
- the last sync and the date range of data held;
- the one thing the owner must do next, if anything.

**Owner-only steps.** Developer accounts, app creation and keys are hard stops (AGENTS.md §2). For each one, Pulso shows the exact steps on the card, and the owner does them. Agents never create accounts or handle secrets.

**Secrets.** Tokens are encrypted at rest with a key from env and owned by the workspace. They never appear in logs, raw payloads or error messages.

**Sync:**
- Scheduled polling on crontab, incremental by an updated-at cursor.
- On first connect, a backfill as far back as the platform allows.
- A trailing window is re-pulled each day for late changes, such as Meta's late-attributed conversions. Re-pulls are written as new snapshot rows, never as updates.
- No webhooks until the sync has a public endpoint to receive them.

**Health:**
- Each connection shows its status in Data Health.
- Missed runs are recorded and never filled in.
- Pulso warns 14 and 3 days before a known token expiry *(my call)*.
- A connection that fails authorisation turns itself off and raises one alert.

**Test mode.** A connection can point at a test or sandbox account. Test data is labelled and never added to real totals *(my call)*.

### Platform by platform

| Platform | Route and sign-in | Testing before launch | Fresh sign-in needed | Rules that shape the design |
|---|---|---|---|---|
| **Shopify** | An app the owner creates in Shopify's Dev Dashboard, in his own organisation. It uses the client-credentials token (24 h, renewed by Pulso with no redirect). Scopes: orders (all history), products, inventory (unit cost), customers without personal fields, reports (ShopifyQL), payouts, disputes, marketing events. | Free development stores with demo data and test orders. These need a free Shopify Partner/developer account first (owner step). Real traffic stays near zero there. | None in normal use. Only if the app is uninstalled or its secret is rotated. | Sessions, conversion and profit reports (ShopifyQL) need Level-2 protected data, likely the **Grow plan or higher**. On Basic, those metrics show "no source yet". API Terms §2.3.24: read conservatively, Shopify data trains no models without Shopify's written consent, so store data feeds rules and statistics only. The unit cost API returns only today's cost, so Pulso snapshots cost history itself. |
| **Meta ads** (Facebook, Instagram) | A Business-type app plus a system user token with `ads_read`. Own-account apps get Standard access automatically, with no App Review (one Meta page conflicts; check at phase entry). | The sandbox ad account delivers no ads, and Insights don't work in it, so analytics are built on saved sample payloads. | Usually none: "never expires" is an option. Meta says some businesses must use 60-day tokens, which Pulso refreshes itself; a PC that's off for 60+ days means a new token. | 37 months of history. The 7- and 28-day view attribution windows stopped returning on 2026-01-12. Reach and frequency can't be summed. Developer Policies §10.7 limit mixing Meta data with other platforms' data, and §10.6(b) requires separate Meta reporting from 2027-02-03. So Meta numbers always appear in their own views and are never summed with other ad platforms (§9 combined numbers). |
| **TikTok ads** | Marketing API, registered as a "Direct Advertiser" app with read-only reporting scopes. The long-term token doesn't expire. | Sandbox ad accounts with mock data, available after developer approval. | None unless revoked. | **Developer registration refuses individuals.** It needs an email on a company domain, a public website on that domain, and a brand or legal name (question Q2). The Developer Terms are ambiguous about keeping history (D(4), Appendix 1 §2(k)); check them at phase entry. |
| **Google ads** (incl. YouTube) | A Google Cloud project with Explorer access (automatic approval), plus a service account added read-only to the Ads account. | Test manager and test accounts. They serve no ads, so analytics use sample payloads. | None. Google revokes access after 90 days of no use. | 37 months of daily data. Google Ads data is shown separately from other platforms' data (API policy). |
| **eBay** | An eBay Developers Program keyset plus the owner's one-time consent. | Sandbox with test users. | About every **18 months**, and after an eBay password change. | License §8.1(d)(2): showing promoted-listing or ad performance, or conversion rates, needs eBay's written permission, so that stays off by default. §9.10: no model training. §9.5: no price modelling. §3.1(b): only limited copies, so a storage rule is set at phase entry. eBay also requires an always-on public "account deletion" endpoint; it lives in the public web app (on Railway today). |
| **Etsy** (kept, Q1) | A Seller App, which needs an open shop. File upload (Etsy's own orders CSV) is the fallback. | No sandbox, so sample payloads only. | The refresh token lasts 90 days and rotates; Pulso refreshes it daily. | The current API terms couldn't be read (403). The archived terms limit caching and analytics, so the owner reads the current terms before any Etsy history is stored. Shop visit statistics: no API was found. |
| **TikTok Shop** | US Partner Center, registered as a seller in-house developer with a custom app (third-party evidence only). | Seller test accounts (unverified for the US). | Possibly yearly re-authorisation. | Every fact here is third-party; recheck at phase entry. Data: orders, finance statements, and shop/product/video/LIVE analytics. TikTok Shop orders that sync into Shopify carry no TikTok fees, so fees come from TikTok Shop's finance data and those orders are de-duplicated. |
| **Vinted** (kept, uploads only, Q1) | No API route: Pro Integrations are only for allowlisted EU/UK Pro businesses. The owner uploads a sales file (Pulso's template, or Vinted's own account-data download if it can be parsed). | Sample files. | — | US terms (from 2026-10-08): personal, non-professional use only. Listing items you don't own counts as commercial activity, and repeat violations can mean a permanent ban. The owner keeps Vinted knowing this (Q1); Pulso never automates the account. |
| **Depop** (kept, uploads only, Q1) | No API route: a private partner API for companies, with £1M/£2M liability and £2M cyber insurance. The owner uploads a sales file. | Sample files. | — | Depop's user terms reportedly bar selling items you don't possess unless you designed them (unverified). The owner keeps Depop knowing this (Q1). |

Reading Vinted and Depop sale emails through Gmail (a restricted Google scope, needing a Cloud project in production status) would remove the upload chore. It goes to BACKLOG, not this design *(my call, following Q1)*.

## 6. Stores section

There's a page per store and an **All stores** view. Every number shows "as of", its source on hover, and "no source yet" where a platform doesn't provide it.

- **Sales:** gross sales, discounts, returns, net sales, shipping charged, taxes, orders, units, AOV, new vs returning orders.
- **Traffic and funnel** (where the API has it): sessions, visitors, add-to-cart, reached checkout, conversion rate, bounce rate. Broken down by landing page (that is, by product), referrer, UTM, device and country. Sources: Shopify ShopifyQL (plan-gated), the eBay traffic report, TikTok Shop analytics.
- **Profit by product and variant:** net sales, units, refund rate, cost of goods, gross profit, allocated ad spend, net profit. For CJ and AliExpress products, Pulso's existing landed-cost math supplies cost. Each cost line is marked actual or estimated.
- **Fees and payouts by platform:** Shopify Payments fees and payouts, the eBay Finances API, the Etsy ledger, TikTok Shop statements. Settled and estimated amounts are shown separately.
- **Costs no API supplies** (owner settings, with history): cost of goods, shipping rules, handling, recurring costs (apps, subscriptions), marketplace commission estimates.
- **Marketing efficiency:** for each ad platform separately, spend, ROAS against store sales, CAC, profit on ad spend and ad spend per order. Platform-reported ROAS sits beside the store-measured figure, never mixed into it. Ad platforms are never summed into one total (§9 combined numbers).
- **Customers and cohorts** (Shopify): repurchase rate, a retention heatmap by first-order month, CAC payback.
- **Inventory:** stock, sell-through, stock-outs.
- **Alerts and digest:**
  - threshold alerts;
  - a simple anomaly check against each metric's own baseline;
  - broken-connection and stale-data alerts;
  - a daily digest in-app (email and Discord are already in Phase 7).
- **All stores:**
  - store tiles and totals;
  - a Store dimension on every report;
  - USD, with the FX source and date shown;
  - a day is the UTC date unless a DEC chooses store-local display at phase entry;
  - orders that sync between channels are counted once.

## 7. Ads section

There's a view per ad account, and it can be filtered by store: an ad's landing URL or UTM links it to a store and a product.

- **Ingestion:** daily ad-level stats saved as append-only snapshots, with the late-change window re-pulled each day (§5). Reach and frequency are stored only for fixed windows (7 and 30 days) or fetched live.
- **Creative identity:** creative ID, video and image, headline, copy, landing page and call to action. Ads are grouped by any of these.
- **Metric library** (fixed definitions in code and docs):
  - Viewing: hook rate (3-second views ÷ impressions), hold rate, completion rate, average watch time.
  - Clicks and cost: link CTR, outbound CTR, thumbstop CTR, CPM, CPC.
  - Results: CPA, ROAS, conversion rate, AOV, spend share, frequency (fixed windows).
  - Each platform maps onto the same library with its own definitions recorded: Meta uses 3-second views and ThruPlay, TikTok uses 2- and 6-second views, Google uses video quartiles.
- **Naming-convention parser:** the owner defines his ad-name fields once (for example concept_hook_format), and ads group themselves with no per-ad work.
- **Scores (0–100):** percentiles against the owner's own ads only, covering hook, hold, click and convert. Below a minimum spend, the score reads "not enough data".
- **Reports, all generated automatically:**
  - top performers;
  - comparisons by tag or name field;
  - period over period;
  - a weekly leaderboard with movers;
  - launch analysis (the last 14 days sorted into winning, scaling and losing);
  - video drop-off;
  - placement and age/gender breakdowns;
  - a page per creative.
- **AI tags** on the owner's own creatives (hook type, format, angle, offer and so on). They're labelled AI and flagged `ai_derived` (DEC-047), the owner can override them, and only recent creatives are tagged, to cap cost.
- **Advice, each item explained with its rule and evidence:**
  - **Scale:** spend is above a threshold, the goal metric beats target over 7–14 days, and the trend is flat or rising.
  - **Cut:** spend has passed k × target CPA with poor or no conversions.
  - **Refresh the hook:** weak hook score with a strong convert score.
  - **Fatigue:** CPC or CPA rising against the ad's own baseline while frequency rises and CTR falls.
  - **Iterate:** promising, but spend is still below the threshold.
  - Targets default to each product's break-even ROAS from Pulso's margin math. Thresholds are owner-editable defaults, and every piece of advice is stored append-only with the thresholds it used.
- **What can't be reproduced under Pulso's rules:**
  - competitor ad libraries;
  - benchmarks across other businesses;
  - models trained on other advertisers' data;
  - pixel attribution;
  - 7- and 28-day view conversions (Meta stopped returning them);
  - Meta's own fatigue flags (no API).

## 8. How the sections connect

- Testing Board cards fill in spend, revenue, orders, CPA and ROAS on their own from connected store and ad data. Manual entry stays for anything that isn't connected.
- A product pushed from Pulso to Shopify stays linked to its research product.
- Test outcomes become labelled outcomes for forecasting (SPEC §8), **but only from data whose terms allow model use**: not Shopify-derived data without Shopify's written consent, and not eBay data. Data that can't be used is still shown, just not used for training.
- **Training flag (my call).** From the first hub migration, every hub row records whether it may be used for model training. Shopify- and eBay-derived rows default to "no", while outcomes the owner enters by hand stay usable. The forecasting pipeline filters on the flag. If Shopify later gives written consent, or the owner settles the reading of §2.3.24 (the Phase 7 vault note reads it as merchant consent), the default can change without backfilling append-only tables.

## 9. Constraints

- SPEC §4.2 compliance. Official APIs only, with no browser automation of any account.
- Hard stops (AGENTS.md §2): accounts, keys, paid plans, Railway configuration, terms questions.
- History is append-only (AGENTS.md §3).
- **Platforms whose terms limit storage (my call).** For eBay, Etsy and Depop, nothing is ever deleted on a schedule, because that would relax AGENTS.md §3. Instead their data is fetched live with a short cache (the DEC-037 AliExpress pattern) until an owner-approved DEC allows keeping more. Their pages are live views with no trend history until then.
- **No buyer personal data (my call).** Pulso never stores buyer names, emails, phone numbers or addresses from any platform. That also keeps eBay's account-deletion notices a simple acknowledgement.
- **Combined numbers (my call, re-checked at Phase 7 entry).** Meta's Developer Policies allow Meta ad data only for measuring that advertiser's Meta campaigns (§10.7(a)/(b)). They say "don't mix" it with campaigns on other ad platforms (§10.7(d)), and from 2027-02-03 they require Meta reporting to be shown separately (§10.6(b)). Google's API policy asks for separate display too. So:
  - Meta spend and results may be compared with the owner's own store sales and product margins (profit per product, Meta ROAS vs break-even, Testing Board auto-fill), because that measures his Meta campaigns.
  - Meta, TikTok and Google ad numbers are shown side by side, each in its own block, and never added into one cross-platform ad total or blended ROAS. Store-side figures that use no ad data (net sales, payouts, fees) roll up freely.
  - Meta data never feeds research scores, forecasts across platforms, or anything outside the owner's own campaign analysis.
  - The data model keeps each ad platform's rows separate. Combining happens only in views that follow these rules.
- Data rules:
  - every row is workspace-owned (`workspace_id NOT NULL`);
  - money is stored in minor units plus a currency;
  - times are UTC.
- **Naming.** The existing `stores` table and the `/stores` and `/ads` pages are competitor research. Own accounts get distinct names, and own data never shares a page with competitor data. Routes *(my call)*:
  - `/my-stores` and `/my-stores/[id]`;
  - `/my-ads` and `/my-ads/[account]`;
  - `/settings/connections`.
- **Where syncs run (Q3).** Syncs run wherever the collectors run: the home PC today (DEC-001), while the live Railway site has its own empty database (DEC-102). At launch the owner plans to move collection and the site to one always-on server, "probably … net cup since it would be cheaper". That move is its own owner decision and project, not part of this design. So:
  - the hub code is host-agnostic: the same sync jobs, connection store and pages run on the home PC or a server;
  - until the move, building uses test accounts and sample payloads, and real accounts wait for launch anyway;
  - Phase 7's two connections need no redirect (Shopify client credentials, the Meta system user token). From Phase 9, sign-ins that return to a public URL (TikTok ads, eBay, Etsy, TikTok Shop) go through the public web app;
  - while collection runs on a PC that is sometimes off, a long outage can force a fresh sign-in (Meta 60-day tokens if required, Google after 90 days unused, Etsy after 90 days). Pulso warns ahead of each one.
- UI rules (AGENTS.md §8) apply to every new screen.

## 10. Owner-only steps, by phase

All of these go to the vault note `Phases/Owner To-Dos` when the phase starts. None blocks the build.

- **Phase 7:**
  - a free Shopify Partner or developer account, for the test store;
  - a Meta developer account, a business portfolio, a Business app and a system user token;
  - at launch, the live store's plan (Basic or Grow) and its Dev Dashboard app.
- **Phase 9:**
  - for TikTok, a brand with its own domain, a domain email and a website (Q2), then developer registration;
  - for Google, a Cloud project, Explorer access and a read-only service account.
- **Phase 10:**
  - eBay: a Developers Program account (it asks for a business email) and the one-time consent;
  - Etsy: an open shop, a Seller App, and a read of Etsy's current API terms.
- **Phase 11:**
  - a TikTok Shop seller account and Partner Center registration, confirming the developer type, sandbox and authorisation period there;
  - uploading Vinted and Depop sales files whenever he wants those numbers current (the one manual step in the hub, chosen in Q1).
- **At launch (any phase):** the server move (Q3) and the custom domain and brand email (Q2).

## 11. Left to the builder

- Schema and module layout.
- Exact field lists, confirmed against real responses at first connect.
- Sync cadence.
- Default rule thresholds.
- Screen layouts within DEC-007/024/025.
- How each phase splits into tasks.

## 12. Owner answers (2026-10-26)

A builder read this document before the owner did. These three questions were the ones only the owner could answer.

- **Q1: Etsy, Vinted and Depop.** He was told all three restrict dropshipping: Vinted can permanently ban members for listing items they don't own, Depop reportedly bars selling items you don't have unless you designed them, and Etsy allows it only for craft and party supplies or your own designs. He was also told Vinted and Depop have no usable connection. **His answer: "Keep all three, uploads only."** Etsy keeps its official automatic connection, because one exists (my call), with file upload as a fallback. Vinted and Depop come in by file upload. The ban risk on those platforms is the owner's own business decision; Pulso never automates those accounts.
- **Q2: a brand for TikTok ads.** TikTok's developer registration needs a brand name, a website on its own domain and an email on that domain. **His answer: "yes i will set up custom domains once i decide to start opening stores".** Until then, TikTok ads are built on sample payloads, with a file-export import as the fallback.
- **Q3: where the owner sees store and ad numbers.** **His answer: "we will probably move this to net cup since it would be cheaper".** The design stays host-agnostic (§9). The server move is a separate owner decision before launch.

## 13. Calls made in this document (please check)

1. **Phases.** Phase 7 becomes Hub 1 (Shopify + Meta ads plus its existing scope). Phase 8 stays between Hub 1 and Hub 2. Phases 9–11 are new. Vinted and Depop uploads join Phase 11 instead of getting a Phase 12.
2. **Advice only.** In version 1, Pulso never pauses ads or changes budgets.
3. **Combined numbers.** Meta, TikTok and Google ad numbers are shown side by side and never summed. Meta spend may be compared with store sales and margins. Meta data never feeds research scores (§9).
4. **Training flag.** Shopify- and eBay-derived rows default to "not for model training". Hand-entered outcomes stay usable (§8).
5. **Storage-limited platforms.** eBay, Etsy and Depop data is fetched live with a short cache, with no scheduled deletion, until a DEC allows keeping more (§9).
6. **No buyer personal data** is stored from any platform.
7. **eBay ad analytics** stays off unless eBay gives written permission.
8. **Shopify on the Basic plan.** Session and conversion metrics show "no source yet" there.
9. **Reconnect warnings** go out 14 and 3 days before a known token expiry. Test-account data is labelled and never counted in real totals.
10. **Routes.** `/my-stores`, `/my-ads` and `/settings/connections`. The existing `/stores` and `/ads` stay competitor research.
11. **Gmail sale-email reading** for Vinted and Depop goes to BACKLOG.

## Appendix: key sources (read 2026-10-25)

- Shopify: [access scopes](https://shopify.dev/docs/api/usage/access-scopes), [ShopifyQL](https://shopify.dev/docs/apps/build/shopifyql/graphql-admin-api), [protected customer data](https://shopify.dev/docs/apps/launch/protected-customer-data), [API Terms](https://www.shopify.com/legal/api-terms).
- Meta: [Marketing API authorization](https://developers.facebook.com/docs/marketing-api/get-started/authorization), [Platform Terms](https://developers.facebook.com/terms/dfc_platform_terms/), [Developer Policies](https://developers.facebook.com/devpolicy/).
- TikTok ads: [Register as a developer](https://business-api.tiktok.com/portal/docs/register-as-a-developer/v1.3) (client-rendered; read through a third-party renderer).
- Google Ads: [access levels](https://developers.google.com/google-ads/api/docs/api-policy/access-levels).
- eBay: [API License Agreement](https://www.edp.ebay.com/join/api-license-agreement) (dated 2025-09-03).
- Etsy: [developer documentation](https://developers.etsy.com/documentation/); the API terms page returned 403.
- Vinted: [US terms](https://www.vinted.com/terms-and-conditions), [commercial activity](https://www.vinted.com/help/1120).
- Depop: [partner API terms](https://partnerapi.depop.com/api-docs/terms/), [authentication](https://partnerapi.depop.com/api-docs/concepts/authentication/).
- Benchmarks: Motion, Foreplay, Atria, Superads, Triple Whale, Madgicx, Birch, TrueProfit, BeProfit, Lifetimely and Polar public pages (feature lists and published rules only).

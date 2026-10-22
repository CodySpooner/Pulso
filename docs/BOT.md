# PulsoBot

PulsoBot is the crawler for **Pulso**, a product-research tool built in this repository. Pulso tracks public product catalogs to spot products that are starting to sell and to follow their prices and availability over time. Today one person runs it for their own product research.

## How to recognise it

Every request sends this User-Agent:

```
PulsoBot/0.1 (+https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md)
```

The version number may change. The `PulsoBot` token and the link to this page stay the same. PulsoBot never sends a browser User-Agent and never pretends to be another client. It uses no proxies and no IP rotation. Requests are not yet signed with Web Bot Auth.

## What it requests

Only public storefront data that any visitor can see without logging in, on Shopify stores:

| Path | Why |
|---|---|
| `/robots.txt` | Read first, before anything else on the site |
| `/meta.json` | Store currency, country and product count |
| `/products.json` | Public catalog: titles, variants, prices, availability, images, timestamps |
| `/products/<handle>.js` | One public product: variant availability and stock fields when the store exposes them |

PulsoBot **never** requests `/cart*`, `/search`, `/checkout`, account or login pages, or password-protected storefronts. It never uses the Storefront API, never fills in forms and never solves CAPTCHAs. It does not collect customer, order or personal data.

## How fast

- At most **30 requests per minute in total**, across every site it visits combined.
- One request at a time, never in parallel.
- A `Crawl-delay` or `Request-rate` in robots.txt, or a `Retry-After` header, makes it slower, never faster.
- Catalog requests use `If-None-Match`, so unchanged pages cost you a `304`.

## robots.txt

PulsoBot reads `/robots.txt` before any other request to a site, and obeys the rules for `User-agent: PulsoBot`, or for `User-agent: *` if there's no PulsoBot group. A disallowed path is not requested. If robots.txt can't be read (anything other than a normal response or a `404`), PulsoBot stops for that site.

To block PulsoBot completely:

```
User-agent: PulsoBot
Disallow: /
```

## When a site says no

- A `429`, `430` or `403` response ends the current run at once. PulsoBot sends no more requests in that run and does not retry.
- The next run waits until any `Retry-After` time has passed.
- Repeated blocks turn the collector off until its operator turns it back on.

PulsoBot never retries from another IP or network, never changes its User-Agent and never tries to get around a block in any other way.

## Opting out or reporting a problem

[Open an issue in this repository](https://github.com/CodySpooner/Pulso/issues/new) with your store's domain and what you want: stop crawling, crawl more slowly, or a question. When we see the issue, we remove the domain from Pulso's store list and stop crawling it. Issues are public, so please don't include personal details or secrets. A robots.txt block (above) works without an issue.

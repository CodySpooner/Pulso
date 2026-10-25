"""Workspace product economics: landed_cost() in SQL and the default-scenario view (DEC-265).

`landed_cost()` here is the SQL twin of `pulso_core.landed_cost.landed_cost`, and the view
resolves its inputs as `pulso_core.landed_cost_loader.calculate` does with no request
overrides: quantity 1, no DDP, the cheapest exact US quote, the lower median live USD store
price, and the best complete supplier listing. The golden vectors in
`packages/core/tests/fixtures/landed_cost_vectors.json` hold the two to the same answers.

Frozen schema: do not import live application models into a revision.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Python's round() on a Fraction: exact, half-even (DEC-246 a).
HALF_EVEN = """
CREATE FUNCTION half_even(numerator numeric, denominator numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN 2 * abs(rest) > abs(denominator)
            OR (2 * abs(rest) = abs(denominator) AND mod(whole, 2) <> 0)
        THEN whole + sign(numerator) * sign(denominator)
        ELSE whole
    END
    FROM (
        SELECT div(numerator, denominator) AS whole,
               numerator - div(numerator, denominator) * denominator AS rest
    ) parts
$$
"""

# landed_cost()'s usd(): USD cents, or the missing code that withholds the line (DEC-250 c).
USD_LINE = """
CREATE FUNCTION usd_line(
    minor numeric, currency text, usd_rate numeric, missing_code text,
    OUT usd numeric, OUT gap text
)
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    places smallint;
BEGIN
    IF minor IS NULL THEN
        gap := missing_code;
    ELSIF currency = 'USD' THEN
        usd := minor;
    ELSIF usd_rate IS NULL THEN
        gap := 'fx_missing';
    ELSIF usd_rate <= 0 OR usd_rate = 'NaN'
        OR minor >= 9223372036854775808 OR minor < -9223372036854775808 THEN
        gap := 'amount_out_of_range';  -- convert_minor() raises: a bad rate, or past BIGINT
    ELSE
        SELECT c.exponent INTO places FROM currencies c WHERE c.code = currency;
        IF places IS NULL THEN
            RAISE EXCEPTION 'Unknown currency %', currency;
        END IF;
        usd := half_even(minor * 100, power(10::numeric, places) * usd_rate);  -- USD exponent 2
    END IF;
    IF abs(usd) > 9223372036854775807 THEN
        usd := NULL;
        gap := 'amount_out_of_range';
    END IF;
END
$$
"""

# The traced() FX rate: USD-base, dated within 4 days up to the observation's UTC date, newest
# date first; on a tie the daily blend before a manual CSV rate (DEC-246 d).
USD_RATE = """
CREATE FUNCTION usd_rate(quote_currency text, observed_at timestamptz)
RETURNS TABLE (rate numeric, captured_at timestamptz, raw_payload_id bigint, source text)
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT fx.rate, fx.captured_at, fx.raw_payload_id, src.key
    FROM fx_rates fx
    JOIN raw_payloads payload ON payload.id = fx.raw_payload_id
    JOIN sources src ON src.id = payload.source_id
    WHERE quote_currency <> 'USD'
      AND fx.base = 'USD'
      AND fx.quote = quote_currency
      AND fx.date BETWEEN (observed_at AT TIME ZONE 'UTC')::date - 4
                      AND (observed_at AT TIME ZONE 'UTC')::date
    ORDER BY fx.date DESC, fx.source = 'manual', fx.captured_at DESC
    LIMIT 1
$$
"""

LANDED_COST = """
CREATE FUNCTION landed_cost(
    price bigint, unit bigint, unit_currency text, unit_rate numeric,
    freight bigint, freight_currency text, freight_rate numeric,
    duty_bps integer, quantity integer, ddp boolean, customs_fee bigint,
    payment_fee_bps integer, payment_fee_fixed bigint, shopify_fee_bps integer,
    returns_bps integer, ad_cost bigint, freight_gap text,
    OUT price_minor bigint, OUT goods_minor bigint, OUT freight_minor bigint,
    OUT duty_minor bigint, OUT customs_fee_minor bigint, OUT payment_fee_minor bigint,
    OUT shopify_fee_minor bigint, OUT returns_minor bigint, OUT landed_cost_minor bigint,
    OUT margin_minor bigint, OUT margin_bps bigint, OUT ad_cost_minor bigint,
    OUT net_minor bigint, OUT net_bps bigint, OUT complete boolean, OUT missing text[]
)
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    big constant numeric := 9223372036854775807;
    codes constant text[] := ARRAY[  -- pulso_core.landed_cost.MISSING, in order
        'price_missing', 'supplier_cost_missing', 'freight_missing',
        'freight_variant_mismatch', 'duty_not_set', 'fx_missing', 'amount_out_of_range'
    ];
    gaps text[] := '{}';
    line record;
    goods numeric;
    shipped numeric;
    duty numeric := 0;
    landed numeric;
    payment numeric;
    margin numeric;
    margin_rate numeric;
    net numeric;
    net_rate numeric;
BEGIN
    IF price <= 0 THEN
        RAISE EXCEPTION 'A retail price must be positive';
    END IF;
    IF price IS NULL THEN
        gaps := gaps || 'price_missing'::text;
    END IF;
    SELECT * INTO line
    FROM usd_line(quantity::numeric * unit, unit_currency, unit_rate, 'supplier_cost_missing');
    goods := line.usd;
    gaps := gaps || line.gap;
    SELECT * INTO line FROM usd_line(freight, freight_currency, freight_rate, freight_gap);
    shipped := line.usd;
    gaps := gaps || line.gap;
    IF NOT ddp THEN
        IF duty_bps IS NULL THEN
            gaps := gaps || 'duty_not_set'::text;
        END IF;
        duty := half_even(goods * duty_bps, 10000);  -- up to 10 x goods: duty can pass 100%
        IF abs(duty) > big THEN
            duty := NULL;
            gaps := gaps || 'amount_out_of_range'::text;
        END IF;
    END IF;
    customs_fee_minor := CASE WHEN ddp THEN 0 ELSE customs_fee END;
    landed := goods + shipped + duty + customs_fee_minor;  -- null while a line is
    IF abs(landed) > big THEN
        landed := NULL;
        gaps := gaps || 'amount_out_of_range'::text;
    END IF;
    IF price IS NOT NULL THEN
        payment := half_even(price::numeric * payment_fee_bps, 10000) + payment_fee_fixed;
        IF abs(payment) > big THEN
            payment := NULL;
            gaps := gaps || 'amount_out_of_range'::text;
        END IF;
        shopify_fee_minor := half_even(price::numeric * shopify_fee_bps, 10000);  -- <= price
        returns_minor := half_even(price::numeric * returns_bps, 10000);
        margin := price - landed - payment - shopify_fee_minor - returns_minor;
        IF abs(margin) > big THEN
            margin := NULL;
            gaps := gaps || 'amount_out_of_range'::text;
        END IF;
        margin_rate := half_even(margin * 10000, price);
        IF abs(margin_rate) > big THEN
            margin_rate := NULL;
            gaps := gaps || 'amount_out_of_range'::text;
        END IF;
        net := margin - ad_cost;
        IF abs(net) > big THEN
            net := NULL;
            gaps := gaps || 'amount_out_of_range'::text;
        END IF;
        net_rate := half_even(net * 10000, price);
        IF abs(net_rate) > big THEN
            net_rate := NULL;
            gaps := gaps || 'amount_out_of_range'::text;
        END IF;
    END IF;
    gaps := array_remove(gaps, NULL);
    IF NOT gaps <@ codes THEN
        RAISE EXCEPTION 'Unknown missing code in %', gaps;
    END IF;
    missing := ARRAY(
        SELECT code FROM unnest(codes) WITH ORDINALITY AS listed(code, place)
        WHERE code = ANY(gaps) ORDER BY place
    );
    complete := cardinality(missing) = 0;
    IF NOT complete THEN  -- R-16: only a complete row has a margin, so only it can rank
        margin := NULL;
        margin_rate := NULL;
        net := NULL;
        net_rate := NULL;
    END IF;
    price_minor := price;
    goods_minor := goods;
    freight_minor := shipped;
    duty_minor := duty;
    landed_cost_minor := landed;
    payment_fee_minor := payment;
    margin_minor := margin;
    margin_bps := margin_rate;
    ad_cost_minor := ad_cost;
    net_minor := net;
    net_bps := net_rate;
END
$$
"""

# One row per workspace and non-merged product: calculate() with no overrides (DEC-265). A live
# answer, so it reads every capture; a dated reader puts DEC-031's cutoff inside the ranked
# subquery's WHERE, before both window functions (P2-18, P2-22).
VIEW = """
CREATE VIEW workspace_product_economics AS
SELECT
    s.workspace_id,
    p.id AS product_id,
    pick.supplier_listing_id,
    pick.method,
    pick.price_minor, pick.goods_minor, pick.freight_minor, pick.duty_minor,
    pick.customs_fee_minor, pick.payment_fee_minor, pick.shopify_fee_minor, pick.returns_minor,
    pick.landed_cost_minor, pick.margin_minor, pick.margin_bps, pick.ad_cost_minor,
    pick.net_minor, pick.net_bps, pick.complete, pick.missing,
    jsonb_build_object(
        'customs_fee_minor', owner.trace, 'payment_fee_bps', owner.trace,
        'payment_fee_fixed_minor', owner.trace, 'shopify_fee_bps', owner.trace,
        'returns_bps', owner.trace, 'ad_cost_minor', owner.trace
    )
    || CASE WHEN s.duty_default_bps IS NULL THEN '{}'::jsonb
            ELSE jsonb_build_object('duty_bps', owner.trace) END
    || coalesce(pick.sources, '{}'::jsonb) AS sources,
    pick.as_of
FROM settings s
CROSS JOIN products p
CROSS JOIN (
    SELECT '{"source": "settings", "as_of": null, "raw_payload_id": null}'::jsonb AS trace
) owner
LEFT JOIN LATERAL (  -- the reference price: the lower median of live USD store prices
    SELECT ranked.price_min_minor AS minor, ranked.captured_at, ranked.raw_payload_id, ranked.key
    FROM (
        SELECT latest.*,
               row_number() OVER (ORDER BY latest.price_min_minor, latest.listing_id) AS place,
               count(*) OVER () AS stores
        FROM (  -- each live store listing's latest snapshot
            SELECT DISTINCT ON (snap.listing_id)
                snap.listing_id, snap.price_min_minor, snap.currency, snap.captured_at,
                snap.raw_payload_id, src.key
            FROM listings l
            JOIN listing_snapshots snap ON snap.listing_id = l.id
            JOIN sources src ON src.id = l.source_id
            WHERE l.product_id = p.id AND l.store_id IS NOT NULL AND l.delisted_at IS NULL
            ORDER BY snap.listing_id, snap.captured_at DESC, snap.id DESC
        ) latest
        WHERE latest.currency = 'USD' AND latest.price_min_minor > 0
    ) ranked
    WHERE ranked.place = (ranked.stores + 1) / 2
) price ON true
CROSS JOIN LATERAL (  -- each live supplier listing costed; the best one
    SELECT
        l.id AS supplier_listing_id,
        quote.method,
        cost.*,
        (
            SELECT jsonb_object_agg(
                trace.name,
                jsonb_build_object(
                    'source', trace.source, 'as_of', trace.at, 'raw_payload_id', trace.payload
                )
            )
            FROM (VALUES
                ('price_minor', price.key, price.captured_at, price.raw_payload_id),
                ('unit_cost', unit.key, unit.captured_at, unit.raw_payload_id),
                ('fx_unit_cost', unit_fx.source, unit_fx.captured_at, unit_fx.raw_payload_id),
                ('freight', quote.key, quote.captured_at, quote.raw_payload_id),
                ('fx_freight', quote.fx_source, quote.fx_at, quote.fx_payload)
            ) AS trace(name, source, at, payload)
            WHERE trace.source IS NOT NULL
        ) AS sources,
        LEAST(
            price.captured_at, unit.captured_at, unit_fx.captured_at, quote.captured_at,
            quote.fx_at
        ) AS as_of
    FROM (
        SELECT listings.id FROM listings
        WHERE listings.product_id = p.id
          AND listings.supplier_id IS NOT NULL
          AND listings.delisted_at IS NULL
        UNION ALL
        SELECT NULL  -- costed with no supplier; used only when the product has none
    ) l
    LEFT JOIN LATERAL (  -- the latest supplier snapshot, if it has a price: never an older one
        SELECT * FROM (
            SELECT snap.price_min_minor AS minor, snap.currency, snap.captured_at,
                   snap.raw_payload_id, src.key
            FROM listing_snapshots snap
            JOIN raw_payloads payload ON payload.id = snap.raw_payload_id
            JOIN sources src ON src.id = payload.source_id
            WHERE snap.listing_id = l.id
            ORDER BY snap.captured_at DESC, snap.id DESC
            LIMIT 1
        ) latest
        WHERE latest.minor IS NOT NULL
    ) unit ON true
    LEFT JOIN LATERAL usd_rate(unit.currency, unit.captured_at) unit_fx ON true
    CROSS JOIN LATERAL (  -- only a single-variant listing takes a null-variant quote
        SELECT count(*) <= 1 AS single, CASE WHEN count(*) <= 1 THEN min(v.id) END AS wanted
        FROM listing_variants v
        WHERE v.listing_id = l.id AND v.delisted_at IS NULL
    ) live
    LEFT JOIN LATERAL (  -- the cheapest exact US quote at quantity 1 (DEC-250, DEC-258)
        SELECT newest.method, newest.minor, newest.currency, newest.captured_at,
               newest.raw_payload_id, newest.key, fx.rate, fx.captured_at AS fx_at,
               fx.raw_payload_id AS fx_payload, fx.source AS fx_source
        FROM (
            SELECT DISTINCT ON (ranked.origin_country, ranked.method) ranked.*
            FROM (
                SELECT so.id, so.variant_id, so.origin_country, so.method,
                       so.cost_minor AS minor, so.currency, so.captured_at, so.raw_payload_id,
                       so.observed_for, src.key,
                       max(so.observed_for)
                           OVER (PARTITION BY coalesce(so.variant_id, live.wanted)) AS day,
                       rank() OVER (
                           PARTITION BY coalesce(so.variant_id, live.wanted), so.origin_country
                           ORDER BY so.observed_for DESC, so.captured_at DESC,
                                    so.raw_payload_id DESC
                       ) AS capture
                FROM shipping_options so
                JOIN raw_payloads payload ON payload.id = so.raw_payload_id
                JOIN sources src ON src.id = payload.source_id
                WHERE so.listing_id = l.id
                  AND so.destination_country = 'US'  -- settings.default_country (v1_market)
                  AND so.quantity = 1
            ) ranked
            WHERE ranked.capture = 1
              AND ranked.observed_for = ranked.day
              AND (ranked.variant_id = live.wanted
                   OR (ranked.variant_id IS NULL AND live.single))
            ORDER BY ranked.origin_country, ranked.method, ranked.id DESC
        ) newest
        LEFT JOIN LATERAL usd_rate(newest.currency, newest.captured_at) fx ON true
        CROSS JOIN LATERAL usd_line(newest.minor, newest.currency, fx.rate, NULL) usd
        ORDER BY usd.usd IS NULL, usd.usd, newest.id DESC  -- no FX or past BIGINT: last
        LIMIT 1
    ) quote ON true
    CROSS JOIN LATERAL landed_cost(
        price.minor, unit.minor, unit.currency, unit_fx.rate,
        quote.minor, quote.currency, quote.rate,
        s.duty_default_bps, 1, false, s.customs_fee_minor,
        s.payment_fee_bps, s.payment_fee_fixed_minor, s.shopify_fee_bps,
        s.returns_bps, s.default_cpa_minor,
        CASE WHEN EXISTS (
            SELECT FROM shipping_options so
            WHERE so.listing_id = l.id AND so.destination_country = 'US' AND so.quantity = 1
        ) THEN 'freight_variant_mismatch' ELSE 'freight_missing' END
    ) cost
    -- best(): the highest complete margin; with none, the fewest missing; then the lowest id
    ORDER BY l.id IS NULL, cost.complete DESC, cost.margin_minor DESC NULLS LAST,
             cardinality(cost.missing), l.id
    LIMIT 1
) pick
WHERE p.merged_into_id IS NULL
"""

LANDED_COST_ARGS = (
    "bigint, bigint, text, numeric, bigint, text, numeric, integer, integer, boolean, bigint, "
    "integer, bigint, integer, integer, bigint, text"
)


def upgrade() -> None:
    for statement in (HALF_EVEN, USD_LINE, USD_RATE, LANDED_COST, VIEW):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW workspace_product_economics")
    op.execute(f"DROP FUNCTION landed_cost({LANDED_COST_ARGS})")
    op.execute("DROP FUNCTION usd_rate(text, timestamptz)")
    op.execute("DROP FUNCTION usd_line(numeric, text, numeric, text)")
    op.execute("DROP FUNCTION half_even(numeric, numeric)")

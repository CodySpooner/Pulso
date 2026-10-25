import {
  Activity,
  Bell,
  BookOpen,
  Bookmark,
  CalendarDays,
  CircleDollarSign,
  Columns3,
  Compass,
  DatabaseZap,
  FlaskConical,
  GitMerge,
  LayoutGrid,
  ListOrdered,
  Megaphone,
  MessageSquareText,
  Palette,
  PenLine,
  Settings,
  SlidersHorizontal,
  Star,
  Store,
  Target,
  Trophy,
  type LucideIcon,
} from "lucide-react";

// One nav config feeds the sidebar, the mobile sheet, the bottom bar, breadcrumbs, the Ctrl+K palette and
// the "coming in Phase N" pages (vault Design/App Shell & Navigation). `CURRENT_PHASE` is the phase in progress, the
// feature flag that moves with the build. A route is built once its phase is done, or earlier with `built` (DEC-284).

export const CURRENT_PHASE = 3;

export const PHASES = [
  "Foundation",
  "Data engine",
  "Core product",
  "Signals expansion",
  "Scores & workflow",
  "AI layer",
  "Forecasting",
  "Store operations",
  "Expansion & launch",
] as const;

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Phase that ships the route (SPEC §11). */
  phase: number;
  /** What the page will show; used by the palette and the coming-soon page. */
  summary: string;
  /** Built before its phase is done: a task of that phase shipped it. */
  built?: true;
}

export interface NavGroup {
  label: string | null;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    label: null,
    items: [
      { label: "Daily Pulse", href: "/", icon: Activity, phase: 0, summary: "What changed overnight and what deserves attention today." },
      { label: "Alerts", href: "/alerts", icon: Bell, phase: 4, summary: "Alerts that fired when a product crossed one of your rules. Each fires once per crossing." },
    ],
  },
  {
    label: "Research",
    items: [
      { label: "Discover", href: "/discover", icon: Compass, phase: 2, built: true, summary: "Trending products with lifecycle stage, trend score, margin and freshness on every row." },
      { label: "Google popular", href: "/google-popular", icon: ListOrdered, phase: 2, built: true, summary: "Google's weekly ranking of what US shoppers buy, from your Merchant Center report, big brands hidden." },
      { label: "Amazon ranks", href: "/amazon", icon: Trophy, phase: 3, built: true, summary: "Amazon Best Sellers and Movers & Shakers ranks from the CSV files you import, each list on its own." },
      { label: "Screener", href: "/screener", icon: SlidersHorizontal, phase: 4, summary: "Filter every tracked product by any metric and save the screens you reuse." },
      { label: "Compare", href: "/compare", icon: Columns3, phase: 8, summary: "Up to four products side by side: demand, suppliers, margin and risk." },
      { label: "Niches", href: "/niches", icon: LayoutGrid, phase: 8, summary: "Categories ranked by growth, saturation and margin." },
      { label: "Seasonality", href: "/calendar", icon: CalendarDays, phase: 8, summary: "Upcoming retail events with the products that rose before them last year." },
    ],
  },
  {
    label: "Competitors",
    items: [
      { label: "Store Spy", href: "/stores", icon: Store, phase: 3, summary: "Tracked competitor stores: catalog size, launches, price changes and best sellers." },
      { label: "Ad Intelligence", href: "/ads", icon: Megaphone, phase: 8, summary: "Ads from Meta Ad Library and TikTok, linked to the products they promote." },
    ],
  },
  {
    label: "Workflow",
    items: [
      { label: "Watchlists", href: "/watchlists", icon: Star, phase: 4, summary: "Products you are watching, with 30-day sparklines and daily change." },
      { label: "Boards", href: "/boards", icon: Bookmark, phase: 4, summary: "Saved collections of products and notes for an idea or a niche." },
      { label: "Testing", href: "/testing", icon: FlaskConical, phase: 4, summary: "Your product tests from idea to winner or kill, with spend, revenue and ROAS." },
    ],
  },
  {
    label: "AI",
    items: [
      { label: "Ask Pulso", href: "/ask", icon: MessageSquareText, phase: 5, summary: "Questions about your data, answered with the numbers and sources it used." },
      { label: "Creative Studio", href: "/studio", icon: PenLine, phase: 5, summary: "Ad angles, hooks and product copy drafted from reviews and competitor pages." },
    ],
  },
  {
    label: "Business",
    items: [
      { label: "Profit", href: "/profit", icon: CircleDollarSign, phase: 7, summary: "Revenue, costs and margin from your Shopify orders and ad spend." },
    ],
  },
  {
    label: "Trust",
    items: [
      { label: "Track Record", href: "/track-record", icon: Target, phase: 6, summary: "How accurate Pulso's forecasts have been, published as they resolve." },
      { label: "Methodology", href: "/methodology", icon: BookOpen, phase: 4, summary: "How every score is computed and where each number comes from." },
    ],
  },
  {
    label: "Admin",
    items: [
      { label: "Data Health", href: "/admin/data-health", icon: DatabaseZap, phase: 1, summary: "Every source's last run, status, rows, errors and freshness, with gaps flagged." },
      { label: "Matching", href: "/admin/matching", icon: GitMerge, phase: 2, built: true, summary: "Confirm, merge or split possible product matches across sources." },
      { label: "UI gallery", href: "/admin/ui", icon: Palette, phase: 0, summary: "Every design token, type style, control, state and motion sample in one place." },
    ],
  },
];

export const settingsItem: NavItem = {
  label: "Settings",
  href: "/settings",
  icon: Settings,
  phase: 2,
  built: true,
  summary: "Default country, currency, fee assumptions and target margin.",
};

/** Detail routes with no sidebar item: they highlight their parent and show its breadcrumb. */
const detailRoutes = [
  { prefix: "/products/", label: "Product", parentHref: "/discover", phase: 2, summary: "One product's demand, suppliers, sellers, profit and risk in one place." },
  { prefix: "/stores/", label: "Store", parentHref: "/stores", phase: 3, summary: "One competitor store's catalog, launches and price changes." },
];

export const allNavItems: NavItem[] = [...navGroups.flatMap((g) => g.items), settingsItem];

export function isBuilt(item: Pick<NavItem, "phase" | "built">): boolean {
  return item.built === true || item.phase < CURRENT_PHASE;
}

export interface ResolvedRoute {
  item: NavItem;
  group: string | null;
  /** The sidebar item to highlight (the parent for detail routes). */
  activeHref: string;
  /** Set on detail routes, e.g. "Product". */
  detail?: string;
}

function groupOf(href: string): string | null {
  return navGroups.find((g) => g.items.some((i) => i.href === href))?.label ?? null;
}

export function resolveRoute(pathname: string): ResolvedRoute | undefined {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const item = allNavItems.find((i) => i.href === path);
  if (item) return { item, group: groupOf(item.href), activeHref: item.href };

  const detail = detailRoutes.find((d) => path.startsWith(d.prefix) && !path.slice(d.prefix.length).includes("/"));
  if (!detail || path.length === detail.prefix.length) return undefined;
  const parent = allNavItems.find((i) => i.href === detail.parentHref)!;
  return {
    item: { ...parent, label: detail.label, href: path, phase: detail.phase, summary: detail.summary },
    group: parent.label,
    activeHref: parent.href,
    detail: detail.label,
  };
}

# Dashboard UI

The analytics dashboard the Staff Portal links to. A Next.js app that reads the
registry database directly and renders one screen: coverage, demographics, land
tenure and the registration trend, filtered by geography, farming type and
record state.

```
http://dashboard.localtest.me:3001
```

It is reached from the **Dashboard** button in the portal header, and its
**Back** button returns to whatever page that click came from.

## Why it is a separate service

The Staff Portal is published by the registry platform as a prebuilt Next.js
image. This repo adds no frontend code to it — the register the portal renders is
described by the metadata `farmer-extension` seeds, not by a build. That leaves
no way to add a route to the portal and no way to add a component to it, so the
dashboard runs on its own origin and the portal only gains a link.

That link is added by `docker/staff-ui/assets/patch-dashboard-nav.js`, which
rewrites the compiled bundle at image build time to insert a Dashboard control
immediately left of Configuration. It appends the page it left behind as
`?returnUrl=`, which is what Back reads.

`lib/return-url.ts` only follows a `returnUrl` whose origin is
`NEXT_PUBLIC_PORTAL_URL`; anything else falls back to the portal root, so the
parameter cannot be used to bounce a signed-in user to an arbitrary site.

## Where the numbers come from

Two databases, both read-only:

| Connection | Holds | Used for |
|---|---|---|
| `DB_*` — the registry | `g2p_register_farmers`, `_lands`, `_households`, `_change_requests` | Every count, area and trend on screen |
| `MD_DB_*` — master data | `g2p_geo_levels`, `g2p_geo_level_values` | The geography cascade, the level names, and the denominators behind Geographic Coverage |

There is no fixture, sample constant or fallback dataset in this path. An empty
registry renders empty panels.

Master Data is needed because the registry stores the units a record sits in but
not the catalogue they came from — counting coverage in the registry alone could
only ever report "100% of the places we have reached". Where no country pack is
loaded, the geography filters fall back to the units the register itself has
records in and the coverage panel reports no data rather than inventing a total.

`lib/chart-queries.ts` holds the SQL. Its `SCOPE` CTE resolves a farmer's
geography, holding and approval state once, and every panel selects from it —
including the CSV export, so a downloaded file is the same set of records the
panels were drawn from by construction.

### Things this registry names differently

The dashboard was ported from a deployment built around Ethiopia, and three
things did not carry over unchanged:

- **Level names are read from the country pack**, not hard-coded. The Kamuntu
  pack this stack seeds calls them Region / District / Ward / Village; the
  variables in the code still use the Ethiopian names for the same positions.
- **PSNP participation** has no counterpart here. The safety-net population this
  register does record is farmers whose `source_of_income` is government or NGO
  support, and the panel says so rather than relabelling it PSNP.
- **Record state** is the approval status of a record's most recent change
  request. A farmer that never went through one is already in the register,
  which is what `APPROVED` means here.

### The map panel

`public/maps` carries Ethiopian boundaries, matched on P-code. A deployment whose
country pack is something else stores different ids — Kamuntu uses slug paths
like `kamuntu/chakula` — so no boundary would ever match and the choropleth would
draw a foreign outline with every unit at zero. When nothing matches, the panel
renders a ranked breakdown instead, clickable to drill down in the same way.

To get a real map, replace the three `.topojson.br` files with the country's own
boundaries carrying its `level_value_id`s as `admin1Pcod` / `admin2Pcod` /
`admin3Pcod`.

## Configuration

See `.env.example`. In the compose stack these are set on the `dashboard-ui`
service in `docker-compose.yml` instead.

`NEXT_PUBLIC_PORTAL_URL` is baked into the client bundle at build time, so
changing it needs a rebuild — as does `DASHBOARD_URL`, which is compiled into the
portal's bundle by the patch script.

## Developing

```bash
cd dashboard-ui
npm install
cp .env.example .env.local     # points at the compose stack's Postgres
npm run dev
```

The compose stack must be up for there to be a database to read.

`package-lock.json` has to be resolved under Linux, because `npm ci` in the image
rejects a macOS-resolved tree:

```bash
docker run --rm -v "$PWD":/w -w /w node:24-slim npm install --package-lock-only
```

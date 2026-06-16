# Spurs Analytics MCP

A governed data pipeline for NBA ticketing and attendance data, exposed to AI agents through a Model Context Protocol (MCP) server — not just another dashboard.

**[→ Live Dashboard](https://sirilahari10.github.io/spurs-analytics-mcp)**

---

## Why MCP instead of just an API or a dashboard

I built this after reading SS&E's job posting more carefully than I usually do — the language about "governed context layers" and letting "internal tools and agents interact with enterprise data safely" stood out, because that's a genuinely different problem than building a dashboard.

A dashboard answers questions a person already knows to ask. An MCP server lets an *agent* ask new questions on the fly — "how did marquee games perform compared to standard nights" — without that exact query being pre-built anywhere. The tradeoff is you have to think much more carefully about what you expose and how you document it, because the agent has no other context about your data than what the tool descriptions give it. That's the part I found most interesting to actually build.

## What it does

1. **Python ETL** extracts raw ticketing, attendance, and fan engagement data, transforms it into a governed two-table model (game-level facts + seat-tier breakdown), and emits a data dictionary alongside it
2. **Node.js MCP server** exposes that governed model as four typed tools — not raw SQL access, not a REST dump, but specific, documented operations an agent can call safely
3. **Dashboard** visualizes the resulting data model and shows a live sample of an actual tool call against the running server

## The data model

Two tables, each with a documented grain and primary key (see `data/data_dictionary.json`):

- **`game_performance`** — one row per home game (41 rows). Ticket sales aggregated up from seat-tier level, joined with attendance and fan engagement signals.
- **`seat_tier_sales`** — one row per game per seat tier (205 rows). Pricing, sellthrough, and channel mix (season ticket / secondary market / mobile app) at the tier level.

I kept these as two separate tables instead of one denormalized mega-table because they're genuinely different grains, and collapsing them would have made the seat-tier channel-mix data either duplicated five times per game or lost entirely.

## MCP tools

| Tool | Purpose |
|---|---|
| `list_games` | Browse games with filters (opponent tier, min sellthrough, promo nights) |
| `get_game_detail` | Full fact + seat-tier breakdown for one game |
| `query_revenue_summary` | Pre-aggregated stats — avoids agents pulling 41 rows just to average them |
| `get_data_dictionary` | Self-describing schema, so an agent can check what's available before querying |

`get_data_dictionary` was an afterthought that turned out to matter more than I expected — without it, an agent has to guess column names from tool output alone, which works until it doesn't.

## Tested

I ran the server through a manual JSON-RPC handshake (initialize → list tools → call each tool) before trusting it, since MCP servers fail silently in ways that are hard to debug from the client side. All four tools return correctly, including the error path for an invalid `game_id`.

```
✓ initialize handshake
✓ tools/list returns all 4 tools with schemas
✓ get_data_dictionary returns full schema
✓ list_games with filters (opponent_tier: marquee) returns 9 games
✓ get_game_detail returns game + seat tier breakdown
✓ get_game_detail with invalid id returns isError: true
✓ query_revenue_summary aggregates correctly across filtered subset
```

## Limitations

- **Synthetic data** — calibrated to realistic NBA arena economics (capacity, tier pricing, sellthrough patterns) but not real SS&E data, obviously.
- **Read-only, no write tools** — intentional for a demo, but a production version would need write tools (e.g., flagging a game for pricing review) with appropriate guardrails.
- **No auth layer** — runs locally over stdio. A real deployment would need to think about which agents/users get which tool access.
- **Flat JSON storage** — I'd planned to use SQLite for the governed layer but hit a native build issue in this sandboxed environment (better-sqlite3 needs compiled bindings). JSON files work fine at this data volume; at real scale this would move to an actual warehouse, which is a one-line config change since the MCP server only talks to the data access layer, not the files directly.

## Stack

```
Python 3.11        — ETL: pandas, raw extract → governed model
Node.js / JS (ESM)  — MCP server: @modelcontextprotocol/sdk, zod for schema validation
Chart.js            — dashboard visualization
```

## Run it

```bash
git clone https://github.com/sirilahari10/spurs-analytics-mcp
cd spurs-analytics-mcp

# 1. Generate + transform data
pip install -r requirements.txt
python etl/generate_data.py
python etl/transform.py

# 2. Run the MCP server
npm install
node mcp_server/server.js

# 3. (optional) Inspect it interactively
npx @modelcontextprotocol/inspector node mcp_server/server.js
```

## About

**Siri Lahari Chava** — Data Scientist at Moderna, background in ML and computer vision.

[LinkedIn](https://linkedin.com/in/sirilahari) · [GitHub](https://github.com/sirilahari10)

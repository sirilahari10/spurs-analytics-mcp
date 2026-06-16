/**
 * server.js
 *
 * MCP server exposing governed Spurs game-performance and seat-tier data
 * to AI agents. This is the "governed context layer" piece — agents (or
 * Claude Desktop, or any MCP client) get read-only, schema-documented
 * access to the curated data model built by etl/transform.py, not the
 * raw source extracts.
 *
 * Tools exposed:
 *   - list_games             browse games with optional filters
 *   - get_game_detail        full fact + seat-tier breakdown for one game
 *   - query_revenue_summary  aggregate revenue stats across a filter
 *   - get_data_dictionary    self-describing schema, so an agent can introspect
 *                            the model before querying it
 *
 * Run: node mcp_server/server.js
 * Inspect with the MCP Inspector: npx @modelcontextprotocol/inspector node mcp_server/server.js
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, "..", "data");

function loadJSON(filename) {
  return JSON.parse(readFileSync(join(DATA_DIR, filename), "utf-8"));
}

// Load the governed data model once at startup. In a production version
// this would hit a real warehouse (Snowflake / Azure SQL per the JD) —
// here it's the curated JSON the ETL layer produced, which keeps this
// demo runnable with zero external dependencies.
const games = loadJSON("game_performance.json");
const seatTiers = loadJSON("seat_tier_sales.json");
const dataDictionary = loadJSON("data_dictionary.json");

const server = new McpServer({
  name: "spurs-analytics-mcp",
  version: "1.0.0",
});

// ── Tool: list_games ────────────────────────────────────────────────────────
server.registerTool(
  "list_games",
  {
    title: "List Games",
    description:
      "Browse home games with optional filters. Returns game_id, date, opponent, " +
      "sellthrough, attendance, and revenue for each matching game.",
    inputSchema: {
      opponent_tier: z
        .enum(["rival", "marquee", "division", "standard"])
        .optional()
        .describe("Filter by opponent demand tier"),
      min_sellthrough: z
        .number()
        .min(0)
        .max(1)
        .optional()
        .describe("Only return games with overall_sellthrough >= this value"),
      promo_night_only: z.boolean().optional().describe("If true, only return promo nights"),
      limit: z.number().int().positive().max(41).default(10).describe("Max rows to return"),
    },
  },
  async ({ opponent_tier, min_sellthrough, promo_night_only, limit }) => {
    let results = games;

    if (opponent_tier) {
      results = results.filter((g) => g.opponent_tier === opponent_tier);
    }
    if (min_sellthrough !== undefined) {
      results = results.filter((g) => g.overall_sellthrough >= min_sellthrough);
    }
    if (promo_night_only) {
      results = results.filter((g) => g.is_promo_night === 1);
    }

    results = results.slice(0, limit ?? 10);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              count: results.length,
              games: results.map((g) => ({
                game_id: g.game_id,
                game_date: g.game_date,
                opponent: g.opponent,
                opponent_tier: g.opponent_tier,
                overall_sellthrough: g.overall_sellthrough,
                attendance: g.attendance,
                total_revenue: g.total_revenue,
              })),
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// ── Tool: get_game_detail ───────────────────────────────────────────────────
server.registerTool(
  "get_game_detail",
  {
    title: "Get Game Detail",
    description:
      "Full performance detail for a single game, including the seat-tier-level " +
      "breakdown (pricing, sellthrough, channel mix per tier).",
    inputSchema: {
      game_id: z.string().describe("Game identifier, e.g. GAME-014"),
    },
  },
  async ({ game_id }) => {
    const game = games.find((g) => g.game_id === game_id);
    if (!game) {
      return {
        content: [{ type: "text", text: `No game found with id ${game_id}` }],
        isError: true,
      };
    }
    const tiers = seatTiers.filter((t) => t.game_id === game_id);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ game, seat_tiers: tiers }, null, 2),
        },
      ],
    };
  }
);

// ── Tool: query_revenue_summary ─────────────────────────────────────────────
server.registerTool(
  "query_revenue_summary",
  {
    title: "Query Revenue Summary",
    description:
      "Aggregate revenue and attendance stats, optionally filtered by opponent tier " +
      "or promo night status. Useful for answering 'how did marquee games perform vs " +
      "standard games' type questions without pulling raw rows.",
    inputSchema: {
      opponent_tier: z
        .enum(["rival", "marquee", "division", "standard"])
        .optional()
        .describe("Filter to a single opponent demand tier before aggregating"),
      promo_night_only: z.boolean().optional(),
    },
  },
  async ({ opponent_tier, promo_night_only }) => {
    let subset = games;
    if (opponent_tier) subset = subset.filter((g) => g.opponent_tier === opponent_tier);
    if (promo_night_only) subset = subset.filter((g) => g.is_promo_night === 1);

    if (subset.length === 0) {
      return { content: [{ type: "text", text: "No games matched that filter." }] };
    }

    const sum = (arr, key) => arr.reduce((acc, g) => acc + g[key], 0);
    const avg = (arr, key) => sum(arr, key) / arr.length;

    const summary = {
      games_matched: subset.length,
      total_revenue: Math.round(sum(subset, "total_revenue")),
      avg_revenue_per_game: Math.round(avg(subset, "total_revenue")),
      avg_sellthrough: Number(avg(subset, "overall_sellthrough").toFixed(3)),
      avg_attendance: Math.round(avg(subset, "attendance")),
      avg_fan_satisfaction: Number(avg(subset, "avg_fan_satisfaction").toFixed(2)),
    };

    return { content: [{ type: "text", text: JSON.stringify(summary, null, 2) }] };
  }
);

// ── Tool: get_data_dictionary ───────────────────────────────────────────────
server.registerTool(
  "get_data_dictionary",
  {
    title: "Get Data Dictionary",
    description:
      "Returns the governed schema documentation for this dataset — table grain, " +
      "primary keys, and column definitions. Call this first if you're unsure what " +
      "fields are available before querying.",
    inputSchema: {},
  },
  async () => {
    return { content: [{ type: "text", text: JSON.stringify(dataDictionary, null, 2) }] };
  }
);

// ── Start server over stdio ──────────────────────────────────────────────────
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Spurs Analytics MCP server running on stdio");
}

main().catch((err) => {
  console.error("Fatal error starting MCP server:", err);
  process.exit(1);
});

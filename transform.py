"""
transform.py

ETL transform layer. Takes raw extracted CSVs and builds a governed,
documented data model: a single denormalized "game performance" fact
table plus dimension lookups. This is the layer the MCP server reads
from — never the raw extracts directly. Keeping a transform step here
means the MCP server's schema can stay stable even if upstream source
data changes shape.
"""

import pandas as pd
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_raw():
    games = pd.read_csv(DATA_DIR / "games.csv")
    sales = pd.read_csv(DATA_DIR / "ticket_sales.csv")
    engagement = pd.read_csv(DATA_DIR / "fan_engagement.csv")
    return games, sales, engagement


def build_game_performance_fact(games, sales, engagement):
    """
    One row per game. Aggregates seat-tier sales up to game level and
    joins fan engagement signals. This is the primary table the MCP
    server's `query_games` tool reads from.
    """
    sales_agg = sales.groupby("game_id").agg(
        total_tickets_sold=("tickets_sold", "sum"),
        total_capacity=("tier_capacity", "sum"),
        total_ticket_revenue=("revenue", "sum"),
        avg_ticket_price=("avg_ticket_price", "mean"),
        avg_secondary_market_pct=("secondary_market_pct", "mean"),
    ).reset_index()
    sales_agg["overall_sellthrough"] = (sales_agg["total_tickets_sold"] / sales_agg["total_capacity"]).round(3)
    sales_agg["avg_ticket_price"] = sales_agg["avg_ticket_price"].round(2)
    sales_agg["avg_secondary_market_pct"] = sales_agg["avg_secondary_market_pct"].round(3)

    fact = games.merge(sales_agg, on="game_id", how="left")
    fact = fact.merge(engagement, on="game_id", how="left")

    fact["total_revenue"] = (fact["total_ticket_revenue"] + fact["concessions_revenue"] + fact["merch_revenue"]).round(2)
    fact["revenue_per_attendee"] = (fact["total_revenue"] / fact["attendance"]).round(2)

    cols = [
        "game_id", "game_date", "day_of_week", "opponent", "opponent_tier",
        "is_promo_night", "season", "total_tickets_sold", "total_capacity",
        "overall_sellthrough", "avg_ticket_price", "total_ticket_revenue",
        "avg_secondary_market_pct", "attendance", "attendance_pct",
        "app_checkins", "concessions_revenue", "merch_revenue",
        "social_mentions", "avg_fan_satisfaction", "total_revenue",
        "revenue_per_attendee"
    ]
    return fact[cols]


def build_seat_tier_dim(sales):
    """Per-game, per-tier breakdown — kept separate since it's a different grain than the fact table."""
    return sales[[
        "game_id", "seat_tier", "tier_capacity", "tickets_sold",
        "sellthrough_rate", "avg_ticket_price", "revenue",
        "season_ticket_pct", "secondary_market_pct", "mobile_app_pct"
    ]]


def build_data_dictionary(fact_cols, tier_cols):
    """Generates the data dictionary that ships alongside the model — required for the
    'governed dataset' framing this is meant to demonstrate."""
    return {
        "game_performance": {
            "grain": "one row per home game",
            "primary_key": "game_id",
            "columns": {
                "game_id": "Unique game identifier, format GAME-NNN",
                "game_date": "Date of game, YYYY-MM-DD",
                "opponent": "Visiting team name",
                "opponent_tier": "Demand classification: rival / marquee / division / standard",
                "is_promo_night": "1 if a promotional giveaway night, else 0",
                "total_tickets_sold": "Sum of tickets sold across all seat tiers",
                "overall_sellthrough": "total_tickets_sold / total_capacity",
                "avg_ticket_price": "Capacity-weighted average ticket price across tiers",
                "total_ticket_revenue": "Sum of ticket revenue across all tiers, USD",
                "attendance": "Actual scanned attendance (may differ from tickets sold)",
                "attendance_pct": "attendance / arena capacity",
                "app_checkins": "Number of fans who checked in via team app",
                "total_revenue": "Ticket + concessions + merch revenue, USD",
                "revenue_per_attendee": "total_revenue / attendance, USD"
            }
        },
        "seat_tier_sales": {
            "grain": "one row per game per seat tier (5 tiers x 41 games)",
            "primary_key": "game_id + seat_tier",
            "columns": {
                "seat_tier": "Courtside / Lower Bowl / Club Level / Upper Bowl / Nosebleed",
                "sellthrough_rate": "tickets_sold / tier_capacity for that tier",
                "season_ticket_pct": "Share of tier tickets from season ticket holders",
                "secondary_market_pct": "Share of tier tickets resold via secondary market",
                "mobile_app_pct": "Share of tier tickets purchased via mobile app"
            }
        }
    }


def run():
    games, sales, engagement = load_raw()

    fact = build_game_performance_fact(games, sales, engagement)
    tier_dim = build_seat_tier_dim(sales)
    data_dict = build_data_dictionary(fact.columns.tolist(), tier_dim.columns.tolist())

    fact.to_csv(DATA_DIR / "game_performance.csv", index=False)
    tier_dim.to_csv(DATA_DIR / "seat_tier_sales.csv", index=False)

    with open(DATA_DIR / "data_dictionary.json", "w") as f:
        json.dump(data_dict, f, indent=2)

    # Also emit a single JSON the MCP server can load directly without
    # a pandas dependency at runtime (keeps the server lightweight)
    fact_json = fact.to_dict(orient="records")
    tier_json = tier_dim.to_dict(orient="records")

    with open(DATA_DIR / "game_performance.json", "w") as f:
        json.dump(fact_json, f, indent=2)
    with open(DATA_DIR / "seat_tier_sales.json", "w") as f:
        json.dump(tier_json, f, indent=2)

    print(f"✓ game_performance: {len(fact)} rows -> data/game_performance.csv + .json")
    print(f"✓ seat_tier_sales: {len(tier_dim)} rows -> data/seat_tier_sales.csv + .json")
    print(f"✓ data_dictionary.json written")
    print(f"\nSeason summary:")
    print(f"  Total revenue: ${fact['total_revenue'].sum():,.0f}")
    print(f"  Avg sellthrough: {fact['overall_sellthrough'].mean():.1%}")
    print(f"  Avg attendance: {fact['attendance'].mean():,.0f}")


if __name__ == "__main__":
    run()

"""
generate_data.py

Generates synthetic NBA ticketing, attendance, and fan engagement data
for the Frost Bank Center, calibrated to realistic NBA arena benchmarks
(capacity ~18,400, avg ticket $65-180 depending on tier/opponent).

This data feeds the ETL pipeline, which loads it into the governed
data model that the MCP server exposes to AI agents and BI tools.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

np.random.seed(11)

ARENA_CAPACITY = 18418
SEAT_TIERS = ["Courtside", "Lower Bowl", "Club Level", "Upper Bowl", "Nosebleed"]
TIER_BASE_PRICE = {"Courtside": 850, "Lower Bowl": 220, "Club Level": 165, "Upper Bowl": 95, "Nosebleed": 48}
TIER_CAPACITY_PCT = {"Courtside": 0.01, "Lower Bowl": 0.18, "Club Level": 0.12, "Upper Bowl": 0.45, "Nosebleed": 0.24}

OPPONENTS = [
    ("Dallas Mavericks", "rival", 1.35), ("Houston Rockets", "rival", 1.25),
    ("Los Angeles Lakers", "marquee", 1.55), ("Golden State Warriors", "marquee", 1.45),
    ("Boston Celtics", "marquee", 1.30), ("Miami Heat", "standard", 1.10),
    ("Memphis Grizzlies", "division", 1.15), ("New Orleans Pelicans", "division", 1.10),
    ("Phoenix Suns", "standard", 1.05), ("Denver Nuggets", "standard", 1.10),
    ("Oklahoma City Thunder", "division", 1.20), ("Chicago Bulls", "standard", 1.0),
    ("Orlando Magic", "standard", 0.95), ("Charlotte Hornets", "standard", 0.90),
    ("Detroit Pistons", "standard", 0.85), ("Utah Jazz", "standard", 0.90),
]

DAY_TYPES = {0: 0.95, 1: 0.90, 2: 0.95, 3: 1.0, 4: 1.20, 5: 1.30, 6: 1.10}  # Mon-Sun multiplier


def generate_games(n_games=41):
    """Generate one home season's worth of games (41 home games)."""
    games = []
    start_date = datetime(2025, 10, 22)
    game_date = start_date

    for i in range(n_games):
        game_date += timedelta(days=int(np.random.choice([2, 3, 4])))
        opponent, tier, demand_mult = OPPONENTS[i % len(OPPONENTS)]
        day_mult = DAY_TYPES[game_date.weekday()]

        is_weekend_special = game_date.weekday() in [4, 5]
        is_promo_night = np.random.random() < 0.25  # bobblehead, etc.

        games.append({
            "game_id": f"GAME-{i+1:03d}",
            "game_date": game_date.strftime("%Y-%m-%d"),
            "day_of_week": game_date.strftime("%A"),
            "opponent": opponent,
            "opponent_tier": tier,
            "demand_multiplier": round(demand_mult * day_mult, 3),
            "is_promo_night": int(is_promo_night),
            "season": "2025-26"
        })
    return pd.DataFrame(games)


def generate_ticket_sales(games_df):
    """Generate seat-tier level sales for each game."""
    records = []
    for _, game in games_df.iterrows():
        for tier in SEAT_TIERS:
            tier_capacity = int(ARENA_CAPACITY * TIER_CAPACITY_PCT[tier])
            base_price = TIER_BASE_PRICE[tier]

            # Sell-through rate driven by demand multiplier + some noise
            base_sellthrough = 0.72
            sellthrough = base_sellthrough * game["demand_multiplier"]
            sellthrough += np.random.normal(0, 0.05)
            if game["is_promo_night"]:
                sellthrough += 0.08
            sellthrough = np.clip(sellthrough, 0.25, 1.0)

            tickets_sold = int(tier_capacity * sellthrough)
            avg_price = base_price * (0.85 + 0.3 * game["demand_multiplier"])
            avg_price = round(avg_price, 2)

            # Channel mix
            season_ticket_pct = round(np.random.uniform(0.35, 0.55) if tier in ["Courtside", "Lower Bowl"] else np.random.uniform(0.15, 0.30), 2)
            secondary_market_pct = round(np.random.uniform(0.05, 0.20), 2)
            mobile_app_pct = round(np.random.uniform(0.30, 0.55), 2)

            records.append({
                "game_id": game["game_id"],
                "seat_tier": tier,
                "tier_capacity": tier_capacity,
                "tickets_sold": tickets_sold,
                "sellthrough_rate": round(sellthrough, 3),
                "avg_ticket_price": avg_price,
                "revenue": round(tickets_sold * avg_price, 2),
                "season_ticket_pct": season_ticket_pct,
                "secondary_market_pct": secondary_market_pct,
                "mobile_app_pct": mobile_app_pct
            })
    return pd.DataFrame(records)


def generate_fan_engagement(games_df):
    """Generate per-game fan engagement signals (app, concessions, social)."""
    records = []
    for _, game in games_df.iterrows():
        attendance_pct = np.clip(0.78 * game["demand_multiplier"] + np.random.normal(0, 0.04), 0.45, 1.0)
        attendance = int(ARENA_CAPACITY * attendance_pct)

        records.append({
            "game_id": game["game_id"],
            "attendance": attendance,
            "attendance_pct": round(attendance_pct, 3),
            "app_checkins": int(attendance * np.random.uniform(0.35, 0.60)),
            "concessions_revenue": round(attendance * np.random.uniform(14, 26), 2),
            "merch_revenue": round(attendance * np.random.uniform(3, 11), 2),
            "social_mentions": int(attendance * np.random.uniform(0.02, 0.08) * game["demand_multiplier"]),
            "avg_fan_satisfaction": round(np.clip(np.random.normal(8.1, 0.9), 4, 10), 1)
        })
    return pd.DataFrame(records)


if __name__ == "__main__":
    games = generate_games()
    sales = generate_ticket_sales(games)
    engagement = generate_fan_engagement(games)

    games.to_csv("data/games.csv", index=False)
    sales.to_csv("data/ticket_sales.csv", index=False)
    engagement.to_csv("data/fan_engagement.csv", index=False)

    print(f"Generated {len(games)} games")
    print(f"Generated {len(sales)} ticket sales records ({len(SEAT_TIERS)} tiers x {len(games)} games)")
    print(f"Generated {len(engagement)} fan engagement records")
    print(f"\nTotal season revenue: ${sales['revenue'].sum():,.0f}")
    print(f"Avg sellthrough rate: {sales['sellthrough_rate'].mean():.1%}")

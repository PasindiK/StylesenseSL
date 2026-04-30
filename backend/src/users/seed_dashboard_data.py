# Example script to seed synthetic dashboard data to MongoDB
from mongo_repository import MongoUserRepository

mongo_uri = "mongodb+srv://it22225474_db_user:Y6zTIuNbuuTIF146@stylesensesl.ddx4ok0.mongodb.net/"
repo = MongoUserRepository(mongo_uri)

# Example synthetic dashboard data
synthetic_dashboard_data = [
    {"dashboard_id": "1", "metric": "active_users", "value": 1200, "timestamp": "2026-03-08T10:00:00"},
    {"dashboard_id": "1", "metric": "sales", "value": 350, "timestamp": "2026-03-08T10:00:00"},
    {"dashboard_id": "2", "metric": "inventory", "value": 500, "timestamp": "2026-03-08T10:00:00"},
    {"dashboard_id": "2", "metric": "returns", "value": 15, "timestamp": "2026-03-08T10:00:00"}
]

repo.seed_dashboard_data(synthetic_dashboard_data)
print("Synthetic dashboard data seeded successfully.")

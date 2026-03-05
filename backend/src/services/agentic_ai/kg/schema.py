KG_SCHEMA_QUERIES = [
    "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
    "CREATE CONSTRAINT product_id_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
    "CREATE CONSTRAINT shop_id_unique IF NOT EXISTS FOR (s:Shop) REQUIRE s.shop_id IS UNIQUE",
    "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT color_name_unique IF NOT EXISTS FOR (c:Color) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT style_name_unique IF NOT EXISTS FOR (s:StyleTag) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT brand_name_unique IF NOT EXISTS FOR (b:Brand) REQUIRE b.name IS UNIQUE",
    "CREATE INDEX interaction_ts_idx IF NOT EXISTS FOR ()-[r:VIEWED]-() ON (r.ts)",
    "CREATE INDEX add_to_cart_ts_idx IF NOT EXISTS FOR ()-[r:ADDED_TO_CART]-() ON (r.ts)",
    "CREATE INDEX purchase_ts_idx IF NOT EXISTS FOR ()-[r:PURCHASED]-() ON (r.ts)",
]

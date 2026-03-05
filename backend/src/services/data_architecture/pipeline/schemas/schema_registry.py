from pyspark.sql.types import StructType, StructField, IntegerType, StringType, DoubleType, BooleanType, TimestampType
import os
import json
from datetime import datetime

# Path for persisted schema versions (kept alongside metadata used by drift module)
METADATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'metadata')
SCHEMA_VERSIONS_FILE = os.path.join(METADATA_DIR, 'schema_registry_versions.json')
os.makedirs(METADATA_DIR, exist_ok=True)

# Define schemas for each dataset
SCHEMAS = {
    'products': StructType([
        StructField('product_id', IntegerType(), False),  # False = NOT NULL
        StructField('shop_id', IntegerType(), False),
        StructField('name', StringType(), True),
        StructField('category', StringType(), True),
        StructField('color', StringType(), True),
        StructField('fabric', StringType(), True),
        StructField('size_range', StringType(), True),
        StructField('price_LKR', IntegerType(), True),
        StructField('style_tags', StringType(), True),
        StructField('product_url', StringType(), True),
        StructField('created_ts', StringType(), True),
        StructField('popularity_score', DoubleType(), True),
        StructField('stock_count', IntegerType(), True),
    ]),
    
    'users': StructType([
        StructField('user_id', IntegerType(), False),
        StructField('name', StringType(), True),
        StructField('email', StringType(), True),
        StructField('phone', StringType(), True),
        StructField('shipping_address', StringType(), True),
        StructField('signup_ts', StringType(), True),
        StructField('is_active', BooleanType(), True),
    ]),
    
    'transactions': StructType([
        StructField('transaction_id', IntegerType(), False),
        StructField('user_id', IntegerType(), False),
        StructField('product_id', IntegerType(), False),
        StructField('shop_id', IntegerType(), False),
        StructField('quantity', IntegerType(), True),
        StructField('unit_price', IntegerType(), True),
        StructField('total_amount', DoubleType(), True),
        StructField('discount_percent', IntegerType(), True),
        StructField('discount_amount', DoubleType(), True),
        StructField('tax_percent', IntegerType(), True),
        StructField('tax_amount', DoubleType(), True),
        StructField('final_amount', DoubleType(), True),
        StructField('payment_method', StringType(), True),
        StructField('transaction_status', StringType(), True),
        StructField('transaction_date', StringType(), True),
        StructField('transaction_ts', StringType(), True),
        StructField('delivery_date', StringType(), True),
    ]),
    
    'shops': StructType([
        StructField('shop_id', IntegerType(), False),
        StructField('shop_name', StringType(), True),
        StructField('location', StringType(), True),
        StructField('district', StringType(), True),
        StructField('postal_code', StringType(), True),
        StructField('phone_number', StringType(), True),
        StructField('is_active', BooleanType(), True),
        StructField('operating_hours_open', StringType(), True),
        StructField('operating_hours_close', StringType(), True),
    ]),
}

def get_schema(table_name):
    """Get schema for a specific table.

    Behavior:
    - If a persisted schema registry exists at `metadata/schema_registry_versions.json`,
      return the latest registered schema for `table_name`.
    - Otherwise, fall back to the in-memory `SCHEMAS` defaults defined above.
    This allows automated drift handlers to bump versions and have the pipeline
    pick up the persisted version as the current expected schema.
    """
    # Try to read persisted versions
    try:
        if os.path.exists(SCHEMA_VERSIONS_FILE):
            with open(SCHEMA_VERSIONS_FILE, 'r', encoding='utf-8') as f:
                versions = json.load(f)
            table_versions = versions.get(table_name)
            if table_versions:
                # latest is last element
                latest = table_versions[-1]['schema']
                # reconstruct StructType from dict
                fields = []
                from pyspark.sql.types import StringType, StructField
                for col, dtype in latest.items():
                    # stored dtype strings may be simple; default to StringType for unknown
                    # This reconstruction is conservative and sets fields nullable=True
                    fields.append(StructField(col, StringType(), True))
                return StructType(fields)
    except Exception:
        # if any error reading persisted registry, fall back to defaults
        pass

    return SCHEMAS.get(table_name)

def print_all_schemas():
    """Print all available schemas"""
    for table_name, schema in SCHEMAS.items():
        print(f"\n {table_name.upper()} Schema:")
        for field in schema.fields:
            print(f"   - {field.name} ({field.dataType.simpleString()}) - Nullable: {field.nullable}")

if __name__ == "__main__":
    print_all_schemas()
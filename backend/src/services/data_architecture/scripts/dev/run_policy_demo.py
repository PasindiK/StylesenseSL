from pyspark.sql import SparkSession
import pandas as pd
from scripts.schema_drift import handle_schema_drift


def main():
    spark = SparkSession.builder.master("local[1]").appName("policy-demo").getOrCreate()

    # build a small pandas DataFrame that contains new columns to trigger drift
    data = {
        "product_id": [1001, 1002],
        "shop_id": [1, 1],
        "name": ["Demo A", "Demo B"],
        "category": ["TEST", "TEST"],
        "color": ["red", "blue"],
        # new unexpected columns
        "new_feature_x": ["x", "y"],
        "new_feature_y": [1, 2],
    }
    pdf = pd.DataFrame(data)
    sdf = spark.createDataFrame(pdf)

    res = handle_schema_drift(spark, "products", sdf, "synthetic_outerwear_sri_lanka_with_shop_ids.csv", "raw/synthetic_outerwear_sri_lanka_with_shop_ids.csv")
    print("Policy inference result:", res)


if __name__ == "__main__":
    main()

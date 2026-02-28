from pathlib import Path
from src.ingestion.data_loader import DataLoader
from src.agents.catalog_agent import CatalogAgent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_catalog_agent_filters_and_enrichment():
    loader = DataLoader()
    loader.load_products("products.csv")
    # load shops if available for enrichment
    loader.load_shops("shops_dataset.csv")
    agent = CatalogAgent(loader=loader)

    # tag-based filter
    res = agent.find_by_filters(tag="casual")
    assert isinstance(res, list)
    # if there are any results, they must include shop enrichment keys
    if res:
        r = res[0]
        assert '_shop_name' in r
        assert '_shop_location' in r


def test_get_products_by_shop_and_shop_by_product():
    loader = DataLoader()
    loader.load_products("products.csv")
    loader.load_shops("shops_dataset.csv")
    agent = CatalogAgent(loader=loader)

    shop_products = agent.get_products_by_shop('1')
    assert isinstance(shop_products, list)
    # if products exist for the shop, verify shop lookup by product
    if shop_products:
        prod_id = shop_products[0]['product_id']
        shop = agent.get_shop_by_product(prod_id)
        if shop:
            assert 'shop_id' in shop

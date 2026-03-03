from src.services.agentic_ai.agents.catalog_agent import CatalogAgent
from src.ingestion.data_loader import DataLoader
import pandas as pd


# Create a loader, load the desired CSV filename, then pass the loader to the agent
class FixedCatalogAgent(CatalogAgent):
    def __init__(self, csv_path='products.csv'):
        loader = DataLoader()
        loader.load_products(csv_path)
        # now initialize base agent with a proper loader instance
        super().__init__(loader=loader)

def run_test():
    agent = FixedCatalogAgent()

    print('\nTest 6: get shop info for shop_id=1')
    shop_info = agent.loader.get_shop('1')
    print(shop_info)

    # Specific question: "Can you give me a beach wear under 5000 from FOA and give me the location of the shop and shop details?"
    print('\nSpecific Question Test 7: beach wear under 5000 from FOA')
    # find FOA shop id by name
    foa = agent.loader.shops[agent.loader.shops['shop_name'].str.contains('FOA', case=False)]
    
    if not foa.empty:
        foa_id = str(foa.iloc[0]['shop_id'])
        results = [p for p in agent.find_by_filters(category='BEACH WEAR', max_price=5000) if str(p.get('shop_id')) == foa_id]
        print('Products:', results)
        print('Shop details:', agent.loader.get_shop(foa_id))
    else:
        print('FOA shop not found in shops dataset')


if __name__ == '__main__':
    run_test()

"""
Fashion Triplet Dataset Creation & Preprocessing
Prepares training data for Sentence Transformer fine-tuning
"""
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import List, Tuple
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FashionTripletPreprocessor:
    """Create triplets for fine-tuning sentence embeddings"""
    
    def __init__(self, data_dir: str = "data/raw"):
        self.data_dir = Path(data_dir)
        self.products_df = None
        self.interactions_df = None
        self.preferences_df = None
        
    def load_data(self):
        """Load all raw data files"""
        logger.info("📂 Loading raw data files...")
        
        self.products_df = pd.read_csv(self.data_dir / "final_products.csv")
        self.interactions_df = pd.read_csv(self.data_dir / "interactions_dataset.csv")
        self.preferences_df = pd.read_csv(self.data_dir / "user_preferences_dataset.csv")
        
        logger.info(f"✅ Loaded {len(self.products_df)} products")
        logger.info(f"✅ Loaded {len(self.interactions_df)} interactions")
        logger.info(f"✅ Loaded {len(self.preferences_df)} user preferences")
        
    def check_data_quality(self):
        """Check for nulls, duplicates, and issues"""
        logger.info("\n🔍 DATA QUALITY CHECK:")
        
        # Check products
        logger.info("\n📦 Products Dataset:")
        logger.info(f"   Nulls in 'name': {self.products_df['name'].isnull().sum()}")
        logger.info(f"   Nulls in 'category': {self.products_df['category'].isnull().sum()}")
        logger.info(f"   Nulls in 'color': {self.products_df['color'].isnull().sum()}")
        logger.info(f"   Nulls in 'style_tags': {self.products_df['style_tags'].isnull().sum()}")
        logger.info(f"   Duplicates: {self.products_df['product_id'].duplicated().sum()}")
        
        # Check interactions
        logger.info("\n🔗 Interactions Dataset:")
        logger.info(f"   Nulls: {self.interactions_df.isnull().sum().sum()}")
        logger.info(f"   Unique users: {self.interactions_df['user_id'].nunique()}")
        logger.info(f"   Unique products: {self.interactions_df['product_id'].nunique()}")
        logger.info(f"   Interaction types: {self.interactions_df['interaction_type'].unique()}")
        
        # Check preferences
        logger.info("\n👤 Preferences Dataset:")
        logger.info(f"   Nulls: {self.preferences_df.isnull().sum().sum()}")
        logger.info(f"   Unique users: {self.preferences_df['user_id'].nunique()}")
        
    def clean_data(self):
        """Clean and preprocess data"""
        logger.info("\n🧹 CLEANING DATA:")
        
        # Fill nulls in products
        self.products_df['style_tags'].fillna('', inplace=True)
        self.products_df['color'].fillna('Unknown', inplace=True)
        self.products_df['fabric'].fillna('Unknown', inplace=True)
        
        # Remove duplicates
        self.products_df = self.products_df.drop_duplicates(subset=['product_id'])
        
        logger.info(f"✅ Cleaned products: {len(self.products_df)} rows")
        
    def create_product_descriptions(self):
        """Create rich text descriptions for each product"""
        logger.info("\n📝 Creating product descriptions...")
        
        def create_description(row):
            """Build description from product attributes"""
            name = str(row['name']).strip()
            category = str(row['category']).strip()
            color = str(row['color']).strip()
            fabric = str(row['fabric']).strip()
            style_tags = str(row['style_tags']).strip()
            
            # Rich description for semantic matching
            description = f"{name} {category} {color} {fabric} {style_tags}"
            return description.lower()
        
        self.products_df['description'] = self.products_df.apply(create_description, axis=1)
        logger.info(f"✅ Created descriptions for {len(self.products_df)} products")
        
        return self.products_df
        
    def create_triplets(self, num_triplets: int = 1500) -> List[Tuple[str, str, str]]:
        """
        Create triplets (anchor, positive, negative) for training
        
        Anchor: User query or product description
        Positive: Similar product (same category/color/style)
        Negative: Dissimilar product (different category/attributes)
        """
        logger.info(f"\n🎯 Creating {num_triplets} triplets...")
        
        triplets = []
        products = self.products_df.to_dict('records')
        
        # Strategy 1: Same category triplets (most effective)
        categories = self.products_df['category'].unique()
        
        for category in categories:
            cat_products = self.products_df[self.products_df['category'] == category].to_dict('records')
            
            if len(cat_products) < 2:
                continue
                
            # Create multiple triplets per category
            for i in range(min(len(cat_products) - 1, 50)):  # Max 50 per category
                anchor = cat_products[i]
                positive = cat_products[(i + 1) % len(cat_products)]
                
                # Negative: random product from different category
                neg_products = self.products_df[self.products_df['category'] != category]
                if len(neg_products) > 0:
                    negative = neg_products.sample(1).iloc[0]
                    
                    triplets.append((
                        anchor['description'],
                        positive['description'],
                        negative['description']
                    ))
        
        # Strategy 2: Color + Style triplets
        for color in self.products_df['color'].unique():
            color_products = self.products_df[self.products_df['color'] == color].to_dict('records')
            
            if len(color_products) < 2:
                continue
                
            for i in range(min(len(color_products) - 1, 30)):
                anchor = color_products[i]
                positive = color_products[(i + 1) % len(color_products)]
                
                neg_products = self.products_df[self.products_df['color'] != color]
                if len(neg_products) > 0:
                    negative = neg_products.sample(1).iloc[0]
                    
                    triplets.append((
                        anchor['description'],
                        positive['description'],
                        negative['description']
                    ))
        
        # Shuffle and limit
        np.random.shuffle(triplets)
        triplets = triplets[:num_triplets]
        
        logger.info(f"✅ Created {len(triplets)} triplets")
        
        return triplets
    
    def create_query_triplets(self, num_triplets: int = 500):
        """Create triplets based on user queries and preferences"""
        logger.info(f"\n🔍 Creating {num_triplets} query-based triplets...")
        
        query_triplets = []
        
        # Use user preferences to create semantic queries
        for _, pref in self.preferences_df.head(100).iterrows():
            user_id = pref['user_id']
            
            # Parse preferred categories
            if isinstance(pref['preferred_categories'], str):
                preferred_cats = [cat.strip() for cat in pref['preferred_categories'].split(',')]
            else:
                continue
            
            # Get products matching user preferences
            for cat in preferred_cats[:2]:  # Use first 2 categories
                pref_products = self.products_df[
                    self.products_df['category'] == cat
                ].to_dict('records')
                
                if len(pref_products) < 2:
                    continue
                
                # Create natural language query
                color = pref['preferred_colors'].split(',')[0].strip() if pref['preferred_colors'] else ''
                fabric = pref['preferred_fabrics'].split(',')[0].strip() if pref['preferred_fabrics'] else ''
                
                query = f"{color} {cat} {fabric}".lower().strip()
                
                anchor_product = pref_products[0]
                positive_product = pref_products[1] if len(pref_products) > 1 else pref_products[0]
                
                # Negative: different category
                diff_products = self.products_df[
                    self.products_df['category'] != cat
                ]
                if len(diff_products) > 0:
                    negative_product = diff_products.sample(1).iloc[0]
                    
                    query_triplets.append((
                        query,
                        positive_product['description'],
                        negative_product['description']
                    ))
        
        np.random.shuffle(query_triplets)
        query_triplets = query_triplets[:num_triplets]
        
        logger.info(f"✅ Created {len(query_triplets)} query triplets")
        
        return query_triplets
    
    def save_triplets(self, triplets: List[Tuple], output_path: str):
        """Save triplets to CSV for training"""
        logger.info(f"\n💾 Saving triplets to {output_path}...")
        
        df = pd.DataFrame(triplets, columns=['anchor', 'positive', 'negative'])
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        
        logger.info(f"✅ Saved {len(df)} triplets")
        
        return df
    
    def split_train_test(self, df: pd.DataFrame, test_size: float = 0.2):
        """Split into training and testing sets"""
        logger.info(f"\n📊 Splitting data: {int((1-test_size)*100)}% train, {int(test_size*100)}% test")
        
        np.random.seed(42)
        indices = np.random.permutation(len(df))
        split_idx = int(len(df) * (1 - test_size))
        
        train_df = df.iloc[indices[:split_idx]].reset_index(drop=True)
        test_df = df.iloc[indices[split_idx:]].reset_index(drop=True)
        
        logger.info(f"✅ Train: {len(train_df)}, Test: {len(test_df)}")
        
        return train_df, test_df
    
    def create_product_mapping(self):
        """Create product ID to description mapping"""
        mapping = dict(zip(
            self.products_df['product_id'],
            self.products_df['description']
        ))
        return mapping
    
    def run_full_pipeline(self):
        """Execute complete preprocessing pipeline"""
        logger.info("\n" + "="*80)
        logger.info("🚀 STARTING FASHION TRIPLET DATA PREPROCESSING")
        logger.info("="*80)
        
        # Load and check
        self.load_data()
        self.check_data_quality()
        self.clean_data()
        
        # Create descriptions
        self.create_product_descriptions()
        
        # Create triplets
        product_triplets = self.create_triplets(num_triplets=1000)
        query_triplets = self.create_query_triplets(num_triplets=500)
        
        all_triplets = product_triplets + query_triplets
        np.random.shuffle(all_triplets)
        
        # Save combined triplets
        triplets_df = self.save_triplets(
            all_triplets,
            'data/processed/fashion_triplets_1500.csv'
        )
        
        # Split into train/test
        train_df, test_df = self.split_train_test(triplets_df, test_size=0.15)
        
        train_df.to_csv('data/processed/fashion_triplets_train.csv', index=False)
        test_df.to_csv('data/processed/fashion_triplets_test.csv', index=False)
        
        # Save product mapping
        mapping = self.create_product_mapping()
        with open('data/processed/product_mapping.json', 'w') as f:
            json.dump(mapping, f)
        
        logger.info("\n" + "="*80)
        logger.info("✅ PREPROCESSING COMPLETE")
        logger.info("="*80)
        logger.info(f"📁 Training data: data/processed/fashion_triplets_train.csv ({len(train_df)} triplets)")
        logger.info(f"📁 Testing data: data/processed/fashion_triplets_test.csv ({len(test_df)} triplets)")
        logger.info(f"📁 Product mapping: data/processed/product_mapping.json")


if __name__ == "__main__":
    preprocessor = FashionTripletPreprocessor()
    preprocessor.run_full_pipeline()

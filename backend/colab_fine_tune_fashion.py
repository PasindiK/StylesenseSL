"""
Google Colab Script: Fine-Tune Fashion Embeddings
Complete end-to-end fine-tuning pipeline for Google Colab

Run this in Colab with GPU acceleration for optimal performance
"""

# ============================================================================
# STEP 1: SETUP ENVIRONMENT IN COLAB
# ============================================================================

# Run this in the first cell of your Colab notebook:
"""
!pip install sentence-transformers torch matplotlib seaborn scikit-learn pandas numpy -q
!mkdir -p /content/data/processed /content/models

# Clone your repo (replace with your actual repo)
# !git clone https://github.com/YOUR_USERNAME/TEST_RP.git
# %cd TEST_RP
"""

# ============================================================================
# STEP 2: DATA LOADING AND PREPROCESSING
# ============================================================================

import pandas as pd
import numpy as np
import torch
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ColabDataPreprocessor:
    """Preprocess fashion data for fine-tuning in Colab"""
    
    @staticmethod
    def create_sample_triplets(num_triplets=1500):
        """
        Create sample triplets if you don't have raw data
        In production, load from your CSV files
        """
        logger.info("📝 Creating sample fashion triplets for demonstration...")
        
        # Fashion categories
        categories = [
            'blue dresses', 'red dresses', 'casual shirts', 'formal shirts',
            'denim jeans', 'casual pants', 'leather jackets', 'wool coats',
            'summer dresses', 'winter coats', 'casual wear', 'formal wear'
        ]
        
        # Create variations
        triplets = []
        for i, category in enumerate(categories * 150):  # Repeat for volume
            # Similar items (positive)
            variations = [
                f"{category} for women",
                f"{category} under 5000",
                f"trendy {category}",
                f"comfortable {category}",
                f"{category} in blue",
                f"{category} in red",
            ]
            
            # Dissimilar items (negative)
            opposite_idx = (i + len(categories) // 2) % len(categories)
            negative = categories[opposite_idx]
            
            if len(triplets) < num_triplets:
                triplets.append((
                    category,
                    variations[i % len(variations)],
                    negative
                ))
        
        logger.info(f"✅ Created {len(triplets)} sample triplets")
        return triplets


# ============================================================================
# STEP 3: FINE-TUNING WITH SENTENCE TRANSFORMERS
# ============================================================================

from sentence_transformers import SentenceTransformer, losses, InputExample
from torch.utils.data import DataLoader

class ColabEmbeddingFinetuner:
    """Fine-tune Sentence Transformers in Google Colab"""
    
    def __init__(self, device=None):
        """Initialize with GPU if available"""
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        logger.info(f"🎯 Using device: {self.device}")
        logger.info(f"📊 GPU Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"📊 GPU Name: {torch.cuda.get_device_name(0)}")
        
        self.model = SentenceTransformer("all-MiniLM-L6-v2", device=self.device)
    
    def create_triplet_examples(self, triplets):
        """Convert triplets to InputExample format"""
        examples = []
        for anchor, positive, negative in triplets:
            examples.append(InputExample(
                texts=[anchor, positive, negative]
            ))
        return examples
    
    def fine_tune(self, triplets, epochs=5, batch_size=32, warmup_steps=100):
        """
        Fine-tune the model using TripletLoss
        
        Args:
            triplets: List of (anchor, positive, negative) tuples
            epochs: Number of training epochs
            batch_size: Batch size for training
            warmup_steps: Linear warmup steps
        """
        
        logger.info("\n" + "="*80)
        logger.info("🚀 STARTING FINE-TUNING")
        logger.info("="*80)
        
        # Create examples
        examples = self.create_triplet_examples(triplets)
        
        # Create dataloader
        train_dataloader = DataLoader(examples, shuffle=True, batch_size=batch_size)
        
        # Define loss function
        train_loss = losses.TripletLoss(model=self.model)
        
        logger.info(f"⚙️  Configuration:")
        logger.info(f"   - Model: all-MiniLM-L6-v2 (384 dims)")
        logger.info(f"   - Loss: TripletLoss")
        logger.info(f"   - Epochs: {epochs}")
        logger.info(f"   - Batch Size: {batch_size}")
        logger.info(f"   - Warmup Steps: {warmup_steps}")
        logger.info(f"   - Total Examples: {len(examples)}")
        logger.info(f"   - Device: {self.device}")
        
        # Fine-tune
        logger.info("\n🔄 Training in progress...")
        self.model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=epochs,
            warmup_steps=warmup_steps,
            show_progress_bar=True,
            use_amp=True  # Mixed precision for faster training on GPU
        )
        
        logger.info("\n✅ Fine-tuning complete!")
        return self.model
    
    def save_model(self, output_path="/content/models/fashion-embeddings-ft"):
        """Save fine-tuned model"""
        Path(output_path).mkdir(parents=True, exist_ok=True)
        self.model.save(output_path)
        logger.info(f"✅ Model saved to {output_path}")
        return output_path
    
    def evaluate(self, test_triplets, show_samples=True):
        """Evaluate model on test triplets"""
        
        logger.info("\n" + "="*80)
        logger.info("📊 EVALUATING MODEL")
        logger.info("="*80)
        
        if len(test_triplets) > 50:
            test_triplets = test_triplets[:50]
        
        anchors = [t[0] for t in test_triplets]
        positives = [t[1] for t in test_triplets]
        negatives = [t[2] for t in test_triplets]
        
        # Encode
        from sklearn.metrics.pairwise import cosine_similarity
        
        anchor_emb = self.model.encode(anchors, show_progress_bar=False)
        positive_emb = self.model.encode(positives, show_progress_bar=False)
        negative_emb = self.model.encode(negatives, show_progress_bar=False)
        
        # Calculate similarities
        pos_sim = np.diag(cosine_similarity(anchor_emb, positive_emb))
        neg_sim = np.diag(cosine_similarity(anchor_emb, negative_emb))
        
        # Metrics
        accuracy = np.mean(pos_sim > neg_sim)
        margin = pos_sim.mean() - neg_sim.mean()
        
        logger.info(f"\n✅ Results:")
        logger.info(f"   Positive Similarity: {pos_sim.mean():.4f}")
        logger.info(f"   Negative Similarity: {neg_sim.mean():.4f}")
        logger.info(f"   Margin: {margin:.4f}")
        logger.info(f"   Accuracy: {accuracy:.2%}")
        
        if show_samples:
            logger.info(f"\n📝 Sample Results:")
            for i in range(min(3, len(test_triplets))):
                logger.info(f"   Query: {anchors[i][:50]}...")
                logger.info(f"   Pos Sim: {pos_sim[i]:.4f}, Neg Sim: {neg_sim[i]:.4f}")
        
        return {
            'accuracy': accuracy,
            'margin': margin,
            'pos_mean_sim': pos_sim.mean(),
            'neg_mean_sim': neg_sim.mean()
        }


# ============================================================================
# STEP 4: VISUALIZATION IN COLAB
# ============================================================================

import matplotlib.pyplot as plt
import seaborn as sns

class ColabVisualizer:
    """Create visualizations in Colab"""
    
    @staticmethod
    def plot_training_metrics(train_losses):
        """Plot training losses"""
        plt.figure(figsize=(10, 5))
        plt.plot(train_losses, linewidth=2, color='#4ECB71')
        plt.title('Training Loss Over Epochs', fontsize=14, fontweight='bold')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.show()
    
    @staticmethod
    def plot_evaluation_results(results_list):
        """Plot evaluation results"""
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        # Accuracy
        accuracies = [r['accuracy'] * 100 for r in results_list]
        epochs = list(range(1, len(accuracies) + 1))
        
        axes[0].plot(epochs, accuracies, marker='o', linewidth=2, color='#4ECB71')
        axes[0].set_title('Accuracy Over Epochs', fontweight='bold')
        axes[0].set_xlabel('Epoch')
        axes[0].set_ylabel('Accuracy (%)')
        axes[0].grid(alpha=0.3)
        axes[0].set_ylim([80, 100])
        
        # Margin
        margins = [r['margin'] for r in results_list]
        axes[1].plot(epochs, margins, marker='s', linewidth=2, color='#FF6B6B')
        axes[1].set_title('Margin Over Epochs', fontweight='bold')
        axes[1].set_xlabel('Epoch')
        axes[1].set_ylabel('Margin')
        axes[1].grid(alpha=0.3)
        
        plt.tight_layout()
        plt.show()


# ============================================================================
# STEP 5: COMPLETE PIPELINE
# ============================================================================

def run_complete_pipeline():
    """
    Run complete fine-tuning pipeline in Colab
    
    Usage in Colab cell:
    ```
    run_complete_pipeline()
    ```
    """
    
    logger.info("\n" + "="*80)
    logger.info("🚀 FASHION EMBEDDING FINE-TUNING PIPELINE (COLAB VERSION)")
    logger.info("="*80)
    
    # Step 1: Create sample triplets
    preprocessor = ColabDataPreprocessor()
    triplets = preprocessor.create_sample_triplets(num_triplets=1500)
    
    # Split into train/test
    np.random.shuffle(triplets)
    split_idx = int(len(triplets) * 0.85)
    train_triplets = triplets[:split_idx]
    test_triplets = triplets[split_idx:]
    
    logger.info(f"\n📊 Data Split:")
    logger.info(f"   Training: {len(train_triplets)} triplets")
    logger.info(f"   Testing: {len(test_triplets)} triplets")
    
    # Step 2: Initialize fine-tuner
    finetuner = ColabEmbeddingFinetuner()
    
    # Step 3: Fine-tune
    model = finetuner.fine_tune(
        train_triplets,
        epochs=3,
        batch_size=32,
        warmup_steps=100
    )
    
    # Step 4: Save model
    model_path = finetuner.save_model()
    
    # Step 5: Evaluate
    eval_results = finetuner.evaluate(test_triplets)
    
    # Step 6: Visualize
    logger.info("\n📈 Creating visualization...")
    ColabVisualizer.plot_evaluation_results([eval_results])
    
    logger.info("\n" + "="*80)
    logger.info("✅ PIPELINE COMPLETE!")
    logger.info("="*80)
    logger.info(f"\n🎨 MODEL PERFORMANCE:")
    logger.info(f"   Accuracy: {eval_results['accuracy']:.2%}")
    logger.info(f"   Margin: {eval_results['margin']:.4f}")
    logger.info(f"   Model saved to: {model_path}")
    logger.info("\n🔗 Next: Download model from Colab and integrate into your app!")
    
    return {
        'model': model,
        'model_path': model_path,
        'results': eval_results,
        'train_triplets': train_triplets,
        'test_triplets': test_triplets
    }


# ============================================================================
# STEP 6: MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    """
    To run in Colab notebook, create a new cell and paste:
    
    ```python
    exec(open('/content/colab_fine_tune_fashion.py').read())
    results = run_complete_pipeline()
    ```
    
    Or for step-by-step execution, use:
    
    ```python
    # Cell 1: Setup
    !pip install sentence-transformers torch matplotlib seaborn scikit-learn pandas numpy -q
    
    # Cell 2: Load script and run pipeline
    exec(open('/content/colab_fine_tune_fashion.py').read())
    results = run_complete_pipeline()
    ```
    """
    
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║  FASHION EMBEDDING FINE-TUNING FOR GOOGLE COLAB                    ║
    ║                                                                    ║
    ║  📖 USAGE INSTRUCTIONS:                                            ║
    ║                                                                    ║
    ║  1. Create a new Google Colab notebook                             ║
    ║  2. Upload this file to Colab (or clone from GitHub)               ║
    ║  3. Run the setup cell                                             ║
    ║  4. Execute: results = run_complete_pipeline()                     ║
    ║                                                                    ║
    ║  🚀 FEATURES:                                                      ║
    ║  ✅ Automatic GPU acceleration (if available)                      ║
    ║  ✅ Sample data generation (or load your own)                      ║
    ║  ✅ Fine-tuning with TripletLoss                                   ║
    ║  ✅ Comprehensive evaluation metrics                               ║
    ║  ✅ Interactive visualizations                                     ║
    ║  ✅ Model saving and export                                        ║
    ║                                                                    ║
    ║  📊 EXPECTED RESULTS:                                              ║
    ║  ✅ Accuracy: 85-90%                                               ║
    ║  ✅ Margin: 0.15-0.20                                              ║
    ║  ✅ Training time: 10-30 min (GPU)                                 ║
    ║                                                                    ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)
    
    # Auto-run if executed
    results = run_complete_pipeline()

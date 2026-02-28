"""
Comprehensive Model Evaluation & Visualization
Compare baseline vs fashion-optimized embeddings
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics.pairwise import cosine_similarity
import json
from pathlib import Path

class ModelEvaluator:
    """Evaluate and visualize model performance"""
    
    def __init__(self):
        self.test_data = None
        self.baseline_results = {}
        self.fashion_results = {}
        
    def load_test_data(self):
        """Load test triplets"""
        self.test_data = pd.read_csv('data/processed/fashion_triplets_test.csv')
        return self.test_data.head(50)  # Sample for evaluation
    
    def evaluate_models(self):
        """Evaluate both baseline and fashion models"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        from sentence_transformers import SentenceTransformer
        from src.agents.fashion_embedding_model import get_fashion_embedding_model
        
        print("\n" + "="*80)
        print("🔬 EVALUATING MODELS")
        print("="*80)
        
        test_sample = self.load_test_data()
        
        # Baseline model
        print("\n📊 Evaluating BASELINE model (all-MiniLM-L6-v2)...")
        baseline_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        baseline_anchor_emb = baseline_model.encode(test_sample['anchor'].tolist(), show_progress_bar=False)
        baseline_positive_emb = baseline_model.encode(test_sample['positive'].tolist(), show_progress_bar=False)
        baseline_negative_emb = baseline_model.encode(test_sample['negative'].tolist(), show_progress_bar=False)
        
        # Calculate baseline metrics
        baseline_pos_sim = np.diag(cosine_similarity(baseline_anchor_emb, baseline_positive_emb))
        baseline_neg_sim = np.diag(cosine_similarity(baseline_anchor_emb, baseline_negative_emb))
        baseline_accuracy = np.mean(baseline_pos_sim > baseline_neg_sim)
        
        self.baseline_results = {
            'positive_similarities': baseline_pos_sim,
            'negative_similarities': baseline_neg_sim,
            'mean_pos_sim': baseline_pos_sim.mean(),
            'mean_neg_sim': baseline_neg_sim.mean(),
            'accuracy': baseline_accuracy,
            'margin': baseline_pos_sim.mean() - baseline_neg_sim.mean()
        }
        
        print(f"   ✅ Mean positive similarity: {self.baseline_results['mean_pos_sim']:.4f}")
        print(f"   ✅ Mean negative similarity: {self.baseline_results['mean_neg_sim']:.4f}")
        print(f"   ✅ Accuracy (pos > neg): {self.baseline_results['accuracy']:.2%}")
        print(f"   ✅ Margin: {self.baseline_results['margin']:.4f}")
        
        # Fashion-optimized model
        print("\n📊 Evaluating FASHION-OPTIMIZED model...")
        fashion_model = get_fashion_embedding_model()
        
        fashion_anchor_emb = fashion_model.encode(test_sample['anchor'].tolist())
        fashion_positive_emb = fashion_model.encode(test_sample['positive'].tolist())
        fashion_negative_emb = fashion_model.encode(test_sample['negative'].tolist())
        
        # Calculate fashion metrics
        fashion_pos_sim = np.diag(cosine_similarity(fashion_anchor_emb, fashion_positive_emb))
        fashion_neg_sim = np.diag(cosine_similarity(fashion_anchor_emb, fashion_negative_emb))
        fashion_accuracy = np.mean(fashion_pos_sim > fashion_neg_sim)
        
        self.fashion_results = {
            'positive_similarities': fashion_pos_sim,
            'negative_similarities': fashion_neg_sim,
            'mean_pos_sim': fashion_pos_sim.mean(),
            'mean_neg_sim': fashion_neg_sim.mean(),
            'accuracy': fashion_accuracy,
            'margin': fashion_pos_sim.mean() - fashion_neg_sim.mean()
        }
        
        print(f"   ✅ Mean positive similarity: {self.fashion_results['mean_pos_sim']:.4f}")
        print(f"   ✅ Mean negative similarity: {self.fashion_results['mean_neg_sim']:.4f}")
        print(f"   ✅ Accuracy (pos > neg): {self.fashion_results['accuracy']:.2%}")
        print(f"   ✅ Margin: {self.fashion_results['margin']:.4f}")
        
        # Calculate improvements
        acc_improvement = ((self.fashion_results['accuracy'] - self.baseline_results['accuracy']) / 
                          self.baseline_results['accuracy'] * 100)
        margin_improvement = ((self.fashion_results['margin'] - self.baseline_results['margin']) / 
                             self.baseline_results['margin'] * 100)
        
        print("\n" + "="*80)
        print("📈 IMPROVEMENT SUMMARY")
        print("="*80)
        print(f"✅ Accuracy Improvement: +{acc_improvement:.2f}%")
        print(f"✅ Margin Improvement: +{margin_improvement:.2f}%")
        print(f"✅ Estimated Final Accuracy: {(self.fashion_results['accuracy'] * 100):.1f}%")
        
        return {
            'baseline': self.baseline_results,
            'fashion': self.fashion_results,
            'accuracy_improvement': acc_improvement,
            'margin_improvement': margin_improvement,
            'final_accuracy': self.fashion_results['accuracy'] * 100
        }
    
    def create_visualizations(self):
        """Create comprehensive visualizations"""
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Fashion Embedding Model Evaluation: Baseline vs Fine-Tuned', 
                     fontsize=16, fontweight='bold')
        
        # 1. Similarity Distribution Comparison
        ax = axes[0, 0]
        ax.hist(self.baseline_results['positive_similarities'], bins=15, alpha=0.6, 
               label='Baseline (Positive)', color='blue', edgecolor='black')
        ax.hist(self.fashion_results['positive_similarities'], bins=15, alpha=0.6, 
               label='Fashion-Optimized (Positive)', color='green', edgecolor='black')
        ax.set_xlabel('Cosine Similarity Score')
        ax.set_ylabel('Frequency')
        ax.set_title('Positive Pair Similarity Distribution')
        ax.legend()
        ax.grid(alpha=0.3)
        
        # 2. Margin Analysis
        ax = axes[0, 1]
        models = ['Baseline', 'Fashion-Optimized']
        margins = [self.baseline_results['margin'], self.fashion_results['margin']]
        colors = ['#FF6B6B', '#4ECB71']
        bars = ax.bar(models, margins, color=colors, edgecolor='black', linewidth=2)
        ax.set_ylabel('Margin (Positive - Negative Similarity)')
        ax.set_title('Embedding Margin Comparison')
        ax.grid(axis='y', alpha=0.3)
        
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{margins[i]:.4f}',
                   ha='center', va='bottom', fontweight='bold')
        
        # 3. Accuracy Comparison
        ax = axes[1, 0]
        models = ['Baseline', 'Fashion-Optimized']
        accuracies = [self.baseline_results['accuracy'] * 100, 
                     self.fashion_results['accuracy'] * 100]
        colors = ['#FF6B6B', '#4ECB71']
        bars = ax.bar(models, accuracies, color=colors, edgecolor='black', linewidth=2)
        ax.set_ylabel('Accuracy (%)')
        ax.set_title('Ranking Accuracy: Positive > Negative')
        ax.set_ylim([75, 100])
        ax.grid(axis='y', alpha=0.3)
        
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{accuracies[i]:.1f}%',
                   ha='center', va='bottom', fontweight='bold')
        
        # 4. Metrics Summary Table
        ax = axes[1, 1]
        ax.axis('tight')
        ax.axis('off')
        
        metrics_data = [
            ['Metric', 'Baseline', 'Fashion-Opt', 'Improvement'],
            ['Pos Similarity', f"{self.baseline_results['mean_pos_sim']:.4f}", 
             f"{self.fashion_results['mean_pos_sim']:.4f}", '+'],
            ['Neg Similarity', f"{self.baseline_results['mean_neg_sim']:.4f}", 
             f"{self.fashion_results['mean_neg_sim']:.4f}", '-'],
            ['Margin', f"{self.baseline_results['margin']:.4f}", 
             f"{self.fashion_results['margin']:.4f}",
             f"+{((self.fashion_results['margin'] - self.baseline_results['margin']) / self.baseline_results['margin'] * 100):.1f}%"],
            ['Accuracy', f"{self.baseline_results['accuracy']:.2%}", 
             f"{self.fashion_results['accuracy']:.2%}",
             f"+{((self.fashion_results['accuracy'] - self.baseline_results['accuracy']) / self.baseline_results['accuracy'] * 100):.1f}%"]
        ]
        
        table = ax.table(cellText=metrics_data, cellLoc='center', loc='center',
                        colWidths=[0.25, 0.25, 0.25, 0.25])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2.5)
        
        # Style header
        for i in range(4):
            table[(0, i)].set_facecolor('#4ECB71')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        ax.set_title('Detailed Metrics Comparison', fontweight='bold', pad=20)
        
        plt.tight_layout()
        plt.savefig('data/processed/model_evaluation.png', dpi=300, bbox_inches='tight')
        print("\n✅ Visualization saved: data/processed/model_evaluation.png")
        
        return fig
    
    def save_results(self, results):
        """Save evaluation results"""
        Path('data/processed').mkdir(parents=True, exist_ok=True)
        
        # Convert all values to native Python types for JSON serialization
        def convert_to_native(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, (np.float32, np.float64)):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: convert_to_native(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_native(v) for v in obj]
            return obj
        
        with open('data/processed/model_evaluation_results.json', 'w') as f:
            json.dump({
                'baseline': convert_to_native({k: v for k, v in self.baseline_results.items()}),
                'fashion': convert_to_native({k: v for k, v in self.fashion_results.items()}),
                'improvements': convert_to_native(results)
            }, f, indent=2)
        
        print("✅ Results saved: data/processed/model_evaluation_results.json")


if __name__ == "__main__":
    evaluator = ModelEvaluator()
    results = evaluator.evaluate_models()
    evaluator.create_visualizations()
    evaluator.save_results(results)
    
    print("\n" + "="*80)
    print("✅ EVALUATION COMPLETE")
    print("="*80)
    print(f"\n📊 FINAL ACCURACY: {results['final_accuracy']:.1f}% ✨")
    print("="*80)

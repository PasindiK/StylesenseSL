"""
Fine-Tune Sentence Transformers on Fashion Domain
Trains a fashion-specific embedding model using triplet loss
"""
import pandas as pd
import numpy as np
import logging
import torch
from pathlib import Path
from typing import List, Tuple
import matplotlib.pyplot as plt
import json

from sentence_transformers import SentenceTransformer, losses, InputExample
from sentence_transformers.evaluation import TripletEvaluator, InformationRetrievalEvaluator
from torch.utils.data import DataLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FashionEmbeddingFineTuner:
    """Fine-tune Sentence Transformers for fashion domain"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = None):
        """Initialize fine-tuner"""
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        logger.info(f"🎯 Initializing model: {model_name} on {self.device}")
        
        self.model = SentenceTransformer(model_name, device=self.device)
        self.base_model_name = model_name
        self.training_history = {
            'epoch': [],
            'loss': [],
            'train_loss': []
        }
        
    def load_triplets(self, csv_path: str) -> List[InputExample]:
        """Load triplets from CSV"""
        logger.info(f"📂 Loading triplets from {csv_path}")
        
        df = pd.read_csv(csv_path)
        examples = []
        
        for _, row in df.iterrows():
            example = InputExample(
                texts=[row['anchor'], row['positive'], row['negative']]
            )
            examples.append(example)
        
        logger.info(f"✅ Loaded {len(examples)} triplets")
        return examples
    
    def create_dataloaders(self, 
                          train_examples: List[InputExample],
                          test_examples: List[InputExample],
                          batch_size: int = 16):
        """Create training and evaluation dataloaders"""
        logger.info(f"📊 Creating dataloaders with batch size {batch_size}")
        
        train_dataloader = DataLoader(
            train_examples,
            shuffle=True,
            batch_size=batch_size
        )
        
        logger.info(f"✅ Created dataloaders: {len(train_dataloader)} batches (train)")
        
        return train_dataloader
    
    def fine_tune(self,
                 train_dataloader: DataLoader,
                 epochs: int = 5,
                 warmup_steps: int = 100,
                 output_path: str = "models/fashion-embeddings-ft"):
        """Fine-tune the model using TripletLoss"""
        
        logger.info("\n" + "="*80)
        logger.info("🚀 STARTING FINE-TUNING")
        logger.info("="*80)
        
        Path(output_path).mkdir(parents=True, exist_ok=True)
        
        # Define loss function
        train_loss = losses.TripletLoss(model=self.model)
        
        logger.info(f"⚙️  Training config:")
        logger.info(f"   - Epochs: {epochs}")
        logger.info(f"   - Warmup steps: {warmup_steps}")
        logger.info(f"   - Loss: TripletLoss")
        logger.info(f"   - Device: {self.device}")
        
        # Fine-tune
        self.model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=epochs,
            warmup_steps=warmup_steps,
            checkpoint_path=output_path,
            checkpoint_save_steps=len(train_dataloader),
            show_progress_bar=True,
            use_amp=True  # Mixed precision training for speed
        )
        
        # Save final model
        self.model.save(output_path)
        logger.info(f"\n✅ Model saved to {output_path}")
        
        return output_path
    
    def evaluate_retrieval(self,
                          test_examples: List[InputExample],
                          output_path: str = "models/fashion-embeddings-ft") -> dict:
        """Evaluate using retrieval metrics"""
        
        logger.info("\n" + "="*80)
        logger.info("📊 EVALUATING MODEL")
        logger.info("="*80)
        
        # Extract anchors and positives/negatives for evaluation
        anchors = [ex.texts[0] for ex in test_examples]
        positives = [[ex.texts[1]] for ex in test_examples]
        negatives = [[ex.texts[2]] for ex in test_examples]
        
        # Encode all texts
        logger.info("🔄 Encoding test examples...")
        anchor_embeddings = self.model.encode(anchors, show_progress_bar=True)
        
        # Get all unique documents
        all_docs = set()
        for ex in test_examples:
            all_docs.add(ex.texts[1])
            all_docs.add(ex.texts[2])
        
        all_docs = list(all_docs)
        corpus_embeddings = self.model.encode(all_docs, show_progress_bar=True)
        
        # Calculate metrics
        metrics = self._calculate_metrics(
            anchor_embeddings,
            corpus_embeddings,
            all_docs,
            test_examples
        )
        
        logger.info("\n✅ Evaluation Results:")
        logger.info(f"   NDCG@10: {metrics['ndcg@10']:.4f}")
        logger.info(f"   MRR: {metrics['mrr']:.4f}")
        logger.info(f"   Precision@1: {metrics['precision@1']:.4f}")
        logger.info(f"   Accuracy@1: {metrics['accuracy@1']:.4f}")
        
        return metrics
    
    def _calculate_metrics(self, anchor_embeddings, corpus_embeddings, all_docs, test_examples) -> dict:
        """Calculate retrieval metrics"""
        
        from sklearn.metrics.pairwise import cosine_similarity
        
        metrics = {
            'ndcg@10': 0,
            'mrr': 0,
            'precision@1': 0,
            'accuracy@1': 0,
            'mean_reciprocal_rank': 0,
            'ranking_scores': []
        }
        
        doc_to_idx = {doc: idx for idx, doc in enumerate(all_docs)}
        
        for i, example in enumerate(test_examples):
            # Get positive document index
            positive_doc = example.texts[1]
            positive_idx = doc_to_idx.get(positive_doc)
            
            if positive_idx is None:
                continue
            
            # Calculate similarity between anchor and all docs
            similarity = cosine_similarity(
                anchor_embeddings[i].reshape(1, -1),
                corpus_embeddings
            )[0]
            
            # Rank documents by similarity
            ranked = np.argsort(similarity)[::-1]
            rank = np.where(ranked == positive_idx)[0][0] + 1
            
            # Calculate metrics
            if rank == 1:
                metrics['accuracy@1'] += 1
                metrics['precision@1'] += 1
            
            metrics['mrr'] += 1.0 / rank
            metrics['ranking_scores'].append(rank)
            
            # NDCG calculation
            dcg = 0
            idcg = 0
            for j in range(10):
                if j < len(ranked):
                    if ranked[j] == positive_idx:
                        dcg = 1.0 / (np.log2(j + 2))
                    idcg = 1.0 / (np.log2(j + 2))
            
            metrics['ndcg@10'] += dcg / idcg if idcg > 0 else 0
        
        # Average metrics
        n = len(test_examples)
        metrics['ndcg@10'] /= n
        metrics['mrr'] /= n
        metrics['precision@1'] /= n
        metrics['accuracy@1'] /= n
        metrics['mean_reciprocal_rank'] = metrics['mrr']
        
        return metrics
    
    def compare_with_baseline(self, test_examples: List[InputExample]) -> dict:
        """Compare fine-tuned model with baseline"""
        
        logger.info("\n" + "="*80)
        logger.info("🔬 COMPARING WITH BASELINE")
        logger.info("="*80)
        
        # Load baseline model
        baseline_model = SentenceTransformer(self.base_model_name, device=self.device)
        
        anchors = [ex.texts[0] for ex in test_examples]
        positives = [[ex.texts[1]] for ex in test_examples]
        negatives = [[ex.texts[2]] for ex in test_examples]
        
        all_docs = set()
        for ex in test_examples:
            all_docs.add(ex.texts[1])
            all_docs.add(ex.texts[2])
        all_docs = list(all_docs)
        
        # Evaluate baseline
        logger.info("📊 Evaluating baseline model...")
        baseline_anchor_emb = baseline_model.encode(anchors, show_progress_bar=True)
        baseline_corpus_emb = baseline_model.encode(all_docs, show_progress_bar=True)
        baseline_metrics = self._calculate_metrics(
            baseline_anchor_emb,
            baseline_corpus_emb,
            all_docs,
            test_examples
        )
        
        # Evaluate fine-tuned
        logger.info("📊 Evaluating fine-tuned model...")
        ft_anchor_emb = self.model.encode(anchors, show_progress_bar=True)
        ft_corpus_emb = self.model.encode(all_docs, show_progress_bar=True)
        ft_metrics = self._calculate_metrics(
            ft_anchor_emb,
            ft_corpus_emb,
            all_docs,
            test_examples
        )
        
        # Calculate improvements
        improvement = {
            'ndcg@10': {
                'baseline': baseline_metrics['ndcg@10'],
                'fine_tuned': ft_metrics['ndcg@10'],
                'improvement': (ft_metrics['ndcg@10'] - baseline_metrics['ndcg@10']) / baseline_metrics['ndcg@10'] * 100
            },
            'mrr': {
                'baseline': baseline_metrics['mrr'],
                'fine_tuned': ft_metrics['mrr'],
                'improvement': (ft_metrics['mrr'] - baseline_metrics['mrr']) / baseline_metrics['mrr'] * 100
            },
            'accuracy@1': {
                'baseline': baseline_metrics['accuracy@1'],
                'fine_tuned': ft_metrics['accuracy@1'],
                'improvement': (ft_metrics['accuracy@1'] - baseline_metrics['accuracy@1']) / baseline_metrics['accuracy@1'] * 100
            }
        }
        
        logger.info("\n📈 COMPARISON RESULTS:")
        logger.info(f"\n🏁 NDCG@10:")
        logger.info(f"   Baseline:   {improvement['ndcg@10']['baseline']:.4f}")
        logger.info(f"   Fine-tuned: {improvement['ndcg@10']['fine_tuned']:.4f}")
        logger.info(f"   📊 Improvement: +{improvement['ndcg@10']['improvement']:.2f}%")
        
        logger.info(f"\n🏁 MRR (Mean Reciprocal Rank):")
        logger.info(f"   Baseline:   {improvement['mrr']['baseline']:.4f}")
        logger.info(f"   Fine-tuned: {improvement['mrr']['fine_tuned']:.4f}")
        logger.info(f"   📊 Improvement: +{improvement['mrr']['improvement']:.2f}%")
        
        logger.info(f"\n🏁 Accuracy@1:")
        logger.info(f"   Baseline:   {improvement['accuracy@1']['baseline']:.4f}")
        logger.info(f"   Fine-tuned: {improvement['accuracy@1']['fine_tuned']:.4f}")
        logger.info(f"   📊 Improvement: +{improvement['accuracy@1']['improvement']:.2f}%")
        
        return improvement
    
    def run_full_pipeline(self):
        """Execute complete fine-tuning pipeline"""
        
        logger.info("\n" + "="*80)
        logger.info("🚀 STARTING COMPLETE FINE-TUNING PIPELINE")
        logger.info("="*80)
        
        # Load data
        train_examples = self.load_triplets('data/processed/fashion_triplets_train.csv')
        test_examples = self.load_triplets('data/processed/fashion_triplets_test.csv')
        
        # Create dataloaders
        train_dataloader = self.create_dataloaders(train_examples, test_examples, batch_size=16)
        
        # Fine-tune
        output_path = self.fine_tune(
            train_dataloader,
            epochs=5,
            warmup_steps=100,
            output_path="models/fashion-embeddings-ft"
        )
        
        # Evaluate
        metrics = self.evaluate_retrieval(test_examples, output_path)
        
        # Compare with baseline
        improvement = self.compare_with_baseline(test_examples)
        
        # Save metrics
        results = {
            'metrics': metrics,
            'improvement': improvement,
            'model_path': output_path,
            'base_model': self.base_model_name
        }
        
        with open('data/processed/fine_tuning_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info("\n" + "="*80)
        logger.info("✅ FINE-TUNING COMPLETE")
        logger.info("="*80)
        
        return results


if __name__ == "__main__":
    finetuner = FashionEmbeddingFineTuner()
    results = finetuner.run_full_pipeline()

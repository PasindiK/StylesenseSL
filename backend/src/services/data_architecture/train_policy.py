#!/usr/bin/env python
"""Train policy from data_architecture service root."""
import os
import sys

# Change to the service directory so relative paths work
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Now import and run trainer
from medallions.gold.ml_decision_engine.trainer import offline_train

events_dir = os.path.join("pipeline", "metadata", "drift_events")
print(f"Training from: {events_dir}")
print(f"Current working directory: {os.getcwd()}")

# Run with improved weights and more epochs
policy, metrics = offline_train(events_dir, epochs=5)
print("\n✓ Policy training complete!")
print(f"Training metrics: {metrics}")

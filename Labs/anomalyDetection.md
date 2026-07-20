# Anomaly Detection: Model Comparison and Parameters

## 1. Quantitative Performance Comparison

| Measure | Isolation Forest | Autoencoder + embeddings |
| :--- | :--- | :--- |
| **Detected anomalies** | 33 | 37 |
| **Precision** | 0.970 | 0.865 |
| **Recall** | 1.000 | 1.000 |
| **F1 score** | 0.985 | 0.928 |
| **False positives** | 1 | 5 |
| **False negatives** | 0 | 0 |

## 2. Model Characteristics and Parameters

| Parameter | Isolation Forest | Autoencoder + embeddings |
| :--- | :--- | :--- |
| **Model Type** | Tree-based ensemble | Neural Network (Deep Learning) |
| **Detection Basis** | Isolates anomalies in feature space | Learns normal behavioral combinations |
| **Training Needs** | Unsupervised (no labels needed) | Trained primarily on 'normal' data |
| **Training Time** | Generally fast | Computationally intensive |
| **Interpretability** | Moderate (path length-based) | Low (black-box latent space) |
| **Hyperparameters** | `n_estimators`, `contamination` | Architecture, layers, LR, threshold |


## The models' varying success rates are attributable to the synthetic nature of the dataset.  
---
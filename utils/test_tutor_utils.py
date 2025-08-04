"""
Test script for Pawfessor Meowkins Tutor Agent utility functions.
This demonstrates how to use the document processing, embedding, and retrieval tools.
"""

import sys
import os
import time

# Ensure the parent directory is in the path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils.tutor_utils import (
    chunk_document, 
    embed_chunks, 
    retriever_tool, 
    roadmap_tool, 
    summarizer_tool
)

def test_with_sample_text():
    """Test all utility functions with a sample text document."""
    
    # Sample document text
    document_text = """
    # Introduction to Machine Learning
    
    Machine learning is a subset of artificial intelligence that focuses on the development of algorithms
    that can learn from and make predictions based on data. These algorithms build models from sample inputs
    to make data-driven predictions or decisions, rather than following strictly static program instructions.
    
    ## Types of Machine Learning
    
    There are several types of machine learning approaches:
    
    ### Supervised Learning
    
    Supervised learning uses labeled training data, consisting of input examples and their corresponding target outputs.
    The algorithm learns a function that can be used to predict outputs for new inputs.
    
    Common supervised learning algorithms include:
    - Linear regression for regression problems
    - Logistic regression for classification problems
    - Support Vector Machines (SVM)
    - Decision trees and random forests
    - Neural networks
    
    ### Unsupervised Learning
    
    Unsupervised learning works with unlabeled data. The algorithm learns patterns and structures directly from the data
    without explicit guidance on what to look for.
    
    Common unsupervised learning algorithms include:
    - Clustering algorithms like K-means
    - Dimensionality reduction techniques like PCA
    - Autoencoders
    - Generative models
    
    ### Reinforcement Learning
    
    Reinforcement learning involves an agent that learns to make decisions by performing actions in an environment
    to maximize some notion of cumulative reward. It's different from supervised learning in that correct input/output
    pairs are never presented, and sub-optimal actions are not explicitly corrected.
    
    ## Applications of Machine Learning
    
    Machine learning has a wide range of applications across various domains:
    
    1. **Healthcare**: Disease prediction, medical imaging analysis
    2. **Finance**: Fraud detection, algorithmic trading
    3. **Retail**: Recommendation systems, demand forecasting
    4. **Transportation**: Self-driving cars, traffic prediction
    5. **Entertainment**: Content recommendation, game AI
    
    ## Evaluation Metrics
    
    To assess the performance of machine learning models, various metrics are used:
    
    - **Accuracy**: The proportion of correct predictions among the total number of cases
    - **Precision**: The proportion of true positives among all positive predictions
    - **Recall**: The proportion of true positives identified correctly
    - **F1 Score**: The harmonic mean of precision and recall
    - **ROC-AUC**: Area under the Receiver Operating Characteristic curve
    
    ## Challenges in Machine Learning
    
    Despite its successes, machine learning faces several challenges:
    
    - **Data quality and quantity**: ML models require large amounts of high-quality data
    - **Overfitting**: Models may perform well on training data but poorly on unseen data
    - **Interpretability**: Complex models like deep neural networks can be difficult to interpret
    - **Ethical concerns**: Issues related to bias, privacy, and misuse
    
    ## Future Directions
    
    The field of machine learning continues to evolve rapidly. Some exciting areas of ongoing research include:
    
    - **Federated Learning**: Training models across multiple devices without sharing data
    - **AutoML**: Automating the process of applying machine learning
    - **Few-shot Learning**: Learning from very few examples
    - **Explainable AI**: Making AI systems more transparent and interpretable
    
    As algorithms become more sophisticated and computing power increases, the capabilities and applications of
    machine learning are expected to expand significantly in the coming years.
    """
    
    print("\n--- TESTING DOCUMENT CHUNKING ---")
    chunks = chunk_document(document_text, chunk_size=500, overlap=50)
    print(f"Document split into {len(chunks)} chunks")
    print(f"First chunk: {chunks[0]['content'][:100]}...")
    
    print("\n--- TESTING DOCUMENT EMBEDDING ---")
    doc_id = "test_document_1"
    embedded_chunks = embed_chunks(chunks, doc_id=doc_id)
    print(f"Embedded {len(embedded_chunks)} chunks with doc_id '{doc_id}'")
    
    print("\n--- TESTING RETRIEVAL ---")
    query = "What are the types of supervised learning algorithms?"
    results = retriever_tool(query, doc_id=doc_id, top_k=2)
    print(f"Query: '{query}'")
    print(f"Found {len(results)} relevant chunks")
    for i, result in enumerate(results):
        print(f"Result {i+1} (score: {result['score']:.4f}):")
        print(f"  {result['content'][:150]}...")
    
    print("\n--- TESTING ROADMAP CREATION ---")
    roadmap = roadmap_tool(document_text, doc_id=doc_id)
    print(f"Created roadmap with {len(roadmap['sections'])} sections:")
    for section in roadmap["sections"]:
        print(f"  - {section['section']} (chunks: {len(section['chunk_ids'])})")
    
    print("\n--- TESTING SUMMARIZATION ---")
    # Use the retrieved chunks for summarization
    if results:
        summary = summarizer_tool(results)
        print("Summary of retrieved content:")
        print(summary)
    
    print("\n--- ALL TESTS COMPLETED ---")

if __name__ == "__main__":
    test_with_sample_text()

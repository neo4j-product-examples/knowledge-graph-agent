# Neo4j Aura Agent

This repository contains step-by-step instructions on how to use the new Neo4j Aura Agent functionality. These examples demonstrate how to create intelligent agents that can interact with knowledge graphs to answer domain-specific questions.

## Getting Started
### Prerequisites

1. **Git LFS (Large File Storage)**: This repository contains large backup files that require Git LFS. Install Git LFS before cloning:
   ```bash
   # Install Git LFS (if not already installed)
   git lfs install
   
   # Clone the repository
   git clone https://github.com/neo4j-product-examples/knowledge-graph-agent.git
   cd knowledge-graph-agent/
   ```
   
   If you've already cloned without Git LFS, you can fetch the large files by running:
   ```bash
   git lfs pull
   ```

2. Ensure you have access to Neo4j Aura at [https://console-preview.neo4j.io/](https://console-preview.neo4j.io/)

### Setup Steps

1. Clone this repository (with Git LFS as described above)
2. Follow the specific tutorial for your use case
3. Customize the agents and tools for your specific domain requirements



## Agents Available

### Legal - Commercial Contract Review Agent

Our Contract Review example demonstrates how to build an intelligent agent for legal professionals. The agent can:
- Identifying high-risk contracts with missing or problematic clauses
- Assessing risk factors and compliance issues across contract portfolios
- Finding contracts with similar clauses or terms for comparative analysis
- Identifying all contracts associated with specific organizations
- Identify key clauses for a given contract

**[📖 View the complete Contract Review Agent tutorial](./contract-review.md)**

> **Learn more about CUAD**: The Contract Understanding Atticus Dataset (CUAD) v1 is a corpus of 13,000+ labels in 510 commercial legal contracts. For more information, visit the [Atticus Project CUAD page](https://www.atticusprojectai.org/cuad).

> **For Developers:** Curious about how the CUAD dataset was converted into a knowledge graph? Check out the [CUAD to Knowledge Graph conversion documentation](./code/cuad-to-knowledge-graph/README.md) for details on how the data processing pipeline.

For more on how the evaluation works (metrics, tracing, dataset design), see the **Medium blog post** that describes the full evaluation flow and what happens under the hood.

### Financial Services - Know Your Customer (KYC) Agent

Our comprehensive KYC example shows how to build an intelligent agent for fraud investigation and compliance analysis. The agent can:
- Identify customers involved in suspicious transaction rings
- Detect customers linked to "hot properties" (addresses with many residents)
- Find customers who work for multiple companies (potential bridges)
- Provide detailed customer profiles and risk assessments

**[📖 View the complete KYC Agent tutorial](./kyc-agent.md)**

### People/HR - Employee Agent

Our employee agent example demonstrates how to build an intelligent agent for skills analysis, talent search, team formation & HR. 

**[📖 View the complete Employee Agent tutorial](./employee-agent.md)**


## About Neo4j Aura Agent

Neo4j's Aura Agent combines the power of large language models with the structured knowledge in a Neo4j knowledge graph. 
This enables Aura agents to provide accurate, contextually relevant grounded by your knowledge graph. It helps improve explainability of your agent answers.

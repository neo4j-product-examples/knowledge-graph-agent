# CUAD Dataset to Knowledge Graph Processor

This folder contains Python scripts for processing the CUAD (Contract Understanding Atticus Dataset) and transforming it into a Knowledge Graph stored in Neo4j

## Overview

The CUAD dataset contains 500+ contracts in PDF and text format. These scripts extract contract information, identify clauses, and create a graph-based representation suitable for Neo4j or other graph databases.

**Learn more about CUAD**: The Contract Understanding Atticus Dataset (CUAD) v1 is a corpus of 13,000+ labels in 510 commercial legal contracts. For more information, visit the [Atticus Project CUAD page](https://www.atticusprojectai.org/cuad).

## Setup

The contract files are **not included** in this repository due to their size (500+ PDF and txt files). See the Usage section below for setup and processing instructions.

### Prerequisites
- Python 3.13+
- uv (Python package manager)
- Neo4j database (local or remote instance)
- Google Gemini API key

### Steps to Get Started

1. **Install dependencies and create virtual environment**
   ```bash
   uv sync
   ```

2. **Configure environment variables**
   - Copy `.env.example` to `.env`
   - Edit `.env` with your:
     - Neo4j connection details (URI, username, password)
     - Google Gemini API key

3. **Download the CUAD dataset**
   ```bash
   curl -L "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1" -o CUAD_v1.zip
   unzip CUAD_v1.zip
   rm CUAD_v1.zip
   ```

4. **Process contracts and create knowledge graph**
   - Run the scripts in order (see Usage section below for details)

## Usage

### 1. Install Dependencies

```bash
uv sync
```

### 2. Download CUAD Dataset

Download and extract the CUAD dataset:

```bash
curl -L "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1" -o CUAD_v1.zip
unzip CUAD_v1.zip
rm CUAD_v1.zip
```

### 3. Convert Contracts to JSON Format (`contract-to-json.py`)

This script:
- Reads contract files (PDF/txt) from the CUAD_v1 dataset
- Extracts contract metadata and clauses using Google's Gemini API
- Outputs structured JSON files to the CUAD-JSON directory
- Moves successfully processed files to data/processed

Process contracts

```bash
uv run python contract-to-json.py --max-workers 5
```

Optional arguments:
- `--api-key`: Specify Gemini API key (defaults to GEMINI_KEY environment variable)
- `--max-workers`: Number of concurrent workers (default: 3)
- `--sequential`: Process files sequentially instead of concurrently

Example with options:
```bash
uv run python contract-to-json.py --max-workers 5
```

### 4. Create Knowledge Graph in Neo4j (`json-to-graph.py`)

This script:
- Loads JSON-format contracts from the CUAD-JSON directory
- Creates a Neo4j knowledge graph with nodes for Agreements, Clauses, Organizations, Countries, etc.
- Establishes relationships between contracts, parties, clauses, and jurisdictions
- Creates database indices (full-text and vector) for efficient querying
- Merges duplicate country entities (USA, China, Spain variations)

After converting contracts to JSON, load them into a Neo4j database:

```bash
uv run python json-to-graph.py --batch-size 10
```

Optional arguments:
- `--batch-size`: Number of files to process in each batch (default: 10)

**Prerequisites:**
- Neo4j database running (local or remote)
- Environment variables set in `.env`:
  - `NEO4J_URI`: Neo4j connection URI (default: bolt://localhost:7687)
  - `NEO4J_USERNAME`: Neo4j username (default: neo4j)
  - `NEO4J_PASSWORD`: Neo4j password (required)

Example `.env` file:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
GEMINI_KEY=your_gemini_api_key_here
```

The script will:
1. Connect to your Neo4j database
2. Process JSON files in batches for optimal performance
3. Create nodes for contracts, organizations, clauses, jurisdictions, etc.
4. Establish relationships between entities
5. Create database indices for efficient querying
6. Merge duplicate country entities

### 5. Generate Vector Embeddings (`generate_embeddings.py`)

This script:
- Generates vector embeddings for all Excerpt nodes in the Neo4j graph
- Uses Google's Gemini API (gemini-embedding-001 model) to create 3072-dimensional embeddings
- Processes excerpts in optimized batches with automatic retry and rate-limiting
- Saves embeddings directly to Neo4j for similarity search capabilities
- Resumes from where it left off if interrupted (only processes excerpts without embeddings)

After creating the knowledge graph, generate vector embeddings for all contract excerpts to enable semantic similarity search:

```bash
uv run python generate_embeddings.py
```

**Prerequisites:**
- Completed step 4 (Knowledge graph created in Neo4j)
- Same `.env` configuration as step 4
- `GEMINI_KEY` environment variable set

The script will:
1. Check for existing embeddings and skip those already processed
2. Retrieve all Excerpt nodes that need embeddings
3. Generate 3072-dimensional embeddings using Gemini API in optimized batches
4. Save embeddings to Neo4j with automatic retry and rate-limit handling
5. Create a vector index for efficient similarity search

Features:
- **Resumable**: Can be safely interrupted and rerun - only processes excerpts without embeddings
- **Optimized batching**: Processes up to 100 excerpts per batch for efficiency
- **Automatic retry**: Handles rate limits and API errors with exponential backoff
- **Progress tracking**: Shows detailed progress and status updates

The embeddings enable semantic search capabilities, allowing you to find similar contract clauses based on meaning rather than just keyword matching.

## Data Directory Structure

```
cuad-to-knowledge-graph/
├── CUAD_v1/                          # Raw CUAD dataset (downloaded, not in repo)
│   ├── full_contract_pdf/            # PDF contract files organized by type
│   ├── full_contract_txt/            # Text contract files
│   ├── master_clauses.csv            # Clause labels and metadata
│   └── CUAD_v1.json                  # Dataset index
├── CUAD-JSON/                        # Extracted JSON output files
│   └── *.json                        # One JSON file per processed contract
├── data/
│   └── processed/                    # Successfully processed source files
│       └── *.txt                     # Original contract files after processing
├── contract-to-json.py               # Contract extraction script (PDF/txt → JSON)
├── json-to-graph.py                  # Knowledge graph creation script (JSON → Neo4j)
├── generate_embeddings.py            # Embedding generation script (Neo4j → Vector embeddings)
├── CREATE_GRAPH.cypher               # Cypher query for graph schema creation
├── AgreementSchema.py                # Pydantic schema for contract data
└── contract_extraction_prompt.txt    # Prompt template for Gemini API
```

## Pipeline Summary

The complete processing pipeline:
1. **Extract**: `contract-to-json.py` converts CUAD contracts (PDF/txt) → structured JSON
2. **Load**: `json-to-graph.py` imports JSON contracts → Neo4j knowledge graph
3. **Embed**: `generate_embeddings.py` generates vector embeddings for all contract excerpts
4. **Query**: Use Neo4j to explore contracts, clauses, parties, relationships, and semantic similarity

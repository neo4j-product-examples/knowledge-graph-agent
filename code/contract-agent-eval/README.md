# Contract Agent Evaluation

Minimal setup to run the Aura agent evaluation with Opik tracing.


For more on how the evaluation works (metrics, tracing, dataset design), check this [blog post](https://medium.com/@edward.sandoval.2000/how-to-evaluate-your-neo4j-aura-agent-using-comets-opik-65a08787662d)
![How to evaluate your Aura Agent with Opik](/images/aura-agent-opik.png)



## Prerequisites

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

2. [uv](https://docs.astral.sh/uv/) (Python package manager)

## Start Opik

In a separate terminal, clone and run the Opik platform:

```bash
# Clone the Opik repository
git clone https://github.com/comet-ml/opik.git

# Navigate to the opik folder
cd opik

# Start the Opik platform
./opik.sh
```

Once it's running, Opik will be available at http://localhost:5173

## Setup

1. **Create and sync the environment:**
Go back to the Terminal where you cloned the tutorial repo

   ```bash
   cd code/contract-agent-eval
   uv sync
   uv venv
   ```

2. **Configure environment variables:**

   Copy the example env file and set your own values:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set:

   - `CLIENT_ID` / `CLIENT_SECRET` — your Neo4j Aura API credentials
   - `ENDPOINT_URL` — your Aura agent invoke URL (e.g. `https://api.neo4j.io/v2beta1/projects/<project_id>/agents/<agent_id>/invoke`)
   - `OPENAI_API_KEY` — your OpenAI API key (used by Opik for evaluation metrics)

3. **Use your own evaluation dataset:**

   Replace `aura-agent-evaluation-dataset.json` with your own questions. Each item must have:

   - `input` — array of messages, e.g. `[{"role": "user", "content": "Your question here"}]`
   - `expected_output` — string (reference answer used for evaluation)

   The script reads this file by default.

## Run

```bash
uv run python agent-eval-trace.py
```


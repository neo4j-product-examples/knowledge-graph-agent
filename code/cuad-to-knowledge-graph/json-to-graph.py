import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
import json
import argparse
from pathlib import Path
import time

CREATE_VECTOR_INDEX_CYPHER = """
CREATE VECTOR INDEX excerpt_embedding IF NOT EXISTS 
    FOR (e:Excerpt) ON (e.embedding) 
    OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`:'cosine'}} 
"""




CREATE_FULL_TEXT_INDICES = [
    ("excerptTextIndex", "CREATE FULLTEXT INDEX excerptTextIndex IF NOT EXISTS FOR (e:Excerpt) ON EACH [e.text]"),
    ("agreementTypeTextIndex", "CREATE FULLTEXT INDEX agreementTypeTextIndex IF NOT EXISTS FOR (a:Agreement) ON EACH [a.agreement_type]"),
    ("clauseTypeNameTextIndex", "CREATE FULLTEXT INDEX clauseTypeNameTextIndex IF NOT EXISTS FOR (ct:ClauseType) ON EACH [ct.name]"),
    ("clauseNameTextIndex", "CREATE FULLTEXT INDEX contractClauseTypeTextIndex IF NOT EXISTS FOR (c:ContractClause) ON EACH [c.type]"),
    ("organizationNameTextIndex", "CREATE FULLTEXT INDEX organizationNameTextIndex IF NOT EXISTS FOR (o:Organization) ON EACH [o.name]"),
    ("contractIdIndex","CREATE INDEX agreementContractId IF NOT EXISTS FOR (a:Agreement) ON (a.contract_id) "),
    ("excerptIdIndex","CREATE INDEX excerptIdIndex IF NOT EXISTS FOR (e:Excerpt) ON (e.id)")
]


USA_RESOLUTION_CYPHER = """
MATCH (u1:Country{name:'United States'}), (u2:Country {name:'USA'}), (u3:Country {name:'U.S.A'}), (u4:Country {name:'US'}), (u5:Country {name:'U.S.A.'}) 
WITH [u1,u2,u3,u4,u5] as usa_nodes
CALL apoc.refactor.mergeNodes(usa_nodes,{properties:"discard", mergeRels:true})
YIELD node
RETURN count(*)
"""

CHINA_RESOLUTION_CYPHER="""

MATCH (c1:Country{name:'Republic of China'}), 
    (c2:Country {name:'P.R.C'}), 
    (c3:Country {name:'Peoples Republic of China'}), 
    (c4:Country {name:'China'}),
    (c5:Country {name:'P.R.C.'})  
WITH [c1,c2,c3,c4,c5] as china_nodes
CALL apoc.refactor.mergeNodes(china_nodes,{properties:"discard", mergeRels:true})
YIELD node
RETURN count(*)
"""

SPAIN_RESOLUTION_CYPHER="""

MATCH (s1:Country{name:'Spain'}), (s2:Country {name:'SPAIN'})
WITH [s1,s2] as spain_nodes
CALL apoc.refactor.mergeNodes(spain_nodes,{properties:"discard", mergeRels:true})
YIELD node
RETURN count(*)

"""


def index_exists(driver,  index_name):
  check_index_query = "SHOW INDEXES WHERE name = $index_name"
  result = driver.execute_query(check_index_query, {"index_name": index_name})
  return len(result.records) > 0
  


def create_full_text_indices(driver):
  with driver.session() as session:
    for index_name, create_query in CREATE_FULL_TEXT_INDICES:
      if not index_exists(driver,index_name):
        print(f"Creating index: {index_name}")
        driver.execute_query(create_query)
      else:
        print(f"Index {index_name} already exists.")        


def process_json_batch(driver, json_files_batch, create_graph_statement, start_contract_id, start_excerpt_id):
    """Process a batch of JSON files in a single transaction for better performance"""
    batch_data = []
    current_contract_id = start_contract_id
    current_excerpt_id = start_excerpt_id
    
    for json_file in json_files_batch:
        try:
            # Memory-efficient file reading for large JSON files
            file_size = json_file.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB threshold
                print(f"  📊 Large file detected ({file_size / (1024*1024):.1f}MB): {json_file.name}")
            
            with open(json_file, 'r', encoding='utf-8') as file:
                json_data = json.loads(file.read())
                
                # Add contract_id to the agreement
                json_data['contract_id'] = current_contract_id
                
                # Add unique IDs to all excerpts 
                for clause_idx, clause in enumerate(json_data['clauses']):
                    for excerpt_idx, excerpt in enumerate(clause['excerpts']):
                        json_data['clauses'][clause_idx]['excerpts'][excerpt_idx]['id'] = current_excerpt_id
                        current_excerpt_id += 1
                
                batch_data.append((json_file.name, json_data))
                current_contract_id += 1
                
        except Exception as e:
            print(f"  ✗ Error reading {json_file.name}: {str(e)}")
            continue
    
    # Process the entire batch in a single transaction with retry logic
    if batch_data:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with driver.session() as session:
                    with session.begin_transaction() as tx:
                        for file_name, json_data in batch_data:
                            tx.run(create_graph_statement, agreement_json=json_data)
                return len(batch_data), current_contract_id, current_excerpt_id
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Batch processing attempt {attempt + 1} failed, retrying...")
                    time.sleep(1)  # Brief delay before retry
                else:
                    print(f"  ✗ Error processing batch after {max_retries} attempts: {str(e)}")
                    return 0, start_contract_id, start_excerpt_id
    
    return 0, start_contract_id, start_excerpt_id

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Load CREATE_GRAPH_STATEMENT from the Cypher file
    with open('CREATE_GRAPH.cypher', 'r') as f:
        CREATE_GRAPH_STATEMENT = f.read().strip()
    
    # Get configuration from environment variables
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USERNAME', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD',"password")
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Load JSON contract data into Neo4j graph database')
    parser.add_argument('--batch-size', type=int, default=10, help='Number of files to process in each batch (default: 10)')
    
    args = parser.parse_args()
    
    # Use CUAD-JSON folder
    input_folder = 'CUAD-JSON'
    
    # Validate input folder
    if not os.path.exists(input_folder):
        print(f"Error: Input folder '{input_folder}' does not exist")
        return
    
    # Validate Neo4j password
    if not NEO4J_PASSWORD:
        print("Error: NEO4J_PASSWORD not found in environment variables")
        print("Please set NEO4J_PASSWORD in your .env file")
        return

    # Initialize the Neo4j driver with optimized configuration
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI, 
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30,
            max_transaction_retry_time=15
        )
        print(f"Connected to Neo4j at {NEO4J_URI}")
    except Exception as e:
        print(f"Error connecting to Neo4j: {str(e)}")
        return

    # Get all JSON files from input folder
    input_path = Path(input_folder)
    json_files = list(input_path.glob('*.json'))
    
    if not json_files:
        print(f"No JSON files found in '{input_folder}'")
        return
    
    print(f"Found {len(json_files)} JSON files to process")
    print(f"Input folder: {input_folder}")
    print(f"Batch size: {args.batch_size}")
    print("-" * 50)
    
    # Process files in batches
    successful = 0
    failed = 0
    total_start_time = time.time()
    contract_id = 1
    excerpt_id = 1
    
    # Process in batches for better performance
    for i in range(0, len(json_files), args.batch_size):
        batch = json_files[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(json_files) + args.batch_size - 1) // args.batch_size
        
        print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)...")
        start_time = time.time()
        
        batch_successful, contract_id, excerpt_id = process_json_batch(
            driver, batch, CREATE_GRAPH_STATEMENT, contract_id, excerpt_id
        )
        
        end_time = time.time()
        batch_time = end_time - start_time
        
        successful += batch_successful
        failed += len(batch) - batch_successful
        
        print(f"  ✓ Batch {batch_num} completed in {batch_time:.2f} seconds")
        print(f"  ✓ Successfully processed: {batch_successful}/{len(batch)} files")
        print()
    
    # Summary
    total_time = time.time() - total_start_time
    print("-" * 50)
    print(f"Processing complete!")
    print(f"Successfully processed: {successful} files")
    print(f"Failed: {failed} files")
    print(f"Total execution time: {total_time:.2f} seconds")
    print(f"Average time per file: {total_time/len(json_files):.2f} seconds")

    # Create indices after all data is loaded
    print("Creating database indices...")
    create_full_text_indices(driver)
    driver.execute_query(CREATE_VECTOR_INDEX_CYPHER)
    driver.execute_query(USA_RESOLUTION_CYPHER)
    driver.execute_query(CHINA_RESOLUTION_CYPHER)
    driver.execute_query(SPAIN_RESOLUTION_CYPHER)
    print("✓ Database indices created")
    
    # Close the driver
    driver.close()

if __name__ == "__main__":
    main()

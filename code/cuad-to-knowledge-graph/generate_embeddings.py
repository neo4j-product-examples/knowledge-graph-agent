import os
import json
from dotenv import load_dotenv
from neo4j import GraphDatabase
import google.genai as genai
import time
import random
import numpy as np


def get_all_excerpts(driver):
    """Retrieve all Excerpt nodes with their id and text properties"""
    query = """
    MATCH (e:Excerpt) 
    WHERE e.text IS NOT NULL 
    RETURN e.id as id, e.text as text
    ORDER BY e.id
    """
    
    result = driver.execute_query(query)
    excerpts = []
    
    for record in result.records:
        excerpts.append({
            'id': record['id'],
            'text': record['text']
        })
    
    return excerpts

def get_excerpts_without_embeddings(driver, limit=None):
    """Retrieve Excerpt nodes that don't have embeddings yet with optional limit for memory efficiency"""
    query = """
    MATCH (e:Excerpt) 
    WHERE e.text IS NOT NULL AND e.embedding IS NULL
    RETURN e.id as id, e.text as text
    ORDER BY e.id
    """ + (f" LIMIT {limit}" if limit else "")
    
    result = driver.execute_query(query)
    excerpts = []
    
    for record in result.records:
        # Memory optimization: only keep essential data
        text = record['text']
        if len(text) > 10000:  # Truncate very long texts for memory efficiency
            print(f"  📊 Truncating long excerpt {record['id']} ({len(text)} chars)")
            text = text[:10000] + "..."
        
        excerpts.append({
            'id': record['id'],
            'text': text
        })
    
    return excerpts

def count_existing_embeddings(driver):
    """Count how many excerpts already have embeddings"""
    query = """
    MATCH (e:Excerpt) 
    WHERE e.text IS NOT NULL 
    RETURN 
        COUNT(*) as total_excerpts,
        COUNT(e.embedding) as existing_embeddings
    """
    
    result = driver.execute_query(query)
    record = result.records[0]
    return record['total_excerpts'], record['existing_embeddings']

def generate_embeddings_batch(client, driver, excerpts, batch_size=100, dimensions=3072):
    """Generate embeddings for excerpts in batches and save each batch immediately"""
    total_processed = 0
    
    # Optimized rate limiting - less conservative for better throughput
    base_delay = 1.0  # Reduced base delay between batches in seconds
    max_retries = 3  # Reduced retries for faster failure handling
    
    # Process in batches to avoid API limits
    for i in range(0, len(excerpts), batch_size):
        batch = excerpts[i:i + batch_size]
        batch_num = i//batch_size + 1
        total_batches = (len(excerpts) + batch_size - 1) // batch_size
        
        print(f"Processing batch {batch_num}/{total_batches}: excerpts {i+1} to {min(i+batch_size, len(excerpts))}")
        
        # Prepare the content for batch embedding
        texts = [excerpt['text'] for excerpt in batch]
        batch_embeddings = {}
        
        # Retry logic with exponential backoff
        for attempt in range(max_retries):
            try:
                # Generate embeddings for the batch
                result = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=texts
                )
                
                # Map the embeddings back to excerpt IDs
                for j, embedding in enumerate(result.embeddings):
                    excerpt_id = batch[j]['id']
                    batch_embeddings[excerpt_id] = np.array(embedding.values)
                
                print(f"  ✓ Successfully generated embeddings for batch {batch_num}")
                break  # Success, exit retry loop
                
            except Exception as e:
                error_str = str(e)
                print(f"  ⚠️ Attempt {attempt + 1} failed for batch {batch_num}: {error_str}")
                
                # Check if it's a rate limit error
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "RATE_LIMIT_EXCEEDED" in error_str:
                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        print(f"  ⏳ Rate limit hit, waiting {delay:.1f} seconds before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"  ❌ Max retries reached for batch {batch_num}, trying individual processing...")
                        # Try individual processing for this batch
                        batch_success = process_batch_individually(client, batch, batch_embeddings)
                        if batch_success:
                            print(f"  ✓ Individual processing succeeded for batch {batch_num}")
                        else:
                            print(f"  ❌ Individual processing also failed for batch {batch_num}")
                        break
                else:
                    # Non-rate-limit error, try individual processing immediately
                    print(f"  ⚠️ Non-rate-limit error, trying individual processing...")
                    batch_success = process_batch_individually(client, batch, batch_embeddings)
                    if batch_success:
                        print(f"  ✓ Individual processing succeeded for batch {batch_num}")
                    else:
                        print(f"  ❌ Individual processing also failed for batch {batch_num}")
                    break
        
        # Save this batch to Neo4j if we have embeddings
        if batch_embeddings:
            print(f"  💾 Saving batch {batch_num} embeddings to Neo4j...")
            save_batch_embeddings_to_neo4j(driver, batch_embeddings, dimensions)
            total_processed += len(batch_embeddings)
            print(f"  ✅ Saved {len(batch_embeddings)} embeddings from batch {batch_num}")
        
        # Reduced delay between batches for better throughput
        if i + batch_size < len(excerpts):  # Don't delay after the last batch
            delay = base_delay + random.uniform(0, 0.2)  # Reduced jitter
            print(f"  ⏳ Waiting {delay:.1f} seconds before next batch...")
            time.sleep(delay)
    
    return total_processed

def save_batch_embeddings_to_neo4j(driver, batch_embeddings, dimensions=3072):
    """Save a batch of embeddings to Neo4j with optimized batch processing"""
    update_query = """
    UNWIND $batch as item
    CALL (item) {
        MATCH (e:Excerpt {id: item.id})
        CALL db.create.setNodeVectorProperty(e, 'embedding', item.embedding)
    } IN TRANSACTIONS OF 500 ROWS
    """
    
    try:
        # Prepare batch data with optimized processing
        batch_data = []
        for excerpt_id, embedding in batch_embeddings.items():
            # Convert numpy array to list of floats, taking only first dimensions
            embedding_list = embedding[:dimensions].astype(float).tolist()
            batch_data.append({
                'id': excerpt_id,
                'embedding': embedding_list
            })
        
        # Use session with optimized transaction handling
        with driver.session() as session:
            # Process in smaller chunks if batch is very large
            chunk_size = 500
            for i in range(0, len(batch_data), chunk_size):
                chunk = batch_data[i:i + chunk_size]
                session.run(update_query, {'batch': chunk})
        
    except Exception as e:
        print(f"    ❌ Error saving batch embeddings: {str(e)}")
        raise

def process_batch_individually(client, batch, excerpt_embeddings):
    """Process a batch individually when batch processing fails"""
    success_count = 0
    
    for excerpt in batch:
        max_individual_retries = 3
        for attempt in range(max_individual_retries):
            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=[excerpt['text']]
                )
                excerpt_embeddings[excerpt['id']] = np.array(result.embeddings[0].values)
                success_count += 1
                break
            except Exception as individual_error:
                error_str = str(individual_error)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "RATE_LIMIT_EXCEEDED" in error_str:
                    if attempt < max_individual_retries - 1:
                        delay = 3.0 * (2 ** attempt) + random.uniform(0, 2)
                        print(f"    ⏳ Rate limit on individual excerpt {excerpt['id']}, waiting {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"    ❌ Max retries reached for excerpt {excerpt['id']}: {error_str}")
                        break
                else:
                    print(f"    ❌ Error processing excerpt {excerpt['id']}: {error_str}")
                    break
        
        # Small delay between individual requests
        time.sleep(0.1)
    
    return success_count > 0



def main():
    # Load environment variables
    load_dotenv()
    
    # Configure Gemini API
    gemini_key = os.getenv('GEMINI_KEY')
    if not gemini_key:
        print("Error: GEMINI_KEY not found in environment variables")
        return
    
    client = genai.Client(api_key=gemini_key)
    
    # Get Neo4j configuration from environment variables
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USERNAME', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD',"password")
    DIMENSIONS = 3072
    
    if not NEO4J_PASSWORD:
        print("Error: NEO4J_PASSWORD not found in environment variables")
        return
    
    # Connect to Neo4j with optimized configuration
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI, 
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=20,
            connection_acquisition_timeout=30,
            max_transaction_retry_time=15
        )
        print(f"Connected to Neo4j at {NEO4J_URI}")
    except Exception as e:
        print(f"Error connecting to Neo4j: {str(e)}")
        return
    
    try:
        # Check existing embeddings
        print("Checking existing embeddings...")
        total_excerpts, existing_embeddings = count_existing_embeddings(driver)
        print(f"Found {total_excerpts} total excerpts, {existing_embeddings} already have embeddings")
        
        if existing_embeddings == total_excerpts:
            print("✅ All excerpts already have embeddings! Nothing to do.")
            return
        
        # Get excerpts that need embeddings
        print("Retrieving excerpts that need embeddings...")
        excerpts = get_excerpts_without_embeddings(driver)
        remaining_count = len(excerpts)
        print(f"Found {remaining_count} excerpts that need embeddings")
        
        if not excerpts:
            print("No excerpts found that need embeddings. Exiting.")
            return
        
        # Generate embeddings and save them batch by batch
        print("Generating and saving embeddings using Gemini API...")
        start_time = time.time()
        
        # Optimize batch size based on available memory and API limits
        # Google API allows max 100 requests per batch
        optimal_batch_size = min(100, len(excerpts) // 10 + 1)  # Dynamic batch sizing
        total_processed = generate_embeddings_batch(client, driver, excerpts, batch_size=optimal_batch_size, dimensions=DIMENSIONS)
        
        end_time = time.time()
        print(f"Generated and saved embeddings for {total_processed} excerpts in {end_time - start_time:.2f} seconds")
        
        # Final status check
        print("\nChecking final embedding status...")
        final_total, final_existing = count_existing_embeddings(driver)
        print(f"✅ Final status: {final_existing}/{final_total} excerpts now have embeddings")
        
        if final_existing == final_total:
            print("🎉 All excerpts now have embeddings!")
        else:
            remaining = final_total - final_existing
            print(f"⚠️  {remaining} excerpts still need embeddings")
        
    except Exception as e:
        print(f"Error during processing: {str(e)}")
    finally:
        driver.close()

if __name__ == "__main__":
    main() 
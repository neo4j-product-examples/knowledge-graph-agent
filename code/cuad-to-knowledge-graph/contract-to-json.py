from google import genai
from google.genai import types
from AgreementSchema import Agreement
import time
import os
import json
import argparse
import shutil
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import concurrent.futures
import threading
from queue import Queue


def determine_file_type(file_path):
    """Determine if a file is PDF or text based on its extension"""
    extension = Path(file_path).suffix.lower()
    if extension == '.pdf':
        return 'pdf'
    elif extension in ['.txt', '.text']:
        return 'text'
    else:
        return None

def create_file_part(file_path, file_type):
    """Create appropriate Part object based on file type"""
    if file_type== 'pdf':
        with open(file_path, 'rb') as f:
            pdf_bytes = f.read()
        return types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf')
    elif file_type == 'text':
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        return types.Part.from_text(text=text_content)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

def process_file(client, file_path, prompt, output_folder, thread_id=None):
    """Process a single file and save the JSON output"""
    file_name = Path(file_path).name
    thread_prefix = f"[Thread {thread_id}] " if thread_id else ""
    print(f"{thread_prefix}Processing {file_name}...")
    
    # Determine file type
    file_type = determine_file_type(file_path)
    if file_type is None:
        print(f"  {thread_prefix}Skipping {file_name} - unsupported file type")
        return False
    
    try:
        # Create file part based on file type (pdf or text)
        file_part = create_file_part(file_path, file_type)
        
        # Start timing and capture start datetime
        start_time = time.time()
        start_datetime = datetime.now()
        
        # Generate the content
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, file_part],
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                response_schema=Agreement,
            )
        )
        
        # End timing
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Parse the JSON response
        json_data = json.loads(response.text)
        #add file name to the json data
        json_data['file_name'] = file_name
        
        # Create output filename
        output_filename = f"{Path(file_path).stem}.json"
        output_path = os.path.join(output_folder, output_filename)
        
        # Save the JSON to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        # Move the successfully processed file to data/processed folder
        processed_folder = "data/processed"
        os.makedirs(processed_folder, exist_ok=True)
        
        destination_path = os.path.join(processed_folder, file_name)
        shutil.move(str(file_path), destination_path)
        
        print(f"  {thread_prefix}✓ Processed {file_name} in {execution_time:.2f} seconds (started at {start_datetime.strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"  {thread_prefix}✓ Saved to {output_filename}")
        print(f"  {thread_prefix}✓ Moved to {processed_folder}")
        return True
        
    except Exception as e:
        print(f"  {thread_prefix}✗ Error processing {file_name}: {str(e)}")
        return False

def worker_thread(client, prompt, output_folder, file_queue, results_queue, thread_id):
    """Worker thread function for processing files concurrently"""
    while True:
        try:
            file_path = file_queue.get(timeout=1)  # 1 second timeout
            if file_path is None:  # Sentinel value to stop thread
                break
            
            success = process_file(client, file_path, prompt, output_folder, thread_id)
            results_queue.put((file_path, success))
            file_queue.task_done()
            
        except:
            break  # Queue is empty or timeout occurred

def process_files_concurrent(client, files_to_process, prompt, output_folder, max_workers=3):
    """Process files concurrently using multiple threads"""
    file_queue = Queue()
    results_queue = Queue()
    
    # Add all files to the queue
    for file_path in files_to_process:
        file_queue.put(file_path)
    
    # Start worker threads
    threads = []
    for i in range(max_workers):
        thread = threading.Thread(
            target=worker_thread,
            args=(client, prompt, output_folder, file_queue, results_queue, i+1)
        )
        thread.start()
        threads.append(thread)
    
    # Wait for all files to be processed
    file_queue.join()
    
    # Stop all threads
    for _ in range(max_workers):
        file_queue.put(None)  # Sentinel value
    
    for thread in threads:
        thread.join()
    
    # Collect results
    successful = 0
    failed = 0
    while not results_queue.empty():
        file_path, success = results_queue.get()
        if success:
            successful += 1
        else:
            failed += 1
    
    return successful, failed

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Get API key from environment variable
    gemini_key = os.getenv('GEMINI_KEY')
    
    parser = argparse.ArgumentParser(description='Extract information from contracts and save as JSON')
    parser.add_argument('--api-key', default=gemini_key, help='Google API key (defaults to GEMINI_KEY environment variable)')
    parser.add_argument('--max-workers', type=int, default=3, help='Maximum number of concurrent workers (default: 3)')
    parser.add_argument('--sequential', action='store_true', help='Process files sequentially instead of concurrently')
    
    args = parser.parse_args()
    
    # Validate API key
    if not args.api_key:
        print("Error: GEMINI_KEY not found in environment variables and no --api-key provided")
        print("Please either:")
        print("1. Set GEMINI_KEY in your .env file, or")
        print("2. Use the --api-key argument")
        return
    
    # Determine the script directory and folder locations
    script_dir = Path(__file__).parent
    input_folder = script_dir / 'CUAD_v1'
    output_folder = script_dir / 'CUAD-JSON'
    
    # Validate CUAD_v1 folder exists
    if not input_folder.exists():
        print(f"Error: CUAD_v1 folder not found at '{input_folder}'")
        print(f"Please ensure the CUAD_v1 dataset is located in the same directory as this script.")
        return
    
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Initialize the client
    client = genai.Client(api_key=args.api_key)
    
    # Read the prompt from the text file
    prompt_file = script_dir / 'contract_extraction_prompt.txt'
    with open(prompt_file, 'r') as f:
        contract_extraction_prompt = f.read().strip()
    
    # Get all PDF and text files from CUAD_v1 folder recursively
    supported_extensions = ['.pdf', '.txt', '.text']
    files_to_process = []
    
    # Recursively find all files with supported extensions
    for file_path in input_folder.rglob('*'):
        if file_path.is_file():
            file_ext = file_path.suffix.lower()
            # Skip README.txt files
            if file_path.name.upper() == 'README.TXT':
                continue
            if file_ext in supported_extensions:
                files_to_process.append(file_path)
    
    if not files_to_process:
        print(f"No PDF or text files found in '{input_folder}'")
        return
    
    print(f"Found {len(files_to_process)} files to process in CUAD_v1 folder")
    print(f"Input folder: {input_folder}")
    print(f"Output folder: {output_folder}")
    print(f"Processing mode: {'Sequential' if args.sequential else f'Concurrent ({args.max_workers} workers)'}")
    print("-" * 50)
    
    # Process files
    total_start_time = time.time()
    
    if args.sequential:
        # Sequential processing (original behavior)
        successful = 0
        failed = 0
        for file_path in files_to_process:
            if process_file(client, file_path, contract_extraction_prompt, output_folder):
                successful += 1
            else:
                failed += 1
            print()  # Empty line for readability
    else:
        # Concurrent processing
        print(f"Starting concurrent processing with {args.max_workers} workers...")
        successful, failed = process_files_concurrent(
            client, files_to_process, contract_extraction_prompt, 
            output_folder, args.max_workers
        )
    
    # Summary
    total_time = time.time() - total_start_time
    print("-" * 50)
    print(f"Processing complete!")
    print(f"Successfully processed: {successful} files")
    print(f"Failed: {failed} files")
    print(f"Total execution time: {total_time:.2f} seconds")

    

if __name__ == "__main__":
    main()

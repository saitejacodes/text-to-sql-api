import json
from datasets import load_dataset

def main():
    print("Loading datasets...")
    try:
        queries = load_dataset("beaverbench/beaver-query")
        tables = load_dataset("beaverbench/beaver-table")
        
        print("\nQuery Dataset splits:", queries.keys())
        print("Table Dataset splits:", tables.keys())
        
        if 'train' in queries:
            split = 'train'
        else:
            split = list(queries.keys())[0]
            
        print(f"\nUsing split '{split}' for queries.")
        
        first_query = queries[split][0]
        print("\nFirst query sample:")
        print(json.dumps(first_query, indent=2))
        
        table_split = list(tables.keys())[0]
        print(f"\nUsing split '{table_split}' for tables.")
        first_table = tables[table_split][0]
        print("\nFirst table sample:")
        print(json.dumps(first_table, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

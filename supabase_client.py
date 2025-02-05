from supabase import create_client
import os
from typing import Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Supabase credentials from environment variables
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')

if not supabase_url or not supabase_key:
    raise ValueError("Missing Supabase credentials. Please set SUPABASE_URL and SUPABASE_KEY environment variables.")

# Initialize Supabase client
supabase = create_client(supabase_url, supabase_key)

def insert_contact(contact_data: Dict) -> Dict:
    """
    Insert a contact record into Supabase contacts table.
    """
    try:
        response = supabase.table('contacts').insert(contact_data).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        print(f"Error inserting contact: {e}")
        return {"error": str(e)}

def insert_interaction(interaction_data: Dict) -> Dict:
    """
    Insert an interaction record into Supabase interactions table.
    """
    try:
        response = supabase.table('interactions').insert(interaction_data).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        print(f"Error inserting interaction: {e}")
        return {"error": str(e)}

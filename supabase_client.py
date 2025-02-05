from supabase import create_client
import os
from typing import Dict, List
from dotenv import load_dotenv
import random

load_dotenv()

supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')

if not supabase_url or not supabase_key:
    raise ValueError("Missing Supabase credentials. Please set SUPABASE_URL and SUPABASE_KEY.")

supabase = create_client(supabase_url, supabase_key)

def insert_contact(contact_data: Dict) -> Dict:
    try:
        response = supabase.table('contacts').insert(contact_data).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        print(f"Error inserting contact: {e}")
        return {"error": str(e)}

def insert_interaction(interaction_data: Dict) -> Dict:
    try:
        response = supabase.table('interactions').insert(interaction_data).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        print(f"Error inserting interaction: {e}")
        return {"error": str(e)}

def store_classification_outcome(message: str, original_label: str, correct_label: str):
    """
    Insert a row into classification_outcomes table, so we can see
    how the user corrected a mis-classification.
    """
    try:
        data = {
            "message": message,
            "original_label": original_label,
            "correct_label": correct_label
        }
        supabase.table("classification_outcomes").insert(data).execute()
    except Exception as e:
        print(f"Error storing classification outcome: {e}")

def get_classification_examples(limit: int = 5) -> List[Dict]:
    """
    Fetch up to 'limit' classification_outcomes 
    where the user corrected the classification. 
    We'll pass them as few-shot examples in the system prompt.
    """
    try:
        # For example, get rows where original_label != correct_label
        # and order by created_at desc, limit 5
        resp = (
            supabase.table("classification_outcomes")
            .select("message, original_label, correct_label, created_at")
            .neq("original_label", "correct_label")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data if resp.data else []
    except Exception as e:
        print(f"Error fetching classification examples: {e}")
        return []

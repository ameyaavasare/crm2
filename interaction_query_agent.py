from supabase_client import supabase

def handle_interaction_query(message: str) -> str:
    """
    Query interactions from the 'interactions' table.
    Must handle more complex queries in real usage.
    """
    # Example: "Find all interactions with John in January"
    # For demonstration, do a naive search for contact_id or date range
    contact_id = "SOME_UUID"
    response = supabase.table("interactions").select("*").eq("contact_id", contact_id).execute()
    rows = response.data

    if rows:
        return f"Found {len(rows)} interaction(s) for contact_id={contact_id}. First: {rows[0]}"
    else:
        return "No interactions found."

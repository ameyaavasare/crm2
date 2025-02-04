from supabase_client import supabase

def handle_query_contacts(message: str) -> str:
    """
    Construct a query to 'contacts' table in Supabase and return results.
    This is a placeholder for demonstration.
    """
    # Example: "Find contact info for John"
    # In a real scenario, you'd parse out the name from the message.
    # Here we do a naive "like" query
    name_to_find = "John"  # placeholder
    response = supabase.table("contacts").select("*").ilike("name", f"%{name_to_find}%").execute()
    rows = response.data

    if rows:
        # Format them for the user
        return f"Found {len(rows)} contact(s). First contact: {rows[0]}"
    else:
        return "No contacts found matching your query."

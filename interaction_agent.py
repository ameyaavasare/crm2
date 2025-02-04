from supabase_client import supabase

def handle_interaction(message: str) -> str:
    """
    Create a new interaction record in the 'interactions' table.
    """
    # Example: "New interaction with John, note='Had lunch today to discuss project.'"
    # You'd parse contact name or ID from the message and the note content.
    contact_id = "SOME_UUID"  # you'd actually look up by name, or parse from message
    note = "Had lunch today to discuss project."  # naive placeholder

    data = supabase.table("interactions").insert({
        "contact_id": contact_id,
        "note": note
    }).execute()

    return "New interaction added."

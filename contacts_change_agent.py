from supabase_client import supabase

def handle_contacts_change(message: str) -> str:
    """
    Add, update, or delete a contact.
    If insufficient data, ask the user for more info.
    This is a placeholder to demonstrate approach.
    """

    # Very naive approach to parse whether user wants to add/update/delete
    # In production, parse with GPT or robust logic
    lower_msg = message.lower()
    if "add contact" in lower_msg:
        # Example: "Add contact John Doe, phone=555-1212, email=john@example.com"
        # We'll pretend we've parsed out the data; obviously you'd do robust parsing
        new_contact = {
            "name": "John Doe",
            "phone": "555-1212",
            "email": "john@example.com",
        }
        data = supabase.table("contacts").insert(new_contact).execute()
        return "Contact added successfully."
    elif "update contact" in lower_msg:
        # Example logic: parse contact name, then update phone, etc.
        # ...
        return "Contact updated successfully."
    elif "delete contact" in lower_msg:
        # Example logic: parse contact name or phone, then do supabase.table('contacts').delete()
        # ...
        return "Contact deleted successfully."
    else:
        return "To add, update, or delete a contact, specify the exact action."

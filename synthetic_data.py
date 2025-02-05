import random
from datetime import datetime, timedelta
import os
import openai  # Import the OpenAI module
from supabase_client import supabase  # Your Supabase client
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Set your OpenAI API key using the environment variable
openai.api_key = os.environ.get("OPENAI_API_KEY")

def random_name():
    """Generate a random first+last name."""
    first_names = [
        "Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona", "George", "Hannah",
        "Ian", "Jane", "Kevin", "Laura", "Michael", "Nina", "Oliver", "Paula",
        "Quincy", "Rachel", "Steve", "Tina", "Uma", "Victor", "Wendy", "Xander",
        "Yvonne", "Zack"
    ]
    last_names = [
        "Smith", "Johnson", "Brown", "Miller", "Wilson", "Taylor", "Anderson", 
        "Thomas", "Jackson", "White", "Harris", "Martin", "Garcia", "Thompson"
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def random_phone():
    """Generate a random 10-digit US phone number (E.164 with +1)."""
    digits = "".join(random.choices("0123456789", k=10))
    return f"+1{digits}"

def random_email(name: str):
    """Make a simple email from the person's name."""
    base = name.lower().replace(" ", ".")
    domains = ["example.com", "dummy.org", "test.net"]
    return f"{base}@{random.choice(domains)}"

def random_birthday():
    """Pick a random date in the last ~40 years."""
    start_date = datetime(1975, 1, 1)
    end_date = datetime(2010, 1, 1)
    delta = end_date - start_date
    random_days = random.randrange(delta.days)
    return (start_date + timedelta(days=random_days)).date().isoformat()

def create_contacts(n=30):
    """Generate a list of contact dicts."""
    contacts = []
    for _ in range(n):
        name = random_name()
        contact = {
            "name": name,
            "phone": random_phone(),
            "email": random_email(name),
            "birthday": random_birthday(),
            "family_members": None,
            "description": "Synthetic contact record",
            # created_at/updated_at can rely on DB defaults
        }
        contacts.append(contact)
    return contacts

def insert_contacts_into_db(contacts):
    """Insert multiple contacts at once, returning list of inserted records."""
    result = supabase.table("contacts").insert(contacts).execute()
    return result.data

def process_single_contact(contact, interactions_per_contact=5):
    """Process a single contact's interactions."""
    contact_id = contact["uuid"]
    name = contact["name"]
    print(f"\nProcessing contact {name} (thread: {threading.current_thread().name})")
    
    contact_interactions = []
    for interaction_num in range(1, interactions_per_contact + 1):
        prompt = (
            f"Generate 1 realistic CRM-style note about an interaction with {name}. "
            "This should be a natural entry as if you had a meeting, call, or run-in with them. "
            "Include personal details about their life, work, family, or hobbies. "
            "Write exactly 1 sentence."
        )

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates realistic CRM interaction notes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                request_timeout=30
            )
            
            note = response.choices[0].message.content.strip()
            if note:
                contact_interactions.append({
                    "contact_id": contact_id,
                    "note": note,
                })
                print(f"  Created interaction {interaction_num}/{interactions_per_contact} for {name}")
            
        except Exception as e:
            print(f"  Error during GPT call for contact {name}, interaction {interaction_num}: {e}")
            continue
    
    # Insert interactions for this contact
    if contact_interactions:
        inserted = insert_interactions_into_db(contact_interactions)
        print(f"  Inserted {len(inserted)} interactions for {name}")
    
    return len(contact_interactions)

def create_interactions_for_contacts(contact_records, interactions_per_contact=5, max_workers=5):
    """
    Process contacts in parallel using ThreadPoolExecutor.
    """
    total_interactions = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all contacts for processing
        future_to_contact = {
            executor.submit(process_single_contact, contact, interactions_per_contact): contact
            for contact in contact_records
        }
        
        # Process results as they complete
        for future in as_completed(future_to_contact):
            contact = future_to_contact[future]
            try:
                num_interactions = future.result()
                total_interactions += num_interactions
            except Exception as e:
                print(f"Error processing contact {contact['name']}: {e}")
    
    return total_interactions

def insert_interactions_into_db(interactions):
    """Insert multiple interactions in a single request."""
    result = supabase.table("interactions").insert(interactions).execute()
    return result.data

if __name__ == "__main__":
    # 1) Create 30 random contacts
    synthetic_contacts = create_contacts(n=30)
    
    # 2) Insert them into the DB
    inserted_contacts = insert_contacts_into_db(synthetic_contacts)
    print(f"Inserted {len(inserted_contacts)} contacts.")

    # 3) For each inserted contact, create and insert interactions
    create_interactions_for_contacts(
        contact_records=inserted_contacts,
        interactions_per_contact=5
    )
    # Remove the final insert since we're doing it per-contact now

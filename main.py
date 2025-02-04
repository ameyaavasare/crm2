import os
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import JSONResponse
from twilio.rest import Client
from dotenv import load_dotenv

from agents.classify_agent import classify_message
from agents.contacts_change_agent import handle_contacts_change
from agents.query_contacts_agent import handle_query_contacts
from agents.interaction_agent import handle_interaction
from agents.interaction_query_agent import handle_interaction_query

load_dotenv()

app = FastAPI()

# Twilio client (optional for outbound messages)
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

@app.get("/")
def read_root():
    return {"Hello": "CRM is running!"}

@app.get("/sms")
def sms_get():
    """
    Twilio should POST here. This GET helps avoid 404/405 errors if Twilio (or you) do a GET.
    """
    return {
        "message": "Send a POST request with Twilio form data to this endpoint."
    }

@app.post("/sms")
async def sms_webhook(
    From: str = Form(...),
    Body: str = Form(...),
):
    """
    Twilio will POST form data: 'From', 'Body', etc. 
    The 'From' and 'Body' fields are parsed via FastAPI's Form.
    """
    # Debug print (visible in Replit logs)
    print(f"** Incoming SMS from {From}: {Body}")

    # Step 1: classify the message
    agent_type = classify_message(Body)

    # Step 2: route to the correct agent
    if agent_type == "contacts_change":
        response_text = handle_contacts_change(Body)
    elif agent_type == "query_contacts":
        response_text = handle_query_contacts(Body)
    elif agent_type == "interaction":
        response_text = handle_interaction(Body)
    elif agent_type == "interaction_query":
        response_text = handle_interaction_query(Body)
    else:
        response_text = (
            "I'm not sure how to handle that request. "
            "Try again with more context."
        )

    # Example of responding via Twilio (commented out by default):
    # twilio_client.messages.create(
    #     body=response_text,
    #     from_="YOUR_TWILIO_PHONE_NUMBER",
    #     to=From
    # )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": response_text}
    )

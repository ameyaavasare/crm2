import os
from fastapi import FastAPI, Request, Body, status
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

# Twilio client (if needed for outbound messages)
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

@app.get("/")
def read_root():
    return {"Hello": "CRM is running!"}

@app.post("/sms")
async def sms_webhook(request: Request):
    """
    This endpoint will receive incoming SMS from Twilio.
    Twilio will POST form data: 'From', 'Body', etc.
    """
    form_data = await request.form()
    from_number = form_data.get("From")
    message_body = form_data.get("Body")

    # Step 1: Classify the incoming message
    agent_type = classify_message(message_body)

    # Step 2: Route to the appropriate agent
    if agent_type == "contacts_change":
        response_text = handle_contacts_change(message_body)
    elif agent_type == "query_contacts":
        response_text = handle_query_contacts(message_body)
    elif agent_type == "interaction":
        response_text = handle_interaction(message_body)
    elif agent_type == "interaction_query":
        response_text = handle_interaction_query(message_body)
    else:
        # Fallback
        response_text = (
            "I'm not sure how to handle that request. "
            "Try again with more context."
        )

    # Optionally: respond via Twilio if desired
    # twilio_client.messages.create(
    #     body=response_text,
    #     from_="YOUR_TWILIO_PHONE_NUMBER",
    #     to=from_number
    # )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": response_text}
    )

import streamlit as st
import time
import csv
import os
import json
import sys
from openai import OpenAI

# Define instructions for the assistant
instructions = (
    "You are a chatbot that can handle customer support queries for an e-commerce platform. If you're "
    "asked for something not related to the e-commerce business, orders or customers info, explain "
    "nicely that your goal is to handle the e-commerce business only and not to answer unrelated areas.\n\n"
    "If someone requests human representative that will call him later, ask him to provide with his full "
    "name, valid email address and valid phone number - 10 digit number, can start with zero (no need to "
    "explain that to the customer unless they gave invalid number), and use these 3 parameters with the "
    "provided add_contact function. Also if you feel that the user is angry or mad, suggest the human "
    "representative option yourself.\n\n"
    "If you're asked for order status, ask the user for their order_id. If they provide it, tell them the "
    "order status by using this order id as parameter for the check_order_status function. If they don't "
    "know it, tell them you're sorry but can't do anything without the order_id.\n\n"
    "When asked about return policies, answer this:\n"
    "If the question is 'What is the return policy for items purchased at our store?' answer 'You can "
    "return most items within 30 days of purchase for a full refund or exchange. Items must be in their "
    "original condition, with all tags and packaging intact. Please bring your receipt or proof of purchase "
    "when returning items.'\n\n"
    "If the question is 'Are there any items that cannot be returned under this policy?' answer 'Yes, certain "
    "items such as clearance merchandise, perishable goods, and personal care items are non-returnable. Please "
    "check the product description or ask a store associate for more details.'\n\n"
    "If the question is 'How will I receive my refund?' answer 'Refunds will be issued to the original form of "
    "payment. If you paid by credit card, the refund will be credited to your card. If you paid by cash or check, "
    "you will receive a cash refund.'"
)

# Define tools for the assistant
tools = [
    {
        "type": "function",
        "function": {
            "name": "add_contact",
            "description": "Add user's info to the CSV file",
            "parameters": {
                "type": "object",
                "properties": {
                    "full_name": {
                        "type": "string",
                        "description": "The user's full name"
                    },
                    "email": {
                        "type": "string",
                        "description": "The user's email"
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The user's phone number"
                    }
                },
                "required": ["full_name", "email", "phone_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_order_status",
            "description": "Get the order status based on id from inventory",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order id number"
                    }
                },
                "required": ["order_id"]
            }
        }
    }
]

# Function to add contact details to a CSV file
def add_contact(full_name, email, phone_number):
    filename = 'Contacts_For_Human_Representative.csv'
    contact_exists = False

    if os.path.isfile(filename):
        with open(filename, mode='r', newline='') as file:
            reader = csv.reader(file)
            for row in reader:
                if row == [full_name, email, phone_number]:
                    contact_exists = True
                    break

    if contact_exists:
        return "I can see that you already requested for human representative, I will try to hurry " \
               "out human customer services to call you back!"

    with open(filename, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not os.path.isfile(filename):
            writer.writerow(['Full Name', 'Email', 'Phone Number'])
        writer.writerow([full_name, email, phone_number])

    return "Your contact information was registered, a human representative will call you back soon"

# Function to check the order status based on order ID, in the orders CSV
def check_order_status(order_id):
    filename = 'Orders_Info.csv'
    no_order = "There are no such order id in our orders inventory, are you sure you got the right order id?"

    if not os.path.isfile(filename):
        return no_order

    with open(filename, mode='r', newline='') as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip the header row
        for row in reader:
            if int(row[0]) == int(order_id):
                owner_name = row[1]
                order_status = row[2]
                return f"Hi {owner_name}, your order is currently {order_status}"

    return no_order

# Function to handle tool call outputs
def get_outputs_for_tool_call(tool_call):
    if tool_call.function.name == "add_contact":
        full_name = json.loads(tool_call.function.arguments)["full_name"]
        email = json.loads(tool_call.function.arguments)["email"]
        phone_number = json.loads(tool_call.function.arguments)["phone_number"]
        details = add_contact(full_name, email, phone_number)
    elif tool_call.function.name == "check_order_status":
        order_id = json.loads(tool_call.function.arguments)["order_id"]
        details = check_order_status(order_id)
    else:
        details = ""

    return {
        "tool_call_id": tool_call.id,
        "output": details
    }

# Function to load OpenAI client and assistant
def load_openai_client_and_assistant(api_key, assistant_id):
    client = OpenAI(api_key=api_key)
    if assistant_id:
        my_assistant = client.beta.assistants.retrieve(assistant_id)
    else:
        my_assistant = client.beta.assistants.create(
            name="E-Commerce Bot",
            instructions=instructions,
            tools=tools,
            model='gpt-4o'
        )
    thread = client.beta.threads.create()

    return client, my_assistant, thread

# Function to wait for the assistant to process and handle function calls
def wait_on_run(run, thread):
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        if run.status == 'completed':
            break
        elif run.status == 'requires_action':
            print("Function Calling ...")
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = list(map(get_outputs_for_tool_call, tool_calls))
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
        else:
            print("Waiting for the Assistant to process...")
        time.sleep(0.5)

    return run

# Function to get assistant response
def get_assistant_response(user_input="", assistant_id="",client=None,assistant_thread=None):
    message = client.beta.threads.messages.create(
        thread_id=assistant_thread.id,
        role="user",
        content=user_input,
    )
    run = client.beta.threads.runs.create(
        thread_id=assistant_thread.id,
        assistant_id=assistant_id,
    )
    run = wait_on_run(run, assistant_thread)
    messages = client.beta.threads.messages.list(
        thread_id=assistant_thread.id, order="asc", after=message.id
    )

    return messages.data[0].content[0].text.value

@st.cache_resource
def initial_login():
    try:
        api_key = st.secrets["openai_apikey"]
        print(f"OpenAI api key found: {api_key}")
    except KeyError:
        print("OpenAI api key not found in secrets, you have to get one in order to execute this code")
        sys.exit(1)

    try:
        assistant_id = st.secrets["assistant_id"]
        print(f"Assistant ID found: {assistant_id}")
        client, my_assistant, assistant_thread = load_openai_client_and_assistant(api_key=api_key,
                                                                                  assistant_id=assistant_id)
    except KeyError:
        print("Assistant ID not found in secrets, creating e-commerce assistant")
        client, my_assistant, assistant_thread = load_openai_client_and_assistant(api_key=api_key,
                                                                                  assistant_id=None)
        assistant_id = my_assistant.id

    return api_key, client, assistant_thread, assistant_id

def submit():
    st.session_state.user_input = st.session_state.query
    st.session_state.query = ''

# Initializing API Connection
api_key, client, assistant_thread, assistant_id = initial_login()

# Streamlit Web App
if 'user_input' not in st.session_state:
    st.session_state.user_input = ''
st.title("E-Commerce ChatBot")
st.text_input("Ask me something:", key='query', on_change=submit)
user_input = st.session_state.user_input
if user_input:
    st.write("You entered: ", user_input)
    # Accessing OpenAI api for response
    result = get_assistant_response(user_input=user_input,assistant_id=assistant_id,
                                    client=client,
                                    assistant_thread=assistant_thread)
    st.header('Bot:', divider='rainbow')
    st.text_area(label="Output Data:", value=result, height=250)
import requests
import uuid

# Generate a session ID
session_id = str(uuid.uuid1())
ip_address = "127.0.0.1"  # Localhost or any IP address
user_message = "Hello, chatbot!"

# Define the URL for the FastAPI endpoint
url = "http://127.0.0.1:8000/stream"

# Create the JSON payload
payload = {
    "conv_id": session_id,
    "ip": ip_address,
    "user_input": user_message
}

# Send the POST request
response = requests.post(url, json=payload)

# Print the response from the chatbot
print(response.text)
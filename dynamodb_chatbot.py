import os
import json
import requests
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# Load the interaction flow from the provided JSON file
with open(r'C:\Users\abhi_\Downloads\dynamochatbot\dynamochatbot\interaction_flow.json.json', 'r') as file:
    interaction_flow = json.load(file)

# Environment setup for OpenAI API
OPENAI_API_KEY = ""
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# DynamoDB handler for session tracking (e.g., chatbot interactions and donation data)
class DynamoDBHandler:
    def __init__(self):
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name='us-east-2',  # Replace with your DynamoDB region
        )
        self.table_name = "SessionTable"  # Ensure the table name is correctly set
        self.table = self.dynamodb.Table(self.table_name)

    def get_session(self, session_id):
        try:
            response = self.table.get_item(Key={'SessionId': session_id})
            return response.get('Item', None)
        except ClientError as e:
            print(f"Error fetching session: {e.response['Error']['Message']}")
            return None

    def update_session(self, session_id, new_message, current_node):
        current_time = datetime.now().isoformat()
        new_message_entry = {'timestamp': current_time, 'message': new_message}
        try:
            response = self.table.update_item(
                Key={'SessionId': session_id},
                UpdateExpression="SET Chat_log = list_append(if_not_exists(Chat_log, :empty_list), :new_message), current_node = :current_node",
                ExpressionAttributeValues={
                    ':new_message': [new_message_entry],
                    ':empty_list': [],
                    ':current_node': current_node
                },
                ReturnValues="UPDATED_NEW"
            )
            return response['Attributes']
        except ClientError as e:
            print(f"Error updating session: {e.response['Error']['Message']}")
            return None

# Main chatbot class
class Chatbot:
    def __init__(self, conv_id, ip):
        self.db_handler = DynamoDBHandler()
        self.conv_id = conv_id
        self.session = self.db_handler.get_session(conv_id)
        self.interaction = interaction_flow['interaction']
        # Load the current node from the session or start from 'start'
        self.current_node = self.session.get('current_node', 'start') if self.session else 'start'
        self.state = self.get_location_from_ip(ip)

    def get_location_from_ip(self, ip_address):
        try:
            url = f"https://ipinfo.io/{ip_address}/json?token=56cfb1067eac5b"
            response = requests.get(url)
            data = response.json()
            return data.get('region', 'Unknown')
        except requests.RequestException as e:
            print(f"Error fetching location from IP: {e}")
            return 'Unknown'

    def greet_message(self):
        return self.interaction[self.current_node]['text-a']

    def handle_response(self, user_response):
        current_node_data = self.interaction[self.current_node]
        for next_node in current_node_data['next-nodes']:
            if user_response.lower() in next_node['intent']:
                self.current_node = next_node['node']
                break
        # Save the updated current node and the message to the session
        self.db_handler.update_session(self.conv_id, self.interaction[self.current_node]['text-a'], self.current_node)
        return self.interaction[self.current_node]['text-a']

    def run_agent(self, user_response):
        if self.current_node == 'start':
            return self.greet_message()  # Start the interaction
        else:
            return self.handle_response(user_response)

# FastAPI app
app = FastAPI()

# CORS Middleware setup
origins = ["http://localhost:3000", "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StreamInput(BaseModel):
    conv_id: str
    ip: str
    user_input: str

def send_message(ip: str, sessionId: str, user_input: str):
    chatbot = Chatbot(sessionId, ip)
    response = chatbot.run_agent(user_input)
    print(response)
    static_info = {
        "conversation_id": sessionId,
        "current_node": chatbot.current_node,
        "message": response  # Combine the response with static info
    }
    yield f"data: {json.dumps(static_info)}\n\n"

@app.post("/stream")
@app.get("/stream")
async def stream(input: StreamInput):
    return StreamingResponse(send_message(input.ip, input.conv_id, input.user_input), media_type="text/event-stream")

@app.get("/hasToken/{user_id}")
def has_token(user_id: str):
    db_handler = DynamoDBHandler()
    session = db_handler.get_session(user_id)
    if session:
        return {"status": "success", "message": "Token exists"}
    else:
        return {"status": "error", "message": "Token not found"}

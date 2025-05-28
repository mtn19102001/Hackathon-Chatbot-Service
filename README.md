# Chatbot Service

A chatbot service that integrates with OpenAI's GPT models and maintains user context.

## Architecture

The service consists of three main components:
1. Chatbot Service (Main API) - Handles user questions and coordinates responses
2. Context Service - Manages user context and conversation history
3. LLM Integration - Connects with OpenAI's GPT models

## Setup

1. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory with your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

## Running the Services

1. Start the Context Service:
```bash
python app/context_service.py
```
The Context Service will run on http://localhost:8001

2. Start the Main Chatbot Service:
```bash
python app/main.py
```
The Chatbot Service will run on http://localhost:8000

## API Endpoints

### Chatbot Service (Port 8000)

- POST `/ask`
  - Request body: `{"userId": "string", "question": "string"}`
  - Returns: `{"answer": "string"}`

### Context Service (Port 8001)

- GET `/context/{user_id}`
  - Returns the user's context
- POST `/context/{user_id}`
  - Updates the user's context
  - Request body: `{"user_id": "string", "preferences": {}, "history": []}`

## Testing the Service

You can test the service using curl:

```bash
# Ask a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"userId": "user123", "question": "What is the weather like?"}'

# Get user context
curl http://localhost:8001/context/user123
``` 
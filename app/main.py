from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from openai import OpenAI
import os
from dotenv import load_dotenv
import httpx
import json
import databases
import sqlalchemy
from datetime import datetime
from contextlib import asynccontextmanager

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI()  # It will automatically use OPENAI_API_KEY from environment

# Context service URL
CONTEXT_SERVICE_URL = os.getenv("CONTEXT_SERVICE_URL", "http://localhost:8001")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ntmt01@localhost/chatbot")
database = databases.Database(DATABASE_URL)

# SQLAlchemy setup
metadata = sqlalchemy.MetaData()

# Define the chat history table
chat_history = sqlalchemy.Table(
    "chat_history",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.String, index=True),
    sqlalchemy.Column("question", sqlalchemy.Text),
    sqlalchemy.Column("answer", sqlalchemy.Text),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime),
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect to database and create tables
    await database.connect()
    engine = sqlalchemy.create_engine(DATABASE_URL)
    metadata.create_all(engine)
    
    yield
    
    # Shutdown: disconnect from database
    await database.disconnect()

app = FastAPI(
    title="Chatbot Service",
    description="A service that provides conversational AI capabilities with context awareness",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

class Question(BaseModel):
    userId: str = Field(..., description="Unique identifier for the user", example="user123")
    question: str = Field(..., description="The question to ask the chatbot", example="What is machine learning?")

    class Config:
        schema_extra = {
            "example": {
                "userId": "user123",
                "question": "What is machine learning?"
            }
        }

class Answer(BaseModel):
    answer: str = Field(..., description="The response from the chatbot")

    class Config:
        schema_extra = {
            "example": {
                "answer": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed."
            }
        }

class ChatHistoryItem(BaseModel):
    question: str = Field(..., description="The user's question")
    answer: str = Field(..., description="The chatbot's answer")
    created_at: datetime = Field(..., description="When the interaction occurred")

async def get_user_context(user_id: str) -> dict:
    """
    Retrieve user context from the external context service.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{CONTEXT_SERVICE_URL}/context/{user_id}")
            if response.status_code == 200:
                return response.json()
            return {"user_id": user_id, "preferences": {}, "history": []}
        except Exception as e:
            # If context service is unavailable, return empty context
            return {"user_id": user_id, "preferences": {}, "history": []}

@app.get("/history/{user_id}",
    response_model=List[ChatHistoryItem],
    summary="Get user chat history",
    description="Retrieve the chat history for a specific user",
    tags=["Chat History"]
)
async def get_chat_history(user_id: str, limit: int = 10):
    query = chat_history.select()\
        .where(chat_history.c.user_id == user_id)\
        .order_by(chat_history.c.created_at.desc())\
        .limit(limit)
    
    history = await database.fetch_all(query)
    return [
        {
            "question": h.question,
            "answer": h.answer,
            "created_at": h.created_at
        }
        for h in history
    ]

@app.post("/ask", 
    response_model=Answer,
    summary="Ask a question to the chatbot",
    description="Send a question to the chatbot and receive an AI-generated response. The response will take into account the user's context and chat history.",
    response_description="The chatbot's response to the question",
    tags=["Chatbot"]
)
async def ask_question(question_data: Question):
    try:
        # Get user context from external service
        context = await get_user_context(question_data.userId)
        
        # Get response from LLM
        answer = await get_llm_response(question_data.question, context)
        
        # Store the chat message in our database
        await database.execute(
            chat_history.insert().values(
                user_id=question_data.userId,
                question=question_data.question,
                answer=answer,
                created_at=datetime.utcnow()
            )
        )
        
        return Answer(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_llm_response(question: str, context: dict) -> str:
    """
    Get response from the language model.
    Falls back to mock responses if OpenAI API is not available or has errors.
    """
    # Mock responses for testing or when API is unavailable
    mock_responses = {
        "hello": "Hello! How can I help you today?",
        "how are you": "I'm functioning well, thank you for asking! How can I assist you?",
        "what is machine learning": "Mock response: Machine learning is a branch of artificial intelligence that enables computers to learn from data without being explicitly programmed.",
        "what is your name": "I am a test chatbot. Note that this is a mock response for testing purposes.",
    }
    
    # Check if OpenAI API key exists and try to use it
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # No API key, use mock response
        return mock_responses.get(
            question.lower().strip(),
            f"This is a mock response for testing. Your question was: '{question}'. In production, this would be answered by the AI model."
        )
    
    try:
        # Get recent chat history from our database
        query = chat_history.select()\
            .where(chat_history.c.user_id == context["user_id"])\
            .order_by(chat_history.c.created_at.desc())\
            .limit(5)
        
        recent_history = await database.fetch_all(query)
        
        # Format chat history
        history_context = "\n".join([
            f"User: {h.question}\nAssistant: {h.answer}"
            for h in recent_history
        ])
        
        system_message = (
            f"User context: {json.dumps(context['preferences'])}\n\n"
            f"Previous conversation:\n{history_context}"
        )
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": question}
        ]
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        
        return response.choices[0].message.content
    except Exception as e:
        error_str = str(e)
        if "insufficient_quota" in error_str or "Rate limit" in error_str:
            # API quota exceeded or rate limited, fall back to mock response
            return mock_responses.get(
                question.lower().strip(),
                f"API quota exceeded. Mock response: Your question was: '{question}'. In production, this would be answered by the AI model."
            )
        else:
            # Other API errors
            raise HTTPException(status_code=500, detail=f"LLM API error: {error_str}")

@app.get("/",
    summary="API Information",
    description="Get basic information about the API",
    tags=["Info"]
)
async def root():
    return {
        "name": "Chatbot API",
        "version": "1.0.0",
        "description": "A conversational AI service with context awareness",
        "endpoints": {
            "docs": "/docs - API documentation (Swagger UI)",
            "redoc": "/redoc - Alternative API documentation",
            "ask": "/ask - Ask a question (POST)",
            "history": "/history/{user_id} - Get chat history (GET)"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
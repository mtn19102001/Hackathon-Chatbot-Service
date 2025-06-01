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

# Global variables
client = None

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
    
    # Initialize OpenAI client
    global client
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = OpenAI(api_key=api_key)
        print("OpenAI client initialized successfully")
    else:
        print("Warning: OPENAI_API_KEY not found, chatbot will use mock responses")
    
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

class ContextResponse(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user")
    preferences: Dict = Field(..., description="User preferences and settings")
    history: List[ChatHistoryItem] = Field(default=[], description="Recent chat history")

    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "preferences": {
                    "current_skills": [
                        {
                            "name": "Python",
                            "proficiency": "intermediate",
                            "last_used": "2024-02-15",
                            "years_experience": 2
                        }
                    ],
                    "recommended_skills": [
                        {
                            "name": "FastAPI",
                            "reason": "Complements Python backend development",
                            "priority": "high",
                            "estimated_time": "2 weeks"
                        }
                    ],
                    "learning_behavior": {
                        "preferred_learning_style": "hands-on",
                        "learning_pace": "moderate"
                    }
                },
                "history": []
            }
        }

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
        "hello": "We're sorry, but we're experiencing a technical issue with our learning assistant at the moment. Please try again later or contact support for assistance. In the meantime, you can explore our recommended courses or review your learning progress in your dashboard."
    }
    
    # Check if OpenAI client is available
    print(f"OpenAI client status: {client is not None}")
    if not client:
        print("OpenAI client is not available, using mock response")
        # No API key, use mock response
        return mock_responses.get(
            question.lower().strip(),
            "We're sorry, but we're experiencing a technical issue with our learning assistant at the moment. Please try again later or contact support for assistance. In the meantime, you can explore our recommended courses or review your learning progress in your dashboard."
        )
    
    try:
        print("Getting chat history...")
        # Get recent chat history from our database
        query = chat_history.select()\
            .where(chat_history.c.user_id == context["user_id"])\
            .order_by(chat_history.c.created_at.desc())\
            .limit(5)
        
        recent_history = await database.fetch_all(query)
        print(f"Found {len(recent_history)} chat history items")
        
        # Format chat history
        history_context = "\n".join([
            f"User: {h.question}\nAssistant: {h.answer}"
            for h in recent_history
        ])
        
        print("Formatting user context...")
        # Format user context for better readability
        user_preferences = context.get('preferences', {})
        formatted_context = {
            "Current Skills": user_preferences.get('current_skills', []),
            "Recommended Skills": user_preferences.get('recommended_skills', []),
            "Learning Progress": user_preferences.get('learning_progress', {}),
            "Learning Behavior": user_preferences.get('learning_behavior', {}),
            "Constraints": user_preferences.get('constraints', {})
        }
        print(f"User context: {json.dumps(formatted_context, indent=2)}")
        
        system_message = "You are a learning assistant. Answer questions based on the user's context."
        user_message = f"Given this context about me:\n{json.dumps(formatted_context, indent=2)}\n\nMy question is: {question}"
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        print("Messages being sent to OpenAI:")
        for msg in messages:
            print(f"Role: {msg['role']}")
            print(f"Content: {msg['content']}\n")
        
        print("Sending request to OpenAI...")
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,  # Slightly creative but still focused
                max_tokens=500    # Reasonable response length
            )
            print("Got response from OpenAI")
            print(f"Response: {response}")
            print(f"Response type: {type(response)}")
            print(f"Response dir: {dir(response)}")
            
            if hasattr(response, 'choices') and len(response.choices) > 0 and hasattr(response.choices[0], 'message'):
                print(f"Message content: {response.choices[0].message.content}")
                return response.choices[0].message.content
            else:
                print("Invalid response format from OpenAI")
                raise Exception("Invalid response format from OpenAI API")
        except Exception as api_error:
            print(f"OpenAI API error: {str(api_error)}")
            raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(api_error)}")
            
    except Exception as e:
        error_str = str(e)
        print(f"Error in get_llm_response: {error_str}")
        if "insufficient_quota" in error_str or "Rate limit" in error_str:
            # API quota exceeded or rate limited, fall back to mock response
            return mock_responses.get(
                question.lower().strip(),
                "Our learning assistant is temporarily unavailable due to high demand. Please try again later or check out your personalized course recommendations in your dashboard. If the issue persists, feel free to contact support for help."
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

@app.get("/context/{user_id}",
    response_model=ContextResponse,
    summary="Get user context and chat history",
    description="Retrieve a user's context, preferences, and recent chat history from the context service.",
    tags=["Context"]
)
async def get_user_context_endpoint(user_id: str):
    try:
        # Get context from context service
        context = await get_user_context(user_id)
        
        # Get recent chat history from our database
        query = chat_history.select()\
            .where(chat_history.c.user_id == user_id)\
            .order_by(chat_history.c.created_at.desc())\
            .limit(10)
        
        history = await database.fetch_all(query)
        
        # Format the response
        return ContextResponse(
            user_id=user_id,
            preferences=context.get('preferences', {}),
            history=[
                ChatHistoryItem(
                    question=h.question,
                    answer=h.answer,
                    created_at=h.created_at
                )
                for h in history
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user context: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
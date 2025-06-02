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
    id: int = Field(..., description="Unique identifier for the context")
    learning_preferences: Dict = Field(default={}, description="User learning preferences")
    constraints: Dict = Field(default={}, description="User constraints")
    background: Dict = Field(default={}, description="User background information")
    skills: List[Dict] = Field(default=[], description="User's skills")
    progresses: List[Dict] = Field(default=[], description="User's learning progress")
    history: List[ChatHistoryItem] = Field(default=[], description="Recent chat history")

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "learning_preferences": {
                    "preferred_learning_style": "visual",
                    "time_availability": {
                        "hours_per_week": 6,
                        "preferred_schedule": "weekdays"
                    }
                },
                "constraints": {
                    "time_constraints": 9,
                    "budget_constraints": 10
                },
                "background": {
                    "education_level": "Bachelor's",
                    "work_experience_years": "3",
                    "current_role": "Software Developer",
                    "industry": "Technology"
                },
                "skills": [
                    {
                        "id": 1,
                        "name": "python",
                        "category": "programming",
                        "level": "intermediate",
                        "description": "Python programming language proficiency"
                    }
                ],
                "progresses": [
                    {
                        "target": {
                            "id": 1,
                            "title": "Backend Developer",
                            "type": "Career Path",
                            "description": "Backend development specialization"
                        },
                        "learning_path": {
                            "id": 1,
                            "title": "Python Expert Path",
                            "progress": 60,
                            "completion_date": "2025-06-13T16:09:02.736Z"
                        }
                    }
                ],
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
                context_data = response.json()
                # Ensure we have all required fields
                return {
                    "id": context_data.get("id"),  # Include the context ID
                    "user_id": context_data.get("user_id", user_id),
                    "learning_preferences": context_data.get("learning_preferences", {}),
                    "constraints": context_data.get("constraints", {}),
                    "background": context_data.get("background", {}),
                    "skills": context_data.get("skills", []),
                    "progresses": context_data.get("progresses", [])
                }
            return {
                "id": 0,  # Default ID for non-existent context
                "user_id": user_id,
                "learning_preferences": {},
                "constraints": {},
                "background": {},
                "skills": [],
                "progresses": []
            }
        except Exception as e:
            print(f"Error getting user context: {str(e)}")
            # If context service is unavailable, return empty context with default ID
            return {
                "id": 0,
                "user_id": user_id,
                "learning_preferences": {},
                "constraints": {},
                "background": {},
                "skills": [],
                "progresses": []
            }

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
        formatted_context = {
            "Context ID": context.get("id"),  # Include context ID in LLM context
            "Learning Preferences": context.get("learning_preferences", {}),
            "Constraints": context.get("constraints", {}),
            "Background": context.get("background", {}),
            "Current Skills": context.get("skills", []),
            "Learning Progress": []
        }

        # Format progress information
        for progress in context.get("progresses", []):
            target = progress.get("target", {})
            learning_path = progress.get("learning_path", {})
            formatted_progress = {
                "Career Target": target.get("title"),
                "Learning Path": learning_path.get("title"),
                "Progress": f"{learning_path.get('progress')}%",
                "Expected Completion": learning_path.get("completion_date"),
                "Learned Skills": [
                    {
                        "name": skill.get("skill", {}).get("name"),
                        "level": skill.get("proficiency_level"),
                        "status": skill.get("status")
                    }
                    for skill in learning_path.get("learned_skills", [])
                ],
                "Skills To Learn": [
                    {
                        "name": skill.get("skill", {}).get("name"),
                        "target_level": skill.get("proficiency_level"),
                        "status": skill.get("status")
                    }
                    for skill in learning_path.get("to_learn_skills", [])
                ]
            }
            formatted_context["Learning Progress"].append(formatted_progress)

        print(f"User context: {json.dumps(formatted_context, indent=2)}")
        
        system_message = """You are a learning assistant. Use the provided context to give personalized responses.
Focus on the user's:
1. Current skills and their levels
2. Learning preferences and constraints
3. Career targets and learning progress
4. Recommended next steps based on their learning path

Always be specific and reference the user's actual data."""

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
                temperature=0.7,
                max_tokens=500
            )
            print("Got response from OpenAI")
            
            if hasattr(response, "choices") and len(response.choices) > 0 and hasattr(response.choices[0], "message"):
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
            return mock_responses.get(
                question.lower().strip(),
                "Our learning assistant is temporarily unavailable due to high demand. Please try again later or check out your personalized course recommendations in your dashboard. If the issue persists, feel free to contact support for help."
            )
        else:
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
            id=context["id"],
            learning_preferences=context.get("learning_preferences", {}),
            constraints=context.get("constraints", {}),
            background=context.get("background", {}),
            skills=context.get("skills", []),
            progresses=context.get("progresses", []),
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
        print(f"Error in get_user_context_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user context: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
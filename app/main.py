from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Chatbot Service")

class Question(BaseModel):
    userId: str
    question: str

class Answer(BaseModel):
    answer: str

@app.post("/ask", response_model=Answer)
async def ask_question(question_data: Question):
    try:
        # Get user context
        context = await get_user_context(question_data.userId)
        
        # Get response from LLM
        answer = await get_llm_response(question_data.question, context)
        
        return Answer(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_user_context(user_id: str) -> dict:
    # This will be implemented in the context service
    # For now, return a mock context
    return {"user_id": user_id, "preferences": {}, "history": []}

async def get_llm_response(question: str, context: dict) -> str:
    try:
        messages = [
            {"role": "system", "content": f"User context: {context}"},
            {"role": "user", "content": question}
        ]
        
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=messages
        )
        
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
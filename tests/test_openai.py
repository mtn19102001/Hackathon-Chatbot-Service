from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get API key from environment
api_key = os.getenv("OPENAI_API_KEY")

def test_openai_connection():
    """Test OpenAI API connection and key validity."""
    print("\nTesting OpenAI API connection...")
    
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found in .env file")
        print("Please add your API key to the .env file:")
        print('OPENAI_API_KEY=your_api_key_here')
        return False
    
    try:
        # Initialize OpenAI client
        client = OpenAI()  # It will automatically use OPENAI_API_KEY from environment
        
        # Try a simple completion
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Say 'OpenAI connection successful!'"}
            ]
        )
        
        # Get the response
        answer = response.choices[0].message.content
        print("✅ API Key is valid!")
        print("✅ Successfully connected to OpenAI API")
        print(f"\nTest response: {answer}")
        return True
        
    except Exception as e:
        if "Invalid API key" in str(e):
            print("❌ Error: Invalid API key")
            print("Please check your API key in the .env file")
        elif "Rate limit" in str(e):
            print("❌ Error: Rate limit exceeded")
            print("Your API key is valid but you've hit the rate limit")
        else:
            print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    test_openai_connection() 
import asyncio
import databases
from dotenv import load_dotenv
import os
from datetime import datetime
from tabulate import tabulate
import argparse

# Load environment variables
load_dotenv()

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ntmt01@localhost/chatbot")

# Create database instance
database = databases.Database(DATABASE_URL)

async def show_all_chat_history():
    """Show all chat history entries in the database."""
    query = """
    SELECT user_id, question, answer, created_at 
    FROM chat_history 
    ORDER BY created_at DESC
    """
    results = await database.fetch_all(query)
    
    if not results:
        print("\nNo chat history found in the database.")
        return
    
    # Format data for tabulate
    table_data = [
        [
            r['user_id'],
            r['question'][:50] + '...' if len(r['question']) > 50 else r['question'],
            r['answer'][:50] + '...' if len(r['answer']) > 50 else r['answer'],
            r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        ] for r in results
    ]
    
    print("\nAll Chat History:")
    print(tabulate(
        table_data,
        headers=['User ID', 'Question', 'Answer', 'Created At'],
        tablefmt='grid'
    ))

async def show_user_chat_history(user_id: str):
    """Show chat history for a specific user."""
    query = """
    SELECT question, answer, created_at 
    FROM chat_history 
    WHERE user_id = :user_id 
    ORDER BY created_at DESC
    """
    results = await database.fetch_all(query, {'user_id': user_id})
    
    if not results:
        print(f"\nNo chat history found for user: {user_id}")
        return
    
    # Format data for tabulate
    table_data = [
        [
            r['question'],
            r['answer'],
            r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        ] for r in results
    ]
    
    print(f"\nChat History for user {user_id}:")
    print(tabulate(
        table_data,
        headers=['Question', 'Answer', 'Created At'],
        tablefmt='grid'
    ))

async def show_statistics():
    """Show basic statistics about the chat history."""
    stats_queries = {
        'total_conversations': 'SELECT COUNT(*) as count FROM chat_history',
        'unique_users': 'SELECT COUNT(DISTINCT user_id) as count FROM chat_history',
        'latest_conversation': '''
            SELECT user_id, created_at 
            FROM chat_history 
            ORDER BY created_at DESC 
            LIMIT 1
        ''',
        'most_active_user': '''
            SELECT user_id, COUNT(*) as message_count 
            FROM chat_history 
            GROUP BY user_id 
            ORDER BY message_count DESC 
            LIMIT 1
        '''
    }
    
    print("\nDatabase Statistics:")
    print("-" * 50)
    
    # Total conversations
    result = await database.fetch_one(stats_queries['total_conversations'])
    print(f"Total conversations: {result['count']}")
    
    # Unique users
    result = await database.fetch_one(stats_queries['unique_users'])
    print(f"Unique users: {result['count']}")
    
    # Latest conversation
    result = await database.fetch_one(stats_queries['latest_conversation'])
    if result:
        print(f"Latest conversation: User {result['user_id']} at {result['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Most active user
    result = await database.fetch_one(stats_queries['most_active_user'])
    if result:
        print(f"Most active user: {result['user_id']} with {result['message_count']} messages")

async def main():
    parser = argparse.ArgumentParser(description='Test database entries for the chatbot service.')
    parser.add_argument('--user', '-u', help='Show chat history for specific user')
    parser.add_argument('--all', '-a', action='store_true', help='Show all chat history')
    parser.add_argument('--stats', '-s', action='store_true', help='Show database statistics')
    
    args = parser.parse_args()
    
    try:
        await database.connect()
        
        if not any([args.user, args.all, args.stats]):
            # If no arguments provided, show all options
            await show_statistics()
            await show_all_chat_history()
        else:
            if args.stats:
                await show_statistics()
            if args.all:
                await show_all_chat_history()
            if args.user:
                await show_user_chat_history(args.user)
                
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await database.disconnect()

if __name__ == "__main__":
    asyncio.run(main()) 
import os
import sys
import traceback
import json
from typing import Any, Dict, Optional
from dataclasses import asdict

from botbuilder.core import MemoryStorage, TurnContext
from state import AppTurnState
from teams import Application, ApplicationOptions, TeamsAdapter
from teams.ai import AIOptions
from teams.ai.actions import ActionTurnContext
from teams.ai.models import AzureOpenAIModelOptions, OpenAIModel, OpenAIModelOptions
from teams.ai.planners import ActionPlanner, ActionPlannerOptions
from teams.ai.prompts import PromptManager, PromptManagerOptions
from teams.state import TurnState
from teams.feedback_loop_data import FeedbackLoopData

from config import Config
from agent_logger import get_agent_logger
from tavily_search import search_web_summary, tavily_search
from conversation_store import store_conversation_reference

# Initialize colored logging
logger, log_blue, log_green, log_yellow, log_red, log_cyan = get_agent_logger("TeamsTaskAgent")

config = Config()

log_cyan("🚀 Initializing Teams Task Agent...")
log_blue(f"Bot ID: {config.APP_ID}")
log_blue(f"Azure OpenAI Endpoint: {config.AZURE_OPENAI_ENDPOINT}")
log_blue(f"Azure OpenAI Model: {config.AZURE_OPENAI_MODEL_DEPLOYMENT_NAME}")

# Create AI components
model: OpenAIModel

try:
    log_cyan("🔧 Setting up Azure OpenAI model...")
    model = OpenAIModel(
        AzureOpenAIModelOptions(
            api_key=config.AZURE_OPENAI_API_KEY,
            default_model=config.AZURE_OPENAI_MODEL_DEPLOYMENT_NAME,
            endpoint=config.AZURE_OPENAI_ENDPOINT,
        )
    )
    log_green("✅ Azure OpenAI model configured successfully")
except Exception as e:
    log_red(f"❌ Failed to configure Azure OpenAI model: {str(e)}")
    raise

try:
    log_cyan("📁 Loading prompt manager...")
    prompts = PromptManager(PromptManagerOptions(prompts_folder=f"{os.getcwd()}/prompts"))
    log_green("✅ Prompt manager loaded successfully")
except Exception as e:
    log_red(f"❌ Failed to load prompt manager: {str(e)}")
    raise

try:
    log_cyan("🤖 Initializing action planner...")
    planner = ActionPlanner(
        ActionPlannerOptions(model=model, prompts=prompts, default_prompt="planner")
    )
    log_green("✅ Action planner initialized successfully")
except Exception as e:
    log_red(f"❌ Failed to initialize action planner: {str(e)}")
    raise

# Define storage and application
log_cyan("💾 Setting up memory storage...")
storage = MemoryStorage()
log_green("✅ Memory storage configured")

log_cyan("🏗️ Building Teams application...")
bot_app = Application[AppTurnState](
    ApplicationOptions(
        bot_app_id=config.APP_ID,
        storage=storage,
        adapter=TeamsAdapter(config),
        ai=AIOptions(planner=planner, enable_feedback_loop=True),
    )
)
log_green("✅ Teams application built successfully")

@bot_app.turn_state_factory
async def turn_state_factory(context: TurnContext):
    log_blue(f"🔄 Creating turn state for user: {context.activity.from_property.name}")
    
    # Store conversation reference for proactive messaging
    try:
        user_id = context.activity.from_property.id
        user_name = context.activity.from_property.name
        conversation_reference = TurnContext.get_conversation_reference(context.activity)
        
        log_blue(f"👤 User ID: {user_id}")
        log_blue(f"👤 User Name: {user_name}")
        log_blue(f"🗨️ Conversation ID: {conversation_reference.conversation.id}")
        
        # Store with both user ID and user name for flexibility
        store_conversation_reference(user_id, conversation_reference)
        store_conversation_reference(user_name, conversation_reference)
        
        log_green(f"💾 Stored conversation reference for: {user_id} and {user_name}")
        
    except Exception as e:
        log_red(f"⚠️ Could not store conversation reference: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
    
    return await AppTurnState.load(context, storage)

@bot_app.ai.action("createTask")
async def create_task(context: ActionTurnContext[Dict[str, Any]], state: AppTurnState):
    log_cyan("📝 CREATE TASK action triggered")
    
    try:
        # Initialize tasks if not exists
        if not state.conversation.tasks:
            state.conversation.tasks = {}
            log_blue("🗂️ Initialized empty tasks dictionary")
        
        # Get parameters from planner history
        parameters = state.conversation.planner_history[-1].content.action.parameters
        log_blue(f"📋 Task parameters: {parameters}")
        
        # Create task object
        task = {
            "title": parameters["title"], 
            "description": parameters["description"]
        }
        
        # Store task
        state.conversation.tasks[parameters["title"]] = task
        log_green(f"✅ Task created: '{parameters['title']}'")
        log_blue(f"📄 Task details: {task}")
        
        # Log current task count
        task_count = len(state.conversation.tasks)
        log_cyan(f"📊 Total tasks: {task_count}")
        
        return f"task created, think about your next action"
        
    except Exception as e:
        log_red(f"❌ Error creating task: {str(e)}")
        log_red(f"Stack trace: {traceback.format_exc()}")
        return f"Error creating task: {str(e)}"

@bot_app.ai.action("searchWeb")
async def search_web_action(context: ActionTurnContext[Dict[str, Any]], state: AppTurnState):
    log_cyan("🔍 WEB SEARCH action triggered")
    
    try:
        # Check if Tavily is available
        if not tavily_search.is_available():
            log_yellow("⚠️ Tavily search not available")
            return "Web search is not configured. Please check the Tavily API key configuration."
        
        # Get parameters from planner history
        parameters = state.conversation.planner_history[-1].content.action.parameters
        query = parameters.get("query", "")
        
        if not query:
            log_red("❌ No search query provided")
            return "No search query provided. Please specify what you want to search for."
        
        log_blue(f"🔍 Search query: '{query}'")
        
        # Perform the search
        search_summary = search_web_summary(query)
        
        log_green(f"✅ Search completed for: '{query}'")
        log_blue(f"📄 Summary length: {len(search_summary)} characters")
        
        return f"Here are the search results for '{query}':\n\n{search_summary}"
        
    except Exception as e:
        log_red(f"❌ Error performing web search: {str(e)}")
        log_red(f"Stack trace: {traceback.format_exc()}")
        return f"Error performing web search: {str(e)}"

@bot_app.ai.action("deleteTask")
async def delete_task(context: ActionTurnContext[Dict[str, Any]], state: AppTurnState):
    log_cyan("🗑️ DELETE TASK action triggered")
    
    try:
        # Initialize tasks if not exists
        if not state.conversation.tasks:
            state.conversation.tasks = {}
            log_yellow("⚠️ No tasks found to delete")
        
        # Get parameters from planner history
        parameters = state.conversation.planner_history[-1].content.action.parameters
        log_blue(f"🎯 Target task: '{parameters['title']}'")
        
        # Check if task exists
        if parameters["title"] not in state.conversation.tasks:
            log_yellow(f"⚠️ Task not found: '{parameters['title']}'")
            log_blue(f"📋 Available tasks: {list(state.conversation.tasks.keys())}")
            return "task not found, think about your next action"
        
        # Delete task
        deleted_task = state.conversation.tasks[parameters["title"]]
        del state.conversation.tasks[parameters["title"]]
        log_green(f"✅ Task deleted: '{parameters['title']}'")
        log_blue(f"🗑️ Deleted task details: {deleted_task}")
        
        # Log remaining task count
        task_count = len(state.conversation.tasks)
        log_cyan(f"📊 Remaining tasks: {task_count}")
        
        return f"task deleted, think about your next action"
        
    except Exception as e:
        log_red(f"❌ Error deleting task: {str(e)}")
        log_red(f"Stack trace: {traceback.format_exc()}")
        return f"Error deleting task: {str(e)}"

@bot_app.error
async def on_error(context: TurnContext, error: Exception):
    log_red("🚨 UNHANDLED ERROR OCCURRED")
    log_red(f"Error: {error}")
    log_red(f"Stack trace: {traceback.format_exc()}")
    
    # Log context information
    if context.activity:
        log_yellow(f"Activity type: {context.activity.type}")
        log_yellow(f"Activity text: {context.activity.text}")
        log_yellow(f"From user: {context.activity.from_property.name}")
        log_yellow(f"Channel: {context.activity.channel_id}")
    
    # Send a message to the user
    await context.send_activity("The agent encountered an error or bug.")

@bot_app.feedback_loop()
async def feedback_loop(_context: TurnContext, _state: TurnState, feedback_loop_data: FeedbackLoopData):
    log_cyan("📢 FEEDBACK LOOP triggered")
    feedback_json = json.dumps(asdict(feedback_loop_data), indent=2)
    log_blue(f"Feedback data:\n{feedback_json}")

# Simple logging for incoming messages - non-intrusive
original_process = bot_app.process

async def logged_process(request):
    """Wrapper around the original process method to add logging"""
    try:
        # Extract message info if possible
        if hasattr(request, 'json'):
            try:
                body = await request.json()
                if 'text' in body:
                    log_cyan(f"💬 Processing message: '{body['text']}'")
                if 'from' in body and 'name' in body['from']:
                    log_blue(f"👤 From user: {body['from']['name']}")
            except:
                log_blue("💬 Processing incoming message")
        
        # Call original process method
        result = await original_process(request)
        
        if result:
            log_green("✅ Message processed successfully")
        
        return result
        
    except Exception as e:
        log_red(f"❌ Error in message processing: {str(e)}")
        raise

# Replace the process method with our logged version
bot_app.process = logged_process

log_green("🎉 Teams Task Agent initialization complete!")
log_cyan("📞 Ready to handle requests...")
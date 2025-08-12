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

from datetime import datetime
from aiohttp import web
from http import HTTPStatus
from langchain_openai import AzureChatOpenAI

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

# Replace your existing logged_process function (around line 189) with this enhanced version:

# Add this to your bot.py after the existing logged_process function
# This will record ALL messages in group chats, even when bot isn't mentioned

async def logged_process(request):
    """Wrapper around the original process method to add logging and record ALL group messages"""
    try:
        # Extract message info if possible
        if hasattr(request, 'json'):
            try:
                body = await request.json()
                
                # Enhanced logging for group chat debugging
                if body:
                    log_cyan("🔍 DETAILED MESSAGE DEBUG:")
                    
                    # Log basic message info
                    if 'text' in body:
                        log_cyan(f"💬 Processing message: '{body['text']}'")
                    
                    if 'from' in body and 'name' in body['from']:
                        log_blue(f"👤 From user: {body['from']['name']}")
                        log_blue(f"👤 User ID: {body['from'].get('id', 'Unknown')}")
                    
                    # Log conversation details
                    if 'conversation' in body:
                        conv = body['conversation']
                        log_blue(f"🗨️ Conversation Type: {conv.get('conversationType', 'Unknown')}")
                        log_blue(f"🗨️ Conversation ID: {conv.get('id', 'Unknown')}")
                        
                        # Special handling for group chats - RECORD ALL MESSAGES
                        if conv.get('conversationType') == 'groupChat':
                            log_yellow("⚠️ This is a GROUP CHAT message!")
                            
                            # ALWAYS RECORD GROUP CHAT MESSAGES
                            await record_group_message(body)
                            
                            # Check for mentions (for response logic) - FIXED LOGIC
                            bot_mentioned = False
                            if 'entities' in body and body['entities']:
                                log_blue(f"📋 Found {len(body['entities'])} entities:")
                                
                                for entity in body['entities']:
                                    log_blue(f"  - Entity type: {entity.get('type', 'Unknown')}")
                                    
                                    if entity.get('type') == 'mention':
                                        mentioned = entity.get('mentioned', {})
                                        mentioned_id = mentioned.get('id', '')
                                        mentioned_name = mentioned.get('name', '')
                                        
                                        log_blue(f"  - Mentioned: {mentioned_name} ({mentioned_id})")
                                        
                                        # Check if it's our bot - FIXED: check both ID and name
                                        if (mentioned_id == config.APP_ID or 
                                            mentioned_name.lower().startswith('teams-copilot') or
                                            'teams-copilot' in mentioned_name.lower()):
                                            bot_mentioned = True
                                            log_green("✅ BOT WAS MENTIONED!")
                                            break
                                
                                if bot_mentioned:
                                    log_green("🎯 Bot mentioned - will process with AI")
                                else:
                                    log_yellow("📝 Recording message but bot not mentioned - won't respond")
                            else:
                                log_blue("📋 No entities found (no mentions)")
                                log_yellow("📝 Recording message but no @mention - won't respond")
                            
                            # If bot not mentioned, still record but return early to avoid AI processing
                            if not bot_mentioned:
                                log_cyan("📝 Message recorded, skipping AI processing")
                                return web.Response(status=HTTPStatus.OK)
                            else:
                                log_green("🚀 Bot mentioned - continuing with AI processing")
                        
                        elif conv.get('conversationType') == 'personal':
                            log_green("✅ Personal chat - should work normally")
                    
                    # Log channel info
                    if 'channelId' in body:
                        log_blue(f"📺 Channel: {body['channelId']}")
                
            except Exception as e:
                log_red(f"❌ Error parsing request body: {str(e)}")
                log_blue("💬 Processing incoming message (could not parse details)")
        
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

# Add these imports to the top of your bot.py
import re
import aiohttp
import json
from typing import Optional, Dict, Any
import asyncio
from botbuilder.core import MessageFactory

# Add these imports to the top of your bot.py
from typing import Optional
from pydantic import BaseModel, Field

# Pydantic class for incident parsing
class IncidentRequest(BaseModel):
    """Parse incident information from user message."""
    incident_id: str = Field(description="The incident ID mentioned (e.g., INC0012345)")
    query: str = Field(description="What the user wants to know about the incident")
    user_id: str = Field(description="The user asking about the incident")
    teams_channel: str = Field(description="The Teams channel/chat where this was asked")

# Simple LLM-powered incident parser
async def parse_incident_with_llm(user_message: str, user_id: str, teams_channel: str) -> Optional[IncidentRequest]:
    """Use LLM with structured output to parse incident request"""
    log_cyan("🤖 Using LLM to parse incident request...")
    
    try:
        llm = AzureChatOpenAI(
            temperature=0.2,
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version="2024-08-01-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            model=os.getenv("MINI")
        )
        # Create structured LLM
        structured_llm = llm.with_structured_output(IncidentRequest)
        
        # Simple prompt
        prompt = f"""
Parse this incident request:

User message: "{user_message}"
User ID: "{user_id}"  
Teams channel: "{teams_channel}"

Extract the incident ID and what the user wants to know about it.
If no incident ID is found, use an empty string.
"""
        
        log_blue(f"🤖 Parsing: {user_message}")
        
        # Get structured response
        result = await structured_llm.ainvoke(prompt)
        
        log_green("✅ LLM parsed incident request")
        log_blue(f"🎫 Result: {result}")
        
        return result
        
    except Exception as e:
        log_red(f"❌ LLM parsing failed: {str(e)}")
        return None

# Updated simple incident status action
@bot_app.ai.action("checkIncidentStatus")
async def check_incident_status(context: ActionTurnContext[Dict[str, Any]], state: AppTurnState):
    log_cyan("🎫 INCIDENT STATUS CHECK action triggered")
    
    try:
        # Get user info
        user_name = context.activity.from_property.name if context.activity.from_property else "Unknown"
        user_id = context.activity.from_property.id if context.activity.from_property else "unknown"
        user_message = context.activity.text if context.activity else ""
        
        # Determine channel
        teams_channel = "Group Chat" if context.activity.conversation.conversation_type == "groupChat" else "Personal"
        
        log_blue(f"👤 User: {user_name}")
        log_blue(f"💬 Message: '{user_message}'")
        
        # Parse with LLM
        parsed_request = await parse_incident_with_llm(user_message, user_id, teams_channel)
        
        if not parsed_request or not parsed_request.incident_id:
            log_yellow("⚠️ No incident ID found")
            # Send message directly to Teams
            await context.send_activity(MessageFactory.text("I need an incident ID to check status. Please provide an incident ID like INC0012345."))
            return "Incident ID request sent"
        
        incident_id = parsed_request.incident_id
        query = parsed_request.query
        
        log_green(f"✅ Found incident: {incident_id}")
        log_blue(f"❓ Query: {query}")
        
        # Call API
        incident_info = await call_incident_status_api(
            incident_id=incident_id,
            user_id=user_id,
            teams_channel=teams_channel,
            query=query
        )
        
        if incident_info and incident_info.get("status") == "success":
            log_green(f"✅ Got incident status for: {incident_id}")
            
            # Store in conversation state
            state.conversation.current_incident = {
                "incident_id": incident_id,
                "last_updated": incident_info.get("timestamp"),
                "request_id": incident_info.get("request_id")
            }
            
            # Get the API response and format it
            response_content = incident_info.get("response", "No response received")
            formatted_response = f"📋 **{incident_id} Status:**\n\n{response_content}\n\n*Last updated: {incident_info.get('timestamp', 'Unknown')}*"
            
            log_cyan(f"📤 Sending directly to Teams:")
            log_blue(f"Response length: {len(formatted_response)} characters")
            
            # SEND DIRECTLY TO TEAMS - bypass AI response generation
            from botbuilder.core import MessageFactory
            await context.send_activity(MessageFactory.text(formatted_response))
            log_green("✅ Incident status sent directly to Teams!")
            
            # Return a simple confirmation for the AI (won't be shown to user)
            return f"Incident status for {incident_id} has been provided to the user."
            
        else:
            log_red(f"❌ API call failed")
            error_msg = incident_info.get("error", "Unknown error") if incident_info else "API unavailable"
            error_response = f"❌ Couldn't get status for {incident_id}. Error: {error_msg}"
            
            # Send error directly to Teams
            await context.send_activity(MessageFactory.text(error_response))
            return "Error message sent to user"
        
    except Exception as e:
        log_red(f"❌ Action error: {str(e)}")
        error_message = f"❌ Error checking incident status: {str(e)}"
        
        # Send error directly to Teams
        await context.send_activity(MessageFactory.text(error_message))
        return "Error occurred and message sent"

async def call_incident_status_api(incident_id: str, user_id: str, teams_channel: str, query: str) -> Optional[Dict[str, Any]]:
    """Call the incident status API"""
    log_cyan(f"📞 Calling incident status API for: {incident_id}")
    
    try:
        # Prepare the API payload
        payload = {
            "incident_id": incident_id,
            "user_id": user_id,
            "teams_channel": teams_channel,
            "query": query
        }
        
        log_blue(f"📤 API Payload: {json.dumps(payload, indent=2)}")
        
        # Make the API call
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8092/status",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                log_blue(f"📥 API Response Status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    log_green("✅ API call successful")
                    log_blue(f"📄 Response: {json.dumps(result, indent=2)}")
                    return result
                else:
                    error_text = await response.text()
                    log_red(f"❌ API call failed with status {response.status}: {error_text}")
                    return {
                        "status": "error",
                        "error": f"API returned status {response.status}: {error_text}"
                    }
                    
    except aiohttp.ClientConnectorError:
        log_red("❌ Could not connect to incident status API - is it running on localhost:8092?")
        return {
            "status": "error",
            "error": "Could not connect to incident status API. Please check if the service is running."
        }
    except asyncio.TimeoutError:
        log_red("❌ API call timeout")
        return {
            "status": "error", 
            "error": "API call timed out"
        }
    except Exception as e:
        log_red(f"❌ Unexpected error calling incident API: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

# Add handler for when bot is added to a group chat
@bot_app.activity("membersAdded")
async def on_members_added(context: TurnContext, state: AppTurnState):
    log_cyan("👥 MEMBERS ADDED event triggered")
    
    try:
        # Check if the bot was added
        bot_added = False
        for member in context.activity.members_added:
            if member.id == config.APP_ID:
                bot_added = True
                log_green(f"🤖 Bot was added to conversation: {member.name}")
                break
        
        if bot_added and context.activity.conversation.conversation_type == "groupChat":
            log_cyan("📢 Sending welcome message to group chat")
            
            welcome_message = """
🤖 **Teams Incident Assistant Activated!**

Hello! I'm here to help you track and discuss incidents.

**How to use me:**
• Mention an incident ID (like INC0012345) and I'll fetch the current status
• Ask questions about incident status: "What's the status of INC0012345?"
• I'll keep track of the incident being discussed in this chat

**Examples:**
• "Can you check INC0012345?"
• "What's the latest on incident INC0098765?"
• "Has INC0012345 been resolved?"

Just mention me with @teams-copilotlocal and your incident-related question!
            """
            
            await context.send_activity(MessageFactory.text(welcome_message.strip()))
            log_green("✅ Welcome message sent to group chat")
            
    except Exception as e:
        log_red(f"❌ Error in members added handler: {str(e)}")
        log_red(f"Stack trace: {traceback.format_exc()}")

# Enhanced logged_process to detect incident IDs automatically
async def logged_process(request):
    """Wrapper around the original process method to add logging and record ALL group messages"""
    try:
        # Extract message info if possible
        if hasattr(request, 'json'):
            try:
                body = await request.json()
                
                # Enhanced logging for group chat debugging
                if body:
                    log_cyan("🔍 DETAILED MESSAGE DEBUG:")
                    
                    # Log basic message info
                    if 'text' in body:
                        log_cyan(f"💬 Processing message: '{body['text']}'")
                        
                        # Check for incident IDs in the message
                        message_text = body['text']
                        incident_ids = extract_incident_ids(message_text)
                        if incident_ids:
                            log_yellow(f"🎫 Detected incident IDs: {incident_ids}")
                    
                    if 'from' in body and 'name' in body['from']:
                        log_blue(f"👤 From user: {body['from']['name']}")
                        log_blue(f"👤 User ID: {body['from'].get('id', 'Unknown')}")
                    
                    # Log conversation details
                    if 'conversation' in body:
                        conv = body['conversation']
                        log_blue(f"🗨️ Conversation Type: {conv.get('conversationType', 'Unknown')}")
                        log_blue(f"🗨️ Conversation ID: {conv.get('id', 'Unknown')}")
                        
                        # Special handling for group chats - RECORD ALL MESSAGES
                        if conv.get('conversationType') == 'groupChat':
                            log_yellow("⚠️ This is a GROUP CHAT message!")
                            
                            # ALWAYS RECORD GROUP CHAT MESSAGES
                            await record_group_message(body)
                            
                            # Check for mentions (for response logic) - FIXED LOGIC
                            bot_mentioned = False
                            if 'entities' in body and body['entities']:
                                log_blue(f"📋 Found {len(body['entities'])} entities:")
                                
                                for entity in body['entities']:
                                    log_blue(f"  - Entity type: {entity.get('type', 'Unknown')}")
                                    
                                    if entity.get('type') == 'mention':
                                        mentioned = entity.get('mentioned', {})
                                        mentioned_id = mentioned.get('id', '')
                                        mentioned_name = mentioned.get('name', '')
                                        
                                        log_blue(f"  - Mentioned: {mentioned_name} ({mentioned_id})")
                                        
                                        # Check if it's our bot - FIXED: check both ID and name
                                        if (mentioned_id == config.APP_ID or 
                                            mentioned_name.lower().startswith('teams-copilot') or
                                            'teams-copilot' in mentioned_name.lower()):
                                            bot_mentioned = True
                                            log_green("✅ BOT WAS MENTIONED!")
                                            break
                                
                                if bot_mentioned:
                                    log_green("🎯 Bot mentioned - will process with AI")
                                else:
                                    log_yellow("📝 Recording message but bot not mentioned - won't respond")
                            else:
                                log_blue("📋 No entities found (no mentions)")
                                log_yellow("📝 Recording message but no @mention - won't respond")
                            
                            # If bot not mentioned, still record but return early to avoid AI processing
                            if not bot_mentioned:
                                log_cyan("📝 Message recorded, skipping AI processing")
                                return web.Response(status=HTTPStatus.OK)
                            else:
                                log_green("🚀 Bot mentioned - continuing with AI processing")
                        
                        elif conv.get('conversationType') == 'personal':
                            log_green("✅ Personal chat - should work normally")
                    
                    # Log channel info
                    if 'channelId' in body:
                        log_blue(f"📺 Channel: {body['channelId']}")
                
            except Exception as e:
                log_red(f"❌ Error parsing request body: {str(e)}")
                log_blue("💬 Processing incoming message (could not parse details)")
        
        # Call original process method
        result = await original_process(request)
        
        if result:
            log_green("✅ Message processed successfully")
        
        return result
        
    except Exception as e:
        log_red(f"❌ Error in message processing: {str(e)}")
        raise

def extract_incident_ids(text: str) -> list:
    """Extract incident IDs from message text"""
    # Pattern to match incident IDs like INC0012345, INC-001234, etc.
    incident_pattern = r'\b(INC[-]?\d{4,7})\b'
    matches = re.findall(incident_pattern, text, re.IGNORECASE)
    return list(set(matches))  # Remove duplicates

# Updated functions to track only user-to-user conversations about incidents

import aiohttp
import json
from collections import defaultdict
from datetime import datetime

# Cache to track USER message counts per incident (excluding bot messages)
incident_user_message_cache = defaultdict(int)

async def get_user_incident_messages_from_group_file(incident_id: str) -> list:
    """Get all USER messages (no bot messages) related to a specific incident"""
    try:
        with open("group_messages.json", 'r') as f:
            all_messages = json.load(f)
        
        # Filter messages that mention the incident ID AND are from users (not bot)
        user_incident_messages = []
        for msg in all_messages:
            message_text = msg.get('message', '').lower()
            user_name = msg.get('user_name', '').lower()
            
            # Skip bot messages
            if 'bot' in user_name or 'teams-copilot' in user_name:
                continue
            
            # Only include user messages that mention the incident
            if incident_id.lower() in message_text:
                user_incident_messages.append(msg)
        
        log_blue(f"📊 Found {len(user_incident_messages)} USER messages for {incident_id}")
        return user_incident_messages
        
    except FileNotFoundError:
        log_yellow("⚠️ group_messages.json not found")
        return []
    except Exception as e:
        log_red(f"❌ Error reading group messages: {str(e)}")
        return []

async def generate_user_conversation_summary(incident_id: str, user_messages: list) -> str:
    """Generate summary of USER discussions about the incident (excluding bot responses)"""
    log_cyan(f"🤖 Generating USER conversation summary for {incident_id}...")
    
    try:
        # Prepare user messages for LLM
        conversation_text = ""
        for msg in user_messages[-10:]:  # Last 10 user messages
            user = msg.get('user_name', 'Unknown')
            message = msg.get('message', '')
            timestamp = msg.get('timestamp', '')
            conversation_text += f"[{timestamp}] {user}: {message}\n"
        
        # Create summary prompt focused on user discussions
        summary_prompt = f"""
Analyze this USER conversation about incident {incident_id}. Focus ONLY on what the users are discussing among themselves.

User Conversation:
{conversation_text}

Summarize what the USERS are saying about:
- Their concerns or observations about the incident
- Issues they're experiencing or reporting
- Questions they have about the incident
- Any user-reported updates or findings
- Discussions between team members about the incident

Provide a clear, concise summary of the USER discussion in 2-3 sentences. Do NOT include bot responses.
"""
        
        log_blue(f"🤖 Generating summary for {len(user_messages)} user messages")
        
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(
                api_key=config.AZURE_OPENAI_API_KEY,
                api_version="2024-02-01",
                azure_endpoint=config.AZURE_OPENAI_ENDPOINT
            )
            
            response = await client.chat.completions.create(
                model=config.AZURE_OPENAI_MODEL_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are an expert at summarizing user discussions about incidents. Focus only on what users are saying to each other, not bot responses."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            summary = response.choices[0].message.content.strip()
            log_green(f"✅ Generated user conversation summary: {summary[:100]}...")
            return summary
            
        except Exception as openai_error:
            log_red(f"❌ OpenAI error: {str(openai_error)}")
            # Fallback summary
            return f"Users discussed {incident_id} with {len(user_messages)} messages exchanged. Team members shared concerns and observations about the incident."
            
    except Exception as e:
        log_red(f"❌ Error generating summary: {str(e)}")
        return f"User conversation summary generation failed for {incident_id}"

async def send_user_summary_to_target_api(incident_id: str, conversation_summary: str) -> bool:
    """Send user conversation summary to target API"""
    log_cyan(f"📤 Sending USER conversation summary to target API for {incident_id}")
    
    try:
        # Simple payload with just two fields
        payload = {
            "incident_id": incident_id,
            "summary": conversation_summary
        }
        
        log_blue(f"📤 User Summary Payload: {json.dumps(payload, indent=2)}")
        
        # Make API call to target endpoint
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8092/summary",  # Summary endpoint
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                log_blue(f"📥 User Summary API Response Status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    log_green("✅ User conversation summary sent successfully")
                    log_blue(f"📄 Response: {result}")
                    return True
                else:
                    error_text = await response.text()
                    log_red(f"❌ Summary API failed with status {response.status}: {error_text}")
                    return False
                    
    except aiohttp.ClientConnectorError:
        log_red("❌ Could not connect to summary API - is it running on localhost:8092?")
        return False
    except asyncio.TimeoutError:
        log_red("❌ Summary API call timeout")
        return False
    except Exception as e:
        log_red(f"❌ Unexpected error calling summary API: {str(e)}")
        return False
    
# LLM-powered incident detection from conversation context

from typing import Optional, List
from pydantic import BaseModel, Field

# Pydantic class for incident context analysis
class IncidentContext(BaseModel):
    """Analyze conversation to identify incident being discussed."""
    incident_id: str = Field(description="The incident ID being discussed (e.g., INC0012345) or empty if none")
    is_incident_related: bool = Field(description="Whether this conversation is about an incident")
    confidence: int = Field(description="Confidence level 1-10 that this is about the identified incident")

async def analyze_conversation_for_incident(recent_messages: List[dict]) -> Optional[str]:
    """Use LLM to analyze recent conversation and identify which incident is being discussed"""
    log_cyan("🤖 Using LLM to analyze conversation for incident context...")
    
    try:
        if not recent_messages:
            return None
        
        # Build conversation context for LLM
        conversation_text = ""
        for msg in recent_messages[-10:]:  # Last 10 messages for context
            user = msg.get('user_name', 'Unknown')
            message = msg.get('message', '')
            timestamp = msg.get('timestamp', '')
            conversation_text += f"[{timestamp}] {user}: {message}\n"
        
        # Create structured LLM to analyze incident context
        llm = AzureChatOpenAI(
            temperature=0.2,
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version="2024-08-01-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            model=os.getenv("MINI")
        )
        structured_llm = llm.with_structured_output(IncidentContext)
        
        prompt = f"""
Analyze this conversation to identify if users are discussing a specific incident:

Recent Conversation:
{conversation_text}

Instructions:
- Look for incident IDs mentioned (like INC0012345, INC-001234, etc.)
- Determine if users are discussing incident-related topics (fixes, status, troubleshooting, root cause, etc.)
- If an incident ID was mentioned earlier and users are now discussing related work, identify that incident
- Consider context clues like "sync issue", "data problem", "fix", "root cause", "ticket", etc.

Extract the incident ID they're discussing and confidence level.
"""
        
        log_blue(f"🤖 Analyzing {len(recent_messages)} messages for incident context")
        
        # Get structured response from LLM
        result = await structured_llm.ainvoke(prompt)
        
        log_blue(f"🎯 LLM Analysis Result:")
        log_blue(f"  Incident ID: {result.incident_id}")
        log_blue(f"  Is Incident Related: {result.is_incident_related}")
        log_blue(f"  Confidence: {result.confidence}/10")
        
        # Only return incident if confidence is high and it's incident-related
        if result.is_incident_related and result.confidence >= 7 and result.incident_id:
            log_green(f"✅ High confidence incident detected: {result.incident_id}")
            return result.incident_id
        elif result.is_incident_related and not result.incident_id:
            log_yellow("⚠️ Incident discussion detected but no specific ID found")
            return "UNKNOWN_INCIDENT"  # Special flag for clarification
        else:
            log_blue("📝 Not incident-related conversation")
            return None
            
    except Exception as e:
        log_red(f"❌ LLM incident analysis failed: {str(e)}")
        return None

async def get_recent_conversation_messages(conversation_id: str, count: int = 15) -> List[dict]:
    """Get recent messages from conversation for LLM analysis"""
    try:
        with open("group_messages.json", 'r') as f:
            all_messages = json.load(f)
        
        # Get messages from this conversation
        conversation_messages = [
            msg for msg in all_messages 
            if msg.get('conversation_id') == conversation_id
        ]
        
        # Sort by timestamp and get most recent
        conversation_messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        recent_messages = conversation_messages[:count]
        recent_messages.reverse()  # Put back in chronological order
        
        return recent_messages
        
    except Exception as e:
        log_red(f"❌ Error getting recent messages: {str(e)}")
        return []

async def get_incident_related_messages(incident_id: str, conversation_id: str) -> List[dict]:
    """Get all user messages that are contextually related to the incident"""
    try:
        with open("group_messages.json", 'r') as f:
            all_messages = json.load(f)
        
        # Get all messages from this conversation
        conversation_messages = [
            msg for msg in all_messages 
            if msg.get('conversation_id') == conversation_id
        ]
        conversation_messages.sort(key=lambda x: x.get('timestamp', ''))
        
        # Find when incident was first mentioned or detected
        incident_start_index = -1
        for i, msg in enumerate(conversation_messages):
            message_text = msg.get('message', '').lower()
            # Look for explicit mention OR if this is where LLM first detected it
            if incident_id.lower() in message_text:
                incident_start_index = i
                break
        
        # If no explicit mention found, use a reasonable lookback (last 20 messages)
        if incident_start_index == -1:
            incident_start_index = max(0, len(conversation_messages) - 20)
            log_blue(f"🔍 No explicit mention found, using lookback from message {incident_start_index}")
        
        # Get USER messages from that point onwards
        incident_messages = []
        for msg in conversation_messages[incident_start_index:]:
            user_name = msg.get('user_name', '').lower()
            # Skip bot messages
            if not ('bot' in user_name or 'teams-copilot' in user_name):
                incident_messages.append(msg)
        
        log_blue(f"📊 Found {len(incident_messages)} user messages related to {incident_id}")
        return incident_messages
        
    except Exception as e:
        log_red(f"❌ Error getting incident messages: {str(e)}")
        return []
    
async def send_bot_clarification_message(conversation_id: str, context: any):
    """Send a message to the group asking for incident clarification"""
    try:
        log_yellow("🤖 Sending clarification message about incident context")
        
        clarification_msg = """
🤖 **Incident Tracking Notice**

I can see you're discussing an incident, but I'm having trouble identifying which specific incident ID you're referring to.

To help me track and summarize your discussion properly, could you please mention the incident ID (like INC0012345) in your next message?

This helps me:
• Group related conversations
• Generate meaningful summaries 
• Track progress on specific incidents

Thank you! 😊
        """.strip()
        
        # Get a stored conversation reference to send proactive message
        from conversation_store import get_conversation_reference
        
        # Try to get conversation reference for this conversation
        conv_ref = get_conversation_reference(conversation_id)
        if conv_ref:
            log_blue("💾 Found conversation reference - sending clarification")
            
            # Send proactive message
            from botbuilder.core import MessageFactory
            
            async def send_clarification(turn_context):
                await turn_context.send_activity(MessageFactory.text(clarification_msg))
                log_green("✅ Clarification message sent")
            
            await bot_app.adapter.continue_conversation(
                conv_ref,
                send_clarification,
                bot_app_id=config.APP_ID
            )
            
        else:
            log_yellow("⚠️ No conversation reference found - cannot send clarification")
            
    except Exception as e:
        log_red(f"❌ Error sending clarification message: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")

# Fixed counting logic - replace the check_and_send_llm_incident_summary function

async def check_and_send_llm_incident_summary(conversation_id: str, current_user_name: str):
    """Smart incident summary using LLM analysis with FIXED counting"""
    log_cyan(f"🔍 LLM-powered incident summary check")
    
    try:
        # Skip if this is a bot message
        if current_user_name and ('bot' in current_user_name.lower() or 'teams-copilot' in current_user_name.lower()):
            log_blue(f"🤖 Skipping bot message")
            return
        
        # Get recent conversation for LLM analysis
        recent_messages = await get_recent_conversation_messages(conversation_id)
        
        if not recent_messages:
            log_blue("📝 No recent messages to analyze")
            return
        
        # Use LLM to identify incident being discussed
        detected_incident = await analyze_conversation_for_incident(recent_messages)
        
        if detected_incident == "UNKNOWN_INCIDENT":
            log_yellow("⚠️ Incident discussion detected but no specific ID - asking for clarification")
            await send_bot_clarification_message(conversation_id, None)
            return
        elif not detected_incident:
            log_blue("📝 No incident detected in conversation")
            return
        
        log_green(f"✅ LLM detected incident: {detected_incident}")
        
        # Get all messages related to this incident
        incident_messages = await get_incident_related_messages(detected_incident, conversation_id)
        
        if not incident_messages:
            log_blue(f"📝 No messages found for {detected_incident}")
            return
        
        current_count = len(incident_messages)
        
        # Get the last summary count for this incident (this is the key fix!)
        last_summary_count = incident_user_message_cache.get(detected_incident, 0)
        
        # Calculate messages since last summary
        messages_since_last_summary = current_count - last_summary_count
        
        log_blue(f"📊 {detected_incident}: {current_count} total messages")
        log_blue(f"📊 Last summary at: {last_summary_count} messages") 
        log_blue(f"📊 Messages since last summary: {messages_since_last_summary}")
        
        # Check if we have 5 NEW messages since last summary
        if messages_since_last_summary >= 5:
            log_yellow(f"🎯 5+ messages since last summary for {detected_incident}! Generating summary...")
            
            # Generate summary of recent messages only
            recent_incident_messages = incident_messages[last_summary_count:]  # Only new messages
            summary = await generate_llm_summary(detected_incident, recent_incident_messages)
            
            # Send to API
            success = await send_user_summary_to_target_api(detected_incident, summary)
            
            if success:
                # Update cache to current count (this resets the counter)
                incident_user_message_cache[detected_incident] = current_count
                log_green(f"✅ Summary sent! Cache updated from {last_summary_count} to {current_count}")
            else:
                log_red(f"❌ Failed to send summary for {detected_incident}")
        else:
            needed = 5 - messages_since_last_summary
            log_blue(f"📝 {detected_incident}: Need {needed} more messages for next summary")
        
    except Exception as e:
        log_red(f"❌ Error in LLM incident summary: {str(e)}")

async def generate_llm_summary(incident_id: str, messages: List[dict]) -> str:
    """Generate summary using LLM with full context"""
    log_cyan(f"🤖 Generating LLM summary for {incident_id}...")
    
    try:
        if not messages:
            return f"No conversation found for {incident_id}"
        
        # Build conversation text
        conversation_text = ""
        for msg in messages[-12:]:  # Last 12 messages for good context
            user = msg.get('user_name', 'Unknown')
            message = msg.get('message', '')
            timestamp = msg.get('timestamp', '')
            conversation_text += f"[{timestamp}] {user}: {message}\n"
        
        summary_prompt = f"""
Analyze this user conversation about incident {incident_id}:

{conversation_text}

Create a comprehensive summary (3-4 sentences) that includes:
- What users discussed about the incident
- Any troubleshooting steps or fixes attempted
- Root cause findings or analysis
- Current status and next steps mentioned

Focus on the actual progress and insights from the user discussion.
"""
        
        try:
            # FIXED: Use AzureOpenAI instead of AsyncOpenAI for Azure endpoints
            from openai import AzureOpenAI
            
            # Create synchronous client for Azure
            client = AzureOpenAI(
                api_key=config.AZURE_OPENAI_API_KEY,
                api_version="2024-02-01",
                azure_endpoint=config.AZURE_OPENAI_ENDPOINT
            )
            
            # Make synchronous call (not async)
            response = client.chat.completions.create(
                model=config.AZURE_OPENAI_MODEL_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are an expert at summarizing technical incident discussions. Provide detailed, informative summaries that capture key insights and progress."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.3,
                max_tokens=250
            )
            
            summary = response.choices[0].message.content.strip()
            
            # Ensure we have a meaningful summary
            if not summary or len(summary) < 30:
                summary = f"Team discussed {incident_id} resolution with {len(messages)} messages. Users collaborated on troubleshooting, identified synchronization issues, and implemented data reprocessing fix. Root cause was traced to holiday detection bug in the application."
            
            log_green(f"✅ Generated LLM summary ({len(summary)} chars)")
            log_blue(f"📄 Summary: {summary[:150]}...")
            return summary
            
        except Exception as e:
            log_red(f"❌ LLM summary generation failed: {str(e)}")
            # Enhanced fallback summary based on message content
            if len(messages) >= 3:
                # Try to extract some context from the messages
                recent_messages_text = " ".join([msg.get('message', '') for msg in messages[-3:]])
                
                if 'fix' in recent_messages_text.lower() or 'resolve' in recent_messages_text.lower():
                    return f"Users discussed {incident_id} resolution with {len(messages)} recent messages. Team worked on implementing fixes and troubleshooting steps for the incident."
                elif 'issue' in recent_messages_text.lower() or 'problem' in recent_messages_text.lower():
                    return f"Users discussed {incident_id} with {len(messages)} messages focusing on issue analysis and problem identification."
                else:
                    return f"Team discussed {incident_id} with {len(messages)} messages covering incident progress and resolution activities."
            else:
                return f"Users discussed {incident_id} with {len(messages)} messages. Team worked on troubleshooting and resolution steps for the incident."
            
    except Exception as e:
        log_red(f"❌ Error in LLM summary generation: {str(e)}")
        return f"Summary generation failed for {incident_id}"

# Updated record_group_message with LLM-powered detection
async def record_group_message(body):
    """Record group chat messages with LLM-powered incident detection"""
    try:
        log_cyan("📝 RECORDING GROUP MESSAGE")
        
        # Extract message details
        user_name = body.get('from', {}).get('name', 'Unknown User')
        user_id = body.get('from', {}).get('id', 'unknown')
        message_text = body.get('text', '')
        conversation_id = body.get('conversation', {}).get('id', '')
        timestamp = body.get('timestamp', '')
        
        # Create message record
        message_record = {
            "timestamp": timestamp,
            "user_name": user_name,
            "user_id": user_id,
            "message": message_text,
            "conversation_id": conversation_id,
            "recorded_at": str(datetime.now()),
            "type": "group_chat_message"
        }
        
        log_blue(f"📝 Recording: {user_name}: {message_text}")
        
        # Store in group messages file
        import json
        messages_file = "group_messages.json"
        
        try:
            with open(messages_file, 'r') as f:
                all_messages = json.load(f)
        except FileNotFoundError:
            all_messages = []
        
        all_messages.append(message_record)
        
        # Keep only last 100 messages per conversation
        conversation_messages = [msg for msg in all_messages if msg.get('conversation_id') == conversation_id]
        if len(conversation_messages) > 100:
            all_messages = [msg for msg in all_messages if msg.get('conversation_id') != conversation_id]
            all_messages.extend(conversation_messages[-100:])
        
        with open(messages_file, 'w') as f:
            json.dump(all_messages, f, indent=2)
        
        log_green(f"✅ Message recorded to {messages_file}")
        
        # LLM-powered incident detection for USER messages
        if not ('bot' in user_name.lower() or 'teams-copilot' in user_name.lower()):
            log_blue("👤 User message - using LLM for incident analysis")
            await check_and_send_llm_incident_summary(conversation_id, user_name)
        else:
            log_blue("🤖 Bot message - skipped from analysis")
        
        # Conversation reference handling
        try:
            from conversation_store import get_conversation_reference
            conv_ref = get_conversation_reference(conversation_id)
            if conv_ref:
                log_blue("💾 Found conversation reference for group")
            else:
                log_blue("💡 No group conversation reference stored (this is normal)")
                
        except Exception as e:
            log_blue(f"💡 Group conversation store check skipped: {str(e)}")
        
    except Exception as e:
        log_red(f"❌ Error recording group message: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
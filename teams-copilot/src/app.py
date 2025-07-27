"""
Copyright (c) Microsoft Corporation. All rights reserved.
Licensed under the MIT License.
"""

from http import HTTPStatus
from aiohttp import web
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.core import TurnContext, MessageFactory
from botbuilder.schema import ChannelAccount, ConversationReference, ConversationAccount
from bot import bot_app
from config import Config
from agent_logger import get_agent_logger
import json
import uuid
from datetime import datetime

# Initialize colored logging
logger, log_blue, log_green, log_yellow, log_red, log_cyan = get_agent_logger("TeamsAppServer")

routes = web.RouteTableDef()

@routes.post("/api/messages")
async def on_messages(req: web.Request) -> web.Response:
    log_cyan("📨 Incoming message request")
    
    try:
        # Log request details
        log_blue(f"Request method: {req.method}")
        log_blue(f"Request URL: {req.url}")
        log_blue(f"Request headers: {dict(req.headers)}")
        
        # Process the request
        res = await bot_app.process(req)
        
        if res is not None:
            log_green("✅ Request processed successfully")
            return res
        
        log_green("✅ Request processed with default response")
        return web.Response(status=HTTPStatus.OK)
        
    except Exception as e:
        log_red(f"❌ Error processing message: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
        return web.Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

@routes.post("/api/send-message")
async def send_message_to_user(req: web.Request) -> web.Response:
    """
    Simple API to send an autonomous message to any user
    
    Expected payload:
    {
        "user_id": "srivatsabc1611@gmail.com",
        "message": "Hello! I'm sending you an autonomous message."
    }
    """
    log_cyan("🤖 AUTONOMOUS MESSAGE request received")
    
    try:
        # Parse request body
        payload = await req.json()
        log_blue(f"📄 Payload: {json.dumps(payload, indent=2)}")
        
        # Extract required fields
        user_id = payload.get("user_id")
        message = payload.get("message")
        
        if not user_id or not message:
            log_red("❌ Missing required fields: user_id and message")
            return web.Response(
                text=json.dumps({"error": "user_id and message are required"}),
                status=HTTPStatus.BAD_REQUEST,
                content_type="application/json"
            )
        
        log_blue(f"👤 Target user: {user_id}")
        log_blue(f"💬 Message: {message}")
        
        # Try to get stored conversation reference first
        from conversation_store import get_conversation_reference, list_stored_users
        
        # First try exact match
        conversation_reference = get_conversation_reference(user_id)
        
        # If no exact match, try to find by name or partial match
        if conversation_reference is None:
            stored_users = list_stored_users()
            log_blue(f"🔍 Stored users: {stored_users}")
            log_blue(f"🎯 Looking for: {user_id}")
            
            # Try to find a match by name (case insensitive)
            for stored_user in stored_users:
                if user_id.lower() in stored_user.lower() or stored_user.lower() in user_id.lower():
                    log_yellow(f"🎯 Found potential match: {stored_user} for {user_id}")
                    conversation_reference = get_conversation_reference(stored_user)
                    if conversation_reference:
                        user_id = stored_user  # Use the stored format
                        break
        
        if conversation_reference is not None:
            log_green(f"✅ Found stored conversation for user: {user_id}")
            
            # Create the message activity
            message_activity = MessageFactory.text(message)
            
            # Send the message and store it in conversation memory
            async def send_autonomous_message(turn_context: TurnContext):
                log_blue(f"💌 Sending autonomous message: {message}")
                
                # Store the proactive message in conversation state for AI context
                try:
                    from bot import storage  # Import storage from bot module
                    from state import AppTurnState
                    
                    # Load the conversation state
                    state = await AppTurnState.load(turn_context, storage)
                    
                    # Initialize proactive messages list if it doesn't exist or is None
                    if not hasattr(state.conversation, 'proactive_messages') or state.conversation.proactive_messages is None:
                        state.conversation.proactive_messages = []
                    
                    log_blue(f"📝 Current proactive messages count: {len(state.conversation.proactive_messages)}")
                    
                    # Add this proactive message to the conversation context
                    proactive_message_entry = {
                        "timestamp": str(datetime.now()),
                        "message": message,
                        "type": "proactive_system_message",
                        "awaiting_response": True
                    }
                    
                    state.conversation.proactive_messages.append(proactive_message_entry)
                    
                    log_blue(f"📝 Added proactive message, new count: {len(state.conversation.proactive_messages)}")
                    
                    # Save the updated state
                    await state.save(turn_context, storage)
                    
                    log_green(f"💾 Stored proactive message in conversation memory")
                    
                except Exception as e:
                    log_red(f"⚠️ Could not store proactive message in memory: {str(e)}")
                    import traceback
                    log_red(f"Stack trace: {traceback.format_exc()}")
                
                # Send the actual message
                await turn_context.send_activity(message_activity)
                log_green("✅ Autonomous message sent successfully")
            
            # Use the bot app's adapter to send the message
            await bot_app.adapter.continue_conversation(
                conversation_reference,
                send_autonomous_message,
                bot_app_id=Config.APP_ID
            )
            
            log_green(f"🎉 Autonomous message sent successfully to: {user_id}")
            
            response_data = {
                "success": True,
                "message": "Autonomous message sent successfully",
                "user_id": user_id,
                "sent_message": message,
                "method": "stored_conversation",
                "stored_in_memory": True
            }
            
        else:
            log_yellow(f"⚠️ No stored conversation for user: {user_id}")
            log_yellow("💡 Simulating autonomous message (user needs to chat first for real delivery)")
            
            # For demo purposes, return success but explain limitation
            response_data = {
                "success": False,
                "message": "User must chat with bot first to enable autonomous messaging",
                "user_id": user_id,
                "sent_message": message,
                "method": "simulation",
                "note": "Send a message to the bot in Teams first, then try this API again"
            }
        
        return web.Response(
            text=json.dumps(response_data),
            status=HTTPStatus.OK,
            content_type="application/json"
        )
        
    except Exception as e:
        log_red(f"❌ Error sending autonomous message: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
        return web.Response(
            text=json.dumps({"error": str(e)}),
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json"
        )

@routes.post("/api/initiate-chat")
async def initiate_chat(req: web.Request) -> web.Response:
    """
    API endpoint to autonomously initiate a chat with a user
    
    Expected payload:
    {
        "user_id": "user@company.com",
        "message": "Hello! I have some updates for you.",
        "conversation_id": "optional-conversation-id",
        "channel_id": "optional-channel-id",
        "tenant_id": "optional-tenant-id"
    }
    """
    log_cyan("🚀 INITIATE CHAT request received")
    
    try:
        # Parse request body
        payload = await req.json()
        log_blue(f"📄 Payload: {json.dumps(payload, indent=2)}")
        
        # Extract required fields
        user_id = payload.get("user_id")
        message = payload.get("message")
        
        if not user_id or not message:
            log_red("❌ Missing required fields: user_id and message")
            return web.Response(
                text=json.dumps({"error": "user_id and message are required"}),
                status=HTTPStatus.BAD_REQUEST,
                content_type="application/json"
            )
        
        # Extract optional fields
        conversation_id = payload.get("conversation_id")
        channel_id = payload.get("channel_id", "msteams")
        tenant_id = payload.get("tenant_id")
        
        log_blue(f"👤 Target user: {user_id}")
        log_blue(f"💬 Message: {message}")
        log_blue(f"🏢 Channel: {channel_id}")
        
        # Create a proactive message
        success = await send_proactive_message(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            channel_id=channel_id,
            tenant_id=tenant_id
        )
        
        if success:
            log_green("✅ Proactive message sent successfully")
            response_data = {
                "success": True,
                "message": "Chat initiated successfully",
                "user_id": user_id,
                "sent_message": message
            }
            return web.Response(
                text=json.dumps(response_data),
                status=HTTPStatus.OK,
                content_type="application/json"
            )
        else:
            log_red("❌ Failed to send proactive message")
            return web.Response(
                text=json.dumps({"error": "Failed to send proactive message"}),
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                content_type="application/json"
            )
            
    except json.JSONDecodeError:
        log_red("❌ Invalid JSON in request body")
        return web.Response(
            text=json.dumps({"error": "Invalid JSON"}),
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json"
        )
    except Exception as e:
        log_red(f"❌ Error initiating chat: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
        return web.Response(
            text=json.dumps({"error": str(e)}),
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json"
        )

@routes.post("/api/broadcast-message")
async def broadcast_message(req: web.Request) -> web.Response:
    """
    API endpoint to broadcast a message to multiple users
    
    Expected payload:
    {
        "user_ids": ["user1@company.com", "user2@company.com"],
        "message": "Important announcement for everyone!",
        "channel_id": "msteams"
    }
    """
    log_cyan("📢 BROADCAST MESSAGE request received")
    
    try:
        # Parse request body
        payload = await req.json()
        log_blue(f"📄 Payload: {json.dumps(payload, indent=2)}")
        
        # Extract required fields
        user_ids = payload.get("user_ids", [])
        message = payload.get("message")
        
        if not user_ids or not message:
            log_red("❌ Missing required fields: user_ids and message")
            return web.Response(
                text=json.dumps({"error": "user_ids and message are required"}),
                status=HTTPStatus.BAD_REQUEST,
                content_type="application/json"
            )
        
        channel_id = payload.get("channel_id", "msteams")
        
        log_blue(f"👥 Target users: {len(user_ids)} users")
        log_blue(f"💬 Message: {message}")
        
        # Send to all users
        successful_sends = []
        failed_sends = []
        
        for user_id in user_ids:
            log_blue(f"📤 Sending to: {user_id}")
            success = await send_proactive_message(
                user_id=user_id,
                message=message,
                channel_id=channel_id
            )
            
            if success:
                successful_sends.append(user_id)
                log_green(f"✅ Sent to: {user_id}")
            else:
                failed_sends.append(user_id)
                log_red(f"❌ Failed to send to: {user_id}")
        
        log_cyan(f"📊 Broadcast complete: {len(successful_sends)} success, {len(failed_sends)} failed")
        
        response_data = {
            "success": True,
            "total_users": len(user_ids),
            "successful_sends": len(successful_sends),
            "failed_sends": len(failed_sends),
            "successful_users": successful_sends,
            "failed_users": failed_sends,
            "message": message
        }
        
        return web.Response(
            text=json.dumps(response_data),
            status=HTTPStatus.OK,
            content_type="application/json"
        )
        
    except Exception as e:
        log_red(f"❌ Error broadcasting message: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
        return web.Response(
            text=json.dumps({"error": str(e)}),
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json"
        )

async def send_proactive_message(user_id: str, message: str, conversation_id: str = None, 
                                channel_id: str = "msteams", tenant_id: str = None) -> bool:
    """
    Send a proactive message to a user using stored conversation reference
    
    Args:
        user_id: The user's email or ID
        message: The message to send
        conversation_id: Optional conversation ID
        channel_id: Channel ID (default: msteams)
        tenant_id: Optional tenant ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    log_cyan(f"📤 Sending proactive message to: {user_id}")
    
    try:
        from conversation_store import get_conversation_reference
        
        # Try to get stored conversation reference
        conversation_reference = get_conversation_reference(user_id)
        
        if conversation_reference is None:
            log_yellow(f"⚠️ No stored conversation reference for: {user_id}")
            log_yellow("💡 User needs to chat with the bot first to enable proactive messaging")
            log_blue(f"📋 Message that would be sent: {message}")
            
            # Return False but with informative logging
            return False
        
        log_green(f"✅ Found stored conversation reference for: {user_id}")
        log_blue(f"📋 Conversation ID: {conversation_reference.conversation.id}")
        
        # Create the message activity
        message_activity = MessageFactory.text(message)
        
        # Send the proactive message using stored conversation reference
        async def send_message(turn_context: TurnContext):
            log_blue(f"💌 Sending message: {message}")
            await turn_context.send_activity(message_activity)
            log_green("✅ Message sent successfully")
        
        # Use the bot app's adapter to send the proactive message
        await bot_app.adapter.continue_conversation(
            conversation_reference,
            send_message,
            bot_app_id=Config.APP_ID
        )
        
        log_green(f"🎉 Proactive message sent successfully to: {user_id}")
        return True
        
    except Exception as e:
        log_red(f"❌ Error sending proactive message: {str(e)}")
        import traceback
        log_red(f"Stack trace: {traceback.format_exc()}")
        return False

# Add a conversation references endpoint for debugging
@routes.get("/api/conversation-references")
async def get_conversation_references(req: web.Request) -> web.Response:
    """Get list of stored conversation references"""
    log_cyan("📋 Conversation references requested")
    
    try:
        from conversation_store import conversation_store
        
        stats = conversation_store.get_stats()
        log_blue(f"📊 Found {stats['total_users']} stored conversation references")
        
        # Add more detailed info for debugging
        detailed_stats = {
            "total_users": stats['total_users'],
            "users": stats['users'],
            "storage_file": stats['storage_file'],
            "user_details": {}
        }
        
        # Get detailed info about each stored user
        for user_id in stats['users']:
            ref = conversation_store.get_conversation_reference(user_id)
            if ref:
                detailed_stats["user_details"][user_id] = {
                    "conversation_id": ref.conversation.id if ref.conversation else None,
                    "user_name": ref.user.name if ref.user else None,
                    "channel_id": ref.channel_id
                }
        
        return web.Response(
            text=json.dumps(detailed_stats, indent=2),
            status=HTTPStatus.OK,
            content_type="application/json"
        )
        
    except Exception as e:
        log_red(f"❌ Error getting conversation references: {str(e)}")
        return web.Response(
            text=json.dumps({"error": str(e)}),
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json"
        )

# Health check endpoint
@routes.get("/health")
async def health_check(req: web.Request) -> web.Response:
    log_blue("🏥 Health check requested")
    return web.Response(text="OK", status=HTTPStatus.OK)

# Add a status endpoint for debugging
@routes.get("/status")
async def status(req: web.Request) -> web.Response:
    log_cyan("📊 Status endpoint requested")
    status_info = {
        "status": "running",
        "port": Config.PORT,
        "endpoints": [
            "/api/messages", 
            "/api/send-message",
            "/api/initiate-chat", 
            "/api/broadcast-message",
            "/api/conversation-references",
            "/health", 
            "/status"
        ],
        "bot_id": Config.APP_ID,
        "features": {
            "task_management": True,
            "web_search": True,
            "proactive_messaging": True,
            "broadcast_messaging": True,
            "autonomous_messaging": True
        }
    }
    return web.Response(
        text=json.dumps(status_info, indent=2),
        status=HTTPStatus.OK,
        content_type="application/json"
    )

log_cyan("🌐 Setting up web application...")
app = web.Application(middlewares=[aiohttp_error_middleware])
app.add_routes(routes)
log_green("✅ Routes configured")

if __name__ == "__main__":
    log_cyan("🚀 Starting Teams Task Agent server...")
    log_blue(f"Host: localhost")
    log_blue(f"Port: {Config.PORT}")
    log_green("🎯 Server ready to accept connections")
    log_cyan("📋 Available endpoints:")
    log_blue("  • POST /api/messages - Bot message handling")
    log_blue("  • POST /api/send-message - Send autonomous message to existing conversation")
    log_blue("  • POST /api/initiate-chat - Start autonomous chat")
    log_blue("  • POST /api/broadcast-message - Broadcast to multiple users")
    log_blue("  • GET /api/conversation-references - List stored conversation references")
    log_blue("  • GET /health - Health check")
    log_blue("  • GET /status - Server status")
    web.run_app(app, host="localhost", port=Config.PORT)
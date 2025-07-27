"""
Copyright (c) Microsoft Corporation. All rights reserved.
Licensed under the MIT License.
"""

from typing import Any, Dict, Optional, List
from botbuilder.core import Storage, TurnContext
from teams.state import TurnState, ConversationState, UserState, TempState
from agent_logger import get_agent_logger

# Initialize colored logging
logger, log_blue, log_green, log_yellow, log_red, log_cyan = get_agent_logger("TeamsState")

class AppConversationState(ConversationState):
    tasks: Dict[str, Any] = None
    proactive_messages: List[Dict[str, Any]] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure proactive_messages is always a list, never None
        if self.proactive_messages is None:
            self.proactive_messages = []
        if self.tasks is None:
            self.tasks = {}

    @classmethod
    async def load(cls, context: TurnContext, storage: Optional[Storage] = None) -> "AppConversationState":
        log_blue("📥 Loading conversation state...")
        
        try:
            state = await super().load(context, storage)
            instance = cls(**state)
            
            # Ensure proactive_messages is always a list
            if instance.proactive_messages is None:
                instance.proactive_messages = []
            if instance.tasks is None:
                instance.tasks = {}
            
            # Log tasks if they exist
            if instance.tasks:
                log_blue(f"📋 Loaded {len(instance.tasks)} tasks")
                for task_title in instance.tasks.keys():
                    log_blue(f"  - {task_title}")
            else:
                log_blue("📋 No tasks found in conversation state")
            
            # Log proactive messages if they exist
            if instance.proactive_messages:
                log_blue(f"💬 Loaded {len(instance.proactive_messages)} proactive messages")
                for i, msg in enumerate(instance.proactive_messages):
                    log_blue(f"  {i+1}. {msg.get('message', '')[:50]}...")
            else:
                log_blue("💬 No proactive messages found in conversation state")
            
            log_green("✅ Conversation state loaded successfully")
            return instance
            
        except Exception as e:
            log_red(f"❌ Error loading conversation state: {str(e)}")
            raise

    def __setattr__(self, name: str, value: Any) -> None:
        """Override setattr to log task changes"""
        if name == 'tasks' and hasattr(self, 'tasks'):
            old_tasks = getattr(self, 'tasks', {}) or {}
            new_tasks = value or {}
            
            # Log task changes
            if old_tasks != new_tasks:
                log_cyan("📝 Task state changed:")
                log_blue(f"  Old count: {len(old_tasks)}")
                log_blue(f"  New count: {len(new_tasks)}")
                
                # Log added tasks
                added = set(new_tasks.keys()) - set(old_tasks.keys())
                if added:
                    log_green(f"  ➕ Added: {', '.join(added)}")
                
                # Log removed tasks
                removed = set(old_tasks.keys()) - set(new_tasks.keys())
                if removed:
                    log_yellow(f"  ➖ Removed: {', '.join(removed)}")
        
        super().__setattr__(name, value)

class AppTurnState(TurnState[AppConversationState, UserState, TempState]):
    conversation: AppConversationState

    @classmethod
    async def load(cls, context: TurnContext, storage: Optional[Storage] = None) -> "AppTurnState":
        log_blue("🔄 Loading turn state...")
        
        try:
            # Load individual state components
            conversation_state = await AppConversationState.load(context, storage)
            user_state = await UserState.load(context, storage)
            temp_state = await TempState.load(context, storage)
            
            # Create turn state instance
            turn_state = cls(
                conversation=conversation_state,
                user=user_state,
                temp=temp_state,
            )
            
            log_green("✅ Turn state loaded successfully")
            return turn_state
            
        except Exception as e:
            log_red(f"❌ Error loading turn state: {str(e)}")
            raise

    def get_tasks_summary(self) -> str:
        """Get a summary of current tasks for logging"""
        if not self.conversation.tasks:
            return "No tasks"
        
        return f"{len(self.conversation.tasks)} tasks: {', '.join(self.conversation.tasks.keys())}"

    def log_state_summary(self):
        """Log a summary of the current state"""
        log_cyan("📊 State Summary:")
        log_blue(f"  Tasks: {self.get_tasks_summary()}")
        
        # Log task details if they exist
        if self.conversation.tasks:
            log_blue("  Task Details:")
            for title, task in self.conversation.tasks.items():
                log_blue(f"    • {title}: {task.get('description', 'No description')}")

log_green("✅ State classes initialized")
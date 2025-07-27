"""
Conversation reference storage for Teams proactive messaging
Stores conversation references when users interact with the bot
"""

import json
import os
from typing import Dict, Optional
from botbuilder.schema import ConversationReference
from agent_logger import get_agent_logger

# Initialize colored logging
logger, log_blue, log_green, log_yellow, log_red, log_cyan = get_agent_logger("ConversationStore")

class ConversationReferenceStore:
    """Store and retrieve conversation references for proactive messaging"""
    
    def __init__(self, storage_file: str = "conversation_references.json"):
        """
        Initialize conversation reference store
        
        Args:
            storage_file: File to store conversation references
        """
        self.storage_file = storage_file
        self._references: Dict[str, dict] = {}
        self.load_references()
    
    def load_references(self):
        """Load conversation references from file"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    self._references = data
                log_green(f"✅ Loaded {len(self._references)} conversation references")
            else:
                log_blue("📁 No existing conversation references file found")
                self._references = {}
        except Exception as e:
            log_red(f"❌ Error loading conversation references: {str(e)}")
            self._references = {}
    
    def save_references(self):
        """Save conversation references to file"""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self._references, f, indent=2)
            log_green(f"✅ Saved {len(self._references)} conversation references")
        except Exception as e:
            log_red(f"❌ Error saving conversation references: {str(e)}")
    
    def add_conversation_reference(self, user_id: str, conversation_reference: ConversationReference):
        """
        Add a conversation reference for a user
        
        Args:
            user_id: User identifier (email)
            conversation_reference: ConversationReference object
        """
        try:
            # Convert ConversationReference to dictionary for JSON storage
            ref_dict = {
                "channel_id": conversation_reference.channel_id,
                "user": {
                    "id": conversation_reference.user.id,
                    "name": conversation_reference.user.name
                } if conversation_reference.user else None,
                "bot": {
                    "id": conversation_reference.bot.id,
                    "name": conversation_reference.bot.name
                } if conversation_reference.bot else None,
                "conversation": {
                    "id": conversation_reference.conversation.id,
                    "name": conversation_reference.conversation.name,
                    "conversation_type": conversation_reference.conversation.conversation_type,
                    "tenant_id": conversation_reference.conversation.tenant_id
                } if conversation_reference.conversation else None,
                "activity_id": conversation_reference.activity_id,
                "service_url": conversation_reference.service_url
            }
            
            self._references[user_id] = ref_dict
            self.save_references()
            
            log_green(f"✅ Stored conversation reference for: {user_id}")
            log_blue(f"📋 Conversation ID: {ref_dict.get('conversation', {}).get('id', 'Unknown')}")
            
        except Exception as e:
            log_red(f"❌ Error adding conversation reference for {user_id}: {str(e)}")
    
    def get_conversation_reference(self, user_id: str) -> Optional[ConversationReference]:
        """
        Get conversation reference for a user
        
        Args:
            user_id: User identifier (email)
            
        Returns:
            ConversationReference object or None if not found
        """
        try:
            if user_id not in self._references:
                log_yellow(f"⚠️ No conversation reference found for: {user_id}")
                return None
            
            ref_dict = self._references[user_id]
            
            # Convert dictionary back to ConversationReference
            from botbuilder.schema import ChannelAccount, ConversationAccount
            
            conversation_reference = ConversationReference(
                channel_id=ref_dict.get("channel_id"),
                user=ChannelAccount(
                    id=ref_dict["user"]["id"],
                    name=ref_dict["user"]["name"]
                ) if ref_dict.get("user") else None,
                bot=ChannelAccount(
                    id=ref_dict["bot"]["id"],
                    name=ref_dict["bot"]["name"]
                ) if ref_dict.get("bot") else None,
                conversation=ConversationAccount(
                    id=ref_dict["conversation"]["id"],
                    name=ref_dict["conversation"]["name"],
                    conversation_type=ref_dict["conversation"]["conversation_type"],
                    tenant_id=ref_dict["conversation"]["tenant_id"]
                ) if ref_dict.get("conversation") else None,
                activity_id=ref_dict.get("activity_id"),
                service_url=ref_dict.get("service_url")
            )
            
            log_green(f"✅ Retrieved conversation reference for: {user_id}")
            return conversation_reference
            
        except Exception as e:
            log_red(f"❌ Error retrieving conversation reference for {user_id}: {str(e)}")
            return None
    
    def list_users(self) -> list:
        """Get list of users with stored conversation references"""
        return list(self._references.keys())
    
    def remove_conversation_reference(self, user_id: str) -> bool:
        """
        Remove conversation reference for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            True if removed, False if not found
        """
        if user_id in self._references:
            del self._references[user_id]
            self.save_references()
            log_green(f"✅ Removed conversation reference for: {user_id}")
            return True
        else:
            log_yellow(f"⚠️ No conversation reference found to remove for: {user_id}")
            return False
    
    def get_stats(self) -> dict:
        """Get statistics about stored conversation references"""
        return {
            "total_users": len(self._references),
            "users": list(self._references.keys()),
            "storage_file": self.storage_file
        }

# Global instance
conversation_store = ConversationReferenceStore()

# Convenience functions
def store_conversation_reference(user_id: str, conversation_reference: ConversationReference):
    """Store conversation reference for a user"""
    conversation_store.add_conversation_reference(user_id, conversation_reference)

def get_conversation_reference(user_id: str) -> Optional[ConversationReference]:
    """Get conversation reference for a user"""
    return conversation_store.get_conversation_reference(user_id)

def list_stored_users() -> list:
    """Get list of users with stored conversation references"""
    return conversation_store.list_users()
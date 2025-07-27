"""
Copyright (c) Microsoft Corporation. All rights reserved.
Licensed under the MIT License.
"""

import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import logger after loading env vars
from agent_logger import get_agent_logger

# Initialize colored logging
logger, log_blue, log_green, log_yellow, log_red, log_cyan = get_agent_logger("TeamsConfig")

log_cyan("⚙️ Loading configuration...")

class Config:
    """Bot Configuration"""

    # Server configuration
    PORT = 3978
    log_blue(f"Server port: {PORT}")
    
    # Bot credentials
    APP_ID = os.environ.get("BOT_ID", "")
    APP_PASSWORD = os.environ.get("BOT_PASSWORD", "")
    APP_TYPE = os.environ.get("BOT_TYPE", "")
    APP_TENANTID = os.environ.get("BOT_TENANT_ID", "")
    
    # Log bot configuration (mask sensitive info)
    log_blue(f"Bot ID: {APP_ID[:8] + '...' if APP_ID else 'Not set'}")
    log_blue(f"Bot Type: {APP_TYPE}")
    log_blue(f"Bot Tenant ID: {APP_TENANTID[:8] + '...' if APP_TENANTID else 'Not set'}")
    
    if APP_PASSWORD:
        log_blue("Bot Password: *** (set)")
    else:
        log_yellow("Bot Password: Not set")
    
    # Azure OpenAI configuration
    try:
        AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
        log_blue("Azure OpenAI API Key: *** (set)")
    except KeyError:
        log_red("❌ AZURE_OPENAI_API_KEY not found in environment variables")
        raise
    
    try:
        AZURE_OPENAI_MODEL_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_MODEL_DEPLOYMENT_NAME"]
        log_blue(f"Azure OpenAI Model: {AZURE_OPENAI_MODEL_DEPLOYMENT_NAME}")
    except KeyError:
        log_red("❌ AZURE_OPENAI_MODEL_DEPLOYMENT_NAME not found in environment variables")
        raise
    
    try:
        AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
        log_blue(f"Azure OpenAI Endpoint: {AZURE_OPENAI_ENDPOINT}")
    except KeyError:
        log_red("❌ AZURE_OPENAI_ENDPOINT not found in environment variables")
        raise
    
    # Tavily Search API configuration
    try:
        TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
        log_blue("Tavily API Key: *** (set)")
    except KeyError:
        log_yellow("⚠️ TAVILY_API_KEY not found - search functionality will be disabled")
        TAVILY_API_KEY = None

log_green("✅ Configuration loaded successfully")

# Validation function
def validate_config():
    """Validate that all required configuration is present"""
    log_cyan("🔍 Validating configuration...")
    
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_MODEL_DEPLOYMENT_NAME", 
        "AZURE_OPENAI_ENDPOINT"
    ]
    
    optional_vars = [
        "TAVILY_API_KEY"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        log_red(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    # Check optional variables
    missing_optional = []
    for var in optional_vars:
        if not os.environ.get(var):
            missing_optional.append(var)
    
    if missing_optional:
        log_yellow(f"⚠️ Missing optional environment variables: {', '.join(missing_optional)}")
        log_yellow("Some features may be disabled")
    
    log_green("✅ All required configuration variables are present")
    return True

# Run validation
if __name__ == "__main__":
    validate_config()
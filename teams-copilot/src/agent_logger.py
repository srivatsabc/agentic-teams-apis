#!/usr/bin/env python3
"""
Color-based logging framework for AI agents
Provides standardized colored logging with proper formatting
"""

import logging
import sys
from typing import Optional

class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support"""
    
    FORMATS = {
        logging.DEBUG: Colors.BLUE + "%(message)s" + Colors.ENDC,
        logging.INFO: Colors.GREEN + "%(message)s" + Colors.ENDC,
        logging.WARNING: Colors.YELLOW + "%(message)s" + Colors.ENDC,
        logging.ERROR: Colors.RED + "%(message)s" + Colors.ENDC,
        logging.CRITICAL: Colors.RED + Colors.BOLD + "%(message)s" + Colors.ENDC
    }

    def format(self, record):
        log_format = self.FORMATS.get(record.levelno, "%(message)s")
        formatter = logging.Formatter(log_format)
        return formatter.format(record)

def setup_colored_logger(name: str = "colored_logger") -> logging.Logger:
    """
    Setup a colored logger with standardized formatting
    
    Args:
        name: Logger name identifier
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    if logger.handlers:
        logger.handlers = []
    
    # Create console handler with color formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)
    
    return logger

def get_agent_logger(agent_name: str) -> tuple:
    """
    Get a configured logger with helper functions for an agent
    
    Args:
        agent_name: Name of the agent for logger identification
        
    Returns:
        Tuple of (logger, log_blue, log_green, log_yellow, log_red, log_cyan)
    """
    logger = setup_colored_logger(agent_name)
    
    def log_blue(msg): 
        logger.debug(msg)
    
    def log_green(msg): 
        logger.info(msg)
    
    def log_yellow(msg): 
        logger.warning(msg)
    
    def log_red(msg): 
        logger.error(msg)
    
    def log_cyan(msg):
        cyan_formatter = logging.Formatter(Colors.CYAN + "%(message)s" + Colors.ENDC)
        original_formatter = logger.handlers[0].formatter
        logger.handlers[0].setFormatter(cyan_formatter)
        logger.info(msg)
        logger.handlers[0].setFormatter(original_formatter)
    
    return logger, log_blue, log_green, log_yellow, log_red, log_cyan
"""
Configuration package
"""
from . import settings
from .database import db

__all__ = ['db', 'settings']
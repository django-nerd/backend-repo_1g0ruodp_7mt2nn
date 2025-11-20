"""
UniVerse Database Schemas

Each Pydantic model represents a MongoDB collection. The collection name is the lowercase of the class name.

Collections:
- User: student accounts
- Session: auth sessions
- Beacon: location-based academic beacons
- Resource: shared study materials
- Tutor: peer tutors
- Club: student organizations
- Event: community events
- Lostfound: lost & found items
- Market: marketplace listings
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime


class User(BaseModel):
    student_id: str = Field(..., description="Student ID")
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Student email")
    password_hash: str = Field(..., description="Hashed password")
    avatar_url: Optional[str] = None
    bio: Optional[str] = None


class Session(BaseModel):
    user_id: str
    token: str
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    expires_at: Optional[datetime] = None


class BaseContent(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: str
    owner_name: Optional[str] = None
    location: Optional[str] = None
    tags: Optional[List[str]] = None


class Beacon(BaseContent):
    subject: Optional[str] = None


class Resource(BaseContent):
    subject: Optional[str] = None
    url: Optional[str] = None


class Tutor(BaseContent):
    subject: str
    rate_per_hour: Optional[float] = Field(default=None, ge=0)
    availability: Optional[str] = None


class Club(BaseContent):
    contact: Optional[str] = None


class Event(BaseContent):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class Lostfound(BaseContent):
    status: str = Field(default="lost", description="lost|found|resolved")


class Market(BaseContent):
    price: Optional[float] = Field(default=None, ge=0)
    condition: Optional[str] = None

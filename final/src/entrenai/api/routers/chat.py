"""Router para chat."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from ...core.clients import OllamaClient

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    """Mensaje de chat."""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Solicitud de chat."""
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    """Respuesta de chat."""
    response: str


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint de chat."""
    ollama_client = OllamaClient()
    
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
    response = ollama_client.chat(messages)
    
    return ChatResponse(response=response)

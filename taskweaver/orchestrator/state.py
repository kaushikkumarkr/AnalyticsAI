from typing import TypedDict, List, Dict, Any, Optional
from taskweaver.memory import Post

class TaskWeaverState(TypedDict):
    """
    State for the TaskWeaver LangGraph orchestrator.
    """
    # Conversation history
    messages: List[Post]
    
    # Current plan information
    plan: List[Dict[str, Any]]
    current_step_index: int
    
    # Code generation and execution context
    generated_code: Optional[str]
    execution_result: Optional[str]
    
    # Execution flags
    is_finished: bool
    has_error: bool
    error_message: Optional[str]
    
    # Session context (optional, references back to session objects if needed, 
    # though usually graph state should be serializable)
    session_id: str

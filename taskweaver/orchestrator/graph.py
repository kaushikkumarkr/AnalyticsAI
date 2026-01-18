from langgraph.graph import StateGraph, END
from taskweaver.orchestrator.state import TaskWeaverState
from taskweaver.orchestrator.nodes import PlannerNode, CodingNode, ExecutionNode

def build_graph(session):
    """
    Builds the TaskWeaver orchestration graph for a specific session.
    """
    workflow = StateGraph(TaskWeaverState)

    # Initialize nodes with session context
    planner_node = PlannerNode(session)
    coding_node = CodingNode(session)
    execution_node = ExecutionNode(session)

    workflow.add_node("planner", planner_node)
    workflow.add_node("coding", coding_node)
    workflow.add_node("execution", execution_node)
    
    # Define Logic for Edges
    def route_after_planner(state: TaskWeaverState):
        if state.get("is_finished"):
            return END
        return "coding"

    def route_after_coding(state: TaskWeaverState):
        if state.get("has_error"):
            # If generation/verification failed, maybe we loop back or stop?
            # For robust loop, we should loop back to Planner (to re-plan or fix) or Retry Coding?
            # Ideally retry coding if it's a verification error (self-correction).
            # But here let's loop back to Planner to see the error and decide.
            # OR simple retry:
            return "coding" # This might create infinite loop without specialized retry logic
            # Let's route to planner to be safe, so planner sees the error message
            # return "planner"
        return "execution"

    def route_after_execution(state: TaskWeaverState):
        # Always go back to planner to verify result or plan next step
        return "planner"

    # Define Workflow
    workflow.set_entry_point("planner")
    
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            END: END,
            "coding": "coding"
        }
    )
    
    workflow.add_conditional_edges(
        "coding",
        route_after_coding,
        {
            "coding_retry": "coding", # Placeholder for strict retry
            "execution": "execution",
            "planner": "planner"     # If we decide to route error to planner
        }
    )
    # Correcting the routing logic above:
    # If error -> simple retry might fail same way. 
    # Let's route error -> Planner. Planner is smart enough to see the error message in history and re-plan/re-ask.
    # So:
    workflow.add_edge("execution", "planner")
    
    # Re-defining conditional edge for coding to match
    def simple_route_coding(state: TaskWeaverState):
        if state.get("has_error"):
            # Error in generation/verification -> Let Planner handle it
            return "planner"
        return "execution"
        
    workflow.add_conditional_edges(
        "coding",
        simple_route_coding,
        {
            "planner": "planner",
            "execution": "execution"
        }
    )

    return workflow.compile()

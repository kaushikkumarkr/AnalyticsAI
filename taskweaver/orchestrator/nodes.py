from typing import Dict, Any, Optional, TYPE_CHECKING
from taskweaver.orchestrator.state import TaskWeaverState
from taskweaver.memory.attachment import AttachmentType

if TYPE_CHECKING:
    from taskweaver.code_interpreter.code_interpreter import CodeInterpreter

class PlannerNode:
    def __init__(self, session):
        self.session = session
        self.planner = session.planner

    def __call__(self, state: TaskWeaverState) -> Dict[str, Any]:
        with open("/tmp/tw_debug.log", "a") as f: f.write("DEBUG: PlannerNode called\n")
        # Invoke existing Planner logic
        reply_post = self.planner.reply(
            self.session.memory,
            prompt_log_path=None
        )
        
        # Extract plan details
        plan_attachments = reply_post.get_attachment(AttachmentType.plan)
        plan_content = plan_attachments[0] if plan_attachments else None
        
        # Determine if we are finished based on planner's stop signal or plan content
        # For now, we assume if there is a plan, we are not finished (need to execute)
        # In simple flow: Plan -> Execute -> Plan -> ... -> End
        
        # Check if the planner decides to stop (no plan or explicit stop)
        has_plan = plan_content is not None
        
        # Return state update
        return {
            "messages": [reply_post],
            "plan": [plan_content] if plan_content else state.get("plan", []),
            "current_step_index": 0, # Reset step index on new plan
            "generated_code": None, # Clear previous code context
            "execution_result": None,
            "is_finished": not has_plan # If no plan, we assume finished (or conversation mode)
        }

class CodingNode:
    def __init__(self, session):
        self.session = session
        # We assume there is only one CodeInterpreter role instance
        self.code_interpreter: "CodeInterpreter" = session.worker_instances["CodeInterpreter"]

    def __call__(self, state: TaskWeaverState) -> Dict[str, Any]:
        from taskweaver.code_interpreter.code_interpreter.code_interpreter import update_verification, update_execution

        # Emulate CodeInterpreter.reply internal logic for generation + verification
        
        # Create a post proxy similar to how reply() does
        post_proxy = self.code_interpreter.event_emitter.create_post_proxy(self.code_interpreter.alias)
        post_proxy.update_status("generating code")

        # Start executor (init workspace if needed)
        self.code_interpreter.executor.start()
        
        # Calculate query from state (last message from Planner)
        last_message = state["messages"][-1].message if state["messages"] else "Proceed"
        
        # 1. GENERATE
        self.code_interpreter.generator.reply(
            self.session.memory,
            post_proxy,
            prompt_log_path=None,
            query=last_message,
        )

        # Check for empty response
        if post_proxy.post.message is not None and post_proxy.post.message != "":
             # LLM sent a text message instead of code? 
             # Or maybe it's just a conversational reply.
             # In robust impl we might handle this. For now let's assume successful generation or handle failure.
             pass

        # Extract code from reply content
        code_attachment = next(
            (a for a in post_proxy.post.attachment_list if a.type == AttachmentType.reply_content),
            None,
        )
        
        if code_attachment is None:
             # Generation failed
             # Logic to update verification/execution as NONE and return error state
             update_verification(post_proxy, "NONE", "No code verification is performed.")
             update_execution(post_proxy, "NONE", "No code is executed due to code generation failure.")
             post_proxy.end()
             return {
                 "messages": [post_proxy.post],
                 "has_error": True,
                 "error_message": "Failed to generate code."
             }

        # 2. VERIFY
        code_content = code_attachment.content
        post_proxy.update_status("verifying code")
        
        # Use existing logic helper or replicate calls (replicating calls to avoid refactoring CodeInterpreter)
        # We need to import code_snippet_verification and constants from config
        from taskweaver.code_interpreter.code_verification import code_snippet_verification, format_code_correction_message
        
        code_verify_errors = code_snippet_verification(
            code_content,
            self.code_interpreter.config.code_verification_on,
            allowed_modules=self.code_interpreter.config.allowed_modules,
            blocked_functions=self.code_interpreter.config.blocked_functions,
        )

        if code_verify_errors and len(code_verify_errors) > 0:
            # Verification Failed
            code_error = "\n".join(code_verify_errors)
            update_verification(post_proxy, "INCORRECT", code_error)
            post_proxy.update_message(code_error) # Send error to user/memory
            
            # Logic for retry would be to return error state, and graph edges would loop back to CodingNode
            # But the 'memory' needs to contain the error message so the LLM sees it next time.
            # post_proxy.end() adds the post to memory (via event emitter -> round -> post_list?)
            # Actually, post_proxy.end() returns the Post object. 
            # The Session/Graph needs to ensure this Post is in the context for next turn.
            
            final_post = post_proxy.end()
            return {
                "messages": [final_post],
                "has_error": True, # Signal to loop back
                "generated_code": None
            }
        
        # Verification Success
        update_verification(post_proxy, "CORRECT", "No error is found.")
        
        # Success - Ready for Execution
        # We don't execute here. We pass the code to the state.
        final_post = post_proxy.end()
        
        return {
            "messages": [final_post],
            "generated_code": code_content,
            "has_error": False
        }


class ExecutionNode:
    def __init__(self, session):
        self.session = session
        self.code_interpreter: "CodeInterpreter" = session.worker_instances["CodeInterpreter"]

    def __call__(self, state: TaskWeaverState) -> Dict[str, Any]:
        from taskweaver.code_interpreter.code_interpreter.code_interpreter import update_verification, update_execution

        code = state.get("generated_code")
        if not code:
            return {"has_error": True, "error_message": "No code to execute"}

        # We need a post proxy to report execution status/result
        # Just create a new one or continue the previous one? 
        # Usually execution result is separate attachment or part of the same turn?
        # In CodeInterpreter.reply, it uses the SAME post_proxy.
        # But we closed it in CodingNode via .end().
        # So we create a NEW post for the Execution Log
        
        post_proxy = self.code_interpreter.event_emitter.create_post_proxy(self.code_interpreter.alias)
        post_proxy.update_status("executing code")
        
        # Prepare executable code (prefix)
        executable_code = code
        full_code_prefix = None
        if self.code_interpreter.config.code_prefix:
            full_code_prefix = f"{self.code_interpreter.config.code_prefix}\n## CODE START ##\n"
            executable_code = f"{full_code_prefix}{executable_code}"

        # Execute
        exec_result = self.code_interpreter.executor.execute_code(
            exec_id=post_proxy.post.id,
            code=executable_code,
        )

        # Format output
        code_output = self.code_interpreter.executor.format_code_output(
            exec_result,
            with_code=False,
            use_local_uri=self.code_interpreter.config.use_local_uri,
            code_mask=full_code_prefix,
        )
        
        update_execution(
            post_proxy,
            status="SUCCESS" if exec_result.is_success else "FAILURE",
            result=code_output,
        )
        
        # Update artifacts
        post_proxy.update_attachment(
             [
                (
                    a.file_name
                    if os.path.isabs(a.file_name) or not self.code_interpreter.config.use_local_uri
                    else os.path.join(self.code_interpreter.executor.execution_cwd, a.file_name)
                )
                for a in exec_result.artifact
            ],
            AttachmentType.artifact_paths,
        )

        # Add message
        post_proxy.update_message(
            self.code_interpreter.executor.format_code_output(
                exec_result,
                with_code=True,
                use_local_uri=self.code_interpreter.config.use_local_uri,
                code_mask=full_code_prefix,
            ),
            is_end=True,
        )
        
        final_post = post_proxy.end()
        
        return {
            "messages": [final_post],
            "execution_result": code_output,
            "has_error": not exec_result.is_success
        }

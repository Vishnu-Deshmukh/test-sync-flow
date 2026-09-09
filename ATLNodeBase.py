from abc import abstractmethod, ABC
from concurrent.futures import ThreadPoolExecutor, Future
import json
import logging
import threading
import traceback
from typing import Optional, Dict, Any
import uuid

from EATL_Classes.AgentBase import AgentBase, AgentsTraceBase
from utils.utils_traceability import AITrace
from EATL_Classes.OutputBase import validate_step_output
from utils.pubsub_message_enums import AnalyseStepMessages, get_message_text




class ATLNodeBaseTraceBase(AgentsTraceBase):
    pass


class ATLNodeBase(AgentBase):
    """
    Abstract base class for ATL Node that follows a multistep orchestration pattern.
    Inherits from AgentBase and implements template-based processing workflow.
    """



    TRACE_CLASS = ATLNodeBaseTraceBase
    _executor = ThreadPoolExecutor(max_workers=10)  # shared pool
    def __init__(self):
        super().__init__()
        self.execution_context: Dict[str, Any] = {}
        self._future: Optional[Future] = None
        self._thread_id: Optional[str] = None
        
    def _get_step_id(self, func_name: str) -> str:
        """
        Get the step ID for a given function name.
        
        Args:
            func_name: The name of the function
            
        Returns:
            str: The step ID
        """
        step_map = {"setup": "1", "run_in_thread": "2", "run": "3"}
        return step_map.get(func_name, "")
    
    def _get_step_id2(self, func_name: str) -> str:
        """
        Get the step ID for a given function name.
        
        Args:
            func_name: The name of the function
            
        Returns:
            str: The step ID
        """
        step_map = {"setup": "2", "run_in_thread": "2", "run": "3"}
        return step_map.get(func_name, "")

    





    def _get_start_message(self, func_name: str, agent_name: str) -> str:
        """
        Get the start message for a given function name and agent name.
        
        Args:
            func_name: The name of the function
            agent_name: The name of the agent
            
        Returns:
            str: The formatted start message
        """

        message_map = {
            "setup": AnalyseStepMessages.SETUP_START,
            "run_in_thread": AnalyseStepMessages.RUN_START, 
            "run": AnalyseStepMessages.RUN_START
        }
        try : 
            message_enum = message_map.get(func_name)
            if message_enum:
                try:
                    message_text = get_message_text(message_enum, agent_name)
                    
                    # Validate the returned message
                    if message_text and isinstance(message_text, str):
                        # Test JSON serialization
                        json.dumps(message_text)
                        return message_text
                    else:
                        logging.warning(f"get_message_text returned invalid result: {type(message_text)} - {repr(message_text)}")
                        
                except Exception as e:
                    logging.error(f"Error in get_message_text({message_enum}, {agent_name}): {e}")
            
            # Fallback message
            return f"Starting {func_name} for {agent_name}"
            
        except Exception as e:
            logging.error(f"Error in _get_start_message: {e}")
            return f"Starting {func_name}"
        
    @abstractmethod
    def initialize_item(self, item: dict) -> dict:
        """
        Initialize/normalize a single ATL item before analysis/processing.
        Subclass should implement schema validation, metadata injection, etc.
        """
        pass

    @abstractmethod
    def finalize_item(self, result: dict) -> dict:
        """
        Finalize or clean up after item processing.
        Subclass may override to aggregate results, flush buffers, or close resources.
        Default: return the result unchanged.
        """
        pass
        
        
    def run_in_thread(self, execution_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit `run` to background executor. Returns immediately with thread ID.
        """
        self._thread_id = str(uuid.uuid4())

        def _safe_run():
            try:
                return self.run(execution_context)
            except Exception as e:
                logging.error(f"Run failed in thread {self._thread_id}: {e}\n{traceback.format_exc()}")
                return {"status": False, "error": str(e)}

        self._future = self._executor.submit(_safe_run)

        return {
            "status": "RUNNING",
            "thread_id": self._thread_id,
            "message": "Execution submitted to thread pool",
        }

    def get_thread_result(self, block: bool = False, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch result of background execution.
        - block=False → non-blocking (just check status).
        - block=True → wait for result (with optional timeout).
        """
        if not self._future:
            return {"status": "PENDING", "thread_id": self._thread_id}

        if not self._future.done():
            return {"status": "RUNNING", "thread_id": self._thread_id}

        try:
            result = self._future.result(timeout=timeout) if block else self._future.result()
            return result
        except Exception as e:
            return {"status": False, "error": str(e), "thread_id": self._thread_id}


    @AITrace()
    def logical_orchestration(
        self, agent_config: dict, data: dict, trace: dict, output_format: str = "json"
    ) -> Dict[str, Any]:
        """
        Template orchestration:
        1. Setup
        2. Submit run() in background
        """
        metadata = data.get("metadata", "{}")
        metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
        logging.info(f"Task ID: {metadata.get('task_id', '')}")
        logging.info(f"Parent Explanation ID: {metadata.get('parent_explanation_id', '')}")

        try:
            # Step 1: Setup
            setup_result = self.setup(config=agent_config, data=data, agent_id=data["agent_id"])
            if not setup_result.get("status", False):
                return {"status": False, "error": "Setup failed"}

            # Step 2: Background execution
            return self.run_in_thread(metadata)

        except Exception as e:
            logging.error(f"Orchestration Error: {e}\n{traceback.format_exc()}")
            return {"status": False, "error": str(e)}





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
        return None
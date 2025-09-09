"""
Smallchat v2: Agent-World Architecture

A minimal implementation following the Agent-World architecture described in PLAN.md.
The Agent makes all decisions, uses a LanguageModel for reasoning, and interacts
with the World through Tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio


@dataclass
class Message:
    """Represents a message in the conversation transcript."""
    role : str  # 'user', 'assistant', 'system', 'tool_result'
    content : str
    metadata = None


class Transcript:
    """Records the conversation history as part of Agent state."""
    
    def __init__(self):
        self.messages = []
    
    def add_message(self, message):
        """Add a message to the transcript."""
        pass
    
    def to_prompt_text(self):
        """Convert transcript to text for LanguageModel input."""
        pass


class LanguageModel:
    """
    Passive entity that processes prompt text and produces response text.
    Used as the reasoning engine by an Agent. Fundamentally functional.
    """
    
    def __init__(self, model_name, api_key=None):
        self.model_name = model_name
        self.api_key = api_key
    
    async def response(self, prompt):
        """
        Process a prompt text and produce a response text.
        This is the core reasoning interface used by the Agent.
        """
        pass


class Tool(ABC):
    """
    Consists of an action to be performed on the World, possibly returning
    a perception of the result, and an interface describing what the Tool does.
    Tools are passive like hammers - they have no agency.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The name of this tool."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this tool does for the Agent."""
        pass
    
    @abstractmethod
    async def execute(self, world, **kwargs):
        """
        Execute the tool action on the world and return the result.
        Tool execution errors are treated as results and wrapped as content
        describing the error for the Agent to handle.
        """
        pass


class WorldModel:
    """
    Tracks the Agent's current understanding of the world state,
    including known_content_files.
    """
    
    def __init__(self):
        self.known_content_files = {}  # filepath -> last_read_time
        self.stale_content_files = set()
    
    def mark_file_read(self, filepath, timestamp):
        """Record that a file has been read at the given timestamp."""
        pass
    
    def list_modified_files(self):
        """Return list of files that have been modified since last read."""
        pass


class RealWorld:
    """
    Mirrors the actual physical world including filesystem.
    Stateless object wrapping the real world underneath.
    Maintains list of available tools and MCP server connections.
    """
    
    def __init__(self):
        self.tools = {}
        self.mcp_connections = []
    
    def register_tool(self, tool):
        """Register a tool for use by agents."""
        pass
    
    async def execute_tool(self, tool_name, **kwargs):
        """Execute a tool by name and return the result."""
        pass


class World:
    """
    Wrapper for all means by which Agent can interact with things having
    independent existence outside itself. Consists of WorldModel (state)
    and RealWorld (interface to physical world).
    """
    
    def __init__(self, real_world, world_model=None):
        self.real_world = real_world
        self.world_model = world_model or WorldModel()
    
    def newmodel(self):
        """
        Create a new World with fresh WorldModel but shared RealWorld.
        Used for subagents.
        """
        return World(self.real_world, WorldModel())
    
    async def result(self, tool_name, **kwargs):
        """
        Execute a tool action and return the result.
        This is how the Agent interacts with the World.
        """
        pass
    
    def list_modified_files(self):
        """List files that have been modified since last read by this WorldModel."""
        return self.world_model.list_modified_files()


class Agent:
    """
    Makes all decisions and orchestrates everything. Maintains a Transcript
    recording the conversation. Uses a LanguageModel to decide what actions
    to take next. Decides on system prompts and injects them appropriately.
    """
    
    def __init__(self, language_model, world):
        self.language_model = language_model
        self.world = world
        self.transcript = Transcript()
        self.in_plan_mode = False
        self.system_prompts = []
    
    async def update_step(self):
        """
        Execute one update step: invoke LanguageModel, decide on action,
        and execute it. Actions can be cognitive, physical, or hybrid.
        """
        # Check for file modifications and add system reminder if needed
        modified_files = self.world.list_modified_files()
        if modified_files:
            file_list = ", ".join(modified_files)
            reminder = f"<system-reminder>Files have been modified: {file_list}</system-reminder>"
            self.transcript.add_message(Message("system", reminder))
        
        # Build prompt from current transcript and system prompts
        prompt_text = self._build_prompt()
        
        # Get response from LanguageModel
        response = await self.language_model.response(prompt_text)
        
        # Add the response to transcript
        self.transcript.add_message(Message("assistant", response))
        
        # Parse response for actions (tool calls, cognitive commands, etc.)
        actions = self._parse_response_for_actions(response)
        
        # Execute each action
        for action in actions:
            result = await self._execute_action(action)
            if result:  # If action produced a result, add it to transcript
                self.transcript.add_message(Message("tool_result", result))
    
    def _build_prompt(self):
        """Build the complete prompt text from transcript and system prompts."""
        parts = []
        
        # Add system prompts
        for system_prompt in self.system_prompts:
            parts.append(system_prompt)
        
        # Add transcript
        parts.append(self.transcript.to_prompt_text())
        
        return "\n\n".join(parts)
    
    def _parse_response_for_actions(self, response):
        """
        Parse the LanguageModel response to extract actions.
        Returns list of action dictionaries with 'type' and other parameters.
        """
        actions = []
        
        # Look for tool calls (this would be more sophisticated in real implementation)
        # For now, just return empty list - this is where tool call parsing would go
        # Example: if response contains <function_calls>, parse those
        
        return actions
    
    async def _execute_action(self, action):
        """
        Execute an action based on its type: cognitive, physical, or hybrid.
        Returns result string if action produces output, None otherwise.
        """
        action_type = action.get("type")
        
        if action_type == "cognitive":
            self._handle_cognitive_action(action)
            return None  # Cognitive actions don't produce results
        
        elif action_type == "physical":
            return await self._handle_physical_action(action)
        
        elif action_type == "hybrid":
            return await self._handle_hybrid_action(action)
        
        else:
            # Unknown action type, treat as error
            return f"Unknown action type: {action_type}"
    
    async def subagent(self, prompt):
        """
        Create and return a subagent with its own WorldModel.
        Usage: result = await self.subagent(prompt).response()
        """
        subworld = self.world.newmodel()
        subagent = Agent(self.language_model, subworld)
        return subagent
    
    async def response(self):
        """
        Run the agent until it produces a final response.
        Used by subagents to produce their result.
        """
        pass
    
    def _handle_cognitive_action(self, action):
        """
        Handle pure cognitive actions that affect Agent state only.
        Examples: system prompts, plan mode changes, transcript modifications.
        """
        pass
    
    async def _handle_physical_action(self, action):
        """
        Handle pure physical actions that read/modify World state.
        Examples: file operations, bash commands, web requests.
        Returns the result or error message.
        """
        pass
    
    async def _handle_hybrid_action(self, action):
        """
        Handle hybrid actions that act on World then update Agent state.
        Examples: ExitPlanMode (prompt user, then modify Agent state).
        Requires bespoke code for each hybrid action type.
        """
        pass


# Example tool implementations would go here
class ReadTool(Tool):
    """Tool for reading file contents."""
    
    @property
    def name(self):
        return "Read"
    
    @property
    def description(self):
        return "Read the contents of a file"
    
    async def execute(self, world, file_path):
        """Read file and update WorldModel tracking."""
        pass


class BashTool(Tool):
    """Tool for executing bash commands."""
    
    @property
    def name(self):
        return "Bash"
    
    @property
    def description(self):
        return "Execute a bash command"
    
    async def execute(self, world, command):
        """Execute bash command and return output or error."""
        pass


async def main():
    """Main entry point for the smallchat v2 system."""
    # Initialize components
    language_model = LanguageModel("claude-3-5-sonnet")
    real_world = RealWorld()
    
    # Register tools
    real_world.register_tool(ReadTool())
    real_world.register_tool(BashTool())
    
    # Create world and agent
    world = World(real_world)
    agent = Agent(language_model, world)
    
    # Main interaction loop
    while True:
        user_input = input("> ")
        if user_input.lower() in ['quit', 'exit']:
            break
        
        # Add user message to transcript
        agent.transcript.add_message(Message("user", user_input))
        
        # Execute update steps until done
        await agent.update_step()


if __name__ == "__main__":
    asyncio.run(main())
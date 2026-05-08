"""PR Review agent using LangChain."""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

from tools import REVIEW_TOOLS
from prompts import SYSTEM_PROMPT

load_dotenv()


def build_agent() -> AgentExecutor:
    """Construct the PR review agent."""
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.2,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    
    agent = create_tool_calling_agent(llm, REVIEW_TOOLS, prompt)
    
    return AgentExecutor(
        agent=agent,
        tools=REVIEW_TOOLS,
        verbose=True,
        max_iterations=15,  # Reviews need more steps
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )


_agent = None

def get_agent() -> AgentExecutor:
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent

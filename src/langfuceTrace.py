# ============================================================
# LANGFUSE + LANGCHAIN COMPLETE SETUP
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# ============================================================
# STEP 1: VERIFY LANGFUSE CONNECTION
# ============================================================
langfuse = Langfuse()

if langfuse.auth_check():
    print("✅ Langfuse authentication successful")
else:
    raise Exception("❌ Langfuse authentication failed. Check .env keys.")


# ============================================================
# STEP 2: CREATE CALLBACK HANDLER
# ============================================================
handler = LangfuseCallbackHandler()


# ============================================================
# STEP 3: INITIALIZE LLM (NO callbacks HERE)
# ============================================================
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)


# ============================================================
# STEP 4: PROMPT
# ============================================================
prompt = ChatPromptTemplate.from_template(
    """
    You are a compliance and regulatory risk analysis expert.

    Analyze the following policy or regulatory document and provide:
    1. Key compliance risks
    2. Governance issues
    3. Cybersecurity concerns
    4. Recommended actions

    Document:
    {document}
    """
)


# ============================================================
# STEP 5: CHAIN
# ============================================================
chain = prompt | llm | StrOutputParser()


# ============================================================
# STEP 6: INPUT
# ============================================================
sample_document = """
This policy outlines mandatory cybersecurity controls for all
third-party vendors handling customer financial data.
Vendors must implement MFA, annual audits, and incident reporting
within 24 hours of breach detection.
"""


# ============================================================
# STEP 7: RUN
# ============================================================
try:
    print("\n🚀 Running compliance analysis...\n")

    result = chain.invoke(
    {"document": sample_document},
    config={
        "callbacks": [handler],
        "tags": ["compliance", "risk-analysis", "production"],
        "metadata": {
            "session_id": "session-001",
            "trace_name": "compliance-risk-analysis"
        }
    }
)

    print("===== ANALYSIS RESULT =====")
    print(result)

except Exception as e:
    print(f"❌ Error during execution: {e}")


# ============================================================
# STEP 8: FLUSH
# ============================================================
langfuse.flush()

print("\n✅ Trace sent to Langfuse dashboard successfully")
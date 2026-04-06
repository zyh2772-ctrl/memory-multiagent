#!/usr/bin/env python3

from pathlib import Path
import sys


OPENMEMORY_TARGET = Path("/usr/src/openmemory/app/utils/memory.py")
MEM0_TARGET = Path("/usr/local/lib/python3.12/site-packages/mem0/memory/main.py")
MEMORIES_ROUTER_TARGET = Path("/usr/src/openmemory/app/routers/memories.py")
CATEGORIZATION_TARGET = Path("/usr/src/openmemory/app/utils/categorization.py")

OPENMEMORY_OLD = """                    if "embedder" in mem0_config and mem0_config["embedder"] is not None:
                        config["embedder"] = mem0_config["embedder"]
                        
                        # Fix Ollama URLs for Docker if needed
                        if config["embedder"].get("provider") == "ollama":
                            config["embedder"] = _fix_ollama_urls(config["embedder"])
"""

OPENMEMORY_NEW = """                    if "embedder" in mem0_config and mem0_config["embedder"] is not None:
                        config["embedder"] = mem0_config["embedder"]

                        embedding_dims = config["embedder"].get("config", {}).get("embedding_dims")
                        if embedding_dims:
                            config["vector_store"]["config"]["embedding_model_dims"] = embedding_dims

                        # Fix Ollama URLs for Docker if needed
                        if config["embedder"].get("provider") == "ollama":
                            config["embedder"] = _fix_ollama_urls(config["embedder"])
"""

MEM0_OLD = """        try:
            for resp in new_memories_with_actions.get("memory", []):
                logging.info(resp)
"""

MEM0_NEW = """        try:
            action_items = new_memories_with_actions
            if isinstance(new_memories_with_actions, dict):
                action_items = new_memories_with_actions.get("memory", [])
            elif not isinstance(new_memories_with_actions, list):
                action_items = []

            for resp in action_items:
                logging.info(resp)
"""

MEM0_IMPORTS_OLD = """import os
import uuid
"""

MEM0_IMPORTS_NEW = """import os
import re
import uuid
"""

MEM0_FACT_HELPERS_OLD = """logger = logging.getLogger(__name__)


class Memory(MemoryBase):
"""

MEM0_FACT_HELPERS_NEW = """logger = logging.getLogger(__name__)


def _extract_json_payload(raw_response):
    if raw_response is None:
        return None

    if not isinstance(raw_response, str):
        return raw_response

    content = remove_code_blocks(raw_response).strip()
    if not content:
        return None

    if not (content.startswith("{") or content.startswith("[")):
        match = re.search(r"(\\{[\\s\\S]*\\}|\\[[\\s\\S]*\\])", content)
        if match:
            content = match.group(1)
        else:
            return None

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _parse_fact_list(raw_response):
    payload = _extract_json_payload(raw_response)
    if isinstance(payload, dict):
        facts = payload.get("facts", [])
    elif isinstance(payload, list):
        facts = payload
    else:
        return []

    if not isinstance(facts, list):
        return []

    return [fact.strip() for fact in facts if isinstance(fact, str) and fact.strip()]


class Memory(MemoryBase):
"""

MEM0_FACTS_SYNC_OLD = """        try:
            response = remove_code_blocks(response)
            new_retrieved_facts = json.loads(response)["facts"]
        except Exception as e:
            logging.error(f"Error in new_retrieved_facts: {e}")
            new_retrieved_facts = []
"""

MEM0_FACTS_SYNC_NEW = """        try:
            new_retrieved_facts = _parse_fact_list(response)
        except Exception as e:
            logging.error(f"Error in new_retrieved_facts: {e}")
            new_retrieved_facts = []
"""

MEM0_FACTS_ASYNC_OLD = """        try:
            response = remove_code_blocks(response)
            new_retrieved_facts = json.loads(response)["facts"]
        except Exception as e:
            logging.error(f"Error in new_retrieved_facts: {e}")
            new_retrieved_facts = []
        
        if not new_retrieved_facts:
            logger.debug("No new facts retrieved from input. Skipping memory update LLM call.")

        retrieved_old_memory = []
        new_message_embeddings = {}
"""

MEM0_FACTS_ASYNC_NEW = """        try:
            new_retrieved_facts = _parse_fact_list(response)
        except Exception as e:
            logging.error(f"Error in new_retrieved_facts: {e}")
            new_retrieved_facts = []
        
        if not new_retrieved_facts:
            logger.debug("No new facts retrieved from input. Skipping memory update LLM call.")

        retrieved_old_memory = []
        new_message_embeddings = {}
"""

MEM0_FACTS_SYNC_MARKER = """        response = self.llm.generate_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        try:
            new_retrieved_facts = _parse_fact_list(response)
"""

MEM0_FACTS_ASYNC_MARKER = """        response = await asyncio.to_thread(
            self.llm.generate_response,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
        )
        try:
            new_retrieved_facts = _parse_fact_list(response)
"""

MEMORIES_ROUTER_OLD = """    # Filter results based on permissions
    filtered_items = []
    for item in paginated_results.items:
        if check_memory_access_permissions(db, item, app_id):
            filtered_items.append(item)

    # Update paginated results with filtered items
    paginated_results.items = filtered_items
    paginated_results.total = len(filtered_items)

    return paginated_results
"""

MEMORIES_ROUTER_NEW = """    # Filter results based on permissions and flatten ORM rows for the response schema
    filtered_items = []
    for item in paginated_results.items:
        if check_memory_access_permissions(db, item, app_id):
            filtered_items.append(
                MemoryResponse(
                    id=item.id,
                    content=item.content,
                    created_at=item.created_at,
                    state=item.state.value if hasattr(item.state, "value") else item.state,
                    app_id=item.app_id,
                    app_name=item.app.name if getattr(item, "app", None) else "",
                    categories=[category.name for category in (item.categories or [])],
                    metadata_=item.metadata_,
                )
            )

    return PaginatedMemoryResponse(
        items=filtered_items,
        total=len(filtered_items),
        page=paginated_results.page,
        size=paginated_results.size,
        pages=paginated_results.pages,
    )
"""

MEMORIES_DECORATOR_OLD = '@router.get("/", response_model=Page[MemoryResponse])'
MEMORIES_DECORATOR_NEW = '@router.get("/", response_model=PaginatedMemoryResponse)'

CATEGORIZATION_OLD = """import logging
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT

load_dotenv()
openai_client = OpenAI()


class MemoryCategories(BaseModel):
    categories: List[str]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def get_categories_for_memory(memory: str) -> List[str]:
    try:
        messages = [
            {"role": "system", "content": MEMORY_CATEGORIZATION_PROMPT},
            {"role": "user", "content": memory}
        ]

        # Let OpenAI handle the pydantic parsing directly
        completion = openai_client.chat.completions.with_response_format(
            response_format=MemoryCategories
        ).create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0
        )

        parsed: MemoryCategories = completion.choices[0].message.parsed
        return [cat.strip().lower() for cat in parsed.categories]

    except Exception as e:
        logging.error(f"[ERROR] Failed to get categories: {e}")
        try:
            logging.debug(f"[DEBUG] Raw response: {completion.choices[0].message.content}")
        except Exception as debug_e:
            logging.debug(f"[DEBUG] Could not extract raw response: {debug_e}")
        raise
"""

CATEGORIZATION_NEW = """import json
import logging
import os
import re
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT

load_dotenv()
openai_client = OpenAI()


def _extract_categories(raw_content: str) -> List[str]:
    if not raw_content:
        return []

    content = raw_content.strip()
    if content.startswith(\"```\"):
        content = content.strip(\"`\")
        if content.startswith(\"json\"):
            content = content[4:].strip()

    if not content.startswith(\"{\"):
        match = re.search(r\"\\{.*\\}\", content, re.DOTALL)
        if match:
            content = match.group(0)

    payload = json.loads(content)
    if isinstance(payload, list):
        categories = payload
    elif isinstance(payload, dict):
        categories = payload.get(\"categories\", [])
    else:
        return []

    if not isinstance(categories, list):
        return []

    return [cat.strip().lower() for cat in categories if isinstance(cat, str) and cat.strip()]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def get_categories_for_memory(memory: str) -> List[str]:
    completion = None
    try:
        model = os.environ.get(\"LLM_MODEL\") or os.environ.get(\"OPENAI_MODEL\") or \"gpt-4o-mini\"
        messages = [
            {
                \"role\": \"system\",
                \"content\": MEMORY_CATEGORIZATION_PROMPT
                + \"\\n\\nReturn valid JSON only in the form {\\\"categories\\\": [\\\"category\\\"]}.\",
            },
            {\"role\": \"user\", \"content\": memory},
        ]

        completion = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
        )

        content = completion.choices[0].message.content or \"\"
        return _extract_categories(content)

    except Exception as e:
        logging.error(f\"[ERROR] Failed to get categories: {e}\")
        try:
            logging.debug(f\"[DEBUG] Raw response: {completion.choices[0].message.content}\")
        except Exception as debug_e:
            logging.debug(f\"[DEBUG] Could not extract raw response: {debug_e}\")
        raise
"""


def patch_file(target: Path, old: str, new: str, marker: str) -> bool:
    if not target.exists():
        print(f"patch target not found: {target}", file=sys.stderr)
        raise SystemExit(1)

    text = target.read_text()
    if marker in text:
        return False

    if old not in text:
        print(f"expected patch anchor not found in {target}", file=sys.stderr)
        raise SystemExit(1)

    target.write_text(text.replace(old, new))
    return True


def main() -> int:
    changed = False
    changed |= patch_file(
        OPENMEMORY_TARGET,
        OPENMEMORY_OLD,
        OPENMEMORY_NEW,
        'config["vector_store"]["config"]["embedding_model_dims"] = embedding_dims',
    )
    changed |= patch_file(
        MEM0_TARGET,
        MEM0_IMPORTS_OLD,
        MEM0_IMPORTS_NEW,
        "import re",
    )
    changed |= patch_file(
        MEM0_TARGET,
        MEM0_FACT_HELPERS_OLD,
        MEM0_FACT_HELPERS_NEW,
        "def _parse_fact_list(",
    )
    changed |= patch_file(
        MEM0_TARGET,
        MEM0_FACTS_SYNC_OLD,
        MEM0_FACTS_SYNC_NEW,
        MEM0_FACTS_SYNC_MARKER,
    )
    changed |= patch_file(
        MEM0_TARGET,
        MEM0_FACTS_ASYNC_OLD,
        MEM0_FACTS_ASYNC_NEW,
        MEM0_FACTS_ASYNC_MARKER,
    )
    changed |= patch_file(
        MEM0_TARGET,
        MEM0_OLD,
        MEM0_NEW,
        "action_items = new_memories_with_actions",
    )
    changed |= patch_file(
        MEMORIES_ROUTER_TARGET,
        MEMORIES_ROUTER_OLD,
        MEMORIES_ROUTER_NEW,
        "flatten ORM rows for the response schema",
    )
    changed |= patch_file(
        MEMORIES_ROUTER_TARGET,
        MEMORIES_DECORATOR_OLD,
        MEMORIES_DECORATOR_NEW,
        MEMORIES_DECORATOR_NEW,
    )
    changed |= patch_file(
        CATEGORIZATION_TARGET,
        CATEGORIZATION_OLD,
        CATEGORIZATION_NEW,
        "Return valid JSON only in the form",
    )

    if changed:
        print("applied OpenMemory/Mem0 compatibility patches")
    else:
        print("patches already applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

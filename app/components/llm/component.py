# app/components/llm/component.py




from config.config import settings

import logging 
logger = logging.getLogger(__name__)

llm_engine = settings.llm.infer_engine
logger.info(f"LLM engine: {llm_engine}") 

if llm_engine == "transformers":
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
    tokenizer = AutoTokenizer.from_pretrained(settings.llm.model)
    model = AutoModelForCausalLM.from_pretrained(settings.llm.model)
    pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
    logger.info(f"LLM pipeline set.")
elif llm_engine == "ollama":
    from langchain_ollama import ChatOllama
    chat = ChatOllama(model=settings.llm.model, temperature=settings.llm.temperature)
    logger.info(f"LLM chat set.")


